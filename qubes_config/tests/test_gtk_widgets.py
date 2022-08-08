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
"""Tests for widget library"""
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject

from unittest.mock import Mock, patch
from ..widgets import gtk_widgets


def test_token_name(test_qapp):
    token_name = gtk_widgets.TokenName("test-blue", test_qapp)

    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, gtk_widgets.QubeName)
    assert child.get_style_context().has_class('qube-box-blue')

    token_name.set_token('@anyvm')
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, Gtk.Label)
    assert not child.get_style_context().has_class('qube-box-blue')
    assert child.get_style_context().has_class('qube-type')

    token_name.set_token('test-red')
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, gtk_widgets.QubeName)
    assert not child.get_style_context().has_class('qube-box-blue')
    assert child.get_style_context().has_class('qube-box-red')


def test_token_name_categories(test_qapp):
    token_name = gtk_widgets.TokenName("@anyvm", test_qapp, {'@anyvm': 'Any'})
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, Gtk.Label)
    assert child.get_text() == 'Any'


def test_qube_name(test_qapp):
    # missing name
    qube_name = gtk_widgets.QubeName(None)
    assert qube_name.label.get_text() == "None"
    assert qube_name.get_style_context().has_class('qube-box-black')
    assert qube_name.get_style_context().has_class('qube-box-base')

    vm = test_qapp.domains['test-red']
    qube_name = gtk_widgets.QubeName(vm)
    assert qube_name.label.get_text() == "test-red"
    assert qube_name.get_style_context().has_class('qube-box-red')
    assert qube_name.get_style_context().has_class('qube-box-base')


def test_text_modeler_simple():
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values= {'Pretty': 1, 'Ugly': 2})

    # expected initial setup
    assert combobox.get_active_text() == 'Pretty'

    # select second value in combobox
    combobox.set_active(1)
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() == 2
    assert text_modeler.is_changed()

    # reset to initial settings
    text_modeler.reset()
    assert combobox.get_active_text() == 'Pretty'
    assert text_modeler.get_selected() == 1
    assert not text_modeler.is_changed()

    # select second value via TextModeler
    text_modeler.select_value(2)
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() == 2
    assert text_modeler.is_changed()

    # mark changes as saved
    text_modeler.update_initial()
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() == 2
    assert not text_modeler.is_changed()


def test_text_modeler_none():
    """Check if there is no strangeness if one of the values is None"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values= {'Pretty': 1, 'Ugly': None})

    # none will be selected as initial value if nothing else is provided
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # select second value in combobox
    combobox.set_active(0)
    assert combobox.get_active_text() == 'Pretty'
    assert text_modeler.get_selected() == 1
    assert text_modeler.is_changed()

    # reset to initial settings
    text_modeler.reset()
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # select values via TextModeler
    text_modeler.select_value(1)
    assert combobox.get_active_text() == 'Pretty'
    assert text_modeler.get_selected() == 1
    assert text_modeler.is_changed()

    text_modeler.select_value(None)
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # mark changes as saved
    text_modeler.update_initial()
    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()


def test_text_modeler_initial():
    """Initial value is set"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values= {'Good': 1, 'Ugly': 2, 'Bad': 3},
        selected_value=2)

    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() == 2
    assert not text_modeler.is_changed()


def test_text_modeler_initial_none():
    """Initial value corresponding to None is set"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values= {'Pretty': 1, 'Ugly': None},
        selected_value=None
    )

    assert combobox.get_active_text() == 'Ugly'
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

# selected_value = 'Ugly',
# style_changes = False

# @patch('gi.repository.Gtk.IconTheme', spec=Gtk.IconTheme)
# @patch('gi.repository.Gtk.Image.set_from_pixbuf')
# def test_image_button(*_args):
#     a = Mock()
#     button = lib.ImageTextButton('text', None, click_function=a.do_stuff,
#                                  style_classes=['flat'])
#     button.clicked()
#     print(a.mock_calls)
#     assert False
#
#
# def test_widget_with_buttons(mock, mock2):
#     mock_widget = Mock()
#     mock_widget.mock_add_spec(GObject)
#     mock_widget.mock_add_spec(Gtk.Widget)
#
#     # with patch('gi.repository.Gtk.IconTheme',
#     **{'load_icon.return_value': GdkPixbuf.Pixbuf()}):
#     test_widget = lib.WidgetWithButtons(mock_widget)
#
#     test_widget.edit_button.clicked()
#     print(mock_widget.mock_calls)
#     assert False
