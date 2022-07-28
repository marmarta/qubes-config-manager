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
# pylint: disable=import-error
"""
RPC Policy-related functionality.
"""
import abc
import subprocess
from abc import ABC
from copy import deepcopy
from typing import Optional, List, Tuple, Type, Dict, Set

from qrexec.policy.admin_client import PolicyClient
from qrexec.policy.parser import StringPolicy, Rule
from qrexec.exc import PolicySyntaxError

from ..widgets.qubes_widgets_library import VMListModeler, TextModeler,\
    ImageTextButton, show_error, TokenName, BiDictionary
from .page_handler import PageHandler
from .policy_rules import AbstractRuleWrapper, AbstractVerbDescription

import gi

import qubesadmin
import qubesadmin.vm

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()

SOURCE_CATEGORIES = {
    "@anyvm": "ALL QUBES",
    "@type:AppVM": "TYPE: APP",
    "@type:TemplateVM": "TYPE: TEMPLATES",
    "@type:DispVM": "TYPE: DISPOSABLE",
    "@adminvm": "TYPE: ADMINVM"
}

TARGET_CATEGORIES = {
    "@anyvm": "ALL QUBES",
    "@dispvm": "Default Disposable Qube",
    "@type:AppVM": "TYPE: APP",
    "@type:TemplateVM": "TYPE: TEMPLATES",
    "@type:DispVM": "TYPE: DISPOSABLE",
    "@adminvm": "TYPE: ADMINVM"
}



class PolicyManager:
    """
    Single manager for interacting with Qubes Policy.
    Should be used as a singleton.
    """
    def __init__(self):
        self.policy_client = PolicyClient()
        self.policy_disclaimer = """
# THIS IS AN AUTOMATICALLY GENERATED POLICY FILE.
# Any changes made manually may be overwritten by Qubes Configuration Tools.
"""

    def get_conflicting_policy_files(self, service: str,
                                     own_file: str) -> List[str]:
        """
        Get a list of policy files (as str) that apply to the selected service
        and are before it in load order.
        :param service: service name
        :param own_file: name of the config's own file
        :return: list of file names as str
        """
        files = self.policy_client.policy_get_files(service)

        conflicting_files = []
        for f in files:
            if f == own_file:
                break
            conflicting_files.append(f)
        return conflicting_files

    def get_rules_from_filename(self, filename: str, default_policy: str) -> \
            Tuple[List[Rule], str]:
        """Get rules contained in a provided file. If the file does not exist,
        populate it with provided default policy and return the contents.
        Return list of Rule objects and str of the PolicyClient's token
        for the file."""
        try:
            rules_text, token = self.policy_client.policy_get(filename)
        except subprocess.CalledProcessError:
            self.policy_client.policy_replace(filename, default_policy)
            rules_text, token = self.policy_client.policy_get(filename)

        rules = self.text_to_rules(rules_text)

        return rules, token

    def compare_rules_to_text(self, rules, file_text) -> bool:
        """Check if the list of rules is equivalent to policy file text."""
        second_rules = self.text_to_rules(file_text)
        if len(rules) != len(second_rules):
            return False
        for rule, rule_2 in zip(rules, second_rules):
            if str(rule) != str(rule_2):
                return False
        return True

    @staticmethod
    def new_rule(service: str, source: str, target: str, action: str) -> Rule:
        """Create a new Rule object from given parameters: service, source,
        target and action should be provided according to policy file specs."""
        return Rule.from_line(
            None, f"{service}\t*\t{source}\t{target}\t{action}",
            filepath=None, lineno=0)

    def save_rules(self, file_name: str, rules_list: List[Rule], token: str):
        """Save provided list of rules to a file. Must provide
        a token corresponding to last file access, to avoid unexpected
        overwriting."""
        new_text = self.rules_to_text(rules_list)
        self.policy_client.policy_replace(file_name, new_text, token)

    def rules_to_text(self, rules_list: List[Rule]) -> str:
        """Convert list of Rules to text ready to be stored in a file."""
        return self.policy_disclaimer + \
               '\n'.join([str(rule) for rule in rules_list]) + '\n'

    @staticmethod
    def text_to_rules(text: str) -> List[Rule]:
        """Convert policy file text to a list of Rules."""
        return StringPolicy(policy={'__main__': text}).rules


