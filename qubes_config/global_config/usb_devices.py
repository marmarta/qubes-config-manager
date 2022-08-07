# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
"""
USB Devices-related functionality.
"""
from functools import partial
from typing import List, Union, Optional, Dict

from qrexec.policy.parser import Allow

from ..widgets.qubes_widgets_library import WidgetWithButtons
from ..widgets.utils import get_feature, apply_feature_change_from_widget, \
    apply_feature_change
from .page_handler import PageHandler
from .policy_rules import RuleSimple
from .policy_manager import PolicyManager
from .rule_list_widgets import VMWidget, ActionWidget
from .vm_flowbox import VMFlowboxHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()


class USBVMHandler:
    """Handler for the usb vm selector."""

    FEATURE_NAME = 'config-usbvm-name'

    def __init__(self, qapp: qubesadmin.Qubes, gtk_builder: Gtk.Builder):
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.usb_qube_box: Gtk.Box = \
            gtk_builder.get_object('usb_select_usb_qube_box')

        self.select_widget = VMWidget(
            qapp=self.qapp, categories=None,
            initial_value=self._get_current_usbvm(),
            change_callback=self._emit_signal)
        self.widget_with_buttons = WidgetWithButtons(self.select_widget)
        self.usb_qube_box.pack_start(self.widget_with_buttons, False, False, 0)

    def _emit_signal(self, *_args):
        self.usb_qube_box.get_toplevel().emit('usbvm-changed', None)

    def _get_current_usbvm(self):
        usb_vm_name = get_feature(self.vm, self.FEATURE_NAME, 'sys-usb')
        return self.qapp.domains.get(usb_vm_name)

    def save(self):
        """Save user changes."""
        apply_feature_change_from_widget(self.select_widget,
                                         self.vm, self.FEATURE_NAME)
        self.widget_with_buttons.update_changed()
        # # TODO: do some sort of general close all edits?

    def get_selected_usbvm(self):
        """Get currently chosen usbvm."""
        # TODO: how this interacts with select in progress?????
        return self.select_widget.get_selected()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.widget_with_buttons.is_changed():
            return "USB qube"
        return ""

    def reset(self):
        """Reset all changes to their initial state."""
        self.widget_with_buttons.reset()


class InputDeviceHandler:
    """Handler for various qubes.Input policies."""
    ACTION_CHOICES = {
        "ask": "always ask",
        "allow": "enable",
        "deny": "disable"
    }
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager,
                 gtk_builder: Gtk.Builder,
                 sys_usb: qubesadmin.vm.QubesVM
                 ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_file_name = '50-config-input'
        self.sys_usb = sys_usb
        # generally do an update_usb thingy

        self.default_policy = f"""
qubes.InputMouse * {self.sys_usb} @adminvm deny
qubes.InputKeyboard * {self.sys_usb} @adminvm deny
qubes.InputTablet * {self.sys_usb} @adminvm deny
"""

        # this is unavoidable piece of ugliness to avoid unaligned columns
        self.policy_order = {'qubes.InputKeyboard': 0,
                             'qubes.InputMouse': 1,
                             'qubes.InputTablet': 2}
        self.action_widgets: Dict[str, WidgetWithButtons] = {}

        self.rules, self.current_token = \
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, self.default_policy)

        self.grid: Gtk.Grid = gtk_builder.get_object('usb_input_grid')

        if len(self.rules) != 3:
            self._warn()

        for rule in self.rules:
            if rule.service not in self.policy_order or \
                    rule.target != '@adminvm':
                self._warn()
            wrapped_rule = RuleSimple(rule)

            action_widget = ActionWidget(
                choices=self.ACTION_CHOICES,
                initial_value=type(rule.action).__name__.lower(),
                verb_description=None,
                rule=wrapped_rule)
            widget_with_buttons = WidgetWithButtons(action_widget)

            self.action_widgets[rule.service] = widget_with_buttons
            self.grid.attach(child=widget_with_buttons,
                             left=1, top=self.policy_order[rule.service],
                             width=1, height=1)

    def _warn(self):
        pass
        # TODO: fixme

    def save(self):
        """Save user changes"""
        rules = []
        for widget in self.action_widgets.values():
            widget.close_edit()
            widget.select_widget.rule.action = \
                widget.select_widget.get_selected()
            rules.append(widget.select_widget.rule.raw_rule)

        self.policy_manager.save_rules(self.policy_file_name, rules,
                                       self.current_token)
        _, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, self.default_policy)

        for widget in self.action_widgets.values():
            widget.update_changed()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = []
        for policy, widget in self.action_widgets.items():
            widget.close_edit()
            if widget.is_changed():
                name = policy[len('qubes.Input'):]
                unsaved.append(f'{name} input settings')
        return "\n".join(unsaved)

    def reset(self):
        """Reset changes to the initial state."""
        for widget in self.action_widgets.values():
            widget.reset()


