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
import subprocess
from typing import Optional, List, Tuple, Union

from qrexec.policy.admin_client import PolicyClient
from qrexec.policy.parser import StringPolicy, Rule, Allow, Ask, Deny, \
    Source, Target
from qrexec.exc import PolicySyntaxError

from ..widgets.qubes_widgets_library import QubeName, VMListModeler, \
    TextModeler, TypeName, ImageTextButton, show_error
from .page_handler import PageHandler

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()


CHOICE_NAMES_ASK_IS_ALLOW = {
    'always': 'ask',
    'never': 'deny'
}

CHOICE_NAMES = {
    'always': 'allow',
    'ask': 'ask',
    'never': 'deny'
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


class RuleListBoxRow(Gtk.ListBoxRow):
    """Row in a listbox representing a policy rule"""
    def __init__(self,
                 rule: Rule,
                 qapp: qubesadmin.Qubes,
                 verb_description: str,
                 ask_is_allow: bool = False,
                 is_fundamental_rule: bool = False):
        """
        :param rule: Rule object to be represented
        :param qapp: Qubes object
        :param verb_description: description of what the rule does, to be used
        as Qube1 (will) NEVER/ALWAYS (verb_description) Qube2, for example
        "be allowed to paste into clipboard of"
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
        self.outer_box.pack_start(self.main_widget_box, False, False, 0)

        self.additional_widget_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL)

        save_button = ImageTextButton("qubes-ok", "ACCEPT",
                                      self.validate_and_save)
        save_button.get_style_context().add_class('button_save')
        save_button.get_style_context().add_class('flat_button')
        self.additional_widget_box.pack_end(save_button, False, False, 10)
        self.additional_widget_box.set_no_show_all(True)

        cancel_button = ImageTextButton(
            "qubes-delete", "CANCEL", self.revert)
        cancel_button.get_style_context().add_class('flat_button')
        cancel_button.get_style_context().add_class('button_cancel')
        self.additional_widget_box.pack_end(cancel_button, False, False, 10)

        self.outer_box.pack_start(self.additional_widget_box, False, False, 10)

        self.source_widget: Optional[Gtk.Widget] = None
        self.source_model: Optional[VMListModeler] = None
        self.action_widget: Optional[Gtk.Widget] = None
        self.action_model: Optional[TextModeler] = None
        self.target_widget: Optional[Gtk.Widget] = None
        self.target_model: Optional[VMListModeler] = None

        self.error_msg: Optional[str] = None
        self.editing: bool = False

        self.set_edit_mode(False)

    def _get_delete_button(self) -> Gtk.Button:
        """Get a delete button appropriate for the class."""
        delete_button: Gtk.Button = Gtk.Button()
        delete_icon = Gtk.Image()
        delete_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-delete' if not self.is_fundamental_rule
                else 'qubes-padlock', 14, 0))
        delete_button.add(delete_icon)
        delete_button.get_style_context().add_class('flat')
        if not self.is_fundamental_rule:
            delete_button.connect("clicked", self._delete_self)
        else:
            delete_button.set_sensitive(False)
        return delete_button

    def _parse_action(self) -> Union[Allow, Ask, Deny]:
        """Turn selected action to Action object."""
        assert self.action_model
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
        """Remove self from parent. Used to delete the rule."""
        parent_widget = self.get_parent()
        parent_widget.remove(self)

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

        # remove existing widgets
        for child in self.main_widget_box.get_children():
            self.main_widget_box.remove(child)

        action_function = self._get_action_selector if editing \
            else self._get_action_label

        if editing and not self.is_fundamental_rule:
            token_function = self._get_token_selector
        else:
            token_function = self._get_token_label

        self.source_widget, self.source_model = token_function(self.rule.source)
        self.source_widget.set_halign(Gtk.Align.START)

        label = Gtk.Label('will')
        label.set_halign(Gtk.Align.END)
        label.get_style_context().add_class('didascalia')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(self.source_widget, True, True, 0)
        box.pack_start(label, False, False, 0)
        self.main_widget_box.pack_start(box, False, True, 0)

        self.action_widget, self.action_model = action_function()
        self.action_widget.set_halign(Gtk.Align.START)
        if isinstance(self.rule.action, Ask):
            # I'm so sorry, but English is terrible
            description = "to " + self.verb_description
        else:
            description = self.verb_description
        label = Gtk.Label(description)
        label.set_halign(Gtk.Align.END)
        label.get_style_context().add_class('didascalia')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(self.action_widget, True, True, 0)
        box.pack_start(label, False, False, 0)
        self.main_widget_box.pack_start(box, False, True, 0)

        self.target_widget, self.target_model = token_function(self.rule.target)
        delete_button = self._get_delete_button()
        delete_button.set_halign(Gtk.Align.START)
        self.target_widget.set_halign(Gtk.Align.START)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(self.target_widget, True, True, 0)
        box.pack_start(delete_button, False, False, 0)
        self.main_widget_box.pack_start(box, False, True, 0)

        self.show_all()
        self.editing = editing

    def _get_token_label(self, token) -> \
            Tuple[Gtk.Widget, Optional[VMListModeler]]:
        """Make a pretty token widget, appropriately formatted for
        keywords/vms."""
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
            try:
                current_value = self.qapp.domains[token]
            except KeyError:
                # The VM was not found
                current_value = str(token)

        combobox = Gtk.ComboBox.new_with_entry()
        model = VMListModeler(combobox=combobox, qapp=self.qapp,
                              filter_function=lambda x: str(x) != 'dom0',
                              event_callback=None,
                              default_value=None, current_value=current_value,
                              style_changes=False, allow_none=False,
                              add_categories=True)
        return combobox, model

    def _get_action_label(self) -> Tuple[Gtk.Widget, Optional[TextModeler]]:
        choices = CHOICE_NAMES_ASK_IS_ALLOW if self.ask_is_allow \
            else CHOICE_NAMES
        name = type(self.rule.action).__name__.lower()
        for readable_name, action_name in choices.items():
            if action_name == type(self.rule.action).__name__.lower():
                name = readable_name
        label = Gtk.Label()
        label.set_markup(f'<b>{name}</b>')
        return label, None

    def _get_action_selector(self) -> Tuple[Gtk.Widget, Optional[TextModeler]]:
        if self.ask_is_allow:
            choices = CHOICE_NAMES_ASK_IS_ALLOW
        else:
            choices = CHOICE_NAMES

        combobox = Gtk.ComboBoxText()
        model = TextModeler(
            combobox,
            choices,
            selected_value=type(self.rule.action).__name__.lower())
        return combobox, model

    def __str__(self):  # pylint: disable=arguments-differ
        # base class has automatically generated params
        result = "From: "
        if self.source_model:
            result += str(self.source_model)
        else:
            result += str(self.rule.source)
        result += " to: "
        if self.target_model:
            result += str(self.target_model)
        else:
            result += str(self.rule.target)
        result += " Action: " + str(self._parse_action())
        return result

    def is_changed(self) -> bool:
        """Return True if rule was changed."""
        if not self.editing:
            return False
        if self.source_model:
            if str(self.source_model.get_selected()) != str(self.rule.source):
                return True
        if self.target_model:
            if str(self.target_model.get_selected()) != str(self.rule.target):
                return True
        new_action = self._parse_action()
        if str(new_action) != str(self.rule.action):
            return True
        return False

    def revert(self, *_args):
        """Revert all changes to the Rule."""
        if self.source_model and self.target_model:
            self.source_model.select_entry(str(self.rule.source))
            self.target_model.select_entry(str(self.rule.target))
        if self.action_model:
            self.action_model.select_value(
                type(self.rule.action).__name__.lower())
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

    def validate_and_save(self, *_args) -> bool:
        """Validate if the rule is not duplicate or conflicting with another
        rule, then save. If this fails, return False, else return True."""
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
                    break
                self.error_msg = "This rule conflicts with another rule"
                break

        if self.error_msg:
            show_error("Cannot save rule",
                       'The following errors occurred when trying to save '
                       f'this rule:\n{self.error_msg}\n')
            self.error_msg = None
            return False

        self.rule.source = new_source
        self.rule.target = new_target
        self.rule.action = new_action
        self.set_edit_mode(False)
        self.get_parent().invalidate_sort()

        self.get_parent().emit('rules-changed', None)
        return True


class PolicyHandler(PageHandler):
    """
    Handler for generic simple list of policy rules.
    """
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 prefix: str,
                 policy_manager: PolicyManager,
                 default_policy: str,
                 service_name: str,
                 policy_file_name: str,
                 verb_description: str,
                 ask_is_allow: bool):
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
        :param verb_description: description used in policy rows, as in
        Qube1 (will) NEVER (verb_description) Qube2
        :param ask_is_allow: should ask be treated the same as allow
        """

        self.qapp = qapp
        self.policy_manager = policy_manager
        self.default_policy = default_policy
        self.service_name = service_name
        self.policy_file_name = policy_file_name
        self.verb_description = verb_description
        self.ask_is_allow = ask_is_allow

        # load rules
        self.initial_rules, self.current_token = \
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, self.default_policy)

        # main widgets
        self.main_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_main_list')
        self.exception_list_box: Gtk.ListBox = \
            gtk_builder.get_object(f'{prefix}_exception_list')
        self.add_button: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_rule_button')

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
        self.raw_defaults: Gtk.Button = gtk_builder.get_object(
            f'{prefix}_raw_defaults')
        self.text_buffer: Gtk.TextBuffer = self.raw_text.get_buffer()

        # enable/disable custom policy
        self.enable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f'{prefix}_enable_radio')
        self.disable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f'{prefix}_disable_radio')

        # fill data
        self._load_rules(self.initial_rules)
        self._fill_raw_rules()

        # connect events
        self.exception_list_box.connect('row-activated', self._rule_clicked)
        self.main_list_box.connect('row-activated', self._rule_clicked)

        self.add_button.connect("clicked", self._add_new_rule)
        self.exception_list_box.set_sort_func(self._sorting_function)

        self.enable_radio.connect("toggled", self._custom_toggled)
        self.disable_radio.connect("toggled", self._custom_toggled)

        self.raw_event_box.connect(
            'button-release-event', self._show_hide_raw)
        self.main_list_box.connect('rules-changed', self._fill_raw_rules)
        self.exception_list_box.connect('rules-changed', self._fill_raw_rules)
        self.raw_save.connect("clicked", self._save_raw)
        self.raw_cancel.connect("clicked", self._cancel_raw)

        self.check_custom_rules(self.initial_rules)

        self.conflict_handler = ConflictFileHandler(
            gtk_builder, "clipboard", self.service_name,
            self.policy_file_name, self.policy_manager)

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
        self._set_custom_editable(self.enable_radio.get_active())
        self.main_list_box.emit('rules-changed', None)

    def _save_raw(self, _widget):
        try:
            rules = self.policy_manager.text_to_rules(
                self.text_buffer.get_text(
                    self.text_buffer.get_start_iter(),
                    self.text_buffer.get_end_iter(), False))
            self._load_rules(rules)
            self.check_custom_rules(rules)
            self._show_hide_raw()
        except PolicySyntaxError as ex:
            show_error("Policy error",
                       f"Cannot save policy.\n"
                       f"Encountered the following error(s):\n{ex}")
            return

    def _cancel_raw(self, _widget):
        self._fill_raw_rules()

    def _set_custom_editable(self, state):
        self.add_button.set_sensitive(state)
        self.main_list_box.set_sensitive(state)
        self.exception_list_box.set_sensitive(state)

    def _load_rules(self, rules: List[Rule]):
        for child in self.main_list_box.get_children():
            self.main_list_box.remove(child)
        for child in self.exception_list_box.get_children():
            self.exception_list_box.remove(child)

        for rule in rules:
            if rule.source == '@anyvm' and rule.target == '@anyvm':
                self.main_list_box.add(RuleListBoxRow
                                       (rule, self.qapp, self.verb_description,
                                        ask_is_allow=self.ask_is_allow,
                                        is_fundamental_rule=True))
                break
            fundamental = rule.source == '@adminvm' and rule.target == '@anyvm'
            self.exception_list_box.add(RuleListBoxRow(
                rule=rule, qapp=self.qapp,
                verb_description=self.verb_description,
                ask_is_allow=self.ask_is_allow,
                is_fundamental_rule=fundamental))

        if not self.main_list_box.get_children():
            deny_all_rule = self.policy_manager.new_rule(
                self.service_name, '@anyvm', '@anyvm', 'deny')
            self.main_list_box.add(
                RuleListBoxRow(
                    deny_all_rule, self.qapp,
                    self.verb_description,
                    ask_is_allow=self.ask_is_allow,
                    is_fundamental_rule=True))

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

    def _fill_raw_rules(self, *_args):
        self.text_buffer.set_text(self.policy_manager.rules_to_text(
            self.get_current_rules()))

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
        if not self.close_all_edits():
            return
        deny_all_rule = self.policy_manager.new_rule(
            self.service_name, '@anyvm', '@anyvm', 'deny')
        new_row = RuleListBoxRow(
            deny_all_rule, self.qapp, self.verb_description,
            ask_is_allow=self.ask_is_allow)
        self.exception_list_box.add(new_row)
        new_row.activate()

    def get_current_rules(self) -> List[Rule]:
        """Get the current set of rules, taking into account default and
        custom."""
        if self.disable_radio.get_active():
            rules = self.policy_manager.text_to_rules(self.default_policy)
        else:
            rules = [child.rule for child in
                     self.exception_list_box.get_children()]\
                    + [child.rule for child in
                       self.main_list_box.get_children()]
        return rules

    def _rule_clicked(self, _list_box, row: RuleListBoxRow, *_args):
        if row.editing:
            # if the current row was clicked, nothing should happen
            return
        if not self.close_all_edits():
            return
        row.set_edit_mode(True)

    def close_all_edits(self) -> bool:
        """Attempt to close all edited rows; if failed, return False, else
        return True"""
        for list_box in [self.main_list_box, self.exception_list_box]:
            for child in list_box.get_children():
                if child.editing:
                    if not child.is_changed():
                        child.set_edit_mode(False)
                        continue
                    dialog = Gtk.MessageDialog(
                        None,
                        Gtk.DialogFlags.MODAL,
                        Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
                    dialog.set_title("A rule is currently being edited")
                    dialog.set_markup(
                        "Do you want to save changes to the following "
                        f"rule?\n{str(child)}")
                    response = dialog.run()
                    if response == Gtk.ResponseType.YES:
                        if not child.validate_and_save():
                            return False
                    else:
                        child.revert()
                    dialog.destroy()
        return True

    def check_for_unsaved(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        if not self.close_all_edits():
            return False
        unsaved_found = False
        current_rules = self.get_current_rules()
        if len(self.initial_rules) != len(current_rules):
            unsaved_found = True
        for rule1, rule2 in zip(self.initial_rules, current_rules):
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

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""
        rules = self.get_current_rules()
        try:
            self.policy_manager.save_rules(self.policy_file_name,
                                           rules, self.current_token)
        except Exception as ex:
            show_error("Failed to save rules", f"Error {str(ex)}")
            return False
        self.initial_rules = rules
        return True

    def reset(self):
        self._load_rules(self.initial_rules)
        self._fill_raw_rules()
        self.check_custom_rules(self.initial_rules)


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