class VMWidget(Gtk.Box):
    """VM/category selection widget."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 categories: Optional[Dict[str, str]],
                 initial_value: str,
                 additional_text: Optional[str] = None,
                 additional_widget: Optional[Gtk.Widget] = None):
        """
        :param qapp: Qubes object
        :param categories: list of additional categories available for this
        VM, in the form of token/api name: readable name
        :param initial_value: initial selected value as str
        :param additional_text: additional text to be added after
        selector widget
        :param additional_widget: additional widget to be packed after selector
        widget
        """

        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.qapp = qapp
        self.selected_value = initial_value

        self.combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
        self.combobox.get_child().set_width_chars(24)
        self.model = VMListModeler(combobox=self.combobox,
                                   qapp=self.qapp,
                                   filter_function=lambda x: str(x) != 'dom0',
                                   current_value=str(self.selected_value),
                                   additional_options=categories)

        self.name_widget = TokenName(self.selected_value, self.qapp,
                                     categories=categories)

        self.combobox.set_no_show_all(True)
        self.name_widget.set_no_show_all(True)

        self.pack_start(self.combobox, True, True, 0)
        self.pack_start(self.name_widget, True, True, 0)
        self.combobox.set_halign(Gtk.Align.START)

        if additional_text:
            additional_text_widget = \
                Gtk.Label(additional_text)
            additional_text_widget.get_style_context().add_class(
                'didascalia')
            additional_text_widget.set_halign(Gtk.Align.END)
            self.pack_end(additional_text_widget, False, False, 0)
        if additional_widget:
            additional_widget.set_halign(Gtk.Align.END)
            self.pack_end(additional_widget, False, False, 0)

        self.set_editable(False)

    def set_editable(self, editable: bool):
        """Change state between editable and non-editable."""
        self.combobox.set_visible(editable)
        self.name_widget.set_visible(not editable)

    def is_changed(self) -> bool:
        """Return True if widget was changed from its initial state."""
        new_value = self.model.get_selected()
        return str(self.selected_value) != str(new_value)

    def save_changes(self):
        """Store changes in model; must be used before set_editable(True) if
        it's desired to see changes reflected in non-editable state"""
        new_value = str(self.model.get_selected())
        self.selected_value = new_value
        self.name_widget.set_token(new_value)

    def get_selected(self):
        """Get currently selected value."""
        return self.model.get_selected()

    def revert_changes(self):
        """Roll back to last saved state."""
        self.model.select_entry(self.selected_value)


class ActionWidget(Gtk.Box):
    """Action selection widget."""
    def __init__(self,
                 choices: Dict[str, str],
                 initial_value: str,
                 verb_description: AbstractVerbDescription,
                 rule: AbstractRuleWrapper):
        """
        :param choices: dictionary of policy value: readable name
        :param initial_value: initial policy value
        :param verb_description: AbstractVerbDescription object to get
        additional text
        :param rule: relevant Rule
        """
        # choice is code: readable
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        self.choices = BiDictionary(choices)
        self.verb_description = verb_description
        self.rule = rule

        # to avoid inconsistencies
        self.selected_value = initial_value.lower()
        self.combobox = Gtk.ComboBoxText()
        self.model = TextModeler(
            self.combobox,
            self.choices.inverted,
            selected_value=self.selected_value)
        self.name_widget = Gtk.Label()
        self.additional_text_widget = Gtk.Label()
        self.additional_text_widget.get_style_context().add_class(
            'didascalia')

        self.combobox.set_no_show_all(True)
        self.name_widget.set_no_show_all(True)

        self.pack_start(self.combobox, True, True, 0)
        self.pack_start(self.name_widget, True, True, 0)
        self.pack_end(self.additional_text_widget, False, False, 0)
        self.combobox.set_halign(Gtk.Align.START)
        self.name_widget.set_halign(Gtk.Align.START)
        self.additional_text_widget.set_halign(Gtk.Align.END)

        self._format_new_value(initial_value)
        self.set_editable(False)

    def _format_new_value(self, new_value):
        # TODO: FIXXXXX when rule is weird
        self.name_widget.set_markup(f'<b>{self.choices[new_value]}</b>')
        self.additional_text_widget.set_text(
            self.verb_description.get_verb_for_action_and_target(
                new_value, self.rule.target))

    def set_editable(self, editable: bool):
        """Change state between editable and non-editable."""
        self.combobox.set_visible(editable)
        self.name_widget.set_visible(not editable)

    def is_changed(self) -> bool:
        """Return True if widget was changed from its initial state."""
        new_value = self.model.get_selected()
        return str(self.selected_value) != str(new_value)

    def save_changes(self):
        """Store changes in model; must be used before set_editable(True) if
        it's desired to see changes reflected in non-editable state"""
        new_value = self.model.get_selected()
        self.selected_value = new_value
        self._format_new_value(new_value)

    def get_selected(self):
        """Get currently selected value."""
        return self.model.get_selected()

    def revert_changes(self):
        """Roll back to last saved state."""
        self.model.select_value(self.selected_value)


