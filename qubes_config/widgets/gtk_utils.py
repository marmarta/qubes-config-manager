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
"""Utility functions using Gtk"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, GLib

def load_icon_at_gtk_size(icon_name,
                          icon_size: Gtk.IconSize = Gtk.IconSize.LARGE_TOOLBAR):
    """Load icon from provided name, if available. If not, attempt to treat
    provided name as a path. If icon not found in any of the above ways,
    load a blank icon of specified size, provided as Gtk.IconSize.
    Returns GdkPixbuf.Pixbuf.
    """
    _, width, height = Gtk.icon_size_lookup(icon_size)
    return load_icon(icon_name, width, height)


def load_icon(icon_name: str, width: int = 24, height: int = 24):
    """Load icon from provided name, if available. If not, attempt to treat
    provided name as a path. If icon not found in any of the above ways,
    load a blank icon of specified size.
    Returns GdkPixbuf.Pixbuf.
    width and height must be in pixels.
    """
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_name, width, height)
    except (GLib.Error, TypeError):
        try:
            # icon name is a path
            image: GdkPixbuf.Pixbuf = Gtk.IconTheme.get_default().load_icon(
                icon_name, width, 0)
            return image
        except (TypeError, GLib.Error):
            # icon not found in any way
            pixbuf: GdkPixbuf.Pixbuf = GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, True, 8, width, height)
            pixbuf.fill(0x000)
            return pixbuf

def show_error(title, text):
    """
    Helper function to display error messages.
    """
    dialog = Gtk.MessageDialog(
        parent=None, flags=0, message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK)
    content_area = dialog.get_content_area()
    content_area.get_style_context().add_class('question_dialog')
    dialog.set_title(title)
    dialog.set_markup(text)
    dialog.connect("response", lambda *x: dialog.destroy())
    dialog.run()
    dialog.destroy()


def ask_question(parent, title: str, text: str,
                 options: Gtk.ButtonsType = Gtk.ButtonsType.YES_NO):
    """
    Helper function to show question dialogs.
    """
    dialog = Gtk.MessageDialog(
        parent=parent,
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.QUESTION, buttons=options)
    dialog.set_title(title)
    content_area = dialog.get_content_area()
    content_area.get_style_context().add_class('question_dialog')
    dialog.set_markup(f'<b>{title}</b>')
    dialog.format_secondary_markup(text)
    response = dialog.run()
    dialog.destroy()
    return response
