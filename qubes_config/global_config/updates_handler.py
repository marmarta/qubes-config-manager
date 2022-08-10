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
Updates page handler
"""
import os
import subprocess
from typing import Optional, List, Dict

from qrexec.policy.parser import Rule

from ..widgets.gtk_widgets import VMListModeler, NONE_CATEGORY
from ..widgets.gtk_utils import show_error, ask_question
from ..widgets.utils import get_boolean_feature, apply_feature_change
from .page_handler import PageHandler
from .policy_rules import RuleTargeted, SimpleVerbDescription
from .policy_manager import PolicyManager
from .rule_list_widgets import NoActionListBoxRow
from .conflict_handler import ConflictFileHandler
from .vm_flowbox import VMFlowboxHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


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
        self.initial_state: Dict[str, bool] = {}

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

        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                self.initial_state[repo] = widget.get_active()

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

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if not self.repos:
            return ""

        dom0_changed = False
        itl_changed = False
        community_changed = False

        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                if self.initial_state[repo] != widget.get_active():
                    if 'dom0' in repo:
                        dom0_changed = True
                    elif 'community' in repo:
                        community_changed = True
                    elif 'itl' in repo:
                        itl_changed = True
        unsaved = []
        if dom0_changed:
            unsaved.append("dom0 update source changed")
        if itl_changed:
            unsaved.append("Official template update source changed")
        if community_changed:
            unsaved.append("Community template update source changed")

        return "\n".join(unsaved)

    def save(self):
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
                    raise qubesadmin.exc.QubesException(
                        f'Failed to set repository data: {ex}') from ex
        self._load_data()
        self._load_state()

    def reset(self):
        """Reset any user changes."""
        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                widget.set_active(self.initial_state[repo])


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

        for vm in self.qapp.domains:
            if vm.klass == 'AdminVM':
                continue
            if get_boolean_feature(vm, self.FEATURE_NAME, True) != \
                    self.initial_default:
                self.initial_exceptions.append(vm)

        self.exceptions_check.set_active(bool(self.initial_exceptions))

        self.flowbox_handler = VMFlowboxHandler(
            gtk_builder, qapp, "updates_exception",
            initial_vms=self.initial_exceptions,
            filter_function=(lambda vm: vm.klass != 'AdminVM'))

        self._enable_exceptions_clicked()

        self.exceptions_check.connect("toggled",
                                      self._enable_exceptions_clicked)

    def _set_label(self, *_args):
        if self.enable_radio.get_active():
            self.exception_label.set_markup(
                'Except the following qubes, for which checking for updates'
                ' will be <b>disabled</b>')
        else:
            self.exception_label.set_markup(
                'Except the following qubes, for which checking for updates'
                ' will be <b>enabled</b>')
        self.exceptions_check.set_active(False)

    def _enable_exceptions_clicked(self, _widget=None):
        self.flowbox_handler.set_visible(self.exceptions_check.get_active())

    def is_changed(self) -> bool:
        """Did the user change anything from the initial settings?"""
        if self.initial_dom0 != self.dom0_update_check.get_active():
            return True
        if self.initial_default != self.enable_radio.get_active():
            return True
        return self.flowbox_handler.is_changed()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = []
        if self.initial_dom0 != self.dom0_update_check.get_active():
            unsaved.append('dom0 "check for updates" setting')
        if self.initial_default != self.enable_radio.get_active():
            unsaved.append('Default "check for updates" setting')
        if self.exceptions_check.get_active() != \
                bool(self.initial_exceptions) or \
                self.flowbox_handler.is_changed():
            unsaved.append("Qubes selected for unusual 'check for updates'"
                           " behaviors")
        return "\n".join(unsaved)

    def save(self):
        """Save any changes."""
        # FUTURE: this is fairly slow
        if self.initial_dom0 != self.dom0_update_check.get_active():
            apply_feature_change(self.qapp.domains['dom0'],
                                 self.FEATURE_NAME,
                                 self.dom0_update_check.get_active())
            self.initial_dom0 = self.dom0_update_check.get_active()

        default_state = self.enable_radio.get_active()
        changed_default = False

        if self.initial_default != default_state:
            apply_feature_change(
                self.qapp.domains['dom0'], 'config.default.qubes-update-check',
                default_state)
            changed_default = True

        exceptions = self.flowbox_handler.selected_vms
        if changed_default or self.flowbox_handler.is_changed():
            for vm in self.qapp.domains:
                if vm.klass == 'dom0':
                    continue
                vm_state = default_state if vm not in exceptions else \
                    not default_state
                apply_feature_change(vm, self.FEATURE_NAME, vm_state)
        self.flowbox_handler.save()

    def reset(self):
        """Reset changes and go back to initial state."""
        self.dom0_update_check.set_active(self.initial_dom0)
        self.enable_radio.set_active(self.initial_default)
        self.exceptions_check.set_active(bool(self.initial_exceptions))
        self.flowbox_handler.reset()


class UpdateProxy:
    """Handler for the rules connected to UpdateProxy policy."""
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager, policy_file_name: str,
                 service_name: str):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_file_name = policy_file_name
        self.service_name = service_name

        self.has_whonix = self._check_for_whonix()

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
            filter_function=self._whonixupdatevm_filter,
            current_value=None)
        self.load_rules()

        # connect events
        self.updatevm_exception_list.connect('row-activated',
                                             self._rule_clicked)
        self.add_updatevm_rule_button.connect("clicked", self.add_new_rule)

        self.whonix_updatevm_box.set_visible(self.has_whonix)

    def _check_for_whonix(self) -> bool:
        for vm in self.qapp.domains:
            if 'whonix-updatevm' in vm.tags or 'anon-gateway' in vm.tags:
                return True
        return False

    @staticmethod
    def _updatevm_filter(vm):
        return getattr(vm, 'provides_network', False)

    @staticmethod
    def _whonixupdatevm_filter(vm):
        return 'anon-gateway' in vm.tags

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

        self.updatevm_model.select_value(str(def_updatevm))
        self.updatevm_model.update_initial()

        if self.has_whonix:
            self.whonix_updatevm_model.select_value(str(def_whonix_updatevm))
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
        self.close_all_edits()
        new_rule = self.policy_manager.new_rule(
            service=self.service_name, source=str(self.first_eligible_vm),
            target='@default', action=f'allow target={self.default_updatevm}')
        new_row = self._get_row(new_rule)
        self.updatevm_exception_list.add(new_row)
        new_row.activate()

    def _rule_clicked(self, _list_box, row: NoActionListBoxRow, *_args):
        if row.editing:
            # if the current row was clicked, nothing should happen
            return
        self.close_all_edits()
        row.set_edit_mode(True)

    def close_all_edits(self):
        """Close all edited rows"""
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
                        row.revert()
                else:
                    row.revert()

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
        new_target_vm = self.qapp.domains[new_target]
        new_source_vm = self.qapp.domains[new_source]
        if 'whonix-updatevm' in new_source_vm.tags and \
                'anon-gateway' not in new_target_vm.tags:
            return "Whonix qubes can only use Whonix update proxies!"
        return None

    @property
    def current_exception_rules(self):
        """Current rules from the Exception list."""
        rules = []
        for row in self.updatevm_exception_list.get_children():
            rules.append(row.rule)
        return rules

    def is_changed(self) -> bool:
        """Check if state has changed."""
        if self.updatevm_model.is_changed():
            return True
        if self.whonix_updatevm_model.is_changed():
            return True
        if [rule.raw_rule for rule in self.current_exception_rules] != \
                self.rules[:-2]:
            return True
        return False

    def reset(self):
        """Reset to initial state."""
        self.load_rules()

    def save(self):
        """Save currently chosen settings."""
        if not self.is_changed():
            return
        rules = self.current_exception_rules
        raw_rules = [rule.raw_rule for rule in rules]

        new_update_proxies = set()
        for rule in rules:
            new_update_proxies.add(self.qapp.domains[rule.target])

        raw_rules.append(
            self.policy_manager.new_rule(service=self.service_name,
                source="@tag:whonix-updatevm", target="@default",
                action="allow "
                f"target={self.whonix_updatevm_model.get_selected()}"))
        new_update_proxies.add(self.whonix_updatevm_model.get_selected())

        raw_rules.append(
            self.policy_manager.new_rule(service=self.service_name,
                source="@type:TemplateVM", target="@default",
                action="allow "
                       f"target={self.updatevm_model.get_selected()}"))
        new_update_proxies.add(self.updatevm_model.get_selected())

        self.policy_manager.save_rules(self.policy_file_name,
                                       raw_rules, self.current_token)
        _, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, "")

        for vm in self.qapp.domains:
            if 'service.qubes-updates-proxy' in vm.features:
                apply_feature_change(vm, 'service.qubes-updates-proxy',
                                     vm in new_update_proxies)
            elif vm in new_update_proxies:
                apply_feature_change(vm, 'service.qubes-updates-proxy',
                                     True)

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
            gtk_builder=gtk_builder, prefix="updates",
            service_names=[self.service_name],
            own_file_name=self.policy_file_name,
            policy_manager=self.policy_manager)


    def close_all_edits(self):
        """Close all edited rows"""
        self.update_proxy.close_all_edits()

    def get_unsaved(self) -> str:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""
        self.close_all_edits()

        unsaved = [self.repo_handler.get_unsaved(),
                   self.update_checker.get_unsaved()]

        if self.dom0_updatevm_model.is_changed():
            unsaved.append("dom0 Update Proxy")
        if self.update_proxy.is_changed():
            unsaved.append("Update proxy settings")
        unsaved = [x for x in unsaved if x]
        return "\n".join(unsaved)


    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        self.dom0_updatevm_model.reset()
        self.repo_handler.reset()
        self.update_checker.reset()
        self.update_proxy.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""

        for handler in [self.repo_handler, self.update_checker,
                        self.update_proxy]:
            handler.save()  # type: ignore

        if self.dom0_updatevm_model.is_changed():
            self.qapp.updatevm = self.dom0_updatevm_model.get_selected()

# Filtering for dropdowns:
# qubes-update-proxy service? or set it up when adding as proxy??
