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
from typing import Optional, List, Tuple, Dict, Any
import pkg_resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from .application_selector import ApplicationBoxHandler
from .template_handler import TemplateHandler, TemplateSelector
from .network_selector import NetworkSelector
from .advanced_handler import AdvancedHandler
from ..widgets.qubes_widgets_library import show_error
from ..widgets.gtk_utils import load_icon

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf


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
        pixbuf = load_icon(icon, 20, 20)
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

        self.advanced_handler = AdvancedHandler(self.builder, self.qapp)

        self.create_button: Gtk.Button = \
            self.builder.get_object('create_button')
        self.create_button.connect('clicked', self._do_create_qube)

        self.cancel_button: Gtk.Button = \
            self.builder.get_object('cancel_button')
        self.cancel_button.connect('clicked', self._quit)

        self.main_window.connect('delete-event', self._quit)

    def _quit(self, *_args):
        self.quit()

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
                load_icon('qubes-question', 20, 20))
            return
        self.template_handler.change_vm_type(button_name)
        self.tooltips[button_name].set_from_pixbuf(load_icon(
                'qubes-question-light', 20, 20))

    def _do_create_qube(self, *_args):
        if not self.qube_label or not self.qube_name:
            raise ValueError

        tree_iter = self.qube_label.get_active_iter()

        if tree_iter is not None:
            model = self.qube_label.get_model()
            label = self.qapp.labels[model[tree_iter][1]]
        else:
            return

        if self.qube_type_template.get_active():
            klass = 'TemplateVM'
        elif self.qube_type_standalone.get_active():
            klass = 'StandaloneVM'
        elif self.qube_type_disposable.get_active():
            klass = 'DisposableVM'
        else:
            klass = 'AppVM'

        properties: Dict[str, Any] = {'provides_network':
                          self.advanced_handler.get_provides_network()}
        if self.network_selector.get_selected_netvm():
            properties['netvm'] = self.network_selector.get_selected_netvm()
        if klass == 'StandaloneVM' and \
                not self.template_handler.get_selected_template():
            properties['virt_mode'] = 'hvm'
            properties['kernel'] = None

        if self.advanced_handler.get_init_ram():
            properties['memory'] = self.advanced_handler.get_init_ram()

        vm = None
        err = None

        try:
            vm = self._create_qube(
                vmclass=klass,
                name=self.qube_name.get_text(),
                label = label,
                template=self.template_handler.get_selected_template(),
                properties=properties,
                pool=self.advanced_handler.get_pool(),
            )
        except qubesadmin.exc.QubesException as qex:
            err  = str(qex)
        except Exception as ex:  # pylint: disable=broad-except
            err = repr(ex)

        if err or not vm:
            show_error("Could not create qube", f"An error occurred: {err}")
            return

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

        msg = Gtk.MessageDialog(
            self.main_window,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.OK,
            "Qube created successfully!")
        msg.run()

        if self.advanced_handler.get_launch_settings():
            subprocess.check_call(['qubes-vm-settings', str(vm)])
        if self.advanced_handler.get_install_system():
            subprocess.check_call(['qubes-vm-boot-from-device', str(vm)])

        # TODO: discuss: should we quit after a failure?
        self.quit()

    def _create_qube(self, vmclass, name, label, template,
                     properties, pool) -> qubesadmin.vm.QubesVM:
        if vmclass == 'StandaloneVM' and template is not None:
            args = {
                'ignore_volumes': ['private']
            }
            if pool:
                args['pool'] = pool

            vm = self.qapp.clone_vm(template, name, vmclass, **args)
            vm.label = label
            for k, v in properties.items():
                setattr(vm, k, v)
        else:
            args = {
                "name": name,
                "label": label,
                "template": template
            }
            if pool:
                args['pool'] = pool

            vm = self.qapp.add_new_vm(vmclass, **args)
            for k, v in properties.items():
                setattr(vm, k, v)

        return vm


def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    app = CreateNewQube(qapp)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
