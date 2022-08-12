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
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=protected-access

from unittest.mock import patch, call

from ..global_config.usb_devices import WidgetWithButtons, USBVMHandler, \
    InputDeviceHandler, U2FPolicyHandler, DevicesHandler
from ..global_config.rule_list_widgets import VMWidget

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk


def test_widget_with_buttons(test_qapp):
    simple_widget = VMWidget(qapp=test_qapp, categories=None,
                             initial_value='test-vm')

    test_widget = WidgetWithButtons(simple_widget)

    assert not simple_widget.combobox.get_visible()
    assert simple_widget.name_widget.get_visible()
    assert not test_widget.is_changed()

    # edit
    test_widget.edit_button.clicked()

    assert simple_widget.combobox.get_visible()
    assert not simple_widget.name_widget.get_visible()

    # change
    assert simple_widget.model.is_vm_available(test_qapp.domains['test-blue'])
    simple_widget.model.select_value('test-blue')

    # cancel
    test_widget.cancel_button.clicked()
    assert not test_widget.is_changed()

    assert not simple_widget.combobox.get_visible()
    assert simple_widget.name_widget.get_visible()
    assert simple_widget.get_selected() == test_qapp.domains['test-vm']

    # change and confirm
    assert simple_widget.model.is_vm_available(test_qapp.domains['test-blue'])
    simple_widget.model.select_value('test-blue')
    test_widget.confirm_button.clicked()

    assert not simple_widget.combobox.get_visible()
    assert simple_widget.name_widget.get_visible()
    assert simple_widget.get_selected() == test_qapp.domains['test-blue']
    assert test_widget.is_changed()

    # revert

    test_widget.reset()
    assert not simple_widget.combobox.get_visible()
    assert simple_widget.name_widget.get_visible()
    assert simple_widget.get_selected() == test_qapp.domains['test-vm']
    assert not test_widget.is_changed()

    # change, save and update initial
    assert simple_widget.model.is_vm_available(test_qapp.domains['test-blue'])
    simple_widget.model.select_value('test-blue')
    test_widget.confirm_button.clicked()
    test_widget.update_changed()
    assert not test_widget.is_changed()

    test_widget.reset()
    assert not simple_widget.combobox.get_visible()
    assert simple_widget.name_widget.get_visible()
    assert simple_widget.get_selected() == test_qapp.domains['test-blue']


# this is just a fairly basic test, crucial for usbvm is how it interacts
# with other places
def test_usbvm_handler(test_qapp, real_builder):
    handler = USBVMHandler(test_qapp, real_builder)

    # try making some changes
    handler.widget_with_buttons.edit_button.clicked()
    handler.widget_with_buttons.select_widget.model.select_value('sys-net')
    handler.widget_with_buttons.confirm_button.clicked()

    assert handler.get_unsaved() == "USB qube"
    assert handler.get_selected_usbvm() == test_qapp.domains['sys-net']

    # and revert
    handler.reset()
    assert handler.get_selected_usbvm() == test_qapp.domains['sys-usb']
    assert handler.get_unsaved() == ""


    # change and save
    handler.widget_with_buttons.edit_button.clicked()
    handler.widget_with_buttons.select_widget.model.select_value('sys-net')
    handler.widget_with_buttons.confirm_button.clicked()

    with patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change_from_widget') as mock_apply:
        handler.save()
        mock_apply.assert_called_with(
            handler.select_widget, test_qapp.domains['sys-net'],
            handler.FEATURE_NAME)

    # things look correct
    assert handler.get_selected_usbvm() == test_qapp.domains['sys-net']
    assert handler.get_unsaved() == ""


