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
from copy import deepcopy
from typing import Optional, List, Type, Set

from qrexec.policy.parser import Rule
from qrexec.exc import PolicySyntaxError

from ..widgets.qubes_widgets_library import VMListModeler, show_error, \
    ask_question
from .page_handler import PageHandler
from .policy_rules import AbstractRuleWrapper, AbstractVerbDescription
from .policy_manager import PolicyManager
from .rule_list_widgets import RuleListBoxRow, LimitedRuleListBoxRow

import gi

import qubesadmin
import qubesadmin.vm

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()


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
                                        enable_delete=False,
                                        enable_vm_edit=False))
                continue
            fundamental = not (rule.source == '@adminvm' and rule.target == '@anyvm')
            self.exception_list_box.add(RuleListBoxRow(self,
                rule=wrapped_rule, qapp=self.qapp,
                verb_description=self.verb_description,
                enable_delete=fundamental, enable_vm_edit=fundamental))

        if not self.main_list_box.get_children():
            deny_all_rule = self.policy_manager.new_rule(
                self.service_name, '@anyvm', '@anyvm', 'deny')
            self.main_list_box.add(
                RuleListBoxRow(self,
                    self.rule_class(deny_all_rule), self.qapp,
                    self.verb_description,
                    enable_delete=False, enable_vm_edit=False))

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
        self._show_hide_raw()

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
                        new_action: str) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        for other_row in self.current_rows:
            if other_row == row:
                continue
            if other_row.rule.is_rule_conflicting(new_source, new_target,
                                                  new_action):
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
                response = ask_question(row.get_toplevel(),
                    "A rule is currently being edited",
                    "Do you want to save changes to the following "
                    f"rule?\n{str(row)}")
                if response == Gtk.ResponseType.YES:
                    if not row.validate_and_save():
                        return False
                else:
                    row.revert()
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
            response = ask_question(self.main_list_box.get_toplevel(),
                "Save changes",
                "Do you want to save changes to current policy rules?")
            if response == Gtk.ResponseType.YES:
                return self.save()
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
        self.add_select_box: Gtk.Box = gtk_builder.get_object(
            f'{prefix}_add_select_box')
        self.add_select_button: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_add_select_button')
        self.add_select_confirm: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_add_select_confirm')
        self.add_select_cancel: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_add_select_cancel')
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
        self.add_select_button.connect('clicked', self._add_select_qube)
        self.add_select_confirm.connect('clicked', self._add_select_confirm)
        self.add_select_cancel.connect('clicked', self._add_select_cancel)

        self.main_list_box.connect('rules-changed', self._select_qubes_changed)
        self._select_qubes_changed()

    def _select_qubes_changed(self, *_args):
        self.select_qubes = {row.rule.target for row in
                        self.main_list_box.get_children()}
        self.populate_rule_lists(self.current_rules)

    def _add_main_rule(self, rule):
        self.main_list_box.add(RuleListBoxRow(
            parent_handler=self,
            rule=self.main_rule_class(rule),
            qapp=self.qapp,
            verb_description=self.main_verb_description,
            enable_delete=True,
            enable_vm_edit=False, initial_verb=""))

    def _add_exception_rule(self, rule):
        row = LimitedRuleListBoxRow(
            parent_handler=self,
            rule=self.exception_rule_class(rule),
            qapp=self.qapp,
            verb_description=self.exception_verb_description,
            filter_function=lambda x: str(x) in self.select_qubes
        )
        self.exception_list_box.add(row)
        return row

    @staticmethod
    def _has_partial_duplicate(rule: Rule, rules: List[Rule]) -> bool:
        # do not add a rule if it has target other than default and
        # there exists a rule with @default and that target as target
        # or default target
        for other_rule in rules:
            if other_rule.source == rule.source and \
                    other_rule.target == '@default' and (
                    getattr(other_rule.action, "target", None) == rule.target
                    or getattr(other_rule.action, "default_target", None) ==
                    rule.target):
                return True
        return False

    def populate_rule_lists(self, rules: List[Rule]):
        for child in self.main_list_box.get_children() + \
                     self.exception_list_box.get_children():
            child.get_parent().remove(child)
        # rules with source = '@anyvm' go to main list and their
        # qubes are key qubes
        for rule in rules:
            if rule.target != 'default':
                if self._has_partial_duplicate(rule, rules):
                    continue
            if rule.source == '@anyvm':
                if rule.target.type == 'keyword':
                    # we do not support this
                    continue
                self._add_main_rule(rule)
            else:
                self._add_exception_rule(rule)
        self.add_button.set_sensitive(bool(self.main_list_box.get_children()))

    def set_custom_editable(self, state: bool):
        super().set_custom_editable(state)
        self.add_select_button.set_sensitive(state)

    def _add_select_qube(self, *_args):
        self.add_select_box.set_visible(True)

    def _add_select_confirm(self, *_args):
        new_qube = self.select_qube_model.get_selected()
        if new_qube.is_networked():
            response = ask_question(
                self.main_list_box.get_toplevel(),
                "Add new key qube",
                f"Are you sure you want to add {new_qube} as a key qube? It "
                f"has network access, which may lead to decreased security.")
            if response == Gtk.ResponseType.NO:
                self._add_select_cancel()
                return
        new_qube = str(self.select_qube_model.get_selected())
        new_rule = self.policy_manager.new_rule(
            self.service_name, '@anyvm', new_qube, 'ask')
        self._add_main_rule(new_rule)
        self.add_select_box.set_visible(False)
        self.main_list_box.emit('rules-changed', None)

    def _add_select_cancel(self, *_args):
        self.add_select_box.set_visible(False)

    def add_new_rule(self, *_args):
        """Add a new rule."""
        if not self.close_all_edits():
            return
        for qube in self.select_qubes:
            rule = self.policy_manager.new_rule(
                self.service_name, str(qube), str(qube), 'deny')
            new_row = self._add_exception_rule(rule)
            new_row.activate()
            break

    def close_all_edits(self) -> bool:
        """Attempt to close all edited rows; if failed, return False, else
        return True"""
        if not super().close_all_edits():
            return False
        if self.add_select_box.get_visible():
            self._add_select_cancel()
        return True

    @property
    def current_rules(self) -> List[Rule]:
        """
        Due to possible existing manual rules, every rule with @default
        is saved as two rules: a normal one and a one with target/default_target
        put in the default space"""
        rules = []
        for row in self.exception_list_box.get_children():
            new_rule: Rule = row.rule.raw_rule
            if str(new_rule) in [str(rule) for rule in rules]:
                # do not save duplicates
                continue
            rules.append(new_rule)

            if new_rule.target == '@default':
                if getattr(new_rule.action, "default_target", None):
                    new_target = new_rule.action.default_target
                elif getattr(new_rule.action, "target", None):
                    new_target = new_rule.action.target
                else:
                    continue
                another_rule = self.policy_manager.new_rule(
                    self.service_name, new_rule.source, new_target,
                    type(new_rule.action).__name__.lower())
                if str(another_rule) in [str(rule) for rule in rules]:
                    # do not save duplicates
                    continue
                rules.append(another_rule)
        rules.extend([row.rule.raw_rule for row in
                      self.main_list_box.get_children()])
        return rules
