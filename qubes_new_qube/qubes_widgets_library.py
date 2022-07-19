import gi

import abc
import qubesadmin
import qubesadmin.vm
import itertools

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject

from typing import Optional, Callable, Dict, Any

# TODO: generalize loading icons, too much boilerplate?
# TODO: or just IconCache


VM_CATEGORIES = {
    "@anyvm": "ALL QUBES",
    "@type:AppVM": "TYPE: APP",
    "@type:TemplateVM": "TYPE: TEMPLATES",
    "@type:DispVM" : "TYPE: DISPOSABLE",
    "@adminvm": "TYPE: ADMINVM"}


class TypeName(Gtk.Box):
    """
    A Gtk.Box containing type label plus name, nicely formatted.
    """
    def __init__(self, vm_type: str):
        """
        Type should be one of the VM_CATEGORIES keys.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.vm_type = vm_type
        nice_name = VM_CATEGORIES.get(self.vm_type, self.vm_type)
        self.label = Gtk.Label()
        self.label.set_text(nice_name)
        self.label.get_style_context().add_class('qube-type')
        self.pack_start(self.label, False, False, 0)


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
        self.vm = vm
        if vm is not None:
            self.image = Gtk.Image()
            self.image.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                    vm.icon, 20, 0))
        self.label = Gtk.Label()
        self.label.set_label(vm.name if vm else 'None')

        self.set_spacing(5)
        self.image.set_halign(Gtk.Align.CENTER)

        self.add(self.image)
        self.add(self.label)

        self.get_style_context().add_class(f'qube-box-base')
        if vm:
            self.get_style_context().add_class(f'qube-box-{vm.label}')
        else:
            self.get_style_context().add_class(f'qube-box-black')

        self.show_all()

# TODO: make a VM cache actually...


class TraitSelector(abc.ABC):
    @abc.abstractmethod
    def get_selected(self):
        """
        Get selected value
        """

    @abc.abstractmethod
    def is_changed(self) -> bool:
        """
        Has the value changed from initial value?
        """


class TextModeler(TraitSelector):
    """
    Class to handle modeling a text combo box.
    """
    def __init__(self, combobox: Gtk.ComboBoxText,
                 values: Dict[str, Any],
                 selected_value: Optional[str] = None,
                 style_changes: bool = False):
        """
        :param combobox: target ComboBoxText object
        :param values: dictionary of displayed strings and corresponding values.
        :param selected_value: which value should be selected initially, if None
         the first option will be selected.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value changes
        """
        self._combo: Gtk.ComboBoxText = combobox
        self._values: Dict[str, Any] = values

        for text in self._values.keys():
            # to ensure that the correct option id is selected, we use
            # explicit id for both text and id
            self._combo.append(text, text)

        if selected_value:
            self.select_value(selected_value)
        else:
            self._combo.set_active(0)

        self._initial_value = self._combo.get_active_text()

        if style_changes:
            self._combo.connect('changed', self._on_changed)

    def get_selected(self):
        return self._values[self._combo.get_active_text()]

    def is_changed(self) -> bool:
        return self._initial_value != self._combo.get_active_text()

    def select_value(self, selected_value):
        for key, value in self._values.items():
            if value == selected_value:
                self._combo.set_active_id(key)

    def _on_changed(self, _widget):
        self._combo.get_style_context().remove_class('combo-changed')
        if self.is_changed():
            self._combo.get_style_context().add_class('combo-changed')

# TODO: future improvement: better combobox with custom selection, multiple cols
# etc., see design doc in Figma

class VMListModeler(TraitSelector):
    """
    Modeler for Gtk.ComboBox contain a list of qubes VMs.
    Based on boring-stuff's code in core-qrexec qrexec_policy_agent.py.
    """
    def __init__(self, combobox: Gtk.ComboBox, qapp: qubesadmin.Qubes,
                 filter_function: Optional[Callable[[qubesadmin.vm.QubesVM],
                                                    bool]] = None,
                 event_callback: Optional[Callable[[], None]] = None,
                 default_value: Optional[qubesadmin.vm.QubesVM] = None,
                 current_value: Optional[qubesadmin.vm.QubesVM] = None,
                 style_changes: bool = False,
                 allow_none: bool = False,
                 add_categories: bool = False):
        """
        :param combobox: target ComboBox object
        :param qapp: Qubes object, necessary to retrieve VM info
        :param filter_function: function used to filter VMs, must take as input
        QubesVM object and return bool; caution: remember not all properties
        are always available for all VMs, in particular dom0 can cause problems
        :param event_callback: function to be called whenever combobox value
        changes
        :param default_value: default VM (will get a (default) decoration
        next to its name), and, if current_value not specified, it will be
        selected as the initial value
        :param current_value: value to be selected; if None and there is
        a default value, it will be selected; if neither exist,
         first position will be selected
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value changes
        """
        self.qapp = qapp
        self.combo = combobox
        self.entry_box = self.combo.get_child()
        self.change_function = event_callback
        self.style_changes = style_changes

        self._entries = {}

        self._icons = {}
        self._icon_size = 20

        self._theme = Gtk.IconTheme.get_default()

        self.initial_value = None
        self._create_entries(filter_function, default_value, allow_none,
                             add_categories)

        self._apply_model()

        self._initial_id = None

        if current_value:
            self.select_entry(current_value)
        elif default_value:
            self.select_entry(default_value)
        else:
            self.combo.set_active(0)

        self._initial_id = self.combo.get_active_id()

    def connect_change_callback(self, event_callback):
        self.change_function = event_callback

    def is_changed(self) -> bool:
        if self._initial_id is None:
            return False
        return self._initial_id != self.combo.get_active_id()

    def _get_icon(self, name):
        if name not in self._icons:
            try:
                icon = self._theme.load_icon(name, self._icon_size, 0)
            except GLib.Error:  # pylint: disable=catching-non-exception
                # TODO: check why how what?
                icon = self._theme.load_icon("edit-find", self._icon_size, 0)
            self._icons[name] = icon
        return self._icons[name]

    def _create_entries(
            self, filter_function: Callable[[qubesadmin.vm.QubesVM], bool],
            default_value: Optional[qubesadmin.vm.QubesVM], allow_none: bool,
            add_categories: bool):

        if add_categories:
            self._entries["TYPE: TEMPLATES"] = {
                "api_name": "@type:TemplateVM",
                "icon": None,
                "vm": None
            }
            # TODO: discuss approach to dom0-adminvm; are they the same? are they not?
            self._entries["TYPE: ADMINVM"] = {
                "api_name": "@adminvm",
                "icon": None,
                "vm": None
            }
            self._entries["TYPE: DISPOSABLE"] = {
                "api_name": "@type:DispVM",
                "icon": None,
                "vm": None
            }
            self._entries["TYPE: APP"] = {
                "api_name": "@type:AppVM",
                "icon": None,
                "vm": None
            }
            self._entries["ALL QUBES"] = {
                "api_name": "@anyvm",
                "icon": None,
                "vm": None
            }

        if allow_none:
            self._entries['(none)'] = {
                "api_name": "None",
                "icon": None,
                "vm": None
            }

        for domain in self.qapp.domains:
            if filter_function and not filter_function(domain):
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

        if self.style_changes:
            self.entry_box.get_style_context().remove_class('combo-changed')
            if self.is_changed():
                self.entry_box.get_style_context().add_class('combo-changed')

    def _apply_model(self):
        assert isinstance(self.combo, Gtk.ComboBox)
        list_store = Gtk.ListStore(int, str, GdkPixbuf.Pixbuf, str, str, str)

        for entry_no, display_name in zip(itertools.count(),
                                          sorted(self._entries)):
            entry = self._entries[display_name]
            list_store.append(
                [
                    entry_no,
                    display_name,
                    entry["icon"],
                    entry["api_name"],
                    '#f2f2f2' if entry['vm'] is None else None,  # background color
                    '#000000' if entry['vm'] is None else None,  # foreground color
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
        text_column: Gtk.CellRenderer = self.combo.get_cells()[0]
        self.combo.reorder(text_column, 1)

        # use list_store's 4th and 5th columns as source for background and
        # foreground color
        self.combo.add_attribute(text_column, 'background', 4)
        self.combo.add_attribute(text_column, 'foreground', 5)

        self.combo.connect("changed", self._combo_change)
        self.entry_box.connect("changed", self._event_callback)

    def _event_callback(self, *_args):
        if self.change_function:
            self.change_function()

    def get_selected(self) -> qubesadmin.vm.QubesVM:
        """
        Get currently selected VM, if any
        :return: QubesVM object
        """
        selected = self._get_valid_qube_name()

        if selected in self._entries:
            return self._entries[selected]["vm"] or self._entries[selected]["api_name"]

    def select_entry(self, vm_name):
        """
        Select VM by name.
        :param vm_name: str
        :return: None
        """
        for display_name, entry in self._entries.items():
            if entry["api_name"] == vm_name:
                self.combo.set_active_id(display_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """Check if given VM is available in the list."""
        for entry in self._entries.values():
            if entry['vm'] == vm:
                return True
        return False


class ImageTextButton(Gtk.Button):
    def __init__(self, icon_name: str, label: str, click_function):
        super().__init__()
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                icon_name, 20, 0))
        self.box.pack_start(self.image, False, False, 0)
        self.label = Gtk.Label()
        self.label.set_text(label)
        self.box.pack_start(self.label, False, False, 0)
        self.add(self.box)
        self.show_all()
        self.connect("clicked", click_function)
