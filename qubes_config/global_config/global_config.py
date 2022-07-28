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

# pylint: disable=import-error
"""Global Qubes Config tool."""
import sys
import threading
from typing import Optional, Dict, Union, Any
import abc
import pkg_resources
import subprocess
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from ..widgets.qubes_widgets_library import VMListModeler, \
    TextModeler, TraitSelector, NONE_CATEGORY
from .page_handler import PageHandler
from .policy_handler import PolicyManager, PolicyHandler, \
    VMSubsetPolicyHandler, AbstractPolicyHandler
from .policy_rules import RuleSimple, \
    RuleSimpleAskIsAllow, RuleTargeted, SimpleVerbDescription, \
    TargetedVerbDescription

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')


class TraitHolder(abc.ABC):
    """Abstract trait (property, feature, anything)"""
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
    """VM Feature."""
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
        """helper function to get a feature converted to a Bool if it does
        exist. Necessary because of the true/false in features being coded as
        1/empty string."""
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
    """A property that holds VMs."""
    def __init__(self, property_name: str,
                 property_holder: Union[qubesadmin.vm.QubesVM,
                                        qubesadmin.Qubes],
                 relevant_widget: TraitSelector,
                 default_value: Optional[Any] = None):
        """
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
            additional_options=NONE_CATEGORY)

        self.deftemplate_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_deftemplate_combo')
        self.deftemplate_handler = VMListModeler(
            combobox=self.deftemplate_combo, qapp=self.qapp,
            filter_function=lambda x: x.klass == 'TemplateVM',
            event_callback=None, default_value=None,
            current_value=self.qapp.default_template, style_changes=True,
            additional_options=NONE_CATEGORY)

        self.defdispvm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_defdispvm_combo')
        self.defdispvm_handler = VMListModeler(
            combobox=self.defdispvm_combo, qapp=self.qapp,
            filter_function=lambda x: getattr(
                x, 'template_for_dispvms', False),
            event_callback=None, default_value=None,
            current_value=self.qapp.default_dispvm, style_changes=True,
            additional_options=NONE_CATEGORY)

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


class FileAccessHandler(PageHandler):
    """Handler for FileAccess page. Requires separate handler because
    it combines two policies in itself."""
    def __init__(self, qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 policy_manager: PolicyManager):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.filecopy_handler = PolicyHandler(
            qapp=self.qapp,
            gtk_builder=gtk_builder,
            prefix="filecopy",
            policy_manager=self.policy_manager,
            default_policy="""qubes.Filecopy * @adminvm @anyvm deny\n
qubes.Filecopy * @anyvm @anyvm ask""",
            service_name="qubes.Filecopy",
            policy_file_name="50-config-filecopy",
            verb_description=SimpleVerbDescription({
                "ask": "to be allowed to copy files to",
                "allow": "allow files to copied to",
                "deny": "be allowed to copy files to"
            }),
            rule_class=RuleSimple)
        self.openinvm_handler = PolicyHandler(
            qapp=self.qapp,
            gtk_builder=gtk_builder,
            prefix="openinvm",
            policy_manager=self.policy_manager,
            default_policy="""qubes.OpenInVM * @adminvm @anyvm deny\n
qubes.OpenInVM * @anyvm @dispvm allow\n
qubes.OpenInVM * @anyvm @anyvm ask""",
            service_name="qubes.OpenInVM",
            policy_file_name="50-config-openinvm",
            verb_description=TargetedVerbDescription(
                    single_target_descr={
                        "allow": 'open files in',
                        "ask": 'where to open files,\nand select by default',
                        "deny": 'be allowed to open files in'
                    },
                    multi_target_descr={
                        "allow": 'open files in',
                        "ask": 'where to open files in',
                        "deny": 'be allowed to open files in'
                    }
                ),
            rule_class=RuleTargeted)

    def reset(self):
        self.filecopy_handler.reset()
        self.openinvm_handler.reset()

    def save(self):
        return self.filecopy_handler.save() and self.openinvm_handler.save()

    def check_for_unsaved(self) -> bool:
        return self.filecopy_handler.check_for_unsaved() \
               and self.openinvm_handler.check_for_unsaved()


class ThisDeviceHandler(PageHandler):
    """Handler for the ThisDevice page."""
    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder):
        self.qapp = qapp

        self.model_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_model_label')
        self.data_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_data_label')

        computer_model = ""
        cpu_model = ""
        chipset = ""
        graphics_card = ""
        storage = ""
        ram = ""
        qubes_version = ""
        bios_version = ""
        kernel = ""
        xen = ""

        label_text = f"""<b>Model:</b> {computer_model}
        
<b>CPU:</b> {cpu_model}
<b>Chipset:</b> {chipset}
<b>Graphics:</b> {graphics_card}

<b>Storage:</b> {storage}
<b>RAM:</b> {ram}

