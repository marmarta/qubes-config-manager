import gi

import qubesadmin
import qubesadmin.vm

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, GObject


class QubeName(Gtk.Box):
    # nice name with nice padding
    def __init__(self, vm: qubesadmin.vm.QubesVM):
        super(QubeName, self).__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(Gtk.IconTheme.get_default().load_icon(
                vm.icon, 16, 0))
        self.label = Gtk.Label()
        self.label.set_label(vm.name)
        # TODO: color
        self.add(self.image)
        self.add(self.label)
        self.get_style_context().add_class(f'qube-box-base')
        self.get_style_context().add_class(f'qube-box-{vm.label}')
        self.show_all()

    # TODO: styling
    # TODO: how to handle color??? magic needed
    # TODO: like styles or smth


# styling

class VMListStore(Gtk.ListStore):
    # TODO: add default here somehow, so that some are marked as 'default'
    def __init__(self, qapp: qubesadmin.Qubes, filter_func=None):
        super(VMListStore, self).__init__(GdkPixbuf.Pixbuf, str)

        data = [(vm.name, vm.icon) for vm in qapp.domains if not filter_func or filter_func(vm)]

        for text, icon in data:
            # TODO: icon SIZES
            pixbuf = Gtk.IconTheme.get_default().load_icon(icon, 16, 0)
            self.append([pixbuf, text])

    def attach_to_combobox(self, combobox: Gtk.ComboBox):
        combobox.set_model(self)

        renderer = Gtk.CellRendererPixbuf()
        combobox.pack_start(renderer, True)
        combobox.add_attribute(renderer, "pixbuf", 0)

        renderer = Gtk.CellRendererText()
        combobox.pack_start(renderer, False)
        combobox.add_attribute(renderer, "text", 1)

