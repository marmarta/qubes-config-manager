import gi

import qubesadmin
import qubesadmin.vm
import itertools

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

from typing import Optional, Callable

# TODO: generalize loading icons, too much boilerplate?
# TODO: or just IconCache

# TODO: question icon needs bolder insides...


class QubeName(Gtk.Box):
    """
    A Gtk.Box containing qube icon plus name, colored in the label color and
    bolded.
    """
    def __init__(self, vm: qubesadmin.vm.QubesVM):
        """
        :param vm: Qubes VM to be represented.
        """
        super(QubeName, self).__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                vm.icon, 20, 0))
        self.label = Gtk.Label()
        self.label.set_label(vm.name)

        self.set_spacing(5)
        self.image.set_halign(Gtk.Align.CENTER)

        self.add(self.image)
        self.add(self.label)

        self.get_style_context().add_class(f'qube-box-base')
        self.get_style_context().add_class(f'qube-box-{vm.label}')

        self.show_all()

# TODO: adjust colors for readability, e.g. yellow needs to be darker
# TODO: make a VM cache actually...


class VMListModeler:
    """
    Modeler for Gtk.ComboBox contain a list of qubes VMs.
    Based on boring-stuff's code in core-qrexec qrexec_policy_agent.py.
    """
    def __init__(self, combobox: Gtk.ComboBox, qapp: qubesadmin.Qubes,
                 filter_function: Optional[Callable[[qubesadmin.vm.QubesVM], bool]]=None,
                 event_callback: Optional[Callable[[], None]]=None,
                 default_value: Optional[qubesadmin.vm.QubesVM]=None):
        """
        :param combobox: target ComboBox object
        :param qapp: Qubes object, necessary to retrieve VM info
        :param filter_function: function used to filter VMs, must take as input
        QubesVM object and return bool; caution: remember not all properties
        are always available for all VMs, in particular dom0 can cause problems
        :param event_callback: function to be called whenever combobox value
        changes
        :param default_value: default VM to be selected (will be selected as
        initial value and get a (default) decoration next to its name)
        """
        self.qapp = qapp
        self.combo = combobox
        self.entry_box = self.combo.get_child()
        self.change_function = event_callback

        self._entries = {}

        self._icons = {}
        self._icon_size = 20

        self._theme = Gtk.IconTheme.get_default()

        self.initial_value = None
        self._create_entries(filter_function, default_value)

        self._apply_model()

        self.combo.set_active_id(self.initial_value)

    def _get_icon(self, name):
        if name not in self._icons:
            try:
                icon = self._theme.load_icon(name, self._icon_size, 0)
            except GLib.Error:  # pylint: disable=catching-non-exception
                # TODO: check why how what?
                icon = self._theme.load_icon("edit-find", self._icon_size, 0)
            self._icons[name] = icon
        return self._icons[name]

    def _create_entries(self, filter_function, default_value):
        for domain in self.qapp.domains:
            if not filter_function(domain):
                continue
            vm_name = domain.name
            icon = self._get_icon(domain.icon)
            display_name = vm_name
            if self.initial_value is None:
                self.initial_value = display_name

            if domain == default_value:
                display_name = display_name + ' (default)'
                self.initial_value = display_name

            self._entries[display_name] = {
                "api_name": vm_name,
                "icon": icon,
                "vm": domain,
            }

    def _get_valid_qube_name(self):
        selected = self.combo.get_active_id()
        if selected in self._entries:
            return selected

        typed = self.entry_box.get_text()
        if typed in self._entries:
            return typed

    def _combo_change(self, _widget):
        name = self._get_valid_qube_name()

        if name:
            entry = self._entries[name]
            self.entry_box.set_icon_from_pixbuf(
                Gtk.EntryIconPosition.PRIMARY, entry["icon"]
            )
        else:
            self.entry_box.set_icon_from_stock(
                Gtk.EntryIconPosition.PRIMARY, "gtk-find"
            )

        if self.change_function:
            self.change_function()

    def _apply_model(self):
        # TODO: discuss connecting to validator - if incorrect template selected, scream
        assert isinstance(self.combo, Gtk.ComboBox)
        list_store = Gtk.ListStore(int, str, GdkPixbuf.Pixbuf, str)

        for entry_no, display_name in zip(itertools.count(), sorted(self._entries)):
            entry = self._entries[display_name]
            list_store.append(
                [
                    entry_no,
                    display_name,
                    entry["icon"],
                    entry["api_name"],
                ])

        self.combo.set_model(list_store)
        self.combo.set_id_column(1)

        icon_column = Gtk.CellRendererPixbuf()
        self.combo.pack_start(icon_column, False)
        self.combo.add_attribute(icon_column, "pixbuf", 2)
        self.combo.set_entry_text_column(1)

        entry_box = self.combo.get_child()

        area = Gtk.CellAreaBox()
        area.pack_start(icon_column, False, False, False)
        area.add_attribute(icon_column, "pixbuf", 2)

        completion = Gtk.EntryCompletion.new_with_area(area)
        completion.set_inline_selection(True)
        completion.set_inline_completion(True)
        completion.set_popup_completion(True)
        completion.set_popup_single_match(False)
        completion.set_model(list_store)
        completion.set_text_column(1)

        entry_box.set_completion(completion)

        # A Combo with an entry has a text column already
        text_column = self.combo.get_cells()[0]
        self.combo.reorder(text_column, 1)

        self.combo.connect("changed", self._combo_change)
        if self.change_function:
            self.entry_box.connect("changed", lambda combo: self.change_function())

    def get_selected(self) -> qubesadmin.vm.QubesVM:
        """
        Get currently selected VM, if any
        :return: QubesVM object
        """
        selected = self._get_valid_qube_name()

        if selected in self._entries:
            return self._entries[selected]["vm"]

    def select_entry(self, vm_name):
        """
        Select VM by name.
        :param vm_name: str
        :return: None
        """
        for display_name, entry in self._entries.items():
            if entry["api_name"] == vm_name:
                self.combo.set_active_id(display_name)
