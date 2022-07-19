# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Marta Marczykowska-Górecka
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

# pylint: disable=import-error
import asyncio
import subprocess
import sys
import os
from typing import Optional, List, Tuple, Dict, Callable, Union
import abc
from contextlib import suppress
import pkg_resources
import logging
from functools import partial

from qrexec.policy.admin_client import PolicyClient
from qrexec.policy.parser import StringPolicy, Rule, Allow, Ask, Deny, Source, Target

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from .qubes_widgets_library import QubeName, VMListModeler, TextModeler, TraitSelector, TypeName, ImageTextButton

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')


class TraitHolder(abc.ABC):
    def __init__(self, relevant_widget: TraitSelector):
        """
        :param relevant_widget: widget that contains relevant property data
        """
        self.relevant_widget = relevant_widget

    @abc.abstractmethod
    def set_trait(self, new_value):
        """
        Set the appropriate trait, if changed.
        """

    @abc.abstractmethod
    def get_current_value(self):
        """
        Return whatever is the current value of the trait,
        :return:
        """


def get_feature(vm, feature_name, default_value=None):
    """
    get feature value
    """
    try:
        return vm.features.get(feature_name, default_value)
    except qubesadmin.exc.QubesDaemonAccessError:
        return default_value


def get_boolean_feature(vm, feature_name):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    return result


# TODO: just... do smth, rethink or what
class VMFeatureHolder(TraitHolder):
    def __init__(self, feature_name: str, feature_holder: qubesadmin.vm.QubesVM,
                 default_value, relevant_widget: TraitSelector,
                 is_boolean: bool = False):
        """
        :param feature_name: name of the feature
        :param feature_holder: object that has the feature
        :param default_value: default feature value
        :param relevant_widget: widget that contains relevant property data
        :param is_boolean: is the feature a bool? (needed because boolean
        features are encoded as 1 or empty string)
        """
        super().__init__(relevant_widget)
        self.feature_holder = feature_holder
        self.feature_name = feature_name
        self.default_value = default_value
        self.is_boolean = is_boolean
        if self.is_boolean:
            self.current_value = self._get_boolean_feature()
        else:
            self.current_value = self._get_feature()

    def _get_feature(self, force_default_none: bool = False):
        """
        get feature value
        :param force_default_none: if True, use None as default regardless
        of TraitHolder
        """
        default = None if force_default_none else self.default_value
        try:
            return self.feature_holder.features.get(
                self.feature_name, default)
        except qubesadmin.exc.QubesDaemonAccessError:
            return self.default_value

    def _get_boolean_feature(self):
        """helper function to get a feature converted to a Bool if it does exist.
        Necessary because of the true/false in features being coded as 1/empty
        string."""
        result = self._get_feature(force_default_none=True)
        if result is not None:
            result = bool(result)
        return result

    def get_current_value(self):
        return self.current_value

    def set_trait(self, new_value):
        """ set the feature"""
        # TODO: implement all possible edgecases

        self.feature_holder.features[self.feature_name] = new_value
        if self.is_boolean:
            self.current_value = self._get_boolean_feature()
        else:
            self.current_value = self._get_feature()


class VMPropertyHolder(TraitHolder):
    def __init__(self, property_name: str,
                 property_holder: Union[qubesadmin.vm.QubesVM, qubesadmin.Qubes],
                 relevant_widget: TraitSelector,
                 default_value: Optional = None):
        """
        A property that holds VMs.
        :param property_name: name of the property
        :param property_holder: object that has the property
        :param relevant_widget: widget that contains relevant property data
        :param default_value: default value of the property
        """
        super().__init__(relevant_widget)
        self.property_holder = property_holder
        self.property_name = property_name
        self.default_value = default_value
        self.current_value = getattr(self.property_holder, self.property_name,
                                     default_value)

    def set_trait(self, new_value):
        if hasattr(self.property_holder, self.property_name):
            setattr(self.property_holder, self.property_name, new_value)
            self.current_value = getattr(self.property_holder,
                                         self.property_name,
                                         self.default_value)
        else:
            # TODO ???
            return

    def get_current_value(self):
        return self.current_value


