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
from typing import Optional, List, Tuple
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm
from .application_selector import ApplicationBoxHandler
from .template_handler import TemplateHandler, TemplateSelector
from .network_selector import NetworkSelector

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')
WHONIX_QUBE_NAME = 'sys-whonix'


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

        self.create_button: Gtk.Button = \
            self.builder.get_object('create_button')
        self.create_button.connect('clicked', self._do_create_qube)

        self.cancel_button: Gtk.Button = \
            self.builder.get_object('cancel_button')
        self.cancel_button.connect('clicked', self._quit)

        self.main_window.connect('delete-event', self._quit)

    def _quit(self, _widget, *args):
        self.quit()

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
