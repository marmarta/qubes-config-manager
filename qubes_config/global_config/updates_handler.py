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
RPC Policy-related functionality.
"""
import os
import subprocess
from typing import Optional, List, Dict

from qrexec.policy.parser import Rule

from ..widgets.qubes_widgets_library import VMListModeler, show_error, \
    ask_question, NONE_CATEGORY, QubeName
from .page_handler import PageHandler
from .policy_rules import RuleTargeted, SimpleVerbDescription
from .policy_manager import PolicyManager
from .rule_list_widgets import NoActionListBoxRow
from .policy_handler import ConflictFileHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()


def get_feature(vm, feature_name, default_value):
    """Get feature, with a working default_value."""
    try:
        return vm.features.get(feature_name, default_value)
    except qubesadmin.exc.QubesDaemonAccessError:
        return default_value

def get_boolean_feature(vm, feature_name, default):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    else:
        result = default
    return result


class RepoHandler:
    """Handler for repository settings."""
    def __init__(self, gtk_builder: Gtk.Builder):
        self.dom0_stable_radio: Gtk.RadioButton = \
            gtk_builder.get_object('updates_dom0_stable_radio')
        self.dom0_testing_sec_radio: Gtk.RadioButton = \
            gtk_builder.get_object('updates_dom0_testing_sec_radio')
        self.dom0_testing_radio: Gtk.RadioButton = \
            gtk_builder.get_object('updates_dom0_testing_radio')

        self.template_official: Gtk.CheckButton = \
            gtk_builder.get_object('updates_template_official')
        self.template_official_testing: Gtk.CheckButton = \
            gtk_builder.get_object('updates_template_official_testing')
        self.template_community: Gtk.CheckButton = \
            gtk_builder.get_object('updates_template_community')
        self.template_community_testing: Gtk.CheckButton = \
            gtk_builder.get_object('updates_template_community_testing')

        self.problems_repo_box: Gtk.Box = \
            gtk_builder.get_object('updates_problem_repo')

        # the code below relies on dicts in Python 3.6+ keeping the
        # order of items
        self.repo_to_widget_mapping = [{
            'qubes-dom0-current-testing': self.dom0_testing_radio,
            'qubes-dom0-security-testing': self.dom0_testing_sec_radio,
            'qubes-dom0-current': self.dom0_stable_radio,
            },
            {'qubes-templates-itl-testing': self.template_official_testing,
            'qubes-templates-itl': self.template_official},
            {'qubes-templates-community-testing':
                self.template_community_testing,
             'qubes-templates-community': self.template_community,
            }]

        self.template_community.connect('toggled', self._community_toggled)

        self.repos: Dict[str, Dict] = dict()
        self._load_data()

        self._load_state()
        self._community_toggled()

    def _community_toggled(self, _widget=None):
        if not self.template_community.get_active():
            self.template_community_testing.set_active(False)
            self.template_community_testing.set_sensitive(False)
        else:
            self.template_community_testing.set_sensitive(True)

    def _load_data(self):
        try:
            for row in self._run_qrexec_repo('qubes.repos.List').split('\n'):
                lst = row.split('\0')
                repo_name = lst[0]
                self.repos[repo_name] = dict()
                self.repos[repo_name]['prettyname'] = lst[1]
                self.repos[repo_name]['enabled'] = (lst[2] == 'enabled')
        except qubesadmin.exc.QubesException as ex:
            show_error("Error loading repository data",
                       f"An error has occurred: {ex}")
            # disable all repo-related stuff
            self.dom0_stable_radio.set_sensitive(False)
            self.dom0_testing_sec_radio.set_sensitive(False)
            self.dom0_testing_radio.set_sensitive(False)
            self.template_official_testing.set_sensitive(False)
            self.template_community.set_sensitive(False)
            self.template_community_testing.set_sensitive(False)
            self.repos = {}
            self.problems_repo_box.set_visible(True)

    def _load_state(self):
        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                if self.repos[repo]['enabled']:
                    widget.set_active(self.repos[repo]['enabled'])
                    break

    @staticmethod
    def _run_qrexec_repo(service, arg=''):
        # Set default locale to C in order to prevent error msg
        # in subprocess call related to falling back to C locale
        env = os.environ.copy()
        env['LC_ALL'] = 'C'
        # Fake up a "qrexec call" to dom0 because dom0 can't qrexec to itself
        cmd = '/etc/qubes-rpc/' + service
        process = subprocess.run(['sudo', cmd, arg],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=False, env=env)
        if process.stderr:
            raise qubesadmin.exc.QubesException(
                'qrexec call stderr was not empty',
                {'stderr': process.stderr.decode('utf-8')})
        if process.returncode != 0:
            raise qubesadmin.exc.QubesException(
                'qrexec call exited with non-zero return code',
                {'returncode': process.returncode})
        return process.stdout.decode('utf-8')

    def _set_repository(self, repository, state):
        action = 'Enable' if state else 'Disable'
        try:
            result = self._run_qrexec_repo(f'qubes.repos.{action}', repository)
            if result != 'ok\n':
                raise RuntimeError('qrexec call stdout did not contain "ok"'
                            ' as expected',{'stdout': result})
        except RuntimeError as ex:
            msg = '{desc}; {args}'.format(desc=ex.args[0], args=', '.join(
                # This is kind of hard to mentally parse but really all
                # it does is pretty-print args[1], which is a dictionary
                ['{key}: {val}'.format(key=i[0], val=i[1]) for i in
                 ex.args[1].items()]
            ))
            raise RuntimeError(msg) from ex

    def is_changed(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        if not self.repos:
            return False

        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                if self.repos[repo]['enabled'] != widget.get_active():
                    return True
                if widget.get_active() and self.repos[repo]['enabled'] == \
                        widget.get_active():
                    break

        return False

    def save_changes(self):
        """Save all changes."""
        for repo_dict in self.repo_to_widget_mapping:
            found = False
            for repo, widget in repo_dict.items():
                try:
                    if widget.get_active() or found:
                        found = True
                        self._set_repository(repo, True)
                    else:
                        self._set_repository(repo, False)
                except RuntimeError as ex:
                    show_error('Failed to set repository data',
                               f"An error has occurred: {ex}")
        self._load_data()
        self._load_state()

    def reset_changes(self):
        """Reset any user changes."""
        self._load_state()


class VMFlowBoxButton(Gtk.FlowBoxChild):
    """Simple button  representing a VM that can be deleted."""
    def __init__(self, vm: qubesadmin.vm.QubesVM):
        super().__init__()
        self.vm = vm

        token_widget = QubeName(vm)
        button = Gtk.Button()
        button.get_style_context().add_class('flat')

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(token_widget, False, False, 0)
        remove_icon = Gtk.Image()
        remove_icon.set_from_pixbuf(
            Gtk.IconTheme.get_default().load_icon(
                'qubes-delete', 14, 0))
        box.pack_start(remove_icon, False, False, 10)

        button.add(box)
        button.connect('clicked', self._remove_self)
        self.add(button)
        self.show_all()


    def _remove_self(self, _widget):
        response = ask_question(
            self.get_toplevel(), "Delete",
            "Are you sure you want to remove this exception?")
        if response == Gtk.ResponseType.NO:
            return
        self.get_parent().remove(self)


class UpdateCheckerHandler:
    """Handler for checking for updates settings."""
    FEATURE_NAME = 'service.qubes-update-check'

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        self.qapp = qapp

        # check for updates dom0 checkbutton
        self.dom0_update_check: Gtk.CheckButton = \
            gtk_builder.get_object('updates_dom0_update_check')

        self.enable_radio: Gtk.RadioButton = \
            gtk_builder.get_object('updates_enable_radio')
        self.disable_radio: Gtk.RadioButton = \
            gtk_builder.get_object('updates_disable_radio')

        # check for if there are exceptions for check upd
        self.exceptions_check: Gtk.CheckButton = \
            gtk_builder.get_object('updates_exceptions_check')

        self.exceptions_flowbox: Gtk.FlowBox = \
            gtk_builder.get_object('updates_exceptions_flowbox')
        self.add_exception_box: Gtk.Box = \
            gtk_builder.get_object('updates_add_exception_box')
        # combo for add qube to exception
        self.exception_qube_combo: Gtk.ComboBox = \
            gtk_builder.get_object('updates_exception_qube_combo')

        self.add_exception_cancel: Gtk.Button = \
            gtk_builder.get_object('updates_add_exception_cancel')
        self.add_exception_confirm: Gtk.Button = \
            gtk_builder.get_object('updates_add_exception_confirm')
        self.add_exception_button: Gtk.Button = \
            gtk_builder.get_object('updates_add_exception_button')

        self.exception_label: Gtk.Label = \
            gtk_builder.get_object('updates_check_exception_label')

        self.initial_dom0 = get_boolean_feature(self.qapp.domains['dom0'],
                                 self.FEATURE_NAME, True)
        self.dom0_update_check.set_active(self.initial_dom0)

        self.initial_default = get_boolean_feature(
            self.qapp.domains['dom0'],
            'config.default.qubes-update-check', True)
        if self.initial_default:
            self.enable_radio.set_active(True)
        else:
            self.disable_radio.set_active(True)
        self._set_label()
        self.enable_radio.connect('toggled', self._set_label)
        self.disable_radio.connect('toggled', self._set_label)

        self.initial_exceptions: List[qubesadmin.vm.QubesVM] = []
        self._initialize_flowbox()
        self._enable_exceptions_clicked()
        self.add_exception_model = VMListModeler(
            combobox=self.exception_qube_combo,
            qapp=self.qapp,
            filter_function=(lambda vm: vm.klass != 'AdminVM'))

        self.exceptions_check.connect("toggled",
                                      self._enable_exceptions_clicked)
        self.add_exception_button.connect('clicked',
                                          self._add_exception_button_clicked)
        self.add_exception_cancel.connect('clicked',
                                          self._add_exception_cancel_clicked)
        self.add_exception_confirm.connect('clicked',
                                          self._add_exception_confirm_clicked)

    def _set_label(self, *_args):
        if self.enable_radio.get_active():
            self.exception_label.set_markup(
                'Except the following qubes, for which checking for updates'
                ' will be <b>disabled</b>')
        else:
            self.exception_label.set_markup(
                'Except the following qubes, for which checking for updates'
                ' will be <b>enabled</b>')

    def _add_exception_button_clicked(self, _widget):
        self.add_exception_box.set_visible(True)

    def _add_exception_cancel_clicked(self, _widget):
        self.add_exception_box.set_visible(False)

    def _add_exception_confirm_clicked(self, _widget):
        select_vm = self.add_exception_model.get_selected()
        if select_vm in self.get_current_exceptions():
            show_error("Cannot add exception", "This exception already exists.")
            return
        self.exceptions_flowbox.add(VMFlowBoxButton(select_vm))
        self.add_exception_box.set_visible(False)

    def _initialize_flowbox(self):
        exceptions = []
        for vm in self.qapp.domains:
            if vm.klass == 'AdminVM':
                continue
            if get_boolean_feature(vm, self.FEATURE_NAME, True) != \
                    self.initial_default:
                exceptions.append(vm)

        self.initial_exceptions = exceptions

        self.exceptions_check.set_active(bool(exceptions))

        for vm in exceptions:
            self.exceptions_flowbox.add(VMFlowBoxButton(vm))

        self.exceptions_flowbox.show_all()

    def _enable_exceptions_clicked(self, _widget=None):
        self.exceptions_flowbox.set_visible(self.exceptions_check.get_active())
        self.add_exception_button.set_visible(
            self.exceptions_check.get_active())

    def get_current_exceptions(self) -> List[qubesadmin.vm.QubesVM]:
        """Get current list of exception vms"""
        exceptions: List[qubesadmin.vm.QubesVM] = []
        if not self.exceptions_check.get_active():
            return exceptions
        for child in self.exceptions_flowbox.get_children():
            exceptions.append(child.vm)
        return exceptions

    def is_changed(self) -> bool:
        """Did the user change anything from the initial settings?"""
        if self.initial_dom0 != self.dom0_update_check.get_active():
            return True
        if self.initial_default != self.enable_radio.get_active():
            return True
        exceptions = sorted(self.get_current_exceptions())
        if exceptions != sorted(self.initial_exceptions):
            return True

        return False

    def save_changes(self):
        """Save any changes."""
        # FUTURE: this is fairly slow
        if self.initial_dom0 != self.dom0_update_check.get_active():
            self.qapp.domains['dom0'].features[self.FEATURE_NAME] = \
                self.dom0_update_check.get_active()
            self.initial_dom0 = self.dom0_update_check.get_active()

        default_state = self.enable_radio.get_active()
        changed_default = False

        if self.initial_default != default_state:
            self.qapp.domains['dom0'].features[
                'config.default.qubes-update-check'] = default_state
            changed_default = True

        exceptions = self.get_current_exceptions()
        if changed_default or sorted(exceptions) != \
                sorted(self.initial_exceptions):
            for vm in self.qapp.domains:
                if vm.klass == 'dom0':
                    continue
                vm_state = default_state if vm not in exceptions else \
                    not default_state
                vm.features[self.FEATURE_NAME] = vm_state

        self.initial_exceptions = exceptions

    def reset_changes(self):
        """Reset changes and go back to initial state."""
        self.dom0_update_check.set_active(self.initial_dom0)
        self.enable_radio.set_active(self.initial_default)
        self._initialize_flowbox()


class UpdateProxy:
    """Handler for the rules connected to UpdateProxy policy."""
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager, policy_file_name: str,
                 service_name: str):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_file_name = policy_file_name
        self.service_name = service_name

        # TODO: how to check if has whonix?
        self.has_whonix = True

        self.default_updatevm = self.qapp.domains['sys-net']
        self.default_whonix_updatevm = self.qapp.domains.get('sys-whonix', None)

        self.first_eligible_vm = None
        for vm in self.qapp.domains:
            if vm.klass != 'AdminVM' and not vm.is_networked():
                self.first_eligible_vm = vm
                break

        self.def_updatevm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('updates_def_updatevm_combo')
        self.whonix_updatevm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('updates_whonix_updatevm_combo')
        self.whonix_updatevm_box: Gtk.Box = \
            gtk_builder.get_object('updates_whonix_updatevm_box')

        self.updatevm_exception_list: Gtk.ListBox = \
            gtk_builder.get_object('updates_updatevm_exception_list')
        self.add_updatevm_rule_button: Gtk.Button = \
            gtk_builder.get_object('updates_add_updatevm_rule_button')

        self.problem_box: Gtk.Box = \
            gtk_builder.get_object('updates_problem_policy')

        self.rules, self.current_token = \
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, "")

        self.updatevm_model = VMListModeler(
            combobox=self.def_updatevm_combo, qapp=self.qapp,
            filter_function=self._updatevm_filter,
            current_value=None)
        self.whonix_updatevm_model = VMListModeler(
            combobox=self.whonix_updatevm_combo, qapp=self.qapp,
            filter_function=self._updatevm_filter,
            current_value=None)
        self.load_rules()

        # connect events
        self.updatevm_exception_list.connect('row-activated',
                                             self._rule_clicked)
        self.add_updatevm_rule_button.connect("clicked", self.add_new_rule)

        self.whonix_updatevm_box.set_visible(self.has_whonix)

    @staticmethod
    def _updatevm_filter(vm):
        return getattr(vm, 'provides_network', False)

    @staticmethod
    def _needs_updatevm_filter(vm):
        if vm.klass == 'AdminVM' or vm.klass == 'AppVM':
            # TODO: what about standalone disposables????????
            return False
        return not vm.is_networked()

    def load_rules(self):
        """Load rules into widgets."""
        def_updatevm = self.default_updatevm
        def_whonix_updatevm = None
        if self.has_whonix:
            def_whonix_updatevm = self.default_whonix_updatevm

        remaining_rules = []

        for rule in reversed(self.rules):
            if rule.source == '@type:TemplateVM':
                def_updatevm = rule.action.target
            elif rule.source == '@tag:whonix-updatevm':
                def_whonix_updatevm = rule.action.target
            else:
                remaining_rules.append(rule)

        self.updatevm_model.select_entry(str(def_updatevm))
        self.updatevm_model.update_initial()

        if self.has_whonix:
            self.whonix_updatevm_model.select_entry(str(def_whonix_updatevm))
            self.whonix_updatevm_model.update_initial()

        for child in self.updatevm_exception_list.get_children():
            self.updatevm_exception_list.remove(child)

        for rule in reversed(remaining_rules):
            self.updatevm_exception_list.add(self._get_row(rule))

    def _get_row(self, rule: Rule):
        return NoActionListBoxRow(
            parent_handler=self,
            rule=RuleTargeted(rule),
            qapp=self.qapp,
            verb_description=SimpleVerbDescription({}),
            initial_verb="uses",
            filter_target=self._updatevm_filter,
            filter_source=self._needs_updatevm_filter)

    def add_new_rule(self, *_args):
        """Add a new rule."""
        if not self.close_all_edits():
            return
        new_rule = self.policy_manager.new_rule(
            self.service_name, str(self.first_eligible_vm), '@default',
            f'allow target={self.default_updatevm}')
        new_row = self._get_row(new_rule)
        self.updatevm_exception_list.add(new_row)
        new_row.activate()

    def _rule_clicked(self, _list_box, row: NoActionListBoxRow, *_args):
        if row.editing:
            # if the current row was clicked, nothing should happen
            return
        if not self.close_all_edits():
            return
        row.set_edit_mode(True)

    def close_all_edits(self) -> bool:
        """Attempt to close all edited rows; if failed, return False, else
        return True"""
        for row in self.updatevm_exception_list.get_children():
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

    def verify_new_rule(self, row: NoActionListBoxRow,
                        new_source: str, new_target: str,
                        new_action: str) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        for other_row in self.updatevm_exception_list.get_children():
            if other_row == row:
                continue
            if other_row.rule.is_rule_conflicting(new_source, new_target,
                                                  new_action):
                return str(other_row)
        if new_source == new_target:
            return 'Target cannot be the same as source'
        return None

    @property
    def current_exception_rules(self):
        """Current rules from the Exception list."""
        rules = []
        for row in self.updatevm_exception_list.get_children():
            rules.append(row.rule.raw_rule)
        return rules

    def is_changed(self) -> bool:
        """Check if state has changed."""
        if self.updatevm_model.is_changed():
            return True
        if self.whonix_updatevm_model.is_changed():
            return True
        if self.current_exception_rules != self.rules[:-2]:
            return True

        return False

    def reset(self):
        """Reset to initial state."""
        self.load_rules()

    def save_changes(self):
        """Save currently chosen settings."""
        rules = self.current_exception_rules

        if rules or self.whonix_updatevm_model.is_changed():
            rules.append(
                self.policy_manager.new_rule(self.service_name,
                    "@tag:whonix-updatevm", "@default",
                    f"allow "
                    f"target={self.whonix_updatevm_model.get_selected()}"))
        if rules or self.updatevm_model.is_changed():
            rules.append(
                self.policy_manager.new_rule(self.service_name,
                    "@type:TemplateVM", "@default",
                    f"allow target={self.updatevm_model.get_selected()}"))

        if rules:
            self.policy_manager.save_rules(self.policy_file_name,
                                           rules, self.current_token)


class UpdatesHandler(PageHandler):
    """Handler for all the disparate Updates functions."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager,
                 gtk_builder: Gtk.Builder
 ):
        """
        :param qapp: Qubes object
        :param policy_manager: PolicyManager object
        """

        self.qapp = qapp
        self.policy_manager = policy_manager
        self.service_name = 'qubes.UpdatesProxy'
        self.policy_file_name = '50-updates-config'

        self.dom0_updatevm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('updates_dom0_updatevm_combo')


        self.dom0_updatevm_model = VMListModeler(
            combobox=self.dom0_updatevm_combo,
            qapp=self.qapp,
            filter_function=(
                lambda vm: vm.klass != 'TemplateVM' and vm.klass != 'AdminVM'
                           and vm.is_networked()),
            current_value=self.qapp.updatevm,
            additional_options=NONE_CATEGORY,
            style_changes=True
        )

        # repo handler
        self.repo_handler = RepoHandler(gtk_builder=gtk_builder)
        self.update_checker = UpdateCheckerHandler(gtk_builder=gtk_builder,
                                                   qapp=self.qapp)
        self.update_proxy = UpdateProxy(gtk_builder=gtk_builder, qapp=self.qapp,
                                        policy_manager=policy_manager,
                                        policy_file_name=self.policy_file_name,
                                        service_name=self.service_name)

        self.conflict_handler = ConflictFileHandler(
            gtk_builder, "updates", self.service_name,
            self.policy_file_name, self.policy_manager)


    def close_all_edits(self) -> bool:
        """Attempt to close all edited rows; if failed, return False, else
        return True"""
        return self.update_proxy.close_all_edits()

    def _has_unsaved_changes(self) -> bool:
        if self.repo_handler.is_changed():
            return True
        if self.dom0_updatevm_model.is_changed():
            return True
        if self.update_checker.is_changed():
            return True
        if self.update_proxy.is_changed():
            return True
        return False


    def check_for_unsaved(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        if not self.close_all_edits():
            return False
        if self._has_unsaved_changes():
            # the silly widget invoked here is invoked because we need
            # _something_ to get the toplevel window
            response = ask_question(
                self.dom0_updatevm_combo.get_toplevel(),
                "Unsaved changes found",
                "There are unsaved changes. Do you want to save them?",
                Gtk.ButtonsType.YES_NO)
            if response == Gtk.ResponseType.YES:
                self.save()
            else:
                self.reset()
        return True

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""

        self.repo_handler.reset_changes()

        self.dom0_updatevm_model.select_entry(
            self.dom0_updatevm_model.initial_value)

        self.update_checker.reset_changes()

        self.update_proxy.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""

        for handler in [self.repo_handler, self.update_checker, self.update_proxy]:
            try:
                handler.save_changes()
            except Exception as ex:
                show_error("Failed to save changes",
                           f"Failed to save some changes: {ex}")

        if self.dom0_updatevm_model.is_changed():
            try:
                self.qapp.updatevm = self.dom0_updatevm_model.get_selected()
            except Exception as ex:
                show_error("Failed to save changes",
                           f"Failed to save dom0 update proxy: {ex}")

# Filtering for dropdowns:
# qubes-update-proxy service? or set it up when adding as proxy??
