#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position,import-error

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, Gio, GdkPixbuf


class QubesConfigManager(Gtk.Application):

    vpn_title_label: Gtk.Label
    component_box: Gtk.Box
    main_window: Gtk.ApplicationWindow
    builder: Gtk.Builder

    def __init__(self):
        super(QubesConfigManager, self).__init__(
            application_id="org.gnome.example",
            flags=Gio.ApplicationFlags.FLAGS_NONE)

        self.primary = False

        self.connect("activate", self.do_activate)

    def perform_setup(self, *_args, **_kwargs):
        # pylint: disable=attribute-defined-outside-init
        self.load_css()

        self.builder = Gtk.Builder()
        self.builder.add_from_file('config-manager3.glade')

        self.main_window = self.builder.get_object("main_window")

        self.component_box = self.builder.get_object("components_box")
        
        self.vpn_title_label = self.builder.get_object("vpn_title_label")

        self.load_components()

    def do_activate(self, *_args, **_kwargs):
        if not self.primary:
            self.perform_setup()
            self.primary = True
            self.hold()
        else:
            self.main_window.present()

    def load_css(self):
        style_provider = Gtk.CssProvider()

        css = open('config-manager2.css', 'rb')
        css_data = css.read()
        css.close()

        style_provider.load_from_data(css_data)

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


#nautilus is fucked
    def load_components(self):
        components = [
            ("Personal domain",
             "web browser, office suite",
             "writer and ff3.png"
             ),
            ("Social media domain",
             "web browser",
             False
             ),
            ("Work domain",
             "web browser, office suite",
             False
             ),
            ("Email domain",
             "email client",
             False
             ),
            ("Key management",
             "manage your keys and passwords securely",
             False),
            ("split GPG",
             "manage GPG keys securely",
             False)
        ]

        rows = []

        row = 0
        for c in components:
            main_text, sub_text, image = c
            box = Component(self.component_box, row, main_text, sub_text, image)
            box.attach()
            rows.append(box)
            row += 1

        self.component_box.show_all()

        self.vpn_title_label.set_markup("VPN")
        self.vpn_title_label.set_name("title")
        self.vpn_title_label.set_track_visited_links(False)



class Component:
    def __init__(self, component_box, row, main_text, sub_text=None, image=None):

        self.sub_text = sub_text
        self.main_text = main_text
        self.image = image
        self.component_box = component_box
        self.row = row

        # initialize the switch
        self.switch = Gtk.Switch()
        self.switch.set_state(True)
        self.switch.connect('state-set', self.state_changed)

        self.switch.set_vexpand(False)
        self.switch.set_valign(Gtk.Align.CENTER)

        # initialize the label
        self.name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.main_label = Gtk.Label()
        self.main_label.set_markup(self.main_text)
        self.main_label.set_alignment(0, 0.5)
        self.main_label.set_name("main")

        self.name_box.pack_start(self.main_label, expand=False, fill=False, padding=0)

        if self.sub_text:
            self.sub_label = Gtk.Label()
            self.sub_label.set_markup(self.sub_text)
            self.sub_label.set_alignment(0, 0.5)
            self.sub_label.set_name("sub")

            self.name_box.pack_start(self.sub_label, expand=False, fill=False,
                                     padding=0)

        if self.image:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.image)
            self.image_obj = Gtk.Image.new_from_pixbuf(pixbuf)

        else:
            self.image_obj = Gtk.Image()


    def attach(self):
        self.component_box.attach(self.switch, 0, self.row, 1, 1)
        self.component_box.attach(self.image_obj, 1, self.row, 1, 1)
        self.component_box.attach(self.name_box, 2, self.row, 1, 1)

    def configure(self, *_args, **_kwargs):
        print("button clicked!")

    def state_changed(self, *_args, **_kwargs):
        self.main_label.set_sensitive(not self.main_label.get_sensitive())
        self.sub_label.set_sensitive(not self.sub_label.get_sensitive())
        self.image_obj.set_sensitive(not self.image_obj.get_sensitive())

    def link_handler(self, *_args, **_kwargs):
        print("link clicked ", self.name_label.get_text())

def main():
    app = QubesConfigManager()
    app.run()


if __name__ == '__main__':
    main()
