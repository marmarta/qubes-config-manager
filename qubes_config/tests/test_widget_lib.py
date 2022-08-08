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
# import gi
#
# gi.require_version('Gtk', '3.0')
# from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
#
# from unittest.mock import Mock, patch
# from ..widgets import qubes_widgets_library as lib
#
# WidgetWithButtons
# ImageTextButton
#

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