class PageHandler(abc.ABC):
    """abstract class for page handlers"""
    @abc.abstractmethod
    def save(self):
        """save settings changed in page"""

    @abc.abstractmethod
    def reset(self):
        """Undo all of user's changes"""


class BasicSettingsHandler(PageHandler):
    """
    Handler for the Basic Settings page.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: gtk_builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]

        # TODO: add (current) to list in some way

        self.clockvm_combo = gtk_builder.get_object('basics_clockvm_combo')
        self.clockvm_handler = VMListModeler(
            combobox=self.clockvm_combo, qapp=self.qapp,
            filter_function=lambda x: x.klass != 'TemplateVM',
            event_callback=None, default_value=None,
            current_value=self.qapp.clockvm, style_changes=True,
            allow_none=True)

        self.deftemplate_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_deftemplate_combo')
        self.deftemplate_handler = VMListModeler(
            combobox=self.deftemplate_combo, qapp=self.qapp,
            filter_function=lambda x: x.klass == 'TemplateVM',
            event_callback=None, default_value=None,
            current_value=self.qapp.default_template, style_changes=True,
            allow_none=True)

        self.defdispvm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_defdispvm_combo')
        self.defdispvm_handler = VMListModeler(
            combobox=self.defdispvm_combo, qapp=self.qapp,
            filter_function=lambda x: getattr(
                x, 'template_for_dispvms', False),
            event_callback=None, default_value=None,
            current_value=self.qapp.default_dispvm, style_changes=True,
            allow_none=True)

        self.fullscreen_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_fullscreen_combo')
        self.fullscreen_handler = TextModeler(
            self.fullscreen_combo,
            {'default (disallow)': None, 'allow': True, 'disallow': False},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-allow-fullscreen'),
            style_changes=True)

        self.utf_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_utf_windows_combo')
        self.utf_handler = TextModeler(
            self.utf_combo,
            {'default (disallow)': None, 'allow': True, 'disallow': False},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-allow-utf8-titles'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        # TODO: fix this, make a whole set of methods to get to those
        # complex features
        self.official_templates_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_official_templates_combo')
        self.official_templates_handler = TextModeler(
            self.official_templates_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)
        # TODO: maybe add some funkier methods to those dropdowns, so that
        #  we can just iterate over all of them and apply?

    def save(self):
        pass
        # TODO: implement

    def reset(self):
        pass # TODO: implement


class PolicyHandler:
    def __init__(self):
        self.policy_client = PolicyClient()
        self.policy_disclaimer = """
