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
from unittest.mock import patch, ANY

from ..global_config.global_config import GlobalConfig, ClipboardHandler,\
    FileAccessHandler
from ..global_config.usb_devices import DevicesHandler
from ..global_config.basics_handler import BasicSettingsHandler

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk

# this entire file has a peculiar arrangement with mock signal registration:
# to enable tests from this file to run alone,
# a test_builder fixture is requested because it will try to register
# signals in "test" mode

@patch('subprocess.check_output')
@patch('qubes_config.global_config.global_config.show_error')
def test_global_config_init(mock_error, mock_subprocess,
                            test_qapp, test_policy_manager, test_builder):
    mock_subprocess.return_value = b''
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert test_builder

    # switch across pages, nothing should happen
    while app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()).get_name() != 'thisdevice':
        app.main_notebook.next_page()

    # find clipboard
    app.main_notebook.set_current_page(0)

    while app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()).get_name() != 'clipboard':
        app.main_notebook.next_page()

    clipboard_page_num = app.main_notebook.get_current_page()
    handler = app.get_current_page()
    assert isinstance(handler, ClipboardHandler)

    assert handler.copy_combo.get_active_id() == 'default (Ctrl+Shift+C)'
    handler.copy_combo.set_active_id('Ctrl+Win+C')

    # try to move away from page, we should get a warning
    with patch('qubes_config.global_config.global_config.show_dialog') \
            as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        app.main_notebook.set_current_page(clipboard_page_num + 1)

    assert app.main_notebook.get_current_page() == clipboard_page_num + 1
    app.main_notebook.set_current_page(clipboard_page_num)

    assert handler.copy_combo.get_active_id() == 'default (Ctrl+Shift+C)'
    handler.copy_combo.set_active_id('Ctrl+Win+C')

    # try to move away from page, we should get a warning
    with patch('qubes_config.global_config.global_config.show_dialog') \
            as mock_ask, patch('qubes_config.global_config.basics_handler.'
               'apply_feature_change') as mock_apply:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.set_current_page(clipboard_page_num + 1)
        mock_apply.assert_called_with(
            test_qapp.domains['dom0'], 'gui-default-secure-copy-sequence',
            'Ctrl-Mod4-c')

    mock_error.assert_not_called()


@patch('subprocess.check_output')
@patch('qubes_config.global_config.global_config.show_error')
def test_global_config_usb_change(mock_error, mock_subprocess,
                                  test_qapp, test_policy_manager, test_builder):
    mock_subprocess.return_value = b''
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()

    assert test_builder

    # find clipboard
    app.main_notebook.set_current_page(0)

    while app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()).get_name() != 'usb':
        app.main_notebook.next_page()

    handler = app.get_current_page()
    assert isinstance(handler, DevicesHandler)

    # change usb vm
    with patch('qubes_config.widgets.gtk_utils.Gtk.Dialog') \
        as mock_dialog, patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change_from_widget') as mock_apply:
        mock_dialog.new().run.return_value = Gtk.ResponseType.YES

        handler.usbvm_handler.widget_with_buttons.edit_button.clicked()
        handler.usbvm_handler.select_widget.model.select_value('sys-net')
        handler.usbvm_handler.widget_with_buttons.confirm_button.clicked()

        assert len(mock_dialog.new().run.mock_calls) == 1

        mock_apply.assert_called_with(ANY, test_qapp.domains['dom0'],
                                      'config-usbvm-name')

    mock_error.assert_not_called()


