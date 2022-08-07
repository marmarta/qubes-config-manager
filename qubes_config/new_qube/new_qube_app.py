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
New Qube program.
"""
# pylint: disable=import-error
import subprocess
import sys
import os
from typing import Optional, List, Tuple, Dict, Callable
import abc
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm
from ..widgets.qubes_widgets_library import QubeName, VMListModeler

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')
WHONIX_QUBE_NAME = 'sys-whonix'


class ApplicationData:
    """
    Class representing information about an available application.
    """
    def __init__(self, name: str, ident: str, comment: Optional[str] = None,
                 template: Optional[qubesadmin.vm.QubesVM] = None):
        """
        :param name: application name
        :param ident: application id (as expected by qvm-appmenus)
        :param comment: optional comment
        :param template: optional qubes VM that is this app's template
        """
        self.name = name
        self.ident = ident
        self.template = template
        additional_description = ".desktop filename: " + str(self.ident)

        file_name_root = self.ident[:-len('.desktop')]
        self.icon_path = os.path.expanduser(
            f'~/.local/share/qubes-appmenus/{template}'
            f'/apps.tempicons/{file_name_root}.png')

        if not comment:
            self.comment = additional_description
        else:
            self.comment = comment + "\n" + additional_description

    @classmethod
    def from_line(cls, line, template=None):
        """
        Create object from output line of qvm-appmenus, with optional template.
        """
        ident, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, ident=ident, comment=comment, template=template)


class ApplicationRow(Gtk.ListBoxRow):
    """
    Row representing an app in current template.
    """
    def __init__(self, appdata: ApplicationData, **properties):
        """
        :param app_info: ApplicationInfo obj with data about related app file
        :param properties: additional Gtk.ListBoxRow properties
        """
        super().__init__(**properties)
        self.set_tooltip_text(appdata.comment)
        self.appdata = appdata
        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.label.set_alignment(0, 0.5)
        self.add(self.label)
        self.set_tooltip_text(self.appdata.comment)
        self.label.set_alignment(0, 0.5)
        self.get_style_context().add_class('app_list')


class OtherTemplateApplicationRow(Gtk.ListBoxRow):
    """
    Row representing an app in another template.
    """
    def __init__(self, appdata: ApplicationData, **properties):
        """
        :param app_info: ApplicationInfo obj with data about related app file
        :param properties: additional Gtk.ListBoxRow properties
        """
        super().__init__(**properties)
        self.set_tooltip_text(appdata.comment)
        self.appdata = appdata
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)
        self.first_label = Gtk.Label()
        self.first_label.set_text(f"{self.appdata.name} found in template")
        self.box.pack_start(self.first_label, False, False, 0)
        self.second_label = QubeName(appdata.template)
        self.box.pack_start(self.second_label, False, False, 0)
        self.show_all()


class ApplicationButton(Gtk.Button):
    """
    Button representing a selected application.
    """
    def __init__(self, appdata: ApplicationData):
        """
        :param appdata: ApplicationData object
        """
        super().__init__(label=None)
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)
        self.appdata = appdata

        self.icon = Gtk.Image()
        try:
            self.icon.set_from_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file_at_size(
                    appdata.icon_path, 18, 18))
        except GLib.Error:
            # icon not available, let's move on
            pass

        self.box.pack_start(self.icon, False, False, 3)

        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.label.set_tooltip_text(self.appdata.comment)
        self.box.pack_start(self.label, False, False, 3)

        self.remove_icon = Gtk.Image()
        self.remove_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-delete', 14, 0))
        self.remove_icon.set_tooltip_text(
            'Click to remove this application from selection')
        self.box.pack_end(self.remove_icon, False, False, 3)

        self.show_all()


class AddButton(Gtk.Button):
    """
    Button to open 'select apps' window.
    """
    def __init__(self, **properties):
        super().__init__(properties)
        self.set_label("+")


class ApplicationBoxHandler:
    """
    Class to handle popup application box.
    """
    def __init__(self, flowbox: Gtk.FlowBox, gtk_builder: Gtk.Builder,
                 template_selector):
        """
        :param flowbox: Gtk.Flowbox containing application button list
        :param gtk_builder: Gtk.Builder to get relevant objects
        :param template_selector: TemplateHandler object
        """
        self.template_selector = template_selector
        self.flowbox = flowbox
        self.apps_window = gtk_builder.get_object('applications_popup')
        self.apps_list: Gtk.ListBox = gtk_builder.get_object('apps_list')
        self.label_apps: Gtk.Label = gtk_builder.get_object('label_apps')
        self.label_apps_explain: Gtk.Label = gtk_builder.get_object(
            'label_apps_explain')
        self.apps_close: Gtk.Button = gtk_builder.get_object('apps_close')
        self.apps_search: Gtk.SearchEntry = \
            gtk_builder.get_object('apps_search')
        self.apps_list_placeholder: Gtk.Label = \
            gtk_builder.get_object('apps_list_placeholder')
        self.apps_list_other: Gtk.ListBox = \
            gtk_builder.get_object('apps_list_other_templates')
        self.label_other_templates: Gtk.Label = gtk_builder.get_object(
            'label_other_templates')

        self.change_template_msg: Gtk.Dialog = gtk_builder.get_object(
            'msg_change_template')
        self.change_template_ok: Gtk.Button = gtk_builder.get_object(
            'change_template_ok')
        self.change_template_cancel: Gtk.Button = gtk_builder.get_object(
            'change_template_cancel')
        self.change_template_box: Gtk.Box = gtk_builder.get_object(
            'change_template_box')
        self.target_template_name_widget: Optional[Gtk.Widget] = None

        self.change_template_cancel.connect(
            'clicked', self._hide_template_change)
        self.change_template_ok.connect('clicked', self._do_template_change)
        self.change_template_msg.connect(
            'key_press_event', self._keypress_change_template)

        self.apps_window.connect('key_press_event', self._keypress_event)

        self.fill_app_list(default=True)
        self._fill_flow_list()
        self.apps_close.connect('clicked', self._hide_window)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_search.connect('search-changed', self._do_search)
        self.template_selector.main_window.connect(
            'template-changed', self.template_change_registered)

        self.apps_list.set_filter_func(self._filter_func_app_list)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_filter_func(self._filter_func_other_list)

        self.apps_window.connect('delete-event', self._hide_window)
        self._fill_others_list()

    @staticmethod
    def _cmp(a, b):
        """Helper comparison function, made to comply with Gtk specs"""
        return (a > b) - (b > a)

    def _sort_func_app_list(self, x: ApplicationRow, y: ApplicationRow):
        selection_comparison = self._cmp(not x.is_selected(),
                                         not y.is_selected())
        if selection_comparison == 0:
            return self._cmp(x.appdata.name, y.appdata.name)
        return self._cmp(not x.is_selected(), not y.is_selected())

    def _filter_func_app_list(self, x: ApplicationRow):
        search_text = self.apps_search.get_text()
        if search_text:
            return search_text.lower() in x.appdata.name.lower()
        return True

    def _filter_func_other_list(self, x: ApplicationRow):
        if not self.apps_list_placeholder.get_mapped():
            return False
        if not self.template_selector.is_given_template_available(
                x.appdata.template):
            return False
        return self._filter_func_app_list(x)

    def _do_search(self, *_args):
        self.apps_list.invalidate_filter()
        if self.apps_list_placeholder.get_mapped():
            self.apps_list_other.invalidate_filter()
            self.apps_list_other.set_visible(True)
            self.label_other_templates.set_visible(True)
        else:
            self.apps_list_other.set_visible(False)
            self.label_other_templates.set_visible(False)

    def template_change_registered(self, *_args):
        """
        Fired after template change is noticed.
        """
        self.fill_app_list(default=True)
        self._fill_flow_list()

    def fill_app_list(self, default=False):
        """Fill application list with apps matching current template."""
        for child in self.apps_list.get_children():
            self.apps_list.remove(child)

        template_vm = self.template_selector.get_selected_template()
        self.label_apps.set_visible(template_vm is not None)
        self.label_apps_explain.set_visible(template_vm is not None)
        if not template_vm:
            return

        available_applications = self.template_selector.get_available_apps(
            template_vm)
        selected = []
        if default:
            selected = ['firefox.desktop', 'exo-terminal-emulator.desktop',
                        'xterm.desktop', 'firefox-esr.desktop']
        else:
            for button in self.flowbox.get_children():
                appdata = getattr(button.get_child(), 'appdata', None)
                if appdata:
                    selected.append(appdata.ident)

        for app in available_applications:
            row = ApplicationRow(app)
            self.apps_list.add(row)
            if app.ident in selected:
                self.apps_list.select_row(row)
            row.show_all()

    def _fill_others_list(self):
        # and the other apps
        for app in self.template_selector.get_available_apps():
            row = OtherTemplateApplicationRow(app)
            self.apps_list_other.add(row)
        self.apps_list_other.set_visible(False)
        self.apps_list_other.connect('row-activated', self._ask_template_change)

    def _hide_template_change(self, *_args):
        self.change_template_msg.hide()

    def _do_template_change(self, *_args):
        if self.target_template_name_widget:
            self.template_selector.select_template(
                self.target_template_name_widget.vm)
        self._hide_template_change()
        self._hide_window()

    def _ask_template_change(self, _widget, row, *_args):
        if self.target_template_name_widget:
            self.change_template_box.remove(self.target_template_name_widget)

        self.target_template_name_widget = QubeName(row.appdata.template)
        self.change_template_box.pack_start(
            self.target_template_name_widget, False, False, 0)

        self.change_template_msg.show()

    def _keypress_change_template(self, _widget, event, *_args):
        if event.keyval == Gdk.KEY_Escape:
            self._hide_template_change()
            return True
        if event.keyval == Gdk.KEY_ISO_Enter:
            self._do_template_change()
            return True
        return False

    def _fill_flow_list(self):
        template_vm = self.template_selector.get_selected_template()
        if template_vm is None:
            self.flowbox.set_visible(False)
            return
        self.flowbox.set_visible(True)
        for child in self.flowbox:
            self.flowbox.remove(child)

        for child in self.apps_list.get_children():
            if child.is_selected():
                button = ApplicationButton(child.appdata)
                button.connect('clicked', self._app_button_clicked)
                self.flowbox.add(button)
        plus_button = AddButton()
        plus_button.connect('clicked', self._choose_apps)
        # need interaction with Template object
        self.flowbox.add(plus_button)
        self.flowbox.show_all()

    def _app_button_clicked(self, widget, *_args, **_kwargs):
        self.flowbox.remove(widget)

    def _choose_apps(self, *_args, **_kwargs):
        self.fill_app_list()
        self.apps_window.show()

    def _keypress_event(self, _widget, event, *_args):
        if event.keyval == Gdk.KEY_Escape:
            self._hide_window()
            return True
        return False

    def _hide_window(self, *_args):
        self._fill_flow_list()
        self.apps_window.hide()
        return True  # when connected to delete-event, this tells Gtk to
        # not attempt to destroy the window


class TemplateSelector(abc.ABC):
    """
    Abstract base class for various variants of template/source VM selection.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        self.qapp = qapp
        self.main_window = gtk_builder.get_object('main_window')

    @abc.abstractmethod
    def set_visible(self, state: bool):
        """
        Used whenever visibility of the widgets should change.
        :param state: bool, True for visible, False for hidden
        :return: None
        """

    @abc.abstractmethod
    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """
        Return which VM (if any) is currently selected.
        :return: None or QubesVM
        """

    @abc.abstractmethod
    def select_vm(self, vm_name: str):
        """
        Select a vm given by name.
        :param vm_name: str of vm's name
        :return: None
        """

    def emit_signal(self, widget=None):
        """
        Emit signal signifying template change to the main window widget.
        :param widget: widget emitting the signal
        :return: None
        """
        if widget is None or widget.get_active():
            self.main_window.emit('template-changed', None)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """


class TemplateSelectorCombo(TemplateSelector):
    """
    Simple combobox selector.
    """
    def __init__(self, gtk_builder: Gtk.Builder,
                 qapp: qubesadmin.Qubes,
                 name_suffix: str,
                 filter_function: Callable[[qubesadmin.vm.QubesVM], bool],
                 default_value: Optional[qubesadmin.vm.QubesVM]):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        :param name_suffix: suffix of the object names, expected names are
        label_template_suffix, label_template_explanation_suffix and
        combo_template_suffix
        :param filter_function: function used to filter available VMs
        :param default_value: optional value to be marked as (default) and
        selected
        """
        super().__init__(gtk_builder, qapp)

        self.label: Gtk.Label = \
            gtk_builder.get_object(f'label_template_{name_suffix}')
        self.explain_label: Gtk.Label = \
            gtk_builder.get_object(f'label_template_explanation_{name_suffix}')
        self.combo: Gtk.ComboBox = \
            gtk_builder.get_object(f'combo_template_{name_suffix}')

        self.modeler = VMListModeler(
            combobox=self.combo, qapp=self.qapp,
            filter_function=filter_function, event_callback=self.emit_signal,
            default_value=default_value)

    def set_visible(self, state: bool):
        """Change visibility of widgets to state (True-visible, False-hidden)"""
        self.label.set_visible(state)
        self.combo.set_visible(state)
        self.explain_label.set_visible(state)
        if state:
            self.emit_signal(self.combo)

    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get selected QubesVM object"""
        return self.modeler.get_selected()

    def select_vm(self, vm_name: str):
        """Select qube provided by name."""
        self.modeler.select_value(vm_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """
        return self.modeler.is_vm_available(vm)