class RuleListBoxRow(Gtk.ListBoxRow):
    """Row in a listbox representing a policy rule"""
    def __init__(self,
                 parent_handler: 'AbstractPolicyHandler',
                 rule: AbstractRuleWrapper,
                 qapp: qubesadmin.Qubes,
                 verb_description: AbstractVerbDescription,
                 ask_is_allow: bool = False,
                 is_fundamental_rule: bool = False):
        """
        :param parent_handler: PolicyHandler object this rule belongs to.
        :param rule: Rule object, wrapped in a helper object
        :param qapp: Qubes object
        :param verb_description: AbstractVerbDescription object
        :param ask_is_allow: should 'ask' be treated the same as 'allow'
        :param is_fundamental_rule: can this rule be deleted/can its objects be
        changed
        """
        super().__init__()

        self.qapp = qapp
        self.rule = rule
        self.ask_is_allow = ask_is_allow
        self.is_fundamental_rule = is_fundamental_rule
        self.verb_description = verb_description
        self.parent_handler = parent_handler

        self.get_style_context().add_class("permission_row")

        self.outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.outer_box)

        self.title_label = Gtk.Label("Editing rule:")
        self.title_label.set_no_show_all(True)
        self.title_label.get_style_context().add_class('small_title')
        self.title_label.set_halign(Gtk.Align.START)
        self.outer_box.pack_start(self.title_label, False, False, 0)

        self.main_widget_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_widget_box.set_homogeneous(True)

        self.source_widget = VMWidget(
            self.qapp, SOURCE_CATEGORIES, self.rule.source,
            additional_text="will")
        self.target_widget = VMWidget(
            self.qapp, TARGET_CATEGORIES, self.rule.target,
            additional_widget=self._get_delete_button())
        self.action_widget = ActionWidget(self.rule.ACTION_CHOICES,
            self.rule.action,
            self.verb_description, self.rule)

        self.main_widget_box.pack_start(self.source_widget, False, True, 0)
        self.main_widget_box.pack_start(self.action_widget, False, True, 0)
        self.main_widget_box.pack_start(self.target_widget, False, True, 0)
        self.outer_box.pack_start(self.main_widget_box, False, False, 0)

        self.additional_widget_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL)
        save_button = ImageTextButton(
            icon_name="qubes-ok", label="ACCEPT",
            click_function=self.validate_and_save,
            style_classes=["button_save", "flat_button"])
        cancel_button = ImageTextButton(
            icon_name="qubes-delete", label="CANCEL",
            click_function=self.revert,
            style_classes=["button_cancel", "flat_button"])
        self.additional_widget_box.pack_end(save_button, False, False, 10)
        self.additional_widget_box.pack_end(cancel_button, False, False, 10)

        self.additional_widget_box.set_no_show_all(True)
        self.outer_box.pack_start(self.additional_widget_box, False, False, 10)

        self.editing: bool = False

        self.set_edit_mode(False)

    def _get_delete_button(self) -> Gtk.Button:
        """Get a delete button appropriate for the class."""
        if self.is_fundamental_rule:
            delete_button = ImageTextButton(icon_name='qubes-padlock',
                                            label=None,
                                            click_function=None,
                                            style_classes=["flat"])
        else:
            delete_button = ImageTextButton(icon_name='qubes-delete',
                                            label=None,
                                            click_function=self._delete_self,
                                            style_classes=["flat"])
        return delete_button

    def _delete_self(self, *_args):
        """Remove self from parent. Used to delete the rule."""
        parent_widget = self.get_parent()
        parent_widget.remove(self)
        parent_widget.emit('rules-changed', None)

    def set_edit_mode(self, editing: bool = True):
        """
        Change mode from display to edit and back.
        :param editing: if True, enter editing mode
        """
        if editing:
            self.get_style_context().add_class('edited_row')
            self.title_label.set_visible(True)
            self.additional_widget_box.set_visible(True)
        else:
            self.get_style_context().remove_class('edited_row')
            self.title_label.set_visible(False)
            self.additional_widget_box.set_visible(False)

        if not self.is_fundamental_rule:
            self.source_widget.set_editable(editing)
            self.target_widget.set_editable(editing)
        self.action_widget.set_editable(editing)

        self.show_all()
        self.editing = editing

    def __str__(self):  # pylint: disable=arguments-differ
        # base class has automatically generated params
        result = "From: "
        result += str(self.source_widget.get_selected())
        result += " to: "
        result += str(self.target_widget.get_selected())
        result += " Action: " + self.action_widget.get_selected()
        return result

    def is_changed(self) -> bool:
        """Return True if rule was changed."""
        if not self.editing:
            return False
        return self.source_widget.is_changed() or \
            self.action_widget.is_changed() or \
            self.target_widget.is_changed()

    def revert(self, *_args):
        """Revert all changes to the Rule."""
        self.source_widget.revert_changes()
        self.action_widget.revert_changes()
        self.target_widget.revert_changes()
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

    def validate_and_save(self, *_args) -> bool:
        """Validate if the rule is not duplicate or conflicting with another
        rule, then save. If this fails, return False, else return True."""
        new_source = str(self.source_widget.get_selected())
        new_target = str(self.target_widget.get_selected())
        new_action = self.action_widget.get_selected()

        error = self.rule.is_rule_valid(new_source, new_target, new_action)
        if error:
            show_error("Invalid rule", f'This rule is not valid: {error}')
            return False

        error = self.parent_handler.verify_new_rule(self, new_source,
                                                    new_target, new_action)
        if error:
            show_error("Cannot save rule",
                       'This rule conflicts with the following existing rule:'
                       f'\n{error}\n')
            return False

        self.rule.source = new_source
        self.rule.target = new_target
        self.rule.action = new_action
        self.source_widget.save_changes()
        self.target_widget.save_changes()
        self.action_widget.save_changes()
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

        self.get_parent().emit('rules-changed', None)
        return True