@patch('subprocess.check_output')
@patch('qubes_config.global_config.global_config.show_error')
def test_global_config_usb_change_no_double(mock_error, mock_subprocess,
                                  test_qapp, test_policy_manager, test_builder):
    # this test checks if answering no or cancel to changing usb vm does
    # not lead to a cycle of questions

    mock_subprocess.return_value = b''
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()

    assert test_builder

    app.main_notebook.set_current_page(0)

    while app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()).get_name() != 'usb':
        app.main_notebook.next_page()

    handler = app.get_current_page()
    assert isinstance(handler, DevicesHandler)

    # change usb vm
    with patch('qubes_config.widgets.gtk_utils.Gtk.Dialog') as mock_dialog, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change_from_widget') as mock_apply:
        mock_dialog.new().run.return_value = Gtk.ResponseType.NO

        handler.usbvm_handler.widget_with_buttons.edit_button.clicked()
        handler.usbvm_handler.select_widget.model.select_value('sys-net')
        handler.usbvm_handler.widget_with_buttons.confirm_button.clicked()

        assert len(mock_dialog.new().run.mock_calls) == 1

        mock_apply.assert_not_called()

    assert handler.usbvm_handler.get_selected_usbvm() == \
           test_qapp.domains['sys-usb']

    mock_error.assert_not_called()


@patch('subprocess.check_output')
@patch('qubes_config.global_config.global_config.show_error')
def test_global_config_page_change(mock_error, mock_subprocess,
                                  test_qapp, test_policy_manager, test_builder):
    mock_subprocess.return_value = b''
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert test_builder

    while app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()).get_name() != 'file':
        app.main_notebook.next_page()

    file_page_num = app.main_notebook.get_current_page()
    handler = app.get_current_page()
    assert isinstance(handler, FileAccessHandler)

    # make a small change
    handler.openinvm_handler.enable_radio.set_active(True)
    handler.openinvm_handler.add_button.clicked()

    for child in handler.openinvm_handler.current_rows:
        if child.editing:
            child.activate()
            child.source_widget.model.select_value('sys-net')
            child.validate_and_save()

    for row in handler.openinvm_handler.current_rows:
        if row.rule.source == 'sys-net':
            break
    else:
        assert False  # didn't find the change

    # try to switch pages but refuse to save changes
    with patch('qubes_config.global_config.global_config.show_dialog') \
        as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        app.main_notebook.next_page()
        mock_ask.assert_called()

    assert app.main_notebook.get_current_page() == file_page_num + 1
    app.main_notebook.prev_page()

    # changes should not be makde
    for row in handler.openinvm_handler.current_rows:
        assert row.rule.source != 'sys-net'

    # make changes and try to stick to them
    handler.openinvm_handler.enable_radio.set_active(True)
    handler.openinvm_handler.add_button.clicked()

    for child in handler.openinvm_handler.current_rows:
        if child.editing:
            child.activate()
            child.source_widget.model.select_value('sys-net')
            child.validate_and_save()

    old_text = test_policy_manager.policy_client.files[
        handler.openinvm_handler.policy_file_name]

    # save changes
    with patch('qubes_config.global_config.global_config.show_dialog') \
        as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.next_page()
        mock_ask.assert_called()

    # changes should have been done
    assert old_text != test_policy_manager.policy_client.files[
        handler.openinvm_handler.policy_file_name]

    mock_error.assert_not_called()


@patch('subprocess.check_output')
@patch('qubes_config.global_config.global_config.show_error')
def test_global_config_failure(mock_error, mock_subprocess,
                               test_qapp, test_policy_manager, test_builder):
    mock_subprocess.return_value = b''
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()

    assert test_builder

    # we should be at first page
    assert app.main_notebook.get_current_page() == 0
    handler = app.get_current_page()
    assert isinstance(handler, BasicSettingsHandler)

    # change something manually
    handler.fullscreen_combo.set_active_id('disallow')

    # try to switch pages, error will occur on saving
    with patch('qubes_config.global_config.global_config.show_dialog') \
        as mock_ask, \
            patch('qubes_config.global_config.global_config.'
                  'GLib.timeout_add') as mock_timeout:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.next_page()
        mock_ask.assert_called()
        mock_error.assert_called()

        # and we called the timer to switch back to self; can't check
        # if switch was successful because we don't have the main
        # loop in these tests
        mock_timeout.assert_called()