class TemplateSelectorNoneCombo(TemplateSelector):
    """
    Selector for a combination of None/combobox with VMs.
    """
    def __init__(self, gtk_builder: Gtk.Builder,
                 qapp: qubesadmin.Qubes,
                 name_suffix: str,
                 filter_function: Callable[[qubesadmin.vm.QubesVM], bool],
                 default_value: Optional[qubesadmin.vm.QubesVM]):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        :param name_suffix: suffix of the object names
        :param filter_function: function used to filter available VMs
        :param default_value: optional value to be marked as (default) and
        selected
        """
        super().__init__(gtk_builder, qapp)

        self.label: Gtk.Label = \
            gtk_builder.get_object(f'label_template_{name_suffix}')
        self.explain_label: Gtk.Label = \
            gtk_builder.get_object(f'label_template_explanation_{name_suffix}')
        self.radio_none: Gtk.RadioButton = \
            gtk_builder.get_object(f'radio_{name_suffix}_none')
        self.box_template: Gtk.Box = \
            gtk_builder.get_object(f'box_radio_{name_suffix}')
        self.radio_template: Gtk.RadioButton = \
            gtk_builder.get_object(f'radio_template_{name_suffix}')
        self.combo_template: Gtk.ComboBox = \
            gtk_builder.get_object(f'combo_template_{name_suffix}')

        self.modeler = VMListModeler(
            combobox=self.combo_template, qapp=self.qapp,
            filter_function=filter_function, event_callback=self.emit_signal,
            default_value=default_value)

        self.radio_none.connect('toggled', self.emit_signal)
        self.radio_template.connect('toggled', self._radio_toggled)

    def _radio_toggled(self, widget: Gtk.RadioButton):
        if widget.get_active():
            self.combo_template.set_sensitive(True)
            self.emit_signal()
        else:
            self.combo_template.set_sensitive(False)

    def set_visible(self, state: bool):
        """Change visibility of widgets to state (True-visible, False-hidden)"""
        self.label.set_visible(state)
        self.explain_label.set_visible(state)
        self.radio_none.set_visible(state)
        self.box_template.set_visible(state)
        if state:
            self.emit_signal(self.combo_template)

    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get selected QubesVM object or None"""
        if self.radio_template.get_active():
            return self.modeler.get_selected()
        return None

    def select_vm(self, vm_name: str):
        """Select qube provided by name."""
        if vm_name is None:
            # this is a weird edge case that should not happen, but let's cover
            # it just in case
            self.radio_none.set_active(True)
        self.modeler.select_value(vm_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """
        return self.modeler.is_vm_available(vm)


class TemplateHandler:
    """Class to handle a collection of template selectors"""
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.main_window: Gtk.Window = gtk_builder.get_object('main_window')

        GObject.signal_new('template-changed',
                           self.main_window,
                           GObject.SIGNAL_RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))

        self.template_selectors: Dict[str, TemplateSelector] = {
            'qube_type_app': TemplateSelectorCombo(
                gtk_builder=gtk_builder, qapp=self.qapp, name_suffix='app',
                filter_function=lambda x: x.klass == 'TemplateVM',
                default_value=self.qapp.default_template),
            'qube_type_template': TemplateSelectorNoneCombo(
                gtk_builder=gtk_builder, qapp=self.qapp, name_suffix='template',
                filter_function=lambda x: x.klass == 'TemplateVM',
                default_value=None),
            'qube_type_standalone': TemplateSelectorNoneCombo(
                gtk_builder=gtk_builder, qapp=self.qapp,
                name_suffix='standalone',
                filter_function=lambda x: x.klass == 'TemplateVM' or
                                          x.klass == 'StandaloneVM',
                default_value=None),
            'qube_type_disposable': TemplateSelectorCombo(
                gtk_builder=gtk_builder, qapp=self.qapp, name_suffix='dispvm',
                filter_function=lambda x:
                getattr(x, 'template_for_dispvms', False),
                default_value=self.qapp.default_dispvm)}

        self.selected_type: Optional[str] = None
        self.change_vm_type('qube_type_app')

        self._application_data: \
            Dict[qubesadmin.vm.QubesVM, List[ApplicationData]] = {}
        self._collect_application_data()

    def change_vm_type(self, vm_type: str):
        """Change selector to one appropriate for the type of VM
        being created"""
        for selector_type, selector in self.template_selectors.items():
            selector.set_visible(selector_type == vm_type)
        self.selected_type = vm_type
        self.main_window.emit('template-changed', None)

    def get_selected_template(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get currently selected VM."""
        if self.selected_type:
            return self.template_selectors[self.selected_type].get_selected_vm()
        return None

    def is_given_template_available(self,
                                    template: qubesadmin.vm.QubesVM) -> bool:
        """Check if given qubesVM is among available templates."""
        if self.selected_type:
            return self.template_selectors[self.selected_type].is_vm_available(
                template)
        return False

    def _collect_application_data(self):
        for vm in self.qapp.domains:
            command = ['qvm-appmenus', '--get-available',
                       '--i-understand-format-is-unstable', '--file-field',
                       'Comment', vm.name]

            available_applications = [
                ApplicationData.from_line(line, template=vm)
                for line in subprocess.check_output(
                    command).decode().splitlines()]
            self._application_data[vm] = available_applications

    def get_available_apps(self, vm: Optional[qubesadmin.vm.QubesVM] = None):
        """Get apps available for a given template."""
        if vm:
            return self._application_data.get(vm, [])
        return [appdata for appdata_list
                in self._application_data.values() for appdata in appdata_list]

    def select_template(self, vm: str):
        """Selected a vm in the current selector as provided by vm name"""
        if self.selected_type:
            self.template_selectors[self.selected_type].select_vm(vm)


class NetworkSelector:
    """
    Class that handles network configuration.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp

        self.network_default_icon: Optional[Gtk.Image] = None
        self.network_default_name: Optional[Gtk.Label] = None
        self.network_tor_icon: Optional[Gtk.Image] = None
        self.network_tor_name: Optional[Gtk.Label] = None

        self.network_default_box: Gtk.Box = \
            gtk_builder.get_object('network_default_box')
        self.network_default_box.pack_start(
            QubeName(self.qapp.default_netvm), False, False, 0)

        self.network_tor_box: Gtk.Box = \
            gtk_builder.get_object('network_tor_box')
        self.network_custom: Gtk.RadioButton = \
            gtk_builder.get_object('network_custom')
        self.network_custom_combo: Gtk.ComboBox = \
            gtk_builder.get_object('network_custom_combo')
        self.network_custom.connect('toggled', self._custom_toggled)

        self.network_none: Gtk.RadioButton = \
            gtk_builder.get_object('network_none')
        self.network_tor: Gtk.RadioButton = \
            gtk_builder.get_object('network_tor')
        self.network_default: Gtk.RadioButton = \
            gtk_builder.get_object('network_default')

        if WHONIX_QUBE_NAME in self.qapp.domains:
            self.network_tor_box.pack_start(
                QubeName(self.qapp.domains[WHONIX_QUBE_NAME]), False, False, 0)
        else:
            self.network_tor_box.set_visible(False)

        self.network_modeler = VMListModeler(
            self.network_custom_combo, self.qapp,
            lambda x: getattr(x, 'provides_network', False))

        self.network_tor.connect('toggled', self._netvm_changed)
        self.network_none.connect('toggled', self._netvm_changed)
        self.network_default.connect('toggled', self._netvm_changed)
        self.network_custom.connect('toggled', self._netvm_changed)
        self.network_custom_combo.connect('changed', self._netvm_changed_combo)

        self.network_current_box: Gtk.Box = \
            gtk_builder.get_object('box_network_current')
        self.network_current_none: Gtk.Label = \
            gtk_builder.get_object('label_current_network_none')
        self.network_current_widget = QubeName(self.qapp.default_netvm)
        self.network_current_box.pack_start(
            self.network_current_widget, False, False, 3)
        self.network_current_none.set_visible(False)

        self.button_toggle_settings: Gtk.EventBox = \
            gtk_builder.get_object('eventbox_network_current')
        self.box_network_settings: Gtk.Box = \
            gtk_builder.get_object('box_network_settings')
        self.expander_image: Gtk.Image = \
            gtk_builder.get_object('network_settings_expander_icon')
        self.button_toggle_settings.connect(
            'button-release-event', self._show_hide_more)

    def _show_hide_more(self, *_args):
        self.box_network_settings.set_visible(
            not self.box_network_settings.get_visible())
        if self.box_network_settings.get_visible():
            self.expander_image.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-shown', 20, 0))
        else:
            self.expander_image.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-hidden', 18, 0))

    def _custom_toggled(self, widget):
        self.network_custom_combo.set_sensitive(widget.get_active())

    def _netvm_changed_combo(self, _widget):
        self._netvm_changed(None)

    def _netvm_changed(self, widget: Optional[Gtk.RadioButton]):
        if widget and not widget.get_active():
            # do not perform this twice for every change of netvm
            return
        current_netvm = self.get_selected_netvm()
        self.network_current_none.set_visible(current_netvm is None)
        self.network_current_box.remove(self.network_current_widget)

        if current_netvm == qubesadmin.DEFAULT:
            current_netvm = self.qapp.default_netvm

        if current_netvm:
            self.network_current_widget = QubeName(current_netvm)
            self.network_current_box.pack_start(self.network_current_widget,
                                                False, False, 3)

    def get_selected_netvm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get which vm (if any) is selected as netvm"""
        if self.network_none.get_active():
            return None
        if self.network_tor.get_active():
            return self.qapp.domains[WHONIX_QUBE_NAME]
        if self.network_custom.get_active():
            tree_iter = self.network_custom_combo.get_active_iter()
            if tree_iter is not None:
                model = self.network_custom_combo.get_model()
                netvm = self.qapp.domains[model[tree_iter][1]]
                return netvm
        return qubesadmin.DEFAULT


def init_combobox_with_icons(combobox: Gtk.ComboBox,
                             data: List[Tuple[str, str]]):
    """
    Create a combobox with icons
    :param combobox: Gtk.ComboBox widget
    :param data: list of tuples of text and icon name for combobox contents
    """
    store = Gtk.ListStore(GdkPixbuf.Pixbuf, str)

    for text, icon in data:
        pixbuf = Gtk.IconTheme.get_default().load_icon(icon, 20, 0)
        store.append([pixbuf, text])

    combobox.set_model(store)
    renderer = Gtk.CellRendererPixbuf()
    combobox.pack_start(renderer, False)
    combobox.add_attribute(renderer, "pixbuf", 0)

    renderer = Gtk.CellRendererText()
    combobox.pack_start(renderer, False)
    combobox.add_attribute(renderer, "text", 1)


class CreateNewQube(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, qapp):
        """
        :param qapp: qubesadmin.Qubes object
        """
        super().__init__(application_id='org.qubesos.newqube')
        self.qapp: qubesadmin.Qubes = qapp

        self.builder: Optional[Gtk.Builder] = None
        self.main_window: Optional[Gtk.Window] = None
        self.template_selector: Optional[TemplateSelector] = None

        self.qube_name: Optional[Gtk.Entry] = None
        self.qube_label: Optional[Gtk.ComboBox] = None
        self.apps: Optional[Gtk.FlowBox] = None

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        self.perform_setup()
        assert self.main_window
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, '../new_qube.glade'))
        # self.builder.add_from_file('new_qube.glade')

        self.main_window = self.builder.get_object('main_window')
        self.qube_name = self.builder.get_object('qube_name')
        self.qube_label = self.builder.get_object('qube_label')

        self._handle_theme()

        self.template_handler = TemplateHandler(self.builder, self.qapp)

        self.apps = self.builder.get_object('applications')

        self.qube_type_app: Gtk.RadioButton = \
            self.builder.get_object('qube_type_app')
        self.qube_type_template: Gtk.RadioButton = \
            self.builder.get_object('qube_type_template')
        self.qube_type_standalone: Gtk.RadioButton = \
            self.builder.get_object('qube_type_standalone')
        self.qube_type_disposable: Gtk.RadioButton = \
            self.builder.get_object('qube_type_disposable')

        self.tooltips = {
            'qube_type_app': self.builder.get_object('qube_type_app_q'),
            'qube_type_template':
                self.builder.get_object('qube_type_template_q'),
            'qube_type_standalone':
                self.builder.get_object('qube_type_standalone_q'),
            'qube_type_disposable':
                self.builder.get_object('qube_type_disposable_q')
        }

        self.qube_type_app.connect('toggled', self._type_selected)
        self.qube_type_template.connect('toggled', self._type_selected)
        self.qube_type_standalone.connect('toggled', self._type_selected)
        self.qube_type_disposable.connect('toggled', self._type_selected)

        init_combobox_with_icons(
            self.qube_label,
            [(label, f'appvm-{label}') for label in self.qapp.labels])
        self.qube_label.set_active(0)
        self.qube_name.connect('changed', self._name_changed)

        self.network_selector = NetworkSelector(self.builder, self.qapp)

        self.app_box_handler = ApplicationBoxHandler(
            self.apps, self.builder, self.template_handler)

        self.advanced_events: Gtk.EventBox = \
            self.builder.get_object('eventbox_advanced')
        self.advanced_box: Gtk.Box = \
            self.builder.get_object('advanced_box')
        self.advanced_expander_icon: Gtk.Image = \
            self.builder.get_object('advanced_expander')
        self.advanced_expander_label: Gtk.Label = \
            self.builder.get_object('advanced_label')

        self.advanced_pool: Gtk.ComboBoxText = \
            self.builder.get_object('storage_pool_combobox')
        self.advanced_initram: Gtk.SpinButton = self.builder.get_object(
            'initram_spin_button')

        self._setup_advanced()

        self.create_button: Gtk.Button =  self.builder.get_object('qube_create')
        self.create_button.connect('clicked', self._do_create_qube)

    def _setup_advanced(self):
        self.advanced_events.connect(
            'button-release-event', self._show_hide_advanced)

        for pool in self.qapp.pools.values():
            if pool == self.qapp.default_pool:
                self.advanced_pool.append(str(pool), f'default ({pool})')
                self.advanced_pool.set_active_id(str(pool))
            else:
                self.advanced_pool.append(str(pool), str(pool))

        # discuss: max ram?
        self.advanced_initram.configure(
            Gtk.Adjustment(value=0, lower=0, upper=100000, step_increment=1,
                           page_increment=10, page_size=100),
            climb_rate=10, digits=0)

        self.advanced_initram.connect('output', self._format_initram)

    def _format_initram(self, _widget):
        value = self.advanced_initram.get_adjustment().get_value()
        if value == 0:
            text = '(default)'
        else:
            text = f'{value} MB'
        self.advanced_initram.set_text(text)
        return True

    def _show_hide_advanced(self, *_args):
        self.advanced_box.set_visible(
            not self.advanced_box.get_visible())
        if self.advanced_box.get_visible():
            self.advanced_expander_icon.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-shown', 20, 0))
            self.advanced_expander_label.set_text('Hide advanced settings')
        else:
            self.advanced_expander_icon.set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-expander-hidden', 18, 0))
            self.advanced_expander_label.set_text('Show advanced settings')

    @staticmethod
    def _handle_theme():
        # style_context = self.main_window.get_style_context()
        # window_default_color = style_context.get_background_color(
        #     Gtk.StateType.NORMAL)
        # TODO: future: determine light or dark scheme by checking if text is
        #  lighter or darker than background
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(pkg_resources.resource_filename(
            __name__, '../qubes-new-qube.css'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _name_changed(self, entry: Gtk.Entry):
        if not entry.get_text():
            self.create_button.set_sensitive(False)
        else:
            self.create_button.set_sensitive(True)

    def _type_selected(self, button: Gtk.RadioButton):
        button_name = button.get_name()
        if not button.get_active():
            self.tooltips[button_name].set_from_pixbuf(
                Gtk.IconTheme.get_default().load_icon(
                    'qubes-question', 20, 0))
            return
        self.template_handler.change_vm_type(button_name)
        self.tooltips[button_name].set_from_pixbuf(
            Gtk.IconTheme.get_default().load_icon(
                'qubes-question-light', 20, 0))

    def _do_create_qube(self, *_args, **_kwargs):
        if not self.qube_label or not self.qube_name:
            raise ValueError

        tree_iter = self.qube_label.get_active_iter()
        if tree_iter is not None:
            model = self.qube_label.get_model()
            label = self.qapp.labels[model[tree_iter][1]]
        else:
            return

        args = {
            "name": self.qube_name.get_text(),
            "label": label,
            "template": self.template_handler.get_selected_template()
        }
        vm: qubesadmin.vm.QubesVM = self.qapp.add_new_vm('AppVM', **args)

        apps = []
        for child in self.app_box_handler.flowbox.get_children():
            appdata = getattr(child.get_child(), 'appdata', None)
            if appdata:
                apps.append(appdata.ident)

        with subprocess.Popen([
                'qvm-appmenus',
                '--set-whitelist', '-',
                '--update', vm.name],
                stdin=subprocess.PIPE) as p:
            p.communicate('\n'.join(apps).encode())

        vm.netvm = self.network_selector.get_selected_netvm()

        msg = Gtk.MessageDialog(
            self.main_window,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.OK,
            "Qube created successfully!")
        msg.run()
        # TODO: discuss: should we quit after a failure?
        self.quit()


def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    app = CreateNewQube(qapp)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
