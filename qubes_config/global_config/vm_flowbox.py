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
Widget that's a flow box with vms.
"""
from typing import Optional, List, Callable

from ..widgets.qubes_widgets_library import VMListModeler, show_error, \
    ask_question, QubeName

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gbulb
gbulb.install()

class VMFlowBoxButton(Gtk.FlowBoxChild):
    """Simple button  representing a VM that can be deleted."""
    def __init__(self, vm: qubesadmin.vm.QubesVM):
        super().__init__()
        self.vm = vm

        token_widget = QubeName(vm)
        button = Gtk.Button()
        button.get_style_context().add_class('flat')

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(token_widget, False, False, 0)
        remove_icon = Gtk.Image()
        remove_icon.set_from_pixbuf(
            Gtk.IconTheme.get_default().load_icon(
                'qubes-delete', 14, 0))
        box.pack_start(remove_icon, False, False, 10)

        button.add(box)
        button.connect('clicked', self._remove_self)
        self.add(button)
        self.show_all()


    def _remove_self(self, _widget):
        response = ask_question(
            self.get_toplevel(), "Delete",
            "Are you sure you want to remove this exception?")
        if response == Gtk.ResponseType.NO:
            return
        self.get_parent().remove(self)


class VMFlowboxHandler:
    """
    Handler for the flowbox itself. Requires the following widgets:
    - {prefix}_flowbox - the flowbox widget
    - {prefix}_box - Box containing the entire thing
    - {prefix}_add_box = Box containing the "add new exception" combo
    - {prefix}_qube_combo - combobox to select a qube to add
    - {prefix}_add_cancel - cancel adding new qube button
    - {prefix}_add_confirm - confirm adding a new qube button
    - {prefix}_add_button - add new qube button
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes,
                 prefix: str, initial_vms: List[qubesadmin.vm.QubesVM],
                 filter_function: Optional[Callable] = None,
                 verification_callback:
                 Optional[Callable[[qubesadmin.vm.QubesVM], bool]] = None):
        """
        :param gtk_builder: Gtk.Builder
        :param qapp: qubesadmin.Qubes
        :param prefix: widget name prefix (see above)
        :param initial_vms: list of initially selected vms
        :param filter_function: function to filter vms available in the dropdown
        :param verification_callback: if provided, will be called before adding
        a vm; return True if verification was successful and false if it has
        failed
        """
        self.qapp = qapp
        self.verification_callback = verification_callback

        self.flowbox: Gtk.FlowBox = \
            gtk_builder.get_object(f'{prefix}_flowbox')
        self.box: Gtk.Box = \
            gtk_builder.get_object(f'{prefix}_box')
        self.add_box: Gtk.Box = \
            gtk_builder.get_object(f'{prefix}_add_box')

        self.qube_combo: Gtk.ComboBox = \
            gtk_builder.get_object(f'{prefix}_qube_combo')

        self.add_cancel: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_cancel')
        self.add_confirm: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_confirm')
        self.add_button: Gtk.Button = \
            gtk_builder.get_object(f'{prefix}_add_button')

        self.add_qube_model = VMListModeler(
            combobox=self.qube_combo,
            qapp=self.qapp,
            filter_function=filter_function)

        self.flowbox.set_sort_func(self._sort_flowbox)

        self._initial_vms = sorted(initial_vms)
        for vm in self._initial_vms:
            self.flowbox.add(VMFlowBoxButton(vm))
        self.flowbox.show_all()


        self.add_button.connect('clicked',
                                          self._add_button_clicked)
        self.add_cancel.connect('clicked',
                                          self._add_cancel_clicked)
        self.add_confirm.connect('clicked',
                                          self._add_confirm_clicked)

    @staticmethod
    def _sort_flowbox(child_1, child_2):
        vm_1 = str(child_1.vm)
        vm_2 = str(child_2.vm)
        if vm_1 == vm_2:
            return 0
        return 1 if vm_1 > vm_2 else -1

    def _add_button_clicked(self, _widget):
        self.add_box.set_visible(True)

    def _add_cancel_clicked(self, _widget):
        self.add_box.set_visible(False)

    def _add_confirm_clicked(self, _widget):
        select_vm = self.add_qube_model.get_selected()
        if self.verification_callback:
            if not self.verification_callback(select_vm):
                return
        if select_vm in self.selected_vms:
            show_error("Cannot add qube", "This qube is already selected.")
            return
        self.flowbox.add(VMFlowBoxButton(select_vm))
        self.add_box.set_visible(False)

    def set_visible(self, state: bool):
        """Set flowbox to visible/usable."""
        self.box.set_visible(state)
        if not state:
            self.add_box.set_visible(False)

    def add_selected_vm(self, vm):
        """
        Add a vm to selected vms.
        """
        self.flowbox.add(VMFlowBoxButton(vm))

    @property
    def selected_vms(self) -> List[qubesadmin.vm.QubesVM]:
        """Get current list of selected vms"""
        selected_vms: List[qubesadmin.vm.QubesVM] = []
        if not self.box.get_visible():
            return selected_vms
        for child in self.flowbox.get_children():
            selected_vms.append(child.vm)
        return selected_vms

    def is_changed(self) -> bool:
        """Is the flowbox changed from initial state?"""
        return self.selected_vms != self._initial_vms

    def save(self):
        """Mark changes as saved, for use in is_changed."""
        self._initial_vms = self.selected_vms

    def reset(self):
        """Reset changed to initial state."""
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)

        for vm in self._initial_vms:
            self.flowbox.add(VMFlowBoxButton(vm))