class U2FPolicyHandler:
    """Handler for u2f policy and services."""
    SERVICE_FEATURE = 'service.qubes-u2f-proxy'
    SUPPORTED_SERVICE_FEATURE = 'supported-service.qubes-u2f-proxy'
    AUTH_POLICY = 'u2f.Authenticate'
    REGISTER_POLICY = 'u2f.Register'
    POLICY_REGISTER_POLICY = 'policy.RegisterArgument'

    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager,
                 gtk_builder: Gtk.Builder,
                 sys_usb: qubesadmin.vm.QubesVM
                 ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_filename = '50-config-u2f'
        self.sys_usb = sys_usb

        self.default_policy = f"u2f.Authenticate * @anyvm {sys_usb} deny"

        self.problem_no_vms_box: Gtk.Box = \
            gtk_builder.get_object('usb_u2f_no_qubes_problem')
        self.problem_no_usbvm_box: Gtk.Box = \
            gtk_builder.get_object('usb_u2f_no_usb_vm_problem')

        self.enable_check: Gtk.CheckButton = \
            gtk_builder.get_object('usb_u2f_enable_check') # general enable
        self.box: Gtk.Box = \
            gtk_builder.get_object('usb_u2f_enable_box')  # general box

        self.register_check: Gtk.CheckButton = \
            gtk_builder.get_object('usb_u2f_register_check')
        self.register_box: Gtk.Box = \
            gtk_builder.get_object('usb_u2f_register_box')
        self.register_all_radio: Gtk.RadioButton = \
            gtk_builder.get_object('usb_u2f_register_all_radio')
        self.register_some_radio: Gtk.RadioButton = \
            gtk_builder.get_object('usb_u2f_register_some_radio')

        self.blanket_check: Gtk.CheckButton = \
            gtk_builder.get_object('usb_u2f_blanket_check')

        # TODO: add default: not dom0 func

        self.initially_enabled_vms : List[qubesadmin.vm.QubesVM] = []
        self.available_vms: List[qubesadmin.vm.QubesVM] = []
        self.initial_register_vms: List[qubesadmin.vm.QubesVM] = []
        self.initial_blanket_vms: List[qubesadmin.vm.QubesVM] = []
        self.allow_all_register: bool = False
        self.current_token: Optional[str] = None

        self._initialize_data()

        self.enable_some_handler = VMFlowboxHandler(
            gtk_builder, self.qapp, "usb_u2f_enable_some",
            self.initially_enabled_vms, lambda vm: vm in self.available_vms)

        self.register_some_handler = VMFlowboxHandler(
            gtk_builder, self.qapp, "usb_u2f_register_some",
            self.initial_register_vms, lambda vm: vm in self.available_vms)

        self.blanket_handler = VMFlowboxHandler(
            gtk_builder, self.qapp, "usb_u2f_blanket",
            self.initial_blanket_vms, lambda vm: vm in self.available_vms)

        self.widget_to_box = {
            self.enable_check: self.box,
            self.register_check: self.register_box,
            self.blanket_check: self.blanket_handler,
            self.register_some_radio: self.register_some_handler}

        for widget, box in self.widget_to_box.items():
            widget.connect('toggled', partial(self._enable_clicked, box))
            self._enable_clicked(box, widget)

        self.initial_enable_state: bool = self.enable_check.get_active()
        self.initial_register_state: bool = self.register_check.get_active()
        self.initial_register_all_state: bool = \
            self.register_all_radio.get_active()
        self.initial_blanket_check_state: bool = self.blanket_check.get_active()


    @staticmethod
    def _enable_clicked(related_box: Union[Gtk.Box, VMFlowboxHandler],
                        widget: Gtk.CheckButton):
        related_box.set_visible(widget.get_active())

    def _warn(self):
        # warn about weird data?
        pass

    def _initialize_data(self):
        self.initially_enabled_vms.clear()
        self.available_vms.clear()
        self.initial_register_vms.clear()
        self.initial_blanket_vms.clear()

        for vm in self.qapp.domains:
            if vm.features.check_with_template(self.SUPPORTED_SERVICE_FEATURE):
                if vm == self.sys_usb:
                    continue
                self.available_vms.append(vm)
            if vm.features.get(self.SERVICE_FEATURE):
                self.initially_enabled_vms.append(vm)
        available_in_sys_usb = self.sys_usb.features.check_with_template(
                    self.SUPPORTED_SERVICE_FEATURE)
        if not self.available_vms or not available_in_sys_usb:
            self.problem_no_usbvm_box.show_all()
            self.problem_no_vms_box.show_all()
            self.problem_no_usbvm_box.set_visible(not available_in_sys_usb)
            self.problem_no_vms_box.set_visible(not bool(self.available_vms))
            self.enable_check.set_active(False)
            self.enable_check.set_sensitive(False)
            self.box.set_visible(False)
            return

        self.enable_check.set_active(bool(self.initially_enabled_vms))

        all_rules, self.current_token = \
            self.policy_manager.get_rules_from_filename(
                self.policy_filename, self.default_policy)

        for rule in all_rules:
            if rule.service == self.REGISTER_POLICY:
                if rule.source == '@anyvm' and isinstance(rule.action, Allow):
                    self.allow_all_register = True
                elif rule.source != '@anyvm' and isinstance(rule.action, Allow):
                    try:
                        vm = self.qapp.domains[rule.source]
                        self.initial_register_vms.append(vm)
                    except KeyError:
                        continue
            elif rule.service == self.AUTH_POLICY:
                if rule.source != '@anyvm' and isinstance(rule.action, Allow):
                    try:
                        vm = self.qapp.domains[rule.source]
                        self.initial_blanket_vms.append(vm)
                    except KeyError:
                        continue

        if self.allow_all_register:
            self.register_check.set_active(True)
            self.register_all_radio.set_active(True)
        else:
            if self.initial_register_vms:
                self.register_check.set_active(True)
                self.register_some_radio.set_active(True)

        self.blanket_check.set_active(bool(self.initial_blanket_vms))

    def save(self):
        """Save user changes in policy."""
        if not self.enable_check.get_sensitive():
            return

        if not self.enable_check.get_active():
            # disable all service:
            for vm in self.initially_enabled_vms:
                apply_feature_change(vm, self.SERVICE_FEATURE, None)

            self.policy_manager.save_rules(
                self.policy_filename,
                self.policy_manager.text_to_rules(self.default_policy),
                self.current_token)

            _, self.current_token = self.policy_manager.get_rules_from_filename(
                self.policy_filename, self.default_policy)

            self._initialize_data()
            return

        enabled_vms = self.enable_some_handler.selected_vms
        for vm in self.available_vms:
            value = None if vm not in enabled_vms else True
            apply_feature_change(vm, self.SERVICE_FEATURE, value)

        rules = []

        # register rules
        if not self.register_check.get_active():
            rules.extend(self.policy_manager.text_to_rules(
                f"{self.REGISTER_POLICY} * @anyvm @anyvm deny\n"
                f"{self.POLICY_REGISTER_POLICY} +"
                f"{self.REGISTER_POLICY} @anyvm @anyvm deny"))
        else:
            if self.register_all_radio.get_active():
                rules.extend(self.policy_manager.text_to_rules(
                    f"{self.POLICY_REGISTER_POLICY} +{self.REGISTER_POLICY} "
                    f"{self.sys_usb} @anyvm allow target=dom0"))
                rules.extend(self.policy_manager.text_to_rules(
                    f"{self.REGISTER_POLICY} * @anyvm {self.sys_usb} allow"))
            else:
                for vm in self.register_some_handler.selected_vms:
                    rules.extend(self.policy_manager.text_to_rules(
                        f"{self.REGISTER_POLICY} * {vm} {self.sys_usb} allow"))
                rules.extend(self.policy_manager.text_to_rules(
                    "policy.RegisterArgument +u2f.Authenticate "
                    "sys-usb @anyvm allow target=dom0"))

        if self.blanket_check.get_active():
            for vm in self.blanket_handler.selected_vms:
                rules.extend(self.policy_manager.text_to_rules(
                    f"{self.AUTH_POLICY} * {vm} {self.sys_usb} allow"))

        self.policy_manager.save_rules(self.policy_filename, rules,
                                       self.current_token)
        _, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_filename, self.default_policy)

        self._initialize_data()

    def reset(self):
        """Reset state to initial state."""
        self._initialize_data()
        self.enable_some_handler.reset()
        self.register_some_handler.reset()
        self.blanket_handler.reset()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.initial_enable_state != self.enable_check.get_active():
            if self.enable_check.get_active():
                return "U2F enabled"
            return "Uf2 disabled"
        if not self.enable_check.get_active():
            return ""

        unsaved = []

        if self.enable_some_handler.selected_vms != self.initially_enabled_vms:
            unsaved.append("List of qubes with U2F enabled changed")
        if self.initial_register_state != self.register_check.get_active() or \
            self.initial_register_all_state != \
                self.register_all_radio.get_active() or \
                self.register_some_handler.selected_vms != \
                self.initial_register_vms:
            unsaved.append("U2F key registration settings changed")
        if self.initial_blanket_check_state != \
                self.blanket_check.get_active() or \
                self.blanket_handler.selected_vms != self.initial_blanket_vms:
            unsaved.append("List of qubes with unrestricted U2F key "
                           "access changed")
        return "\n".join(unsaved)


