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

# pylint: disable=import-error
import asyncio
import subprocess
import sys
import os
from typing import Optional, List, Tuple, Dict, Callable, Union
import abc
from contextlib import suppress
import pkg_resources
import logging
from functools import partial

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from ..widgets.qubes_widgets_library import QubeName, VMListModeler, TextModeler, TraitSelector, TypeName, ImageTextButton, show_error
from .policy_handler import PolicyManager, PolicyClient, ConflictFileHandler, PolicyHandler

import gi

import qubesadmin

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')

class TraitHolder(abc.ABC):
    def __init__(self, relevant_widget: TraitSelector):
        """
        :param relevant_widget: widget that contains relevant property data
        """
        self.relevant_widget = relevant_widget

    @abc.abstractmethod
    def set_trait(self, new_value):
        """
        Set the appropriate trait, if changed.
        """

    @abc.abstractmethod
    def get_current_value(self):
        """
        Return whatever is the current value of the trait,
        :return:
        """


def get_feature(vm, feature_name, default_value=None):
    """
    get feature value
    """
    try:
        return vm.features.get(feature_name, default_value)
    except qubesadmin.exc.QubesDaemonAccessError:
        return default_value


def get_boolean_feature(vm, feature_name):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    return result


class VMFeatureHolder(TraitHolder):
    def __init__(self, feature_name: str, feature_holder: qubesadmin.vm.QubesVM,
                 default_value, relevant_widget: TraitSelector,
                 is_boolean: bool = False):
        """
        :param feature_name: name of the feature
        :param feature_holder: object that has the feature
        :param default_value: default feature value
        :param relevant_widget: widget that contains relevant property data
        :param is_boolean: is the feature a bool? (needed because boolean
        features are encoded as 1 or empty string)
        """
        super().__init__(relevant_widget)
        self.feature_holder = feature_holder
        self.feature_name = feature_name
        self.default_value = default_value
        self.is_boolean = is_boolean
        if self.is_boolean:
            self.current_value = self._get_boolean_feature()
        else:
            self.current_value = self._get_feature()

    def _get_feature(self, force_default_none: bool = False):
        """
        get feature value
        :param force_default_none: if True, use None as default regardless
        of TraitHolder
        """
        default = None if force_default_none else self.default_value
        try:
            return self.feature_holder.features.get(
                self.feature_name, default)
        except qubesadmin.exc.QubesDaemonAccessError:
            return self.default_value

    def _get_boolean_feature(self):
        """helper function to get a feature converted to a Bool if it does exist.
        Necessary because of the true/false in features being coded as 1/empty
        string."""
        result = self._get_feature(force_default_none=True)
        if result is not None:
            result = bool(result)
        return result

    def get_current_value(self):
        return self.current_value

    def set_trait(self, new_value):
        """ set the feature"""
        # TODO: implement all possible edgecases

        self.feature_holder.features[self.feature_name] = new_value
        if self.is_boolean:
            self.current_value = self._get_boolean_feature()
        else:
            self.current_value = self._get_feature()


class VMPropertyHolder(TraitHolder):
    def __init__(self, property_name: str,
                 property_holder: Union[qubesadmin.vm.QubesVM, qubesadmin.Qubes],
                 relevant_widget: TraitSelector,
                 default_value: Optional = None):
        """
        A property that holds VMs.
        :param property_name: name of the property
        :param property_holder: object that has the property
        :param relevant_widget: widget that contains relevant property data
        :param default_value: default value of the property
        """
        super().__init__(relevant_widget)
        self.property_holder = property_holder
        self.property_name = property_name
        self.default_value = default_value
        self.current_value = getattr(self.property_holder, self.property_name,
                                     default_value)

    def set_trait(self, new_value):
        if hasattr(self.property_holder, self.property_name):
            setattr(self.property_holder, self.property_name, new_value)
            self.current_value = getattr(self.property_holder,
                                         self.property_name,
                                         self.default_value)
        else:
            # TODO ???
            return

    def get_current_value(self):
        return self.current_value


class PageHandler(abc.ABC):
    """abstract class for page handlers"""
    @abc.abstractmethod
    def save(self):
        """save settings changed in page"""

    @abc.abstractmethod
    def reset(self):
        """Undo all of user's changes"""

    @abc.abstractmethod
    def check_for_unsaved(self) -> bool:
        """Check if there are any unsaved changes and ask user for an action.
        Return True if changes have been handled, False if not."""