<b>QubesOS version:</b> {qubes_version}
<b>BIOS:</b> {bios_version}
<b>Kernel:</b> {kernel}
<b>Xen:</b> {xen}
"""
        self.data_label.set_markup(label_text)
        self.model_label.set_text("Lenovo Thinkpad")

    def reset(self):
        # does not apply
        pass

    def save(self):
        # does not apply
        pass

    def check_for_unsaved(self) -> bool:
        # does not apply
        return True

# TODO: qvm-open is used in both safe-url and file access
# qvm-open-in-vm can be default browser?

# target: @default
# by default open in: ask z default target
# bez pytania open in: allow target=
# deny for a certain combinantion


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
        assert self.main_window
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
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
        self.main_notebook: Gtk.Notebook = \
            self.builder.get_object('main_notebook')

        self._handle_theme()
        policy_manager = PolicyManager()

        self.apply_button: Gtk.Button = self.builder.get_object('apply_button')
        self.cancel_button: Gtk.Button = \
            self.builder.get_object('cancel_button')
        self.ok_button: Gtk.Button = self.builder.get_object('ok_button')

        self.apply_button.connect('clicked', self._apply)
        self.cancel_button.connect('clicked', self._quit)
        self.ok_button.connect('clicked', self._ok)

        self.main_window.connect('delete-event', self._ask_to_quit)

        # match page by id to handler; this is not pretty, but Gtk likes
        # to ID pages by their number, there is no simple page_id
        self.handlers: Dict[int, PageHandler] = {
            0: BasicSettingsHandler(self.builder, self.qapp),  # TODO
            1: None,  # TODO
            2: None,  # TODO
            3: None,  # TODO
            4: None, # TODO
        #     4: VMSubsetPolicyHandler(
        #         qapp=self.qapp,
        #         gtk_builder=self.builder,
        #         policy_manager=policy_manager,
        #         prefix="splitgpg",
        #         service_name='qubes.SplitGPG',
        #         policy_file_name='50-config-splitgpg',
        #         default_policy="""qubes.SplitGPG * @adminvm @anyvm deny\n
        # qubes.SplitGPG * @anyvm @anyvm ask\n""",
        #         verb_description=SimpleVerbDescription({
        #             "ask": "to allow GPG sharing from",
        #             "allow": "allow GPG sharing from",
        #             "deny": "allow GPG sharing from"
        #         }),
        #         rule_class=RuleSimple),
            5: PolicyHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager,
                prefix="clipboard",
                service_name='qubes.ClipboardPaste',
                policy_file_name='50-config-clipboard',
                default_policy="""qubes.ClipboardPaste * @adminvm @anyvm deny\n
qubes.ClipboardPaste * @anyvm @anyvm ask\n""",
                verb_description=SimpleVerbDescription({
                    "ask": 'be allowed to paste\n into clipboard of',
                    "deny": 'be allowed to paste\n into clipboard of'
                }),
                rule_class=RuleSimpleAskIsAllow),
            6: FileAccessHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager
            ),  # TODO
            7: PolicyHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager,
                prefix="url",
                service_name='qubes.OpenURL',
                policy_file_name='50-config-openurl',
                default_policy="""qubes.OpenURL * @adminvm @anyvm deny\n
qubes.OpenURL * @anyvm @dispvm allow\n
qubes.OpenURL * @anyvm @anyvm ask\n""",
                verb_description=TargetedVerbDescription(
                    single_target_descr={
                        "allow": 'open URLs in',
                        "ask": 'where to open URLs,\nand select by default',
                        "deny": 'be allowed to open URLs in'
                    },
                    multi_target_descr={
                        "allow": 'open URLs in',
                        "ask": 'where to open URLs in',
                        "deny": 'be allowed to open URLs in'
                    }
                ),
                rule_class=RuleTargeted),
            8: ThisDeviceHandler(self.qapp, self.builder),  # TODO
        }

        self.main_notebook.connect("switch-page", self._page_switched)

        self._handle_urls()

    def _handle_urls(self):
        url_label_ids = ["url_info", "openinvm_info", "splitgpg_info"]
        for url_label_id in url_label_ids:
            label: Gtk.Label = self.builder.get_object(url_label_id)
            label.connect("activate-link", self._activate_link)

    def _activate_link(self, _widget, url):
        open_thread = threading.Thread(group=None,
                                       target=self._open_url_in_dvm, args=[url])
        open_thread.start()
        return True

    def _open_url_in_dvm(self, url):
        default_dvm = self.qapp.default_dispvm
        subprocess.run(
            ['qvm-run', '-p', '--service', f'--dispvm={default_dvm}',
             'qubes.OpenURL'], input=url.encode())

    def _page_switched(self, *_args):
        old_page_num = self.main_notebook.get_current_page()
        old_page = self.handlers.get(old_page_num, None)
        if old_page and not old_page.check_for_unsaved():
            GLib.timeout_add(1, lambda: self.main_notebook.set_current_page(
                old_page_num))

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

    def _ask_to_quit(self, *_args):
        current_page = self.handlers.get(
            self.main_notebook.get_current_page(), None)
        if current_page and not current_page.check_for_unsaved():
            return True
        self.quit()
        return False

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
