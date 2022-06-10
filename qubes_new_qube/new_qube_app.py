#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application Menu class and helpers.
"""
# pylint: disable=import-error
import asyncio
import subprocess
import sys
from typing import Optional, List, Tuple, Dict, Callable
import abc
from contextlib import suppress
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm
from .qubes_widgets_library import QubeName, VMListModeler

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')
WHONIX_QUBE_NAME = 'sys-whonix'

# TODO: PLAN
# implement advanced options
# - launch settings
# - provides_network
# - storage_pool
# - init ram
# make vm type selection actually work
# - template (needs only actual do_create)
# - disp (needs only actual do_create)
# - standalone (needs only actual do_create)
# styling
# - initial styling pass
# - style the pretty window
# commandline
# window icon
# cleanup of the combobox model methods
# cleanup of custom dropdowns: should only activate when selected, or always active and set to selected when chosen
# light and dark themes: left panel

# TODO: fix blue etc to be more Nina

# move type to the side
# hide network and maybe template?
# select default stuff or first

# TODO: resize with advanced is weird.


class ApplicationData:
    """
    Class representing information about an available application.
    """
    def __init__(self, name: str, ident: str, comment: Optional[str] = None,
                 template: Optional[qubesadmin.vm.QubesVM] = None):
        self.name = name
        self.ident = ident
        self.template = template
        additional_description = ".desktop filename: " + str(self.ident)
        # TODO: get the icon is should have name related to desktop filename
        # TODO: template?

        file_name_root = self.ident[:-len('.desktop')]
        # TODO: this does not work for dispvm templates FFS
        # TODO: maybe let's not hardcode my home dir here, eh?
        self.icon_path = f'/home/marmarta/.local/share/qubes-appmenus/{template}/apps.tempicons/{file_name_root}.png'

        if not comment:
            self.comment = additional_description
        else:
            self.comment = comment + "\n" + additional_description

    @classmethod
    def from_line(cls, line, template=None):
        ident, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, ident=ident, comment=comment, template=template)


class ApplicationRow(Gtk.ListBoxRow):
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
        self.add(self.label)


class OtherTemplateApplicationRow(Gtk.ListBoxRow):
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
    # TODO: add application icon and remove icon
    def __init__(self, appdata: ApplicationData):
        super(ApplicationButton, self).__init__(label=None)
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)
        self.appdata = appdata

        # TODO: here do icon
        self.icon = Gtk.Image()
        self.icon.set_from_pixbuf(
            GdkPixbuf.Pixbuf.new_from_file_at_size(appdata.icon_path, 18, 18))

        self.box.pack_start(self.icon, False, False, 3)

        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.box.pack_start(self.label, False, False, 3)

        self.remove_icon = Gtk.Image()
        self.remove_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-delete', 14, 0))
        self.box.pack_end(self.remove_icon, False, False, 3)

        self.show_all()


class AddButton(Gtk.Button):
    def __init__(self, **properties):
        super(AddButton, self).__init__(properties)
        self.set_label("+")


class ApplicationBoxHandler:
    def __init__(self, flowbox: Gtk.FlowBox, gtk_builder: Gtk.Builder, template_selector):
        # TODO: tooltips
        # TODO: must hide itself after ESC or click outside
        # TODO: refresh?
        self.template_selector = template_selector
        self.flowbox = flowbox
        self.apps_window = gtk_builder.get_object('applications_popup')
        self.apps_list: Gtk.ListBox = gtk_builder.get_object('apps_list')
        self.label_apps: Gtk.Label = gtk_builder.get_object('label_apps')
        self.apps_close: Gtk.Button = gtk_builder.get_object('apps_close')
        self.apps_search: Gtk.SearchEntry = gtk_builder.get_object('apps_search')
        self.apps_list_placeholder: Gtk.Label = gtk_builder.get_object('apps_list_placeholder')
        self.apps_list_other: Gtk.ListBox = gtk_builder.get_object('apps_list_other_templates')

        self.fill_app_list(default=True)
        self.fill_flow_list()
        self.apps_close.connect('clicked', self.hide_window)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_search.connect('search-changed', self._do_search)
        self.template_selector.main_window.connect('template-changed', self.template_change_registered)

        self.apps_list.set_filter_func(self._filter_func_app_list)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_filter_func(self._filter_func_other_list)

        self.apps_window.connect('delete-event', self.hide_window)
        self._fill_others_list()

    def _cmp(self, a, b):
        if a == b:
            return 0
        if a < b:
            return -1
        return 1

    def _sort_func_app_list(self, x: ApplicationRow, y: ApplicationRow):
        selection_comparison = self._cmp(not x.is_selected(), not y.is_selected())
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
        return self._filter_func_app_list(x)

# TODO: install to template
# TODO: when looks good, make behavior after clicking nicer

    def _do_search(self, *args, **kwargs):
        self.apps_list.invalidate_filter()
        if self.apps_list_placeholder.get_mapped():
            self.apps_list_other.invalidate_filter()
            self.apps_list_other.set_visible(True)
        else:
            self.apps_list_other.set_visible(False)

    def template_change_registered(self, *args, **kwargs):
        self.fill_app_list(default=True)
        self.fill_flow_list()

    def fill_app_list(self, default=False):
        for child in self.apps_list.get_children():
            self.apps_list.remove(child)

        template_vm = self.template_selector.get_selected_template()
        self.label_apps.set_visible(template_vm is not None)
        if not template_vm:
            return

        available_applications = self.template_selector.get_available_apps(template_vm)
        selected = []
        if default:
            # TODO use get default list when merged
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

    def _ask_template_change(self, widget, row, *args):
        # TODO: aadd pretty template name and icon
        msg = Gtk.MessageDialog(self.apps_window,
                                         Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                         Gtk.MessageType.QUESTION,
                                         Gtk.ButtonsType.OK_CANCEL,
                                         "Do you want to switch the template to ?")
        response = msg.run()

        if response == Gtk.ResponseType.OK:
            self.template_selector.select_template(row.appdata.template.name)
        self.hide_window()
        msg.destroy()

    def fill_flow_list(self):
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
        # TODO: prettier plus icon
        plus_button.connect('clicked', self._choose_apps)
        # need interaction with Template object
        self.flowbox.add(plus_button)
        self.flowbox.show_all()

    def _app_button_clicked(self, widget, *args, **kwargs):
        self.flowbox.remove(widget)

    def _choose_apps(self, *args, **kwargs):
        # TODO: KEYBOARD NAV
        self.fill_app_list()
        self.apps_window.show_all()

    def hide_window(self, *args, **kwargs):
        self.fill_flow_list()
        self.apps_window.hide()
        return True  # when connected to delete-event, this tells Gtk to not attempt to destroy the window

# TODO: accessiblity show help how?


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

# TODO: some error with choosing apps appeared after the refactor


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
        self.modeler.select_entry(vm_name)


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
        self.modeler.select_entry(vm_name)


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

        self.selected_type = None
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

    def get_selected_template(self):
        """Get currently selected VM."""
        return self.template_selectors[self.selected_type].get_selected_vm()

    def _collect_application_data(self):
        # TODO: check if this works for dispvms
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
        self.template_selectors[self.selected_type].select_vm(vm)


class NetworkSelector:
    # TODO: hide tor if unavailable
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        self.qapp = qapp

        self.network_default_icon: Optional[Gtk.Image] = None
        self.network_default_name: Optional[Gtk.Label] = None
        self.network_tor_icon: Optional[Gtk.Image] = None
        self.network_tor_name: Optional[Gtk.Label] = None

        self.network_default_box: Gtk.Box = gtk_builder.get_object('network_default_box')
        self.network_default_box.pack_start(QubeName(self.qapp.default_netvm), False, False, 0)

        self.network_tor_box: Gtk.Box = gtk_builder.get_object('network_tor_box')
        self.network_custom: Gtk.RadioButton = gtk_builder.get_object('network_custom')
        self.network_custom_combo: Gtk.ComboBox = gtk_builder.get_object('network_custom_combo')
        self.network_custom.connect('toggled', self._custom_toggled)

        self.network_none: Gtk.RadioButton = gtk_builder.get_object('network_none')

        self.network_tor: Gtk.RadioButton = gtk_builder.get_object('network_tor')

        if WHONIX_QUBE_NAME in self.qapp.domains:
            self.network_tor_box.pack_start(QubeName(self.qapp.domains[WHONIX_QUBE_NAME]), False, False, 0)
        else:
            self.network_tor_box.set_visible(False)

        self.network_modeler = VMListModeler(self.network_custom_combo, self.qapp, lambda x: getattr(x, 'provides_network', False))

    def _custom_toggled(self, widget):
        self.network_custom_combo.set_sensitive(widget.get_active())

    def get_selected_netvm(self):
        if self.network_none.get_active():
            return None
        if self.network_tor.get_active():
            return self.qapp.domains['sys-whonix']
        if self.network_custom.get_active():
            tree_iter = self.network_custom_combo.get_active_iter()
            if tree_iter is not None:
                model = self.network_custom_combo.get_model()
                netvm = self.qapp.domains[model[tree_iter][1]]
                return netvm
        return qubesadmin.DEFAULT


# TODO: better model...

def init_combobox_with_icons(combobox: Gtk.ComboBox, data: List[Tuple[str, str]]):
    store = Gtk.ListStore(GdkPixbuf.Pixbuf, str)

    for text, icon in data:
        # TODO: icon SIZES
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
        self.main_window.show()
        self.hold()
# TODO: make buttons work
# TODO: importing should be nicer and refer to an external library

    def perform_setup(self):
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(pkg_resources.resource_filename(
            __name__, 'qubes-new-qube.css'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, 'new_qube.glade'))
        # self.builder.add_from_file('new_qube.glade')

        self.main_window = self.builder.get_object('main_window')
        self.qube_name = self.builder.get_object('qube_name')
        self.qube_label = self.builder.get_object('qube_label')

        self.template_handler = TemplateHandler(self.builder, self.qapp)

        self.apps = self.builder.get_object('applications')

        self.qube_type_app: Gtk.RadioButton = self.builder.get_object('qube_type_app')
        self.qube_type_template: Gtk.RadioButton = self.builder.get_object('qube_type_template')
        self.qube_type_standalone: Gtk.RadioButton = self.builder.get_object('qube_type_standalone')
        self.qube_type_disposable: Gtk.RadioButton = self.builder.get_object('qube_type_disposable')

        self.tooltips = {
            'qube_type_app': self.builder.get_object('qube_type_app_q'),
            'qube_type_template': self.builder.get_object('qube_type_template_q'),
            'qube_type_standalone': self.builder.get_object('qube_type_standalone_q'),
            'qube_type_disposable': self.builder.get_object('qube_type_disposable_q')
        }

        self.qube_type_app.connect('toggled', self._type_selected)
        self.qube_type_template.connect('toggled', self._type_selected)
        self.qube_type_standalone.connect('toggled', self._type_selected)
        self.qube_type_disposable.connect('toggled', self._type_selected)

        # TODO: make do that icons make sense, e.g. provides network make for a service qube icon
        init_combobox_with_icons(self.qube_label,
                                 [(label, f'appvm-{label}') for label in self.qapp.labels])
        self.qube_label.set_active(0)
        self.qube_name.connect('changed', self._name_changed)

        # TODO: what is def netvm is none - qubename should handle that

        # TODO: order of network buttons

        self.network_selector = NetworkSelector(self.builder, self.qapp)

        self.app_box_handler = ApplicationBoxHandler(self.apps, self.builder, self.template_handler)
        # TODO: react to changed template

        self.create_button: Gtk.Button =  self.builder.get_object('qube_create')
        self.create_button.connect('clicked', self.do_create_qube)

    def _name_changed(self, entry: Gtk.Entry):
        if not entry.get_text():
            self.create_button.set_sensitive(False)
        else:
            self.create_button.set_sensitive(True)
            # TODO: needs a tooltip to inform user what is missing

    def _type_selected(self, button: Gtk.RadioButton):
        button_name = button.get_name()
        if not button.get_active():
            self.tooltips[button_name].set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-question', 20, 0))
            return
        self.template_handler.change_vm_type(button_name)
        self.tooltips[button_name].set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                'qubes-question-light', 20, 0))

    def do_create_qube(self, *args, **kwargs):
        # TODO: check for validation, this can actually be done with events and make the create inactive until name etc chosen

        # TODO: make better label handling because ughhhh
        tree_iter = self.qube_label.get_active_iter()
        if tree_iter is not None:
            model = self.qube_label.get_model()
            label = self.qapp.labels[model[tree_iter][1]]
        else:
            # TODO: NO THIS WHOLE SHIT NEEDS A CUSTOM CLASS
            return

        args = {
            "name": self.qube_name.get_text(),
            "label": label,
            "template": self.template_handler.get_selected_template() # TODO: what if none
        }
        vm: qubesadmin.vm.QubesVM = self.qapp.add_new_vm('AppVM', **args)

        # TODO: set apps
        # TODO: extract this
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
            # TODO: error handling, error handling everywhere

        vm.netvm = self.network_selector.get_selected_netvm()

        msg = Gtk.MessageDialog(self.main_window,
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

# TODO: menu bug with deleting VMS.... ughghgh
# TODO: refresh button in app picker?