# THIS IS AN AUTOMATICALLY GENERATED POLICY FILE.
# Any changes made manually may be overwritten by Qubes Configuration Tools.
"""

    def get_conflicting_policy_files(self, service) -> List[str]:
        files = self.policy_client.policy_get_files(service)
        return files
    # TODO: check for actually conflicting once we add ours
    # TODO: more info, better wording

    def get_rules_from_filename(self, filename, default):
        try:
            rules_text, token = self.policy_client.policy_get(filename)
        except subprocess.CalledProcessError:
            self.policy_client.policy_replace(filename, default)
            rules_text, token = self.policy_client.policy_get(filename)

        rules = StringPolicy(policy={'__main__': rules_text}).rules

        return rules, token

    def new_rule(self, service: str, source: str, target: str, action: str) -> Rule:
        return Rule.from_line(
            None, f"{service}\t*\t{source}\t{target}\t{action}",
            filepath=None, lineno=0)

    def save_rules(self, file_name: str, rules_list: List[Rule], token):
        new_text = self.rules_to_text(rules_list)
        self.policy_client.policy_replace(file_name, new_text, token)

    def rules_to_text(self, rules_list: List[Rule]):
        return self.policy_disclaimer + \
               '\n'.join([str(rule) for rule in rules_list]) + '\n'


class RuleListBoxRow(Gtk.ListBoxRow):
    def __init__(self, rule: Rule, qapp: qubesadmin.Qubes,
                 ask_is_allow: bool = False,
                 is_main_rule: bool = False):
        super(RuleListBoxRow, self).__init__()

        self.qapp = qapp
        self.rule = rule
        self.ask_is_allow = ask_is_allow
        self.is_main_rule = is_main_rule

        self.get_style_context().add_class("permission_row")

        self.outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.outer_box)

        self.title_label = Gtk.Label("Editing rule:")
        self.title_label.set_no_show_all(True)
        self.error_label = Gtk.Label()
        self.error_label.set_no_show_all(True)
        self.outer_box.pack_start(self.title_label, False, False,0)
        self.outer_box.pack_start(self.error_label, False, False,0)

        self.main_widget_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_widget_box.set_homogeneous(True)
        self.outer_box.pack_start(self.main_widget_box, False, False,0)

        self.additional_widget_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.additional_widget_box.pack_end(
            ImageTextButton("qubes-delete", "Cancel changes", self.revert),
            False, False, 0)
        self.additional_widget_box.pack_end(
            ImageTextButton("qubes-ok", "Accept changes", self.validate_and_save),
            False, False, 0)
        self.additional_widget_box.set_no_show_all(True)

        self.outer_box.pack_start(self.additional_widget_box, False, False,0)

        self.source_widget = None
        self.source_model = None
        self.action_widget = None
        self.action_model = None
        self.target_widget = None
        self.target_model = None

        self._error_msg = None

        self.editing = None
        self.set_edit_mode(False)

    def _setup_delete_button(self):
        delete_button: Gtk.Button = Gtk.Button()
        delete_button.connect("clicked", self._delete_self)
        delete_icon = Gtk.Image()
        delete_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-delete', 14, 0))
        delete_button.add(delete_icon)
        delete_button.get_style_context().add_class('flat')
        if not self.is_main_rule:
            delete_button.set_no_show_all(True)
        return delete_button

    def _parse_action(self):
        new_action = self.action_model.get_selected()
        if new_action == 'allow':
            action_obj = Allow(self.rule)
        elif new_action == 'ask':
            action_obj = Ask(self.rule)
        elif new_action == 'deny':
            action_obj = Deny(self.rule)
        else:
            raise ValueError
        return action_obj

    def _delete_self(self, *_args):
        parent_widget = self.get_parent()
        parent_widget.remove(self)

    def set_edit_mode(self, editing: bool = True):
        """
        Change mode from display to edit and back.
        :param editing: if True, enter editing mode
        """
        # verify if can be changed tho?
        # TODO: add a revert button
        # TODO: when adding start in edit mode
        if editing:
            self.get_style_context().add_class('edited_row')
            self.title_label.set_visible(True)
            self.additional_widget_box.set_visible(True)
        else:
            self.get_style_context().remove_class('edited_row')
            self.title_label.set_visible(False)
            self.additional_widget_box.set_visible(False)

        # remove existing widgets
        for child in self.main_widget_box.get_children():
            self.main_widget_box.remove(child)

        action_function = self._get_action_selector if editing else self._get_action_label
        if editing and not self.is_main_rule:
            token_function = self._get_token_selector
        else:
            token_function = self._get_token_label

        self.source_widget, self.source_model = token_function(self.rule.source)
        self.main_widget_box.pack_start(self.source_widget, False, False, 0)

        self.action_widget, self.action_model = action_function()
        self.main_widget_box.pack_start(self.action_widget, False, False, 0)

        self.target_widget, self.target_model = token_function(self.rule.target)
        self.main_widget_box.pack_start(self.target_widget, False, False, 0)

        if not self.is_main_rule:
            delete_button = self._setup_delete_button()
            self.main_widget_box.pack_start(delete_button, False, False, 0)

        self.show_all()
        self.editing = editing

    def _get_token_label(self, token) -> \
            Tuple[Gtk.Widget, Optional[VMListModeler]]:
        if token.type == 'keyword':
            widget = TypeName(token)
        else:
            try:
                widget = QubeName(self.qapp.domains[token])
            except KeyError:
                widget = TypeName(f"Unknown Qube: {token}")
        return widget, None

    def _get_token_selector(self, token) -> \
            Tuple[Gtk.Widget, Optional[VMListModeler]]:
        if token.type == 'keyword':
            current_value = str(token)
        else:
            # TODO: handle exceptions
            current_value = self.qapp.domains[token]

        combobox = Gtk.ComboBox.new_with_entry()
        # TODO: figure out a better dom0 approach
        model = VMListModeler(combobox=combobox, qapp=self.qapp,
                              filter_function=lambda x: str(x) != 'dom0',
                              event_callback=None,
                              default_value=None, current_value=current_value,
                              style_changes=False, allow_none=False,
                              add_categories=True)
        return combobox, model

    def _get_action_label(self) -> Tuple[Gtk.Widget, Optional[TextModeler]]:
        action_name = type(self.rule.action).__name__.lower()
        if self.ask_is_allow and action_name == 'ask':
            action_name = 'allow'
        # TODO: styling?
        label = Gtk.Label()
        label.set_text(action_name)
        return label, None

    def _get_action_selector(self) -> Tuple[Gtk.Widget, Optional[TextModeler]]:
        choices = {"deny": "deny"}
        if self.ask_is_allow:
            choices["allow"] = "ask"
            # TODO: some sort of exception? if someone has allow here
        else:
            choices["allow"] = "allow"
            choices["allow"] = "ask"

        combobox = Gtk.ComboBoxText()
        model = TextModeler(
            combobox,
            choices,
            selected_value=type(self.rule.action).__name__.lower())
        return combobox, model

    def revert(self, *_args):
        if self.source_model and self.target_model:
            self.source_model.select_entry(str(self.rule.source))
            self.target_model.select_entry(str(self.rule.target))
        self.action_model.select_value(type(self.rule.action).__name__.lower())
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

    def validate_and_save(self, *_args):
        if self.source_model:
            new_source = Source(str(self.source_model.get_selected()))
        else:
            new_source = self.rule.source
        if self.target_model:
            new_target = Target(str(self.target_model.get_selected()))
        else:
            new_target = self.rule.target
        new_action = self._parse_action()

        self.error_msg = None
        for child in self.get_parent().get_children():
            if child == self:
                continue
            if child.rule.source == new_source and \
                    child.rule.target == new_target:
                if str(child.rule.action) == str(new_action):
                    self.error_msg = "This rule is a duplicate of another rule"
                else:
                    self.error_msg = "This rule conflicts with another rule"

        self.rule.source = new_source
        self.rule.target = new_target
        self.rule.action = new_action
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

    @property
    def error_msg(self):
        return self._error_msg

    @error_msg.setter
    def error_msg(self, value):
        self._error_msg = value
        if self.error_msg is None:
            self.error_label.set_visible(False)
        else:
            self.error_label.set_visible(True)
            self.error_label.set_text(self.error_msg)


class RuleListHandler:
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 prefix: str,
                 policy_handler: PolicyHandler,
                 service_name: str,
                 rules: List[Rule],
                 ask_is_allow: bool):

        self.qapp = qapp

        self.main_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_main_list')
        self.exception_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_exception_list')
        self.add_button: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_rule_button')

        self.policy_handler = policy_handler
        self.service_name = service_name
        self.ask_is_allow = ask_is_allow

        for rule in rules:
            if rule.source == '@anyvm' and rule.target == '@anyvm':
                self.main_list_box.add(RuleListBoxRow
                                       (rule, self.qapp,
                                        ask_is_allow=self.ask_is_allow,
                                        is_main_rule=True))
                break
            self.exception_list_box.add(RuleListBoxRow(
                rule, self.qapp, ask_is_allow=self.ask_is_allow))

        if not self.main_list_box.get_children():
            deny_all_rule = self.policy_handler.new_rule(
                self.service_name, '@anyvm', '@anyvm', 'deny')
            self.main_list_box.add(
                RuleListBoxRow(
                    deny_all_rule, self.qapp, ask_is_allow=self.ask_is_allow,
                    is_main_rule=True))

        self.exception_list_box.connect('row-activated', self._rule_clicked)
        self.main_list_box.connect('row-activated', self._rule_clicked)

        self.add_button.connect("clicked", self._add_new_rule)
        self.exception_list_box.set_sort_func(self._sorting_function)

        self.raw_event_box: Gtk.EventBox = \
            gtk_builder.get_object(f'{prefix}_raw_event')
        self.raw_box: Gtk.Box = \
            gtk_builder.get_object(f'{prefix}_raw_box')
        self.raw_expander_icon: Gtk.Image = \
            gtk_builder.get_object(f'{prefix}_raw_expander')

        self.raw_text: Gtk.TextView = gtk_builder.get_object(f'{prefix}_raw_text')
        self.text_buffer: Gtk.TextBuffer = self.raw_text.get_buffer()
        self.text_buffer.set_text(self.policy_handler.rules_to_text(self.get_current_rules()))

        self.raw_event_box.connect(
            'button-release-event', self._show_hide_raw)

    def _show_hide_raw(self, *_args):
        self.raw_box.set_visible(
            not self.raw_box.get_visible())
        if self.raw_box.get_visible():
            self.raw_expander_icon.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-shown', 20, 0))
        else:
            self.raw_expander_icon.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-hidden', 18, 0))


    @staticmethod
    def _cmp_token(token_1, token_2):
        # generic tokens go at the end, otherwise compare lexically
        if token_1 == token_2:
            return 0
        if token_1.type == token_2.type:
            if token_1 < token_2:
                return -1
            return 1
        if token_1.type == 'keyword':
            return 1
        return -1

    def _sorting_function(self, row_1: RuleListBoxRow, row_2: RuleListBoxRow):
        source_cmp = self._cmp_token(row_1.rule.source, row_2.rule.source)
        if source_cmp != 0:
            return source_cmp
        return self._cmp_token(row_1.rule.target, row_2.rule.target)

    def _add_new_rule(self, *_args):
        deny_all_rule = self.policy_handler.new_rule(
            self.service_name, '@anyvm', '@anyvm', 'deny')
        self.exception_list_box.add(RuleListBoxRow(
            deny_all_rule, self.qapp, ask_is_allow=True))

    def get_current_rules(self) -> List[Rule]:
        # TODO: maintain sorting
        rules = [child.rule for child in self.exception_list_box.get_children()]\
                + [child.rule for child in self.main_list_box.get_children()]
        return rules

    def _rule_clicked(self, _list_box, row, *_args):
        # first, all rows should stop being editable; this will get a warning #TODO
        for list_box in [self.main_list_box, self.exception_list_box]:
            for child in list_box.get_children():
                child.set_edit_mode(False)
            list_box.invalidate_sort()
        row.set_edit_mode(True)


class ClipboardHandler(PageHandler):

    # TODO:
    # - formatting
    # - saving
    # - add new window
    # - icons

    """
    Handler for the Clipboard page.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes, policy_handler: PolicyHandler):
        """
        :param gtk_builder: gtk_builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]
        self.policy_handler = policy_handler

        self.service_name = 'qubes.ClipboardPaste'
        self.policy_file_name = '50-config-clipboard'
        self.default_policy = "qubes.ClipboardPaste * @anyvm @anyvm ask\n"

        self.problem_label: Gtk.Label = gtk_builder.get_object('clipboard_problem_label')
        self.problem_list: Gtk.ListBox = gtk_builder.get_object('clipboard_problem_files_list')

        conflicting_files = self.policy_handler.get_conflicting_policy_files(self.service_name)
        if conflicting_files:
            self.problem_label.set_visible(True)
            for file in conflicting_files:
                row = Gtk.ListBoxRow()
                text = Gtk.Label()
                text.set_text(file)
                text.get_style_context().add_class('red_code')
                row.add(text)
                self.problem_list.add(row)
                # TODO: fix highlighting, the list should be non-clickable
                # TODO: add info box for legacy files
            self.problem_list.show_all()

        rules, self.current_token = \
            self.policy_handler.get_rules_from_filename(
                self.policy_file_name, self.default_policy)

        self.rule_list_handler = RuleListHandler(
            qapp=self.qapp,
            gtk_builder=gtk_builder,
            prefix="clipboard",
            policy_handler=self.policy_handler,
            service_name=self.service_name,
            rules=rules,
            ask_is_allow=True)

    def save(self):
        # TODO: do some sort of sanity checking, e.g. if you add a deny all
        #  and allow all rule?

        rules = self.rule_list_handler.get_current_rules()

        self.policy_handler.save_rules(self.policy_file_name,
                                       rules, self.current_token)
        # TODO: handle exceptions

# TODO: explain dom0 is not part of all?

    def reset(self):
        pass # TODO: implement


### Policy
# 1. detect custom changes: opt. 1: add a method that lists files affecting the given service, if there's something before, warn
#
#### establishing my policy
# 2. handle a single select file (AdminClient to get policy, parse using ????
# 3. serialize - this will be painful?
# this file should have comment DON'T EDIT MANUALLY

# import qrexec.policy.admin_client.PolicyClient
# PolicyClient()
# .policy_get_files(service_name)
# check replace: there's a trick to avoid race conditions
# (get gives token, use in replace)

# the file on parsing will error out horribly if include, which is good.

# treat 4.0 files like: what to do with compat?
# order: 50-* files
# maybe getFiles should give some artifician prefix like LEGACY POLICY:
# to old policy files
# there is a command line tool qubes-policy

class GeneralConfig(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, qapp):
        """
        :param qapp: qubesadmin.Qubes object
        """
        super().__init__(application_id='org.qubesos.generalconfig')
        self.qapp: qubesadmin.Qubes = qapp

        self.builder: Optional[Gtk.Builder] = None
        self.main_window: Optional[Gtk.Window] = None

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        self.perform_setup()
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, 'general_config.glade'))

        self.main_window = self.builder.get_object('main_window')
        self.main_notebook: Gtk.Notebook = self.builder.get_object('main_notebook')

        self._handle_theme()
        policy_handler = PolicyHandler()

        self.apply_button: Gtk.Button = self.builder.get_object('apply_button')
        self.cancel_button: Gtk.Button = self.builder.get_object('cancel_button')
        self.ok_button: Gtk.Button = self.builder.get_object('ok_button')

        self.apply_button.connect('clicked', self._apply)
        self.cancel_button.connect('clicked', self._quit)
        self.ok_button.connect('clicked', self._ok)

        # match page by id to handler; this is not pretty, but Gtk likes
        # to ID pages by their number, there is no simple page_id
        self.handlers: Dict[int, PageHandler] = {
            0: BasicSettingsHandler(self.builder, self.qapp),
            4: ClipboardHandler(self.builder, self.qapp, policy_handler)}

    # TODO: switching pages with unsaved changes should scream

    def _apply(self, _widget):
        print("DEBUG: current page ID:", self.main_notebook.get_current_page())
        current_handler = self.handlers.get(self.main_notebook.get_current_page(), None)
        if current_handler:
            current_handler.save()
        # TODO: scream if not found?

    def _quit(self, _widget):
        self.quit()

    def _ok(self, widget):
        self._apply(widget)
        self._quit(widget)

    def _handle_theme(self):
        # style_context = self.main_window.get_style_context()
        # window_default_color = style_context.get_background_color(
        #     Gtk.StateType.NORMAL)
        # TODO: future: determine light or dark scheme by checking if text is
        #  lighter or darker than background
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(pkg_resources.resource_filename(
            __name__, 'qubes-general-config.css'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    app = GeneralConfig(qapp)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())


# TODO: mark changed by something nicer than (current), maybe e.g. cursive or something; can be done with CSS