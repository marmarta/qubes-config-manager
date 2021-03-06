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
from typing import Optional, Dict, Callable

from ..widgets.qubes_widgets_library import VMListModeler, TextModeler,\
    ImageTextButton, show_error, TokenName, BiDictionary, ask_question
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

LIMITED_CATEGORIES = {
    "@type:AppVM": "TYPE: APP",
    "@type:TemplateVM": "TYPE: TEMPLATES",
    "@type:DispVM": "TYPE: DISPOSABLE",
    "@adminvm": "TYPE: ADMINVM"
}

class VMWidget(Gtk.Box):
    """VM/category selection widget."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 categories: Optional[Dict[str, str]],
                 initial_value: str,
                 additional_text: Optional[str] = None,
                 additional_widget: Optional[Gtk.Widget] = None,
                 filter_function: Optional[Callable] = None):
        """
        :param qapp: Qubes object
        :param categories: list of additional categories available for this
        VM, in the form of token/api name: readable name
        :param initial_value: initial selected value as str
        :param additional_text: additional text to be added after
        selector widget
        :param additional_widget: additional widget to be packed after selector
        widget
        :param filter_function: function used to filter available vms
        """

        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.qapp = qapp
        self.selected_value = initial_value
        self.filter_function = filter_function if filter_function else \
            lambda x: str(x) != 'dom0'

        self.combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
        self.combobox.get_child().set_width_chars(24)
        self.model = VMListModeler(combobox=self.combobox,
                                   qapp=self.qapp,
                                   filter_function=self.filter_function,
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
        self.name_widget.get_style_context().add_class('action_text')
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
        self.name_widget.set_markup(f'{self.choices[new_value]}')
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
                 parent_handler: 'PolicyHandler',
                 rule: AbstractRuleWrapper,
                 qapp: qubesadmin.Qubes,
                 verb_description: AbstractVerbDescription,
                 enable_delete: bool = True,
                 enable_vm_edit: bool = True,
                 initial_verb: str = "will"):
        """
        :param parent_handler: PolicyHandler object this rule belongs to.
        :param rule: Rule object, wrapped in a helper object
        :param qapp: Qubes object
        :param verb_description: AbstractVerbDescription object
        :param enable_delete: can this rule be deleted
        :param enable_vm_edit: can source and target in this rule be edited
        :param initial_verb: verb between source_qube and action
        """
        super().__init__()

        self.qapp = qapp
        self.rule = rule
        self.enable_delete = enable_delete
        self.enable_vm_edit = enable_vm_edit
        self.verb_description = verb_description
        self.initial_verb = initial_verb
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

        self.source_widget = self.get_source_widget()
        self.target_widget = self.get_target_widget()
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

    def get_source_widget(self) -> VMWidget:
        """Widget to be used for source VM"""
        return VMWidget(
            self.qapp, SOURCE_CATEGORIES, self.rule.source,
            additional_text=self.initial_verb)

    def get_target_widget(self) -> VMWidget:
        """Widget to be used for target VM"""
        return VMWidget(
            self.qapp, TARGET_CATEGORIES, self.rule.target,
            additional_widget=self._get_delete_button())

    def _get_delete_button(self) -> Gtk.Button:
        """Get a delete button appropriate for the class."""
        if self.enable_delete:
            delete_button = ImageTextButton(icon_name='qubes-delete',
                                            label=None,
                                            click_function=self._delete_self,
                                            style_classes=["flat"])
        else:
            delete_button = ImageTextButton(icon_name='qubes-padlock',
                                            label=None,
                                            click_function=None,
                                            style_classes=["flat"])
        return delete_button

    def _delete_self(self, *_args):
        """Remove self from parent. Used to delete the rule."""
        response = ask_question(self.get_toplevel(), "Delete rule",
                                "Are you sure you want to delete this rule?")
        if response == Gtk.ResponseType.NO:
            return
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

        if self.enable_vm_edit:
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

class LimitedRuleListBoxRow(RuleListBoxRow):
    def __init__(self,
                 parent_handler,
                 rule: AbstractRuleWrapper,
                 qapp: qubesadmin.Qubes,
                 verb_description: AbstractVerbDescription,
                 enable_delete: bool = True,
                 enable_vm_edit: bool = True,
                 initial_verb: str = "will",
                 filter_function: Optional[Callable] = None):
        self.filter_function = filter_function
        super().__init__(parent_handler, rule, qapp, verb_description,
                         enable_delete, enable_vm_edit, initial_verb)

    def get_source_widget(self) -> VMWidget:
        """Widget to be used for source VM"""
        return VMWidget(
            self.qapp, LIMITED_CATEGORIES, self.rule.source,
            additional_text=self.initial_verb)

    def get_target_widget(self) -> VMWidget:
        """Widget to be used for target VM"""
        return VMWidget(
            self.qapp, None, self.rule.target,
            additional_widget=self._get_delete_button(),
            filter_function=self.filter_function)


