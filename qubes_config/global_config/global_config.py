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
from typing import Dict, Optional, List, Union
import pkg_resources
import subprocess
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from ..widgets.gtk_utils import ask_question, show_error
from .page_handler import PageHandler
from .policy_handler import PolicyHandler, VMSubsetPolicyHandler
from .policy_rules import RuleSimple, \
    RuleSimpleAskIsAllow, RuleTargeted, SimpleVerbDescription, \
    TargetedVerbDescription, RuleSimpleNoAllow
from .policy_manager import PolicyManager
from .updates_handler import UpdatesHandler
from .usb_devices import DevicesHandler
from .basics_handler import BasicSettingsHandler, FeatureHandler

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject


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

        self.copy_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('clipboard_copy_combo')
        self.paste_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('clipboard_paste_combo')

        self.handlers: List[Union[PolicyHandler, FeatureHandler]] = [
            PolicyHandler(
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
                rule_class=RuleSimpleAskIsAllow),
            FeatureHandler(
                trait_holder=self.vm, trait_name=self.COPY_FEATURE,
                widget=self.copy_combo,
                options={'default (Ctrl+Shift+C)': None,
                         'Ctrl+Shift+C': 'Ctrl-Shift-c',
                         'Ctrl+Win+C': 'Ctrl-Mod4-c'},
                readable_name="Global Clipboard copy shortcut"
            ),
            FeatureHandler(
                trait_holder=self.vm, trait_name=self.PASTE_FEATURE,
                widget=self.paste_combo,
                options= {'default (Ctrl+Shift+V)': None,
                          'Ctrl+Shift+V': 'Ctrl-Shift-V',
                          'Ctrl+Win+V': 'Ctrl-Mod4-v',
                          'Ctrl+Insert': 'Ctrl-Ins'},
                readable_name="Global Clipboard paste shortcut"
            )
        ]

    def reset(self):
        for handler in self.handlers:
            handler.reset()

    def save(self):
        for handler in self.handlers:
            handler.save()

    def get_unsaved(self) -> str:
        unsaved = []
        for handler in self.handlers:
            unsaved_changes = handler.get_unsaved()
            if unsaved_changes:
                unsaved.append(unsaved_changes)
        return "\n".join(unsaved)


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
        self.filecopy_handler.save()
        self.openinvm_handler.save()

    def get_unsaved(self) -> str:
        unsaved = []
        for handler in [self.filecopy_handler, self.openinvm_handler]:
            unsaved_changes = handler.get_unsaved()
            if unsaved_changes:
                unsaved.append(unsaved_changes)
        return "\n".join(unsaved)


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

    def get_unsaved(self) -> str:
        return ""