class DevicesHandler(PageHandler):
    """Handler for all the disparate Updates functions."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager,
                 gtk_builder: Gtk.Builder
 ):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.main_window = gtk_builder.get_object('main_window')

        self.usbvm_handler = USBVMHandler(self.qapp, gtk_builder)

        usb_vm = self.usbvm_handler.get_selected_usbvm()

        self.input_handler = InputDeviceHandler(
            qapp, policy_manager, gtk_builder, usb_vm)

        self.u2f_handler = U2FPolicyHandler(self.qapp, self.policy_manager,
                                            gtk_builder, usb_vm)
        self.main_window.connect('usbvm-changed', self._usbvm_changed)

    def _usbvm_changed(self, *_args):
        sys_usb = self.usbvm_handler.get_selected_usbvm()
        self.input_handler.sys_usb = sys_usb
        self.u2f_handler.sys_usb = sys_usb

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = [self.usbvm_handler.get_unsaved(),
                   self.input_handler.get_unsaved(),
                   self.u2f_handler.get_unsaved()]
        return "\n".join([x for x in unsaved if x])

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        self.usbvm_handler.reset()
        self.input_handler.reset()
        self.u2f_handler.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default."""
        self.usbvm_handler.save()
        self.input_handler.save()
        self.u2f_handler.save()
