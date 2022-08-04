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
import os
import subprocess
from typing import Optional, List, Dict, Union

from qrexec.policy.parser import Rule

from ..widgets.qubes_widgets_library import VMListModeler, show_error, \
    ask_question, NONE_CATEGORY, QubeName, ImageTextButton
from ..widgets.utils import get_feature, apply_feature_change_from_widget
from .page_handler import PageHandler
from .policy_rules import RuleSimple, SimpleVerbDescription
from .policy_manager import PolicyManager
from .rule_list_widgets import NoActionListBoxRow, VMWidget, ActionWidget
from .conflict_handler import ConflictFileHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()


# TODO: make this asking somehow available in widget with buttons wrapper?
# response = ask_question(self.usb_qube_box.get_toplevel(),
#                         "Change USB qube",
#                         "Are you absolutely sure you want to change the USB qube? "
#                         "You will also need to <b>manually</b> change device"
#                         " assignment.")
# if response == Gtk.ResponseType.NO:
#     return

class WidgetWithButtons(Gtk.Box):
    """This is a simple wrapper for editable widgets
    with additional confirm/cancel/edit buttons"""
    def __init__(self, widget: Union[ActionWidget, VMWidget]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.select_widget = widget

        self.edit_button = ImageTextButton(icon_name='qubes-customize',
                                           label=None,
                                           click_function=self._edit_clicked,
                                           style_classes=["flat"])
        self.confirm_button = ImageTextButton(
            icon_name="qubes-ok", label="ACCEPT",
            click_function=self._confirm_clicked,
            style_classes=["button_save", "flat_button"])
        self.cancel_button = ImageTextButton(
            icon_name="qubes-delete", label="CANCEL",
            click_function=self._cancel_clicked,
            style_classes=["button_cancel", "flat_button"])

        self.pack_start(self.select_widget, False, False, 0)
        self.pack_start(self.edit_button, False, False, 0)
        self.pack_start(self.confirm_button, False, False, 10)
        self.pack_start(self.cancel_button, False, False, 10)

        self.show_all()
        self._set_editable(False)

    def _set_editable(self, state: bool):
        self.select_widget.set_editable(state)
        self.edit_button.set_visible(not state)
        self.cancel_button.set_visible(state)
        self.confirm_button.set_visible(state)

    def _edit_clicked(self, _widget):
        self._set_editable(True)

    def _cancel_clicked(self, _widget):
        self.select_widget.revert_changes()
        self._set_editable(False)

    def _confirm_clicked(self, _widget):
        self.select_widget.save_changes()
        self._set_editable(False)


class USBVMHandler:
    FEATURE_NAME = 'config-usbvm-name'
    def __init__(self, qapp: qubesadmin.Qubes, gtk_builder: Gtk.Builder):
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.usb_qube_box: Gtk.Box = \
            gtk_builder.get_object('usb_select_usb_qube_box')

        self.select_widget = VMWidget(
                qapp=self.qapp, categories=None,
                initial_value=self._get_current_usbvm())

        self.usb_qube_box.pack_start(
            WidgetWithButtons(self.select_widget), False, False, 0)

    def _get_current_usbvm(self):
        usb_vm_name = get_feature(self.vm, self.FEATURE_NAME, 'sys-usb')
        return self.qapp.domains.get(usb_vm_name)

    def save_changes(self):
        apply_feature_change_from_widget(self.select_widget, self.vm, self.FEATURE_NAME)
        # # TODO: do some sort of general close all edits?

    def get_selected_usbvm(self):
        # TODO: how this interacts with select in progress?????
        return self.select_widget.get_selected()


class InputDeviceHandler:
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
        self.action_widgets = {
            'qubes.InputKeyboard': None,
            'qubes.InputMouse': None,
            'qubes.InputTablet': None}

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

            self.action_widgets[rule.service] = action_widget
            self.grid.attach(child=WidgetWithButtons(action_widget),
                             left=1, top=self.policy_order[rule.service],
                             width=1, height=1)

# multifile conflict file handler

    def _warn(self):
        print("IO IO police plz come to FB")
        # TODO: fixme

    def save_changes(self):
        rules = []
        for widget in self.action_widgets.values():
            widget.rule.action = widget.get_selected()
            rules.append(widget.rule.raw_rule)

        # TODO: oy1!!!! current token handling everywhere check!!! doesn't it break or smth?
        self.policy_manager.save_rules(self.policy_file_name, rules,
                                       self.current_token)

    def is_changed(self):
        for widget in self.action_widgets.values():
            if widget.is_changed():
                return True
        return False


class DevicesHandler(PageHandler):
    """Handler for all the disparate Updates functions."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager,
                 gtk_builder: Gtk.Builder
 ):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.usbvm_handler = USBVMHandler(self.qapp, gtk_builder)

        usb_vm = self.usbvm_handler.get_selected_usbvm()

        self.input_handler = InputDeviceHandler(
            qapp, policy_manager, gtk_builder, usb_vm)
        # TODO: conflict files for input?
        # self.conflict_handler = ConflictFileHandler(
        #     gtk_builder, "updates", self.service_name,
        #     self.policy_file_name, self.policy_manager)


    def check_for_unsaved(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        return True

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""
        self.usbvm_handler.save_changes()
        self.input_handler.save_changes()
        return True


# see docs for input? maybe add a link?

# 2fa authentication
# for u2f keys
# link docs
# policy qubes.u2f
# enable service (show only those who have possible via supported service) and install package
# qubes-u2f-proxy service
# policy: this service adds a virtual device, when firefox or whatnot tries, it asks this device
# ask policy is useless: if you do it slowly, it will fail due to technical constraints of the U2F format
# source: vm z dostępem do sys-usb allow deny [hardcoded sys-usb]

# actually as usually somebody lied
# two services: u2f register [register a new key,
# this can have a allow-all option safely, use this allow/deny exceptions like with ??]
# and u2f authenticate which is problematic [this gets an argument, nobody knows this]
# you can do allow *, but this will allow a VM to use ANY key from the u2f
# if you want a vm to be able to use just one key, just register it in the vm

# see docs, the allow for RegisterArgument+a.... is basically a "use u2f switch"
# if some vms can do register, they need allow
# so basically: enable u2f,
# all/select vms can use this
# these vms can use all keys

# add some sort of open settings, add a special button maybe?
# default is disabled in input, enabled and disabled instead of verb indef
# tablet/touchscreen
# add more docs to input devices
# literowka all qubes CAN

# more lies
# both Register and Register argument need to be on to register stuff
# can use line from docs, anyvm is fine