class GlobalConfig(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, qapp: qubesadmin.Qubes, policy_manager: PolicyManager):
        """
        :param qapp: qubesadmin.Qubes object
        :param policy_manager: PolicyManager object
        """
        super().__init__(application_id='org.qubesos.globalconfig')
        self.qapp: qubesadmin.Qubes = qapp
        self.policy_manager = policy_manager

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

    @staticmethod
    def register_signals():
        """Register necessary Gtk signals"""
        GObject.signal_new('rules-changed',
                           Gtk.ListBox,
                           GObject.SignalFlags.RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))

        GObject.signal_new('usbvm-changed',
                           Gtk.Window,
                           GObject.SignalFlags.RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))

        GObject.signal_new('child-removed',
                           Gtk.FlowBox,
                           GObject.SignalFlags.RUN_LAST, GObject.TYPE_PYOBJECT,
                           (GObject.TYPE_PYOBJECT,))

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
        """
        The function that performs actual widget realization and setup.
        """
        self.register_signals()

        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename(
            __name__, '../global_config.glade'))

        self.main_window = self.builder.get_object('main_window')
        self.main_notebook: Gtk.Notebook = \
            self.builder.get_object('main_notebook')

        self._handle_theme()

        self.apply_button: Gtk.Button = self.builder.get_object('apply_button')
        self.cancel_button: Gtk.Button = \
            self.builder.get_object('cancel_button')
        self.ok_button: Gtk.Button = self.builder.get_object('ok_button')

        self.apply_button.connect('clicked', self._apply)
        self.cancel_button.connect('clicked', self._quit)
        self.ok_button.connect('clicked', self._ok)

        self.main_window.connect('delete-event', self._ask_to_quit)

        # match page by widget name to handler
        self.handlers: Dict[str, PageHandler] = {
            'basics': BasicSettingsHandler(self.builder, self.qapp),
            'usb': DevicesHandler(self.qapp, self.policy_manager, self.builder),
            'updates': UpdatesHandler(
                qapp=self.qapp,
                policy_manager=self.policy_manager,
                gtk_builder=self.builder
            ),
            'splitgpg': VMSubsetPolicyHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=self.policy_manager,
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
            'clipboard': ClipboardHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=self.policy_manager
            ),
            'file': FileAccessHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=self.policy_manager
            ),
            'url': PolicyHandler(
                qapp=self.qapp,
                gtk_builder=self.builder,
                policy_manager=self.policy_manager,
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
            'thisdevice': ThisDeviceHandler(self.qapp, self.builder),
        }

        self.main_notebook.connect("switch-page", self._page_switched)
        self.main_window.connect('usbvm-changed', self._usbvm_changed)

        self._handle_urls()

    def _usbvm_changed(self, *_args):
        response = ask_question(
            self.main_window, "USB qube change",
            "Changing USB qube requires restarting Global Settings to"
            "correctly initialize all defaults. "
            "Do you want to save changes and restart?")
        if response == Gtk.ResponseType.YES:
            self._apply()
            self._quit()
            return
        self._reset()

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

    def get_current_page(self) -> Optional[PageHandler]:
        """Get currently visible page."""
        page_num = self.main_notebook.get_current_page()
        return self.handlers.get(
            self.main_notebook.get_nth_page(page_num).get_name(), None)

    def verify_changes(self) -> bool:
        """Verify the current state of the page. Return True if page can
        be abandoned, False if there are unsaved changes remaining."""
        page = self.get_current_page()
        if page:
            unsaved = page.get_unsaved()
            if unsaved != '':
                response = self._ask_threeway_question(unsaved)
                if response == Gtk.ResponseType.YES:
                    try:
                        page.save()
                    except Exception as ex:
                        show_error("Could not save changes",
                                   f"The following error occurred: {ex}")
                        return False
                elif response == Gtk.ResponseType.NO:
                    page.reset()
                else:
                    return False
        return True

    def _page_switched(self, *_args):
        old_page_num = self.main_notebook.get_current_page()
        allow_switch = self.verify_changes()
        if not allow_switch:
            GLib.timeout_add(1, lambda: self.main_notebook.set_current_page(
                old_page_num))

    def _ask_threeway_question(self, description: str) -> Gtk.ResponseType:
        # The following unsaved changes were found:
        # blah blah
        # Do you want to save the changes?
        # Save changes (yes)
        # Discard changes (no)
        # Cancel (cancel) but
        # TODO: implement
        response = ask_question(self.main_window, "Unsaved changes",
                                f"Changes found:\n{description}")
        return response

    def _apply(self, _widget=None):
        page = self.get_current_page()
        if page:
            try:
                page.save()
            except Exception as ex:
                show_error("Could not save changes",
                           f"The following error occurred: {ex}")

    def _reset(self, _widget=None):
        page = self.get_current_page()
        if page:
            page.reset()

    def _quit(self, _widget=None):
        self.quit()

    def _ok(self, widget):
        self._apply(widget)
        self._quit(widget)

    def _ask_to_quit(self, *_args):
        can_quit = self.verify_changes()
        if not can_quit:
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
    policy_manager = PolicyManager()
    app = GlobalConfig(qapp, policy_manager)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
