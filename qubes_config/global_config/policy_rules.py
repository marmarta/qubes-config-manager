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
"""Classes providing simplified wrap around Rule objects."""
import abc

from typing import Dict
from qrexec.policy.parser import Rule, Allow, Ask, Source, Target, Action


class AbstractRuleWrapper(abc.ABC):
    """Wrapper for Rule objects."""
    ACTION_CHOICES: Dict[str, str] = {}

    def __init__(self, rule: Rule):
        """
        :param rule:
        """
        self._rule = rule

    @property
    @abc.abstractmethod
    def source(self):
        """Policy call source, represented as string."""

    @source.setter
    @abc.abstractmethod
    def source(self, new_value: str):
        """Policy call source setter, takes strings."""

    @property
    @abc.abstractmethod
    def target(self):
        """
        Policy call target (human-readable, it may not correspond to Target
        field in policy files, but may be e.g. allow target=???
        Represented as string.
        """

    @target.setter
    @abc.abstractmethod
    def target(self, new_value: str):
        """Policy call target setter, takes strings."""

    @property
    @abc.abstractmethod
    def action(self):
        """Policy action (ask, allow, deny). Represented as string."""

    @action.setter
    @abc.abstractmethod
    def action(self, new_value: str):
        """Policy action (ask, allow, deny) setter. Takes strings."""

    @property
    @abc.abstractmethod
    def raw_rule(self):
        """
        Rule object.
        """


class RuleSimple(AbstractRuleWrapper):
    """
    Simple Rule wrapper, where:
    source = source
    target = target
    action = just action, without params.
    Returns and accepts strings as target/source/action.
    """
    ACTION_CHOICES = {
        "ask": "ask",
        "allow": "always",
        "deny": "never"
    }

    def __init__(self, rule: Rule):
        super().__init__(rule)

    @property
    def target(self):
        return str(self._rule.target)

    @target.setter
    def target(self, new_value):
        new_target = Target(new_value)
        self._rule.target = new_target

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return str(self._rule.action)

    @action.setter
    def action(self, new_value):
        new_action = Action[new_value].value(self._rule)
        self._rule.action = new_action

    @property
    def raw_rule(self):
        return self._rule


class RuleSimpleAskIsAllow(RuleSimple):
    ACTION_CHOICES = {
        "ask": "always",
        "deny": "never"
    }


class RuleTargeted(AbstractRuleWrapper):
    """
    Rule wrapper, where:
    source = source
    action = action
    target = action's target= if action is allow,
    action's default_target if action is ask, target if action is deny;
    if action is ask or allow, target should be @default
    Returns and accepts strings as target/source/action.
    """
    ACTION_CHOICES = {
        "ask": "ask",
        "allow": "always",
        "deny": "never"
    }

    def __init__(self, rule: Rule):
        super().__init__(rule)

    @property
    def target(self):
        if isinstance(self._rule.action, Ask):
            if self._rule.target == '@default':
                return str(self._rule.action.default_target)
        if isinstance(self._rule.action, Allow):
            if self._rule.target == '@default':
                return str(self._rule.action.target)
        return str(self._rule.target)

    @target.setter
    def target(self, new_value):
        new_target = Target(new_value)

        if new_value.startswith('@'):
            self._rule.target = new_target
            return

        if isinstance(self._rule.action, Ask):
            self._rule.target = Target('@default')
            self._rule.action.default_target = new_target
            return
        if isinstance(self._rule.action, Allow):
            self._rule.target = Target('@default')
            self._rule.action.target = new_target
            return

        self._rule.target = new_target

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return type(self._rule.action).__name__.lower()

    @action.setter
    def action(self, new_value):
        old_target = self.target
        new_action = Action[new_value].value(self._rule)
        self._rule.action = new_action
        self.target = old_target

    @property
    def raw_rule(self):
        return self._rule
