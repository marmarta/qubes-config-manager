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
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
import pytest

from qrexec.policy.parser import Rule
from ..global_config.policy_rules import RuleSimple, RuleTargeted

def make_rule(source, target, action):
    return Rule.from_line(
        None, f"Service\t*\t{source}\t{target}\t{action}",
        filepath=None, lineno=0)


def test_simple_rule():
    basic_rule = make_rule('vm1', 'vm2', 'allow')
    wrapped_rule = RuleSimple(basic_rule)
    assert wrapped_rule.raw_rule == basic_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'allow'

    wrapped_rule.source = 'vm2'
    assert str(wrapped_rule.raw_rule) == str(make_rule('vm2', 'vm2', 'allow'))
    wrapped_rule.target = 'vm1'
    assert str(wrapped_rule.raw_rule) == str(make_rule('vm2', 'vm1', 'allow'))
    wrapped_rule.action = 'deny'
    assert str(wrapped_rule.raw_rule) == str(make_rule('vm2', 'vm1', 'deny'))
    assert not wrapped_rule.is_rule_fundamental()
    assert wrapped_rule.is_rule_conflicting(other_action='deny',
                                            other_source='vm2',
                                            other_target='vm1')
    fundamental_rule = make_rule('@anyvm', '@anyvm', 'deny')
    assert RuleSimple(fundamental_rule).is_rule_fundamental()

    assert RuleSimple.get_rule_errors('@anyvm', '@anyvm', 'deny') is None

    with pytest.raises(ValueError):
        wrapped_rule.action = 'allow target=dom0'


def test_targeted_rule():
    deny_rule = make_rule('vm1', 'vm2', 'deny')
    wrapped_rule = RuleTargeted(deny_rule)
    assert wrapped_rule.raw_rule == deny_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'deny'

    allow_rule = make_rule('vm1', '@default', 'allow target=vm2')
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'allow'

    ask_rule = make_rule('vm1', '@default', 'ask default_target=vm2')
    wrapped_rule = RuleTargeted(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'ask'


def test_targeted_rule_weird_cases():
    # if we get fed wrong-ish values:
    allow_rule = make_rule('vm1', 'vm2', 'allow')
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'allow'

    # but it should get converted to expected things if set
    wrapped_rule.target = 'vm3'
    assert str(wrapped_rule.raw_rule) == \
           str(make_rule('vm1', '@default', 'allow target=vm3'))

    ask_rule = make_rule('vm1', 'vm2', 'ask')
    wrapped_rule = RuleTargeted(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == 'vm2'
    assert wrapped_rule.action == 'ask'

    # and same here
    wrapped_rule.target = 'vm3'
    assert str(wrapped_rule.raw_rule) == \
           str(make_rule('vm1', '@default', 'ask default_target=vm3'))

def test_targeted_tokens():
    # tokens as target should be treated like normal targets
    allow_rule = make_rule('vm1', '@anyvm', 'allow')
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == 'vm1'
    assert wrapped_rule.target == '@anyvm'
    assert wrapped_rule.action == 'allow'

    wrapped_rule.target = 'vm3'
    assert str(wrapped_rule.raw_rule) == \
           str(make_rule('vm1', '@default', 'allow target=vm3'))

    allow_rule = make_rule('vm1', '@default', 'allow target=vm2')
    wrapped_rule = RuleTargeted(allow_rule)
    wrapped_rule.target = '@anyvm'
    assert str(wrapped_rule.raw_rule) == \
           str(make_rule('vm1', '@anyvm', 'allow'))

    ask_rule = make_rule('vm1', '@default', 'ask default_target=vm2')
    wrapped_rule = RuleTargeted(ask_rule)
    wrapped_rule.target = '@anyvm'
    assert str(wrapped_rule.raw_rule) == \
           str(make_rule('vm1', '@anyvm', 'ask'))


def test_targeted_change_action():
    allow_rule = make_rule('vm1', '@default', 'allow target=vm2')
    ask_rule = make_rule('vm1', '@default', 'ask default_target=vm2')

    wrapped_allow = RuleTargeted(allow_rule)
    wrapped_ask = RuleTargeted(ask_rule)

    wrapped_allow.action = 'ask'
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)

    allow_rule = make_rule('vm1', '@default', 'allow target=vm2')
    ask_rule = make_rule('vm1', '@default', 'ask default_target=vm2')

    wrapped_allow = RuleTargeted(allow_rule)
    wrapped_ask = RuleTargeted(ask_rule)

    wrapped_ask.action = 'allow'
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)


def test_targeted_fundamental():
    fundamental_rule = make_rule('@anyvm', '@anyvm', 'ask')
    assert RuleTargeted(fundamental_rule).is_rule_fundamental()

    fundamental_rule = make_rule('@anyvm', '@dispvm', 'allow')
    fundamental_wrapped = RuleTargeted(fundamental_rule)
    assert fundamental_wrapped.is_rule_fundamental()

    fundamental_wrapped.target = 'vm2'
    assert not fundamental_wrapped.is_rule_fundamental()


def test_targeted_validity():
    assert RuleTargeted.get_rule_errors(source='vm1', target='@anyvm',
                                        action='ask')
    assert RuleTargeted.get_rule_errors(source='vm1', target='@anyvm',
                                        action='allow')
    assert not RuleTargeted.get_rule_errors(source='vm1', target='@anyvm',
                                            action='deny')

    assert not RuleTargeted.get_rule_errors(source='vm1', target='@dispvm',
                                            action='ask')
    assert not RuleTargeted.get_rule_errors(source='vm1', target='@dispvm',
                                            action='allow')
    assert not RuleTargeted.get_rule_errors(source='vm1', target='@dispvm',
                                            action='deny')

    assert not RuleTargeted.get_rule_errors(source='vm1', target='vm2',
                                            action='ask')
    assert not RuleTargeted.get_rule_errors(source='vm1', target='vm2',
                                            action='allow')
    assert not RuleTargeted.get_rule_errors(source='vm1', target='vm2',
                                            action='deny')


def test_targeted_conflict():
    rule_allow = make_rule('vm1', '@default', 'allow target=vm2')
    rule_ask = make_rule('vm1', '@default', 'ask default_target=vm2')
    rule_deny = make_rule('vm1', 'vm2', 'deny')

    wrapped_allow = RuleTargeted(rule_allow)
    wrapped_ask = RuleTargeted(rule_ask)
    wrapped_deny = RuleTargeted(rule_deny)

    assert wrapped_allow.is_rule_conflicting(other_source='vm1',
                                             other_target='vm2',
                                             other_action='deny')
    assert wrapped_allow.is_rule_conflicting(other_source='vm1',
                                             other_target='vm2',
                                             other_action='ask')
    assert wrapped_allow.is_rule_conflicting(other_source='vm1',
                                             other_target='vm3',
                                             other_action='allow')

    assert wrapped_ask.is_rule_conflicting(other_source='vm1',
                                           other_target='vm2',
                                           other_action='deny')
    assert not wrapped_ask.is_rule_conflicting(other_source='vm1',
                                               other_target='vm3',
                                               other_action='allow')
    assert not wrapped_ask.is_rule_conflicting(other_source='vm1',
                                               other_target='vm3',
                                               other_action='ask')

    assert wrapped_deny.is_rule_conflicting(other_source='vm1',
                                            other_target='vm2',
                                            other_action='allow')
    assert not wrapped_deny.is_rule_conflicting(other_source='vm1',
                                                other_target='vm3',
                                                other_action='ask')
    assert not wrapped_deny.is_rule_conflicting(other_source='vm1',
                                                other_target='vm3',
                                                other_action='allow')