class BasicSettingsHandler(PageHandler):
    """
    Handler for the Basic Settings page.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: gtk_builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.clockvm_combo = gtk_builder.get_object('basics_clockvm_combo')
        self.clockvm_handler = VMListModeler(
            combobox=self.clockvm_combo, qapp=self.qapp,
            filter_function=lambda x: x.klass != 'TemplateVM',
            event_callback=None, default_value=None,
            current_value=self.qapp.clockvm, style_changes=True,
            allow_none=True)

        self.deftemplate_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_deftemplate_combo')
        self.deftemplate_handler = VMListModeler(
            combobox=self.deftemplate_combo, qapp=self.qapp,
            filter_function=lambda x: x.klass == 'TemplateVM',
            event_callback=None, default_value=None,
            current_value=self.qapp.default_template, style_changes=True,
            allow_none=True)

        self.defdispvm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_defdispvm_combo')
        self.defdispvm_handler = VMListModeler(
            combobox=self.defdispvm_combo, qapp=self.qapp,
            filter_function=lambda x: getattr(
                x, 'template_for_dispvms', False),
            event_callback=None, default_value=None,
            current_value=self.qapp.default_dispvm, style_changes=True,
            allow_none=True)

        self.fullscreen_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_fullscreen_combo')
        self.fullscreen_handler = TextModeler(
            self.fullscreen_combo,
            {'default (disallow)': None, 'allow': True, 'disallow': False},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-allow-fullscreen'),
            style_changes=True)

        self.utf_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_utf_windows_combo')
        self.utf_handler = TextModeler(
            self.utf_combo,
            {'default (disallow)': None, 'allow': True, 'disallow': False},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-allow-utf8-titles'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        # complex features
        self.official_templates_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_official_templates_combo')
        self.official_templates_handler = TextModeler(
            self.official_templates_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)

        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.tray_icon_handler = TextModeler(
            self.tray_icon_combo,
            {'default (thin border)': None,
             'full background': 'bg',
             'thin border': 'border1',
             'thick border': 'border2',
             'tinted icon': 'tint',
             'tinted icon with modified white': 'tint+whitehack',
             'tinted icon with 50% saturation': 'tint+saturation50'},
            selected_value=get_boolean_feature(self.vm,
                                               'gui-default-trayicon-mode'),
            style_changes=True)
        # TODO: maybe add some funkier methods to those dropdowns, so that
        #  we can just iterate over all of them and apply?

    def save(self):
        pass
        # TODO: implement

    def reset(self):
        pass # TODO: implement

    def check_for_unsaved(self) -> bool:
        return True
    # TODO: implement


class ClipboardHandler(PageHandler):
    """
    Handler for the Clipboard page.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes,
                 policy_manager: PolicyManager):
        """
        :param gtk_builder: gtk_builder object
        :param qapp: Qubes object
        """
        # TODO: what do I want to put here?

        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]
        self.policy_manager = policy_manager

        self.service_name = 'qubes.ClipboardPaste'
        self.policy_file_name = '50-config-clipboard'
        self.default_policy = """
qubes.ClipboardPaste * @adminvm @anyvm deny\n
qubes.ClipboardPaste * @anyvm @anyvm ask\n"""
        self.verb_description = ' be allowed to paste\n into clipboard of '

        self.policy_handler = PolicyHandler(
            qapp=self.qapp,
            gtk_builder=gtk_builder,
            prefix="clipboard",
            policy_manager=self.policy_manager,
            default_policy=self.default_policy,
            service_name=self.service_name,
            policy_file_name=self.policy_file_name,
            verb_description=self.verb_description,
            ask_is_allow=True)

    def save(self):
        self.policy_handler.save_rules()

    def reset(self):
        pass # TODO: implement

    def check_for_unsaved(self) -> bool:
        return True
    # TODO: implement


class GlobalConfig(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, qapp):
        """
        :param qapp: qubesadmin.Qubes object
        """
        super().__init__(application_id='org.qubesos.globalconfig')
        self.qapp: qubesadmin.Qubes = qapp

        self.builder: Optional[Gtk.Builder] = None
        self.main_window: Optional[Gtk.Window] = None

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

        GObject.signal_new('rules-changed',
                           Gtk.ListBox,
                           GObject.SIGNAL_RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))

        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, '../global_config.glade'))

        self.main_window = self.builder.get_object('main_window')
        self.main_notebook: Gtk.Notebook = self.builder.get_object('main_notebook')

        self._handle_theme()
        policy_handler = PolicyManager()

        self.apply_button: Gtk.Button = self.builder.get_object('apply_button')
        self.cancel_button: Gtk.Button = self.builder.get_object('cancel_button')
        self.ok_button: Gtk.Button = self.builder.get_object('ok_button')

        self.apply_button.connect('clicked', self._apply)
        self.cancel_button.connect('clicked', self._quit)
        self.ok_button.connect('clicked', self._ok)

        # match page by id to handler; this is not pretty, but Gtk likes
        # to ID pages by their number, there is no simple page_id
        self.handlers: Dict[int, PageHandler] = {
            0: BasicSettingsHandler(self.builder, self.qapp),
            4: ClipboardHandler(self.builder, self.qapp, policy_handler)}

    def _apply(self, _widget):
        current_handler = self.handlers.get(
            self.main_notebook.get_current_page(), None)
        if current_handler:
            current_handler.save()

    def _quit(self, _widget):
        self.quit()

    def _ok(self, widget):
        self._apply(widget)
        self._quit(widget)

    def _handle_theme(self):
        # style_context = self.main_window.get_style_context()
        # window_default_color = style_context.get_background_color(
        #     Gtk.StateType.NORMAL)
        # TODO: future: determine light or dark scheme by checking if text is
        #  lighter or darker than background
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(pkg_resources.resource_filename(
            __name__, '../qubes-global-config.css'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    app = GlobalConfig(qapp)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
