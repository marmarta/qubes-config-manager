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
"""Tests for gtk utils"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GdkPixbuf

from ..widgets.gtk_utils import load_icon, load_icon_at_gtk_size

def test_load_icon():
    """Test loading icon methods; tests if they don't error out and
    return a pixbuf of correct size"""
    # load from existing file
    icon_from_file = load_icon_at_gtk_size('../icons/question_icon.svg')
    # load from an existing icon
    icon_from_name = load_icon('xterm')
    # load from missing name
    icon_from_error = load_icon('qwertyuiop')

    assert (24, 24) == (icon_from_file.get_height(), icon_from_file.get_width())
    assert (24, 24) == (icon_from_name.get_height(), icon_from_name.get_width())
    assert (24, 24) == \
           (icon_from_error.get_height(), icon_from_error.get_width())

    assert isinstance(icon_from_file, GdkPixbuf.Pixbuf)
    assert isinstance(icon_from_name, GdkPixbuf.Pixbuf)
    assert isinstance(icon_from_error, GdkPixbuf.Pixbuf)
