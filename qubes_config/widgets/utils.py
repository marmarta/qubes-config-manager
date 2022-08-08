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
"""Qubes helper functions"""
import qubesadmin
import qubesadmin.exc
import qubesadmin.vm

from typing import Optional, Any, Dict


def get_feature(vm, feature_name, default_value=None):
    """Get feature, with a working default_value."""
    try:
        return vm.features.get(feature_name, default_value)
    except qubesadmin.exc.QubesDaemonAccessError:
        return default_value

def get_boolean_feature(vm, feature_name, default=False):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    else:
        result = default
    return result

def apply_feature_change_from_widget(widget, vm: qubesadmin.vm.QubesVM,
                                     feature_name:str):
    """Change a feature value, taking into account weirdness with None.
    Widget must support is_changed and get_selected methods."""
    if widget.is_changed():
        value = widget.get_selected()
        apply_feature_change(vm, feature_name, value)

def apply_feature_change(vm: qubesadmin.vm.QubesVM,
                         feature_name: str, new_value: Optional[Any]):
    """Change a feature value, taking into account weirdness with None."""
    try:
        if new_value is None:
            if feature_name in vm.features:
                del vm.features[feature_name]
        else:
            vm.features[feature_name] = new_value
    except qubesadmin.exc.QubesDaemonAccessError:
        # pylint: disable=raise-missing-from
        raise qubesadmin.exc.QubesException(
            "Failed to set {} due to insufficient "
            "permissions".format(feature_name))


class BiDictionary(dict):
    """Helper bi-directional dictionary. By design, duplicate values
    cause errors."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inverted: Dict[Any, Any] = {}
        for key, value in self.items():
            if value in self.inverted:
                raise ValueError
            self.inverted[value] = key

    def __setitem__(self, key, value):
        if key in self:
            del self.inverted[self[key]]
        super().__setitem__(key, value)
        if value in self.inverted:
            raise ValueError
        self.inverted[value] = key

    def __delitem__(self, key):
        del self.inverted[self[key]]
        super().__delitem__(key)