class ConflictFileListRow(Gtk.ListBoxRow):
    """A ListBox row representing a policy file with conflicting info."""
    def __init__(self, file_name: str):
        super().__init__()
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)

        self.get_style_context().add_class('problem_row')

        self.label = Gtk.Label()
        self.label.set_text(file_name)
        self.label.get_style_context().add_class('red_code')
        self.box.pack_start(self.label, False, False, 0)

        if file_name.startswith('/etc/qubes-rpc'):
            self.icon = Gtk.Image()
            self.icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-question', 14, 0))
            tooltip = 'This is a legacy file from previous Qubes versions. ' \
                      'Custom policy contained there will no longer ' \
                      'be supported in Qubes 4.2.'
            self.set_tooltip_text(tooltip)
            self.box.pack_start(self.icon, False, False, 0)


class ConflictFileHandler:
    """Handler for conflicting policy files."""
    def __init__(self, gtk_builder: Gtk.Builder, prefix: str, service_name: str,
                 own_file_name: str, policy_manager: PolicyManager):
        self.service_name = service_name
        self.own_file_name = own_file_name
        self.policy_manager = policy_manager

        self.problem_box: Gtk.Box = gtk_builder.get_object(
            f'{prefix}_problem_box')
        self.problem_list: Gtk.ListBox = gtk_builder.get_object(
            f'{prefix}_problem_files_list')

        conflicting_files = self.policy_manager.get_conflicting_policy_files(
            self.service_name, self.own_file_name)
        print(f"Found problem files: {conflicting_files}")

        if conflicting_files:
            self.problem_box.set_visible(True)
            for file in conflicting_files:
                row = ConflictFileListRow(file)
                self.problem_list.add(row)
            self.problem_box.show_all()


