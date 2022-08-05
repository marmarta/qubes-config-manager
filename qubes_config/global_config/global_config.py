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
import re
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
    TextModeler, TraitSelector, NONE_CATEGORY, ask_question
from .page_handler import PageHandler
from .policy_handler import PolicyHandler, VMSubsetPolicyHandler
from .policy_rules import RuleSimple, \
    RuleSimpleAskIsAllow, RuleTargeted, SimpleVerbDescription, \
    TargetedVerbDescription, RuleSimpleNoAllow
from .policy_manager import PolicyManager
from .updates_handler import UpdatesHandler
from .usb_devices import DevicesHandler
from ..widgets.utils import apply_feature_change_from_widget, get_feature, \
    get_boolean_feature
from .basics_handler import BasicSettingsHandler

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject

import gbulb
gbulb.install()


logger = logging.getLogger('qubes-config-manager')


class ClipboardHandler(PageHandler):
    """Handler for Clipboard policy. Adds a couple of comboboxes to a
    normal policy handler."""
    COPY_FEATURE = 'gui-default-secure-copy-sequence'
    PASTE_FEATURE = 'gui-default-secure-paste-sequence'
    def __init__(self, qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 policy_manager: PolicyManager):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.clipboard_handler = PolicyHandler(
                qapp=self.qapp,
                gtk_builder=gtk_builder,
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
                rule_class=RuleSimpleAskIsAllow)

        self.copy_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('clipboard_copy_combo')
        self.copy_handler = TextModeler(
            self.copy_combo,
            {'default (Ctrl+Shift+C)': None,
             'Ctrl+Shift+C': 'Ctrl-Shift-c',
             'Ctrl+Win+C': 'Ctrl-Mod4-c'},
            selected_value=get_feature(self.vm, self.COPY_FEATURE),
            style_changes=True)

        self.paste_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('clipboard_paste_combo')
        self.paste_handler = TextModeler(
            self.paste_combo,
            {'default (Ctrl+Shift+V)': None,
             'Ctrl+Shift+V': 'Ctrl-Shift-V',
             'Ctrl+Win+V': 'Ctrl-Mod4-v',
             'Ctrl+Insert': 'Ctrl-Ins'},
            selected_value=get_feature(self.vm, self.PASTE_FEATURE),
            style_changes=True)

    def reset(self):
        self.copy_handler.reset()
        self.paste_handler.reset()
        self.clipboard_handler.reset()

    def save(self):
        apply_feature_change_from_widget(self.copy_handler, self.vm, self.COPY_FEATURE)
        apply_feature_change_from_widget(self.paste_handler, self.vm, self.PASTE_FEATURE)
        return self.clipboard_handler.save()

    def check_for_unsaved(self) -> bool:
        if self.copy_handler.is_changed() or self.paste_handler.is_changed():
            response = ask_question(self.copy_combo.get_toplevel(),
                                    "Unsaved changes found",
                                    "Do you want to save changes?")
            if response == Gtk.ResponseType.YES:
                self.save()
            else:
                self.reset()
                return True
        return self.clipboard_handler.check_for_unsaved()


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

        hcl_check = subprocess.check_output(['qubes-hcl-report']).decode()

        pattern = re.compile(
            r"Qubes release\s*(?P<qubes>.+)[\n.]*Brand:\s*(?P<brand>.+)[\n.]*"
            r"Model:\s*(?P<model>.+)[\n.]*BIOS:\s*(?P<bios>.*)[\n.]+"
            r"Xen:\s*(?P<xen>.+)[\n.]*Kernel:\s+(?P<kernel>.+)[\n.]*"
            r"RAM:\s+(?P<ram>.+)[\n.]+CPU:\s*(?P<cpu>.*)[\n.]+"
            r"Chipset:\s*(?P<chipset>.*)[\n.]+VGA:\s*(?P<vga>.*)")
        match = pattern.search(hcl_check)
        if not match:
            label_text = hcl_check
            self.data_label.get_style_context().add_class('red_code')
        else:
            label_text = f"""<b>Brand:</b> {match.group('brand')}
<b>Model:</b> {match.group('model')}
        
<b>CPU:</b> {match.group('cpu')}
<b>Chipset:</b> {match.group('chipset')}
<b>Graphics:</b> {match.group('vga')}

<b>RAM:</b> {match.group('ram')}

<b>QubesOS version:</b> {match.group('qubes')}
<b>BIOS:</b> {match.group('bios')}
<b>Kernel:</b> {match.group('kernel')}
<b>Xen:</b> {match.group('xen')}
"""
        self.data_label.set_markup(label_text)

    def reset(self):
        # does not apply
        pass

    def save(self):
        # does not apply
        pass

    def check_for_unsaved(self) -> bool:
        # does not apply
        return True


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

        GObject.signal_new('usbvm-changed',
                           Gtk.Window,
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
            0: BasicSettingsHandler(self.builder, self.qapp),
            1: DevicesHandler(self.qapp, policy_manager, self.builder),
            2: UpdatesHandler(
                qapp=self.qapp,
                policy_manager=policy_manager,
                gtk_builder=self.builder
            ),
            3: VMSubsetPolicyHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager,
                prefix="splitgpg",
                service_name='qubes.Gpg',
                policy_file_name='50-config-splitgpg',
                default_policy="",
                main_rule_class=RuleSimpleNoAllow,
                main_verb_description=SimpleVerbDescription({
                    "ask": "access GPG\nkeys from",
                    "deny": "access GPG\nkeys from"
                }),
                exception_rule_class=RuleTargeted,
                exception_verb_description=SimpleVerbDescription({
                    "allow": 'access GPG\nkeys from',
                    "ask": 'to access GPG\nkeys from',
                    "deny": 'access GPG\nkeys from'
                })),
            4: ClipboardHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager
            ),
            5: FileAccessHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=policy_manager
            ),
            6: PolicyHandler(
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
            7: ThisDeviceHandler(self.qapp, self.builder),
        }

        self.main_notebook.connect("switch-page", self._page_switched)

        self._handle_urls()

    def _handle_urls(self):
        url_label_ids = ["url_info", "openinvm_info", "splitgpg_info",
                         "usb_info", "basics_info"]
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
             'qubes.OpenURL'], input=url.encode(), check=False)

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
