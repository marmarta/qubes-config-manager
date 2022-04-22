#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application Menu class and helpers.
"""
# pylint: disable=import-error
import asyncio
import subprocess
import sys
from typing import Optional, List, Tuple
from contextlib import suppress
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-appmenu')

# TODO: what to do with commandline?
# TODO: window icons... maybe they should NOT all be "just qubes"
# TODO: check qube name length
# TODO: new template
# TODO: new standalone

class ApplicationBoxHandler:
    def __init__(self, flowbox):
        pass

def init_apps(flowbox: Gtk.FlowBox, vm: qubesadmin.vm.QubesVM):
    test_list = ['a', 'b', 'c']
    # TODO: some sort of appsmodel?
    for item in test_list:
        button = Gtk.Button()
        button.set_label(item)
        flowbox.add(button)

    flowbox.show_all()
    pass


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

        self.appqube_name: Optional[Gtk.Entry] = None
        self.appqube_label: Optional[Gtk.ComboBox] = None
        self.appqube_template_custom: Optional[Gtk.ComboBox] = None
        self.appqube_network_custom: Optional[Gtk.ComboBox] = None
        self.appqube_template_default_icon: Optional[Gtk.Image] = None
        self.appqube_template_default_name: Optional[Gtk.Label] = None
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
        self.appqube_template_custom = self.builder.get_object('appqube_template_custom_combo')
        self.appqube_template_default_icon = self.builder.get_object('appqube_template_default_icon')
        self.appqube_template_default_name = self.builder.get_object('appqube_template_default_name')
        self.appqube_network_default_icon = self.builder.get_object('appqube_network_default_icon')
        self.appqube_network_default_name = self.builder.get_object('appqube_network_default_name')
        self.appqube_network_tor_icon = self.builder.get_object('appqube_network_tor_icon')
        self.appqube_network_tor_name = self.builder.get_object('appqube_network_tor_name')
        self.appqube_network_custom = self.builder.get_object('appqube_network_custom_combo')
        self.appqube_apps = self.builder.get_object('appqube_applications')


        # TODO: make do that icons make sense, e.g. provides network make for a service qube icon
        init_combobox_with_icons(self.appqube_label,
                                 [(label, f'appvm-{label}') for label in self.qapp.labels])

        init_combobox_with_icons(
            self.appqube_template_custom, [(vm.name, vm.icon) for vm in self.qapp.domains if vm.klass == 'TemplateVM' and vm.name != self.qapp.default_template])
        # TODO: size
        # TODO: what if theres no default
        # TODO: make template dropdown not work if not selected

        self.appqube_template_default_icon.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                self.qapp.default_template.icon, 16, 0))
        self.appqube_template_default_name.set_text(self.qapp.default_template.name)

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

        init_apps(self.appqube_apps, None)
        # TODO: react to changed template


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