class PolicyHandler(PageHandler):
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 prefix: str,
                 policy_manager: PolicyManager,
                 default_policy: str,
                 service_name: str,
                 policy_file_name: str,
                 verb_description: AbstractVerbDescription,
                 rule_class: Type[AbstractRuleWrapper]):
        """
        :param qapp: Qubes object
        :param gtk_builder: gtk_builder; to avoid inelegant design, this should
        not be stored in this function
        :param prefix: prefix for widgets used by this class
        :param policy_manager: PolicyManager object
        :param default_policy: string representing default policy file
        :param service_name: name of the service being handled by this page
        :param policy_file_name: name of the config's policy file for this
        service
        :param verb_description: AbstractVerbDescription object
        :param rule_class: class to be used for Rules, must inherit from
         AbstractRuleWrapper
        """

        self.qapp = qapp
        self.policy_manager = policy_manager
        self.default_policy = default_policy
        self.service_name = service_name
        self.policy_file_name = policy_file_name
        self.verb_description = verb_description
        self.rule_class = rule_class

        # main widgets
        self.main_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_main_list')
        self.exception_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_exception_list')

        # add new rule button
        self.add_button: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_rule_button')

        # enable/disable custom policy
        self.enable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f'{prefix}_enable_radio')
        self.disable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f'{prefix}_disable_radio')

        # raw policy text widgets
        self.raw_event_box: Gtk.EventBox = \
            gtk_builder.get_object(f'{prefix}_raw_event')
        self.raw_box: Gtk.Box = \
            gtk_builder.get_object(f'{prefix}_raw_box')
        self.raw_expander_icon: Gtk.Image = \
            gtk_builder.get_object(f'{prefix}_raw_expander')
        self.raw_text: Gtk.TextView = gtk_builder.get_object(
            f'{prefix}_raw_text')
        self.raw_save: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_raw_save')
        self.raw_cancel: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_raw_cancel')
        self.text_buffer: Gtk.TextBuffer = self.raw_text.get_buffer()

        # connect events
        self.add_button.connect("clicked", self.add_new_rule)

        self.exception_list_box.connect('row-activated', self._rule_clicked)
        self.main_list_box.connect('row-activated', self._rule_clicked)
        self.exception_list_box.connect('rules-changed', self.fill_raw_rules)
        self.main_list_box.connect('rules-changed', self.fill_raw_rules)

        self.raw_event_box.connect(
            'button-release-event', self._show_hide_raw)
        self.raw_save.connect("clicked", self._save_raw)
        self.raw_cancel.connect("clicked", self._cancel_raw)

        self.enable_radio.connect("toggled", self._custom_toggled)
        self.disable_radio.connect("toggled", self._custom_toggled)

        self.exception_list_box.set_sort_func(self.rule_sorting_function)

        self.conflict_handler = ConflictFileHandler(
            gtk_builder, prefix, self.service_name,
            self.policy_file_name, self.policy_manager)

        self.initial_rules, self.current_token = \
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, self.default_policy)

        # fill data
        rules = deepcopy(self.initial_rules)
        self.populate_rule_lists(rules)
        self.fill_raw_rules()
        self.check_custom_rules(rules)

    def add_new_rule(self, *_args):
        """Add a new rule."""
        if not self.close_all_edits():
            return
        deny_all_rule = self.policy_manager.new_rule(
            self.service_name, '@anyvm', '@anyvm', 'deny')
        new_row = RuleListBoxRow(self,
            self.rule_class(deny_all_rule), self.qapp, self.verb_description)
        self.exception_list_box.add(new_row)
        new_row.activate()

    @property
    def current_rules(self) -> List[Rule]:
        """
        Get the currently selected set of AbstractRuleWrapper rules.
        """
        if self.disable_radio.get_active():
            return self.policy_manager.text_to_rules(self.default_policy)
        return [row.rule.raw_rule for row in self.current_rows]

    @property
    def current_rows(self) -> List[RuleListBoxRow]:
        """
        Get the current list of all RuleListBoxRows
        """
        return self.exception_list_box.get_children() + \
               self.main_list_box.get_children()

    def populate_rule_lists(self, rules: List[Rule]):
        """Populate rule lists with the provided set of Rule objects."""
        for child in self.main_list_box.get_children():
            self.main_list_box.remove(child)
        for child in self.exception_list_box.get_children():
            self.exception_list_box.remove(child)

        for rule in rules:
            wrapped_rule = self.rule_class(rule)
            if wrapped_rule.is_rule_fundamental():
                self.main_list_box.add(RuleListBoxRow
                                       (self, wrapped_rule,
                                        self.qapp, self.verb_description,
                                        is_fundamental_rule=True))
                continue
            fundamental = rule.source == '@adminvm' and rule.target == '@anyvm'
            self.exception_list_box.add(RuleListBoxRow(self,
                rule=wrapped_rule, qapp=self.qapp,
                verb_description=self.verb_description,
                is_fundamental_rule=fundamental))

        if not self.main_list_box.get_children():
            deny_all_rule = self.policy_manager.new_rule(
                self.service_name, '@anyvm', '@anyvm', 'deny')
            self.main_list_box.add(
                RuleListBoxRow(self,
                    self.rule_class(deny_all_rule), self.qapp,
                    self.verb_description,
                    is_fundamental_rule=True))

    def set_custom_editable(self, state: bool):
        """If true, set widgets to accept editing custom rules."""
        self.add_button.set_sensitive(state)
        self.main_list_box.set_sensitive(state)
        self.exception_list_box.set_sensitive(state)

    def _save_raw(self, _widget):
        try:
            rules: List[Rule] = self.policy_manager.text_to_rules(
                self.text_buffer.get_text(
                    self.text_buffer.get_start_iter(),
                    self.text_buffer.get_end_iter(), False))
            self.populate_rule_lists(rules)
            self.check_custom_rules(rules)
            self._show_hide_raw()
        except PolicySyntaxError as ex:
            show_error("Policy error",
                       f"Cannot save policy.\n"
                       f"Encountered the following error(s):\n{ex}")
            return

    def _cancel_raw(self, _widget):
        self.fill_raw_rules()

    def _show_hide_raw(self, *_args):
        # if showing raws, make sure editing is done
        if not self.raw_box.get_visible():
            if not self.close_all_edits():
                return
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

    def fill_raw_rules(self, *_args):
        """Fill raw text window with appropriate data, based on whatever's
        currently selected"""
        self.text_buffer.set_text(self.policy_manager.rules_to_text(
            self.current_rules))

    @staticmethod
    def cmp_token(token_1, token_2):
        """Helper method to compare VMTokens in a format Gtk likes."""
        # @anyvm goes at the end, then other generic tokens,
        # otherwise compare lexically
        if token_1 == token_2:
            return 0
        if token_1 == '@anyvm':
            return 1
        if token_2 == '@anyvm':
            return -1
        is_token_1_keyword = token_1.startswith('@')
        is_token_2_keyword = token_2.startswith('@')
        if is_token_1_keyword == is_token_2_keyword:
            if token_1 < token_2:
                return -1
            return 1
        if is_token_1_keyword:
            return 1
        return -1

    def rule_sorting_function(self,
                              row_1: RuleListBoxRow, row_2: RuleListBoxRow):
        """Sorting function for exceptions."""
        source_cmp = self.cmp_token(row_1.rule.source, row_2.rule.source)
        if source_cmp != 0:
            return source_cmp
        return self.cmp_token(row_1.rule.target, row_2.rule.target)

    def check_custom_rules(self, rules: List[Rule]):
        """
        Check if the provided set of rules is the same as the default set,
        set radio buttons accordingly.
        """
        if self.policy_manager.compare_rules_to_text(rules,
                                                     self.default_policy):
            self.disable_radio.set_active(True)
        else:
            self.enable_radio.set_active(True)
        self._custom_toggled()

    def _custom_toggled(self, _widget=None):
        if not self.close_all_edits():
            return
        self.set_custom_editable(self.enable_radio.get_active())
        self.fill_raw_rules()

    def _rule_clicked(self, _list_box, row: RuleListBoxRow, *_args):
        if row.editing:
            # if the current row was clicked, nothing should happen
            return
        if not self.close_all_edits():
            return
        row.set_edit_mode(True)

    def verify_new_rule(self, row: RuleListBoxRow,
                        new_source: str, new_target: str,
                        _new_action: str) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        for other_row in self.current_rows:
            if other_row == row:
                continue
            if other_row.rule.is_rule_conflicting(new_source, new_target):
                return str(other_row)
        return None

    def close_all_edits(self) -> bool:
        """Attempt to close all edited rows; if failed, return False, else
        return True"""
        for row in self.current_rows:
            if row.editing:
                if not row.is_changed():
                    row.set_edit_mode(False)
                    continue
                dialog = Gtk.MessageDialog(
                    None,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
                dialog.set_title("A rule is currently being edited")
                dialog.set_markup(
                    "Do you want to save changes to the following "
                    f"rule?\n{str(row)}")
                response = dialog.run()
                if response == Gtk.ResponseType.YES:
                    if not row.validate_and_save():
                        return False
                else:
                    row.revert()
                dialog.destroy()
        return True

    def check_for_unsaved(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        if not self.close_all_edits():
            return False
        unsaved_found = False
        if len(self.initial_rules) != len(self.current_rules):
            unsaved_found = True
        for rule1, rule2 in zip(self.initial_rules, self.current_rules):
            if str(rule1) != str(rule2):
                unsaved_found = True

        if unsaved_found:
            dialog = Gtk.MessageDialog(
                None,
                Gtk.DialogFlags.MODAL,
                Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
            dialog.set_title("")
            dialog.set_markup(
                "Do you want to save changes to current "
                "policy rules?")
            # TODO: nicer name? improve when improving message dialogs
            response = dialog.run()
            if response == Gtk.ResponseType.YES:
                dialog.destroy()
                return self.save()
            dialog.destroy()
            self.reset()
        return True

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        rules = deepcopy(self.initial_rules)
        self.populate_rule_lists(rules)
        self.fill_raw_rules()
        self.check_custom_rules(rules)

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""
        rules = self.current_rules
        try:
            self.policy_manager.save_rules(self.policy_file_name,
                                           rules, self.current_token)
        except Exception as ex:
            show_error("Failed to save rules", f"Error {str(ex)}")
            return False
        self.initial_rules = deepcopy(rules)
        return True


class VMSubsetPolicyHandler(PolicyHandler):
    """
    Handler for a list of policy rules where targets are limited to a subset
    of VMs.
    """
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 prefix: str,
                 policy_manager: PolicyManager,
                 default_policy: str,
                 service_name: str,
                 policy_file_name: str,
                 main_verb_description: AbstractVerbDescription,
                 main_rule_class: Type[AbstractRuleWrapper],
                 exception_verb_description: AbstractVerbDescription,
                 exception_rule_class: Type[AbstractRuleWrapper]):
        """
        :param qapp: Qubes object
        :param gtk_builder: gtk_builder; to avoid inelegant design, this should
        not be stored in this function
        :param prefix: prefix for widgets used by this class
        :param policy_manager: PolicyManager object
        :param default_policy: string representing default policy file
        :param service_name: name of the service being handled by this page
        :param policy_file_name: name of the config's policy file for this
        service
        :param main_verb_description: AbstractVerbDescription object for the
        main rules
        :param main_rule_class: class to be used for main Rules, must inherit
        from AbstractRuleWrapper
        :param exception_verb_description: AbstractVerbDescription object for
        the exception rules
        :param exception_rule_class: class to be used for exception Rules, must
         inherit from AbstractRuleWrapper
        """
        self.select_qubes: Set[str] = set()
        self.main_verb_description = main_verb_description
        self.main_rule_class = main_rule_class
        self.exception_verb_description = exception_verb_description
        self.exception_rule_class = exception_rule_class

        # main widgets
        self.flowbox: Gtk.FlowBox = gtk_builder.get_object(
            f"{prefix}_main_flowbox")
        self.custom_box: Gtk.Box = gtk_builder.get_object(
            f'{prefix}_custom_box')

        self.add_select_box: Gtk.Box = gtk_builder.get_object(
            f'{prefix}_add_select_box')
        self.edit_select_qubes_button: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_edit_select_qubes')
        self.cancel_add_select_button: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_cancel_add_select_qube')
        self.add_select_button: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_add_select_qube')
        self.select_qube_combo: Gtk.ComboBox = gtk_builder.get_object(
            f'{prefix}_select_qube_combo')

        super().__init__(
            qapp, gtk_builder, prefix, policy_manager, default_policy,
            service_name, policy_file_name, exception_verb_description,
            exception_rule_class)

        # populate combo
        self.select_qube_model = VMListModeler(
            combobox=self.select_qube_combo,
            qapp=self.qapp)

        # connect events
        self.edit_select_qubes_button.connect('clicked', self.edit_select_qubes)
        self.cancel_add_select_button.connect('clicked', self.edit_select_qubes)
        self.add_select_button.connect('clicked', self._add_select_qube)

# TODO: save rules multiplies them horribly

    def populate_rule_lists(self, rules: List[Rule]):
        # rules with source = '@anyvm' go to main list and their qubes are key qubes
        for rule in rules:
            if rule.source == '@anyvm':
                if rule.target.type == 'keyword':
                    # we do not support this
                    continue
                self.select_qubes.add(str(rule.target))
                self.main_list_box.add(RuleListBoxRow(
                    parent_handler=self,
                    rule=self.main_rule_class(rule),
                    qapp=self.qapp,
                    verb_description=self.main_verb_description,
                    is_fundamental_rule=True))
            else:
                # TODO: LIMITED SELECTION IN TARGET
                # TODO: WHAT TO DO WITH DOUBLE RULES (prolly only in get rules something)
                self.exception_list_box.add(RuleListBoxRow(
                    parent_handler=self,
                    rule=self.exception_rule_class(rule),
                    qapp=self.qapp,
                    verb_description=self.exception_verb_description))
        self._populate_flowbox(False)

    def set_custom_editable(self, state: bool):
        self.custom_box.set_sensitive(state)

    def edit_select_qubes(self, *_args):
        new_state = not self.add_select_box.get_visible()
        self._populate_flowbox(new_state)
        self.add_select_box.set_visible(new_state)
        # TODO: this must be noticed by senpai of changes checking/close all edits

    def _add_select_qube(self, *_args):
        # TODO: validate if selected
        new_qube = str(self.select_qube_model.get_selected())
        self.select_qubes.add(new_qube)
        self.edit_select_qubes()

    def add_new_rule(self, *_args):
        # TODO
        pass

    def _populate_flowbox(self, editable: bool):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)

        for qube in self.select_qubes:
            token_widget = TokenName(qube, self.qapp, {})
            if editable:
                final_widget = Gtk.Button()
                final_widget.get_style_context().add_class('flat')

                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                box.pack_start(token_widget, False, False, 0)
                remove_icon = Gtk.Image()
                remove_icon.set_from_pixbuf(
                    Gtk.IconTheme.get_default().load_icon(
                        'qubes-delete', 14, 0))
                box.pack_start(remove_icon, False, False, 10)

                final_widget.add(box)
                final_widget.connect('clicked', self._remove_select_qube)
            else:
                final_widget = token_widget
            final_widget.set_name(qube)
            final_widget.show_all()
            self.flowbox.add(final_widget)

    def _remove_select_qube(self, widget: Gtk.Widget):
        qube_to_remove = widget.get_name()
        self.select_qubes.remove(qube_to_remove)
        self._populate_flowbox(True)
        # TODO: re-do rules!!!!!

# # adding new keyqube should add a default rule?
# # add default_target?
# # can't save if no key qube selected
