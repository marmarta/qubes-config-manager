#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application Menu class and helpers.
"""
# pylint: disable=import-error
import asyncio
import subprocess
import sys
from typing import Optional, List, Tuple, Dict
from contextlib import suppress
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-appmenu')

# TODO: what to do with commandline?
# TODO: window icons... maybe they should NOT all be "just qubes"
# TODO: check qube name length
# TODO: new template
# TODO: new standalone

# TODO: make a Network object
# TODO: strongly rethink the whole arrangement, maybe a notebook?
# TODO: make a Template object
# TODO: make the App Box Handler better, smarter, lovelier

# TODO: get apps

class ApplicationData:
    def __init__(self, name: str, ident: str, comment: Optional[str] = None):
        self.name = name
        self.ident = ident
        additional_description = ".desktop filename: " + str(self.ident)

        if not comment:
            self.comment = additional_description
        else:
            self.comment = comment + "\n" + additional_description

    @classmethod
    def from_line(cls, line):
        ident, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, ident=ident, comment=comment)


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


class ApplicationButton(Gtk.Button):
    # TODO: add icon
    def __init__(self, appdata: ApplicationData):
        super(ApplicationButton, self).__init__(label=None)
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)
        self.appdata = appdata
        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.box.add(self.label)
        self.show_all()


class AddButton(Gtk.Button):
    def __init__(self, **properties):
        super(AddButton, self).__init__(properties)
        self.set_label("+")


class ApplicationBoxHandler:
    def __init__(self, flowbox: Gtk.FlowBox, gtk_builder: Gtk.Builder, template_selector):
        # TODO: tooltips
        # TODO: must hide itself
        self.template_selector = template_selector
        self.flowbox = flowbox
        # TODO: check for lack of template change
        self.apps_window = gtk_builder.get_object('applications_popup')
        self.apps_list: Gtk.ListBox = gtk_builder.get_object('apps_list')
        self.apps_close: Gtk.Button = gtk_builder.get_object('apps_close')
        self.apps_search: Gtk.SearchEntry = gtk_builder.get_object('apps_search')
        # TODO: make pretty
        self.fill_app_list()
        self.fill_flow_list()
        self.apps_close.connect('clicked', self.hide_window)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_search.connect('search-changed', self._do_search)
        self.template_selector.main_window.connect('template-changed', self.template_change_registered)

    # TODO: connect ESC
    # TODO: refresh do it one day

    # TODO: add other templates

    def _sort_func_app_list(self, x: ApplicationRow, y: ApplicationRow):
        return x.is_selected() < y.is_selected()

    def _filter_func_app_list(self, x: ApplicationRow):
        search_text = self.apps_search.get_text()
        if search_text:
            return search_text.lower() in x.name.lower()
        return True

    def _do_search(self, *args, **kwargs):
        self.apps_list.set_filter_func(self._filter_func_app_list)

    # TODO: what to do when template changes; keep old selected apps?
    def template_change_registered(self, *args, **kwargs):
        self.fill_app_list()
        self.fill_flow_list()

    def fill_app_list(self):
        for child in self.apps_list.get_children():
            self.apps_list.remove(child)

        template_vm = self.template_selector.get_selected_template()
        available_applications = self.template_selector.get_available_apps(template_vm)
# TODO: I NEED THE GET DEFAULT WHITELIST

        for app in available_applications:
            row = ApplicationRow(app)
            self.apps_list.add(row)
            if app.name in ['Firefox', 'Files', 'Terminal']:
                self.apps_list.select_row(row)
            row.show_all()

        self.apps_list.set_sort_func()

    def fill_flow_list(self):
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

    def _app_button_clicked(self, widget, *args, **kwargs):
        self.flowbox.remove(widget)

    def _choose_apps(self, *args, **kwargs):
        # TODO: KEYBOARD NAV
        # TODO: what is there is no template
        self.fill_app_list()
        self.apps_window.show_all()
        # TODO: hide after esc
        # TODO: or click outside
        # TODO: what are defaults??? add them

    def hide_window(self, *args, **kwargs):
        self.fill_flow_list()
        self.apps_window.hide()


class TemplateSelector:
    def __init__(self, gtk_builder: Gtk.Builder, prefix: str, qapp: qubesadmin.Qubes):
        self.prefix = prefix
        self.qapp = qapp

        self.default_template = self.qapp.default_template

        self.default_radio: Gtk.RadioButton = gtk_builder.get_object(f'{self.prefix}_template_default')
        self.default_icon: Gtk.Image = gtk_builder.get_object(f'{self.prefix}_template_default_icon')
        self.default_name: Gtk.Label = gtk_builder.get_object(f'{self.prefix}_template_default_name')
        self.custom_radio: Gtk.RadioButton = gtk_builder.get_object(f'{self.prefix}_template_custom')
        self.custom_combo: Gtk.ComboBox = gtk_builder.get_object(f'{self.prefix}_template_custom_combo')
        self.main_window: Gtk.Window = gtk_builder.get_object('main_window')

        GObject.signal_new('template-changed',
                           self.main_window,
                           GObject.SIGNAL_RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))


        init_combobox_with_icons(
            self.custom_combo, [(vm.name, vm.icon) for vm in self.qapp.domains if vm.klass == 'TemplateVM' and vm.name != self.default_template])
        # TODO: size
        # TODO: what if theres no default
        # TODO: make template dropdown not work if not selected

        self.default_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                self.qapp.default_template.icon, 16, 0))
        self.default_name.set_text(self.default_template.name)

        self._application_data: Dict[qubesadmin.vm.QubesVM, List[ApplicationData]] = {}
        self._collect_application_data()

        self.default_radio.connect('toggled', self._emit_signal)
        self.custom_radio.connect('toggled', self._custom_toggled)
        self.custom_combo.connect('changed', self._custom_combo_selected)

    def _emit_signal(self, widget, *args, **kwargs):
        if widget.get_active():
            # TODO: shit custom is weird
            self.main_window.emit('template-changed', None)

    def _custom_toggled(self, widget, *args, **kwargs):
        if widget.get_active():
            # TODO: select first in combobox?
            self.custom_combo.set_sensitive(True)
            if self.custom_combo.get_active() == -1:
                self.custom_combo.set_active(0)
        else:
            self.custom_combo.set_sensitive(False)

    def _custom_combo_selected(self, widget):
        self.main_window.emit('template-changed', None)

    def get_selected_template(self, *args):
        if self.default_radio.get_active():
            return self.default_template
        tree_iter = self.custom_combo.get_active_iter()
        if tree_iter is not None:
            model = self.custom_combo.get_model()  # TODO: probably can just init this model here and store it
            # TODO: just store vms in the model, if possible?
            return self.qapp.domains[model[tree_iter][1]]

    def _collect_application_data(self):
        for vm in self.qapp.domains:
            if vm.klass != 'TemplateVM':
                continue
            command = ['qvm-appmenus', '--get-available',
                       '--i-understand-format-is-unstable', '--file-field',
                       'Comment', vm.name]

            available_applications = [
                ApplicationData.from_line(line)
                for line in subprocess.check_output(
                    command).decode().splitlines()]
            self._application_data[vm] = available_applications

    def get_available_apps(self, vm: qubesadmin.vm.QubesVM):
        return self._application_data.get(vm, [])


def init_combobox_with_icons(combobox: Gtk.ComboBox, data: List[Tuple[str, str]]):
    store = Gtk.ListStore(GdkPixbuf.Pixbuf, str)

    for text, icon in data:
        # TODO: icon SIZES
        pixbuf = Gtk.IconTheme.get_default().load_icon(icon, 16, 0)
        store.append([pixbuf, text])

    combobox.set_model(store)

    renderer = Gtk.CellRendererPixbuf()
    combobox.pack_start(renderer, True)
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

        self.appqube_name: Optional[Gtk.Entry] = None
        self.appqube_label: Optional[Gtk.ComboBox] = None
        self.appqube_network_custom: Optional[Gtk.ComboBox] = None
        self.appqube_network_default_icon: Optional[Gtk.Image] = None
        self.appqube_network_default_name: Optional[Gtk.Label] = None
        self.appqube_network_tor_icon: Optional[Gtk.Image] = None
        self.appqube_network_tor_name: Optional[Gtk.Label] = None
        self.appqube_apps: Optional[Gtk.FlowBox] = None

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        self.perform_setup()
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        # provider.load_from_path(pkg_resources.resource_filename(
        #     __name__, 'qubes-new-qube.css')) # TODO: restore when packaging
        provider.load_from_path('qubes-new-qube.css')
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.builder = Gtk.Builder()
        # self.builder.add_from_file(pkg_resources.resource_filename(
        #     __name__, 'qubes-menu.glade'))
        self.builder.add_from_file('new_qube.glade')

        # TODO: move all this to new func
        self.main_window = self.builder.get_object('main_window')
        self.appqube_name = self.builder.get_object('appqube_name')
        self.appqube_label = self.builder.get_object('appqube_label')

        self.appqube_template_selector = TemplateSelector(self.builder, 'appqube', self.qapp)

        self.appqube_network_default_icon = self.builder.get_object('appqube_network_default_icon')
        self.appqube_network_default_name = self.builder.get_object('appqube_network_default_name')
        self.appqube_network_tor_icon = self.builder.get_object('appqube_network_tor_icon')
        self.appqube_network_tor_name = self.builder.get_object('appqube_network_tor_name')
        self.appqube_network_custom = self.builder.get_object('appqube_network_custom_combo')
        self.appqube_apps = self.builder.get_object('appqube_applications')

        # TODO: make do that icons make sense, e.g. provides network make for a service qube icon
        init_combobox_with_icons(self.appqube_label,
                                 [(label, f'appvm-{label}') for label in self.qapp.labels])

        # TODO: what is def netvm is none
        self.appqube_network_default_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                self.qapp.default_netvm.icon, 16, 0))
        self.appqube_network_default_name.set_text(self.qapp.default_netvm.name)

        # TODO: hide if nonexisting
        self.appqube_network_tor_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                self.qapp.domains['sys-whonix'].icon, 16, 0))
        self.appqube_network_tor_name.set_text('sys-whonix')

        # TODO: order of network buttons
        # TODO: hide unncesery network buttons

        init_combobox_with_icons(
            self.appqube_network_custom, [(vm.name, vm.icon) for vm in self.qapp.domains if getattr(vm, 'provides_network', False)])

        self.app_box_handler = ApplicationBoxHandler(self.appqube_apps, self.builder, self.appqube_template_selector)
        # TODO: react to changed template

        self.create_button =  self.builder.get_object('qube_create')
        self.create_button.connect('clicked', lambda x: print(self.appqube_template_selector.get_selected_template(x)))


def main():
    """
    Start the menu app
    """
    qapp = qubesadmin.Qubes()
    # dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    app = CreateNewQube(qapp)
    app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())