def test_input_devices_no_policy(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, sys_usb)

    # check if defaults worked
    for widget in handler.action_widgets.values():
        assert widget.select_widget.model.get_selected() == 'deny'

    # change things up

    mouse_widget = handler.action_widgets[
        'qubes.InputMouse']
    mouse_widget.edit_button.clicked()
    mouse_widget.select_widget.model.select_value('ask')
    mouse_widget.confirm_button.clicked()

    assert mouse_widget.select_widget.get_selected() == 'ask'
    assert handler.get_unsaved() == 'Mouse input settings'

    # revert
    handler.reset()
    assert mouse_widget.select_widget.get_selected() == 'deny'
    assert handler.get_unsaved() == ''

    # change and save
    mouse_widget = handler.action_widgets[
        'qubes.InputMouse']
    mouse_widget.edit_button.clicked()
    mouse_widget.select_widget.model.select_value('ask')
    mouse_widget.confirm_button.clicked()

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
"""qubes.InputMouse * sys-usb @adminvm ask
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_handler_init(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert handler.get_unsaved() == ''

    # settings from conftest: only vms that have this available are 'test-vm'
    # and 'fedora-35', only test-vm can use the service, policy is default
    testvm = test_qapp.domains['test-vm']
    testred = test_qapp.domains['test-red']
    fedora35 = test_qapp.domains['fedora-35']
    sysusb = test_qapp.domains['sys-usb']

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]
    assert handler.enable_some_handler.add_qube_model.is_vm_available(testvm)
    assert handler.enable_some_handler.add_qube_model.is_vm_available(fedora35)
    assert not handler.enable_some_handler.add_qube_model.is_vm_available(
        testred)
    assert not handler.enable_some_handler.add_qube_model.is_vm_available(
        sysusb)

    assert not handler.register_check.get_active()
    assert not handler.register_some_handler.selected_vms

    assert not handler.blanket_check.get_active()
    assert not handler.blanket_handler.selected_vms


def test_u2f_handler_init_disable(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert not handler.enable_check.get_active()
    assert not handler.problem_no_usbvm_box.get_visible()


def test_u2f_handler_init_no_sysub(
        test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_qapp.expected_calls[
        ('sys-usb', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert not handler.enable_check.get_active()
    assert handler.problem_no_usbvm_box.get_visible()


def test_u2f_handler_init_policy(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
u2f.Register * fedora-35 sys-usb allow
u2f.Register * test-vm sys-usb allow
u2f.Authenticate * test-vm sys-usb allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]

    assert handler.register_check.get_active()
    assert handler.register_some_radio.get_active()
    assert handler.register_some_handler.selected_vms == [fedora35, testvm]

    assert handler.blanket_check.get_active()
    assert handler.blanket_handler.selected_vms == [testvm]


def test_u2f_handler_init_policy_2(test_qapp,
                                   test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
u2f.Register * @anyvm sys-usb allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]

    assert handler.register_check.get_active()
    assert handler.register_all_radio.get_active()

    assert not handler.blanket_check.get_active()


def test_u2f_unsaved_reset(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']

    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    handler.enable_check.set_active(False)
    assert handler.get_unsaved() == 'U2F disabled'

    handler.enable_check.set_active(True)
    assert handler.get_unsaved() == ''

    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()

    handler.enable_some_handler.add_selected_vm(fedora35)
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]
    assert handler.get_unsaved() == 'List of qubes with U2F enabled changed'

    handler.reset()
    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]
    assert handler.get_unsaved() == ''

    handler.blanket_check.set_active(True)
    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)
    handler.blanket_handler.add_selected_vm(fedora35)
    handler.register_some_handler.add_selected_vm(fedora35)

    assert handler.blanket_handler.selected_vms == [fedora35]
    assert handler.register_some_handler.selected_vms == [fedora35]
    assert 'U2F key registration' in handler.get_unsaved()
    assert 'unrestricted U2F key' in handler.get_unsaved()

    handler.reset()
    assert handler.get_unsaved() == ''
    assert handler.blanket_handler.selected_vms == []
    assert handler.register_some_handler.selected_vms == []

def test_u2f_save_disable(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    handler.enable_check.set_active(False)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        mock_apply.assert_called_with(
            test_qapp.domains['test-vm'], handler.SERVICE_FEATURE, None)
        assert len(mock_apply.mock_calls) == 1

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Authenticate * @anyvm @anyvm deny
u2f.Register * @anyvm @anyvm deny
policy.RegisterArgument +u2f.Register @anyvm @anyvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_save_service(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)
    fedora35 = test_qapp.domains['fedora-35']

    assert handler.enable_check.get_active()
    handler.enable_some_handler.add_selected_vm(fedora35)

    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Set',
                              'service.qubes-u2f-proxy', b'1')] = b'0\x00'
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Set',
                              'service.qubes-u2f-proxy', b'1')] = b'0\x00'

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Register * @anyvm @anyvm deny
policy.RegisterArgument +u2f.Register @anyvm @anyvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]

def test_u2f_handler_save_complex(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert not handler.enable_check.get_active()

    handler.enable_check.set_active(True)
    handler.enable_some_handler.add_selected_vm(testvm)
    handler.enable_some_handler.add_selected_vm(fedora35)

    handler.register_check.set_active(True)
    handler.register_all_radio.set_active(True)

    handler.blanket_check.set_active(True)
    handler.blanket_handler.add_selected_vm(testvm)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        assert call(test_qapp.domains['test-vm'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert call(test_qapp.domains['fedora-35'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert len(mock_apply.mock_calls) == 2

        expected_rules = handler.policy_manager.text_to_rules(
            """
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
u2f.Register * @anyvm sys-usb allow
u2f.Authenticate * test-vm sys-usb allow
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_handler_save_complex_2(test_qapp,
                                    test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert not handler.enable_check.get_active()

    handler.enable_check.set_active(True)
    handler.enable_some_handler.add_selected_vm(testvm)
    handler.enable_some_handler.add_selected_vm(fedora35)

    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)
    handler.register_some_handler.add_selected_vm(fedora35)
    handler.register_some_handler.add_selected_vm(testvm)

    handler.blanket_check.set_active(False)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        assert call(test_qapp.domains['test-vm'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert call(test_qapp.domains['fedora-35'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert len(mock_apply.mock_calls) == 2

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Register * fedora-35 sys-usb allow
u2f.Register * test-vm sys-usb allow
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]

def test_u2f_handler_add_without_service(test_qapp,
                                         test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               sys_usb)

    assert handler.get_unsaved() == ''

    # settings from conftest: only vms that have this available are 'test-vm'
    # and 'fedora-35', only test-vm can use the service, policy is default

    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)

    assert handler.register_some_handler.selected_vms == []
    assert handler.enable_some_handler.selected_vms == [testvm]

    handler.register_some_handler.add_button.clicked()
    handler.register_some_handler.add_qube_model.select_value('fedora-35')
    # refuse
    with patch('qubes_config.global_config.usb_devices.'
               'ask_question') as mock_question:
        mock_question.return_value = Gtk.ResponseType.NO
        handler.register_some_handler.add_confirm.clicked()
        assert mock_question.mock_calls
    assert handler.register_some_handler.selected_vms == []
    assert handler.enable_some_handler.selected_vms == [testvm]

    # accept
    with patch('qubes_config.global_config.usb_devices.'
               'ask_question') as mock_question:
        mock_question.return_value = Gtk.ResponseType.YES
        handler.register_some_handler.add_confirm.clicked()
        assert mock_question.mock_calls
    assert handler.register_some_handler.selected_vms == [fedora35]

    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]


def test_devices_handler_usbvm(test_qapp, test_policy_manager, real_builder):
    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    assert handler.u2f_handler.sys_usb.name == 'sys-usb'
    assert handler.input_handler.sys_usb.name == 'sys-usb'

    # changing usbvm
    handler.usbvm_handler.widget_with_buttons.edit_button.clicked()
    handler.usbvm_handler.widget_with_buttons.select_widget.model.select_value(
        'sys-net')
    handler.usbvm_handler.widget_with_buttons.confirm_button.clicked()

    assert handler.u2f_handler.sys_usb.name == 'sys-net'
    assert handler.input_handler.sys_usb.name == 'sys-net'


def test_devices_handler_unsaved(test_qapp, test_policy_manager, real_builder):
    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    assert handler.get_unsaved() == ''

    # some changes
    kb_widget = handler.input_handler.action_widgets[
        'qubes.InputKeyboard']
    assert kb_widget.select_widget.get_selected() == 'deny'
    kb_widget.edit_button.clicked()
    kb_widget.select_widget.model.select_value('ask')
    kb_widget.confirm_button.clicked()

    assert handler.u2f_handler.enable_check.get_active()
    handler.u2f_handler.enable_check.set_active(False)

    assert 'Keyboard input' in handler.get_unsaved()
    assert 'U2F disabled' in handler.get_unsaved()


def test_devices_handler_save_reset(test_qapp,
                                    test_policy_manager, real_builder):
    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    # check all handlers have their save/reset called
    with patch.object(handler.u2f_handler, 'save') as mock_u2f, \
            patch.object(handler.input_handler, 'save') as mock_input, \
            patch.object(handler.usbvm_handler, 'save') as mock_usb:
        handler.save()
        mock_input.assert_called()
        mock_u2f.assert_called()
        mock_usb.assert_called()


    with patch.object(handler.u2f_handler, 'reset') as mock_u2f, \
            patch.object(handler.input_handler, 'reset') as mock_input, \
            patch.object(handler.usbvm_handler, 'reset') as mock_usb:
        handler.reset()
        mock_input.assert_called()
        mock_u2f.assert_called()
        mock_usb.assert_called()
