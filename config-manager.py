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

        css = open('config-manager.css', 'rb')
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
            ("<a href=\"personal\">Personal</a> domain",
             [("firefox.svg", "Firefox", True),
              ("blue-libreoffice-writer.png", "Libre Office", True),
              ("blue-nautilus.png", "Files", False),
              ("blue-gimp.png", "GIMP", True)],
             True
             ),
            ("<a href=\"smedia\">Social media</a> domain",
             [("green-firefox.png", "Firefox", True)],
             False
             ),
            ("<a href=\"work\">Work</a> domain",
             [("red-firefox.png", "Firefox", True),
              ("red-thunderbird.png", "Thunderbird", True)],
             True
             ),
            ("<a href=\"email\">Email</a> domain",
             [("violet-firefox.png", "Firefox", True)],
             True
             ),
            ("<a href=\"key-management\">Key management</a>",
             None,
             False),
            ("<a href=\"Split GPG\">split GPG</a>",
             None,
             False)
        ]

        row = 0
        for c in components:
            text, programs, has_config = c
            box = Component(self.component_box, row, text, programs, has_config)
            box.attach()
            row += 1

        self.component_box.show_all()

        self.vpn_title_label.set_markup("<a href=\'hint-vpn\'>VPN!!</a>")
        self.vpn_title_label.set_name("title")


class Component:
    def __init__(self, component_box, row, text, programs=None, has_config=False):

        self.programs = programs
        self.text = text
        self.has_config = has_config
        self.component_box = component_box
        self.row = row

        # initialize the switch
        self.switch = Gtk.Switch()
        self.switch.set_state(True)
        self.switch.connect('state-set', self.state_changed)

        self.switch.set_vexpand(False)
        self.switch.set_valign(Gtk.Align.CENTER)

        # initialize the label
        self.name_label = Gtk.Label()
        self.name_label.set_markup(text)
        self.name_label.set_alignment(0, 0.5)
        self.name_label.connect('activate-link', self.link_handler)


        # config button
        if self.has_config:
            self.config_button = Gtk.Button()
            self.config_button.set_label("configure")

        # self.icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        # self.icon_box.set_vexpand(False)
        # self.icon_box.set_valign(Gtk.Align.CENTER)
        # if self.programs:
        #     # this will change
        #     for icon, tooltip, default in self.programs:
        #         if not default:
        #             continue
        #         pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
        #             filename=icon,
        #             width=24,
        #             height=24,
        #             preserve_aspect_ratio=True)
        #         image = Gtk.Image.new_from_pixbuf(pixbuf)
        #         image.set_vexpand(False)
        #         image.set_valign(Gtk.Align.CENTER)
        #         # icon.set_tooltip(tooltip) # this doesnt yet work
        #         self.icon_box.pack_start(
        #             image, expand=False, fill=False, padding=1)
        # if self.has_config:
        #     config_button = Gtk.Button()
        #     button_image = Gtk.Image.new_from_file("options.png")
        #     config_button.set_image(button_image)
        #     config_button.get_style_context().add_class("flat")
        #     config_button.connect('clicked', self.configure)
        #     config_button.set_vexpand(False)
        #     config_button.set_valign(Gtk.Align.CENTER)
        #     self.icon_box.pack_start(
        #         config_button, expand=False, fill=False, padding=0)

    def attach(self):
        self.component_box.attach(self.switch, 0, self.row, 1, 1)
        self.component_box.attach(self.name_label, 1, self.row, 1, 1)
        if self.has_config:
            self.component_box.attach(self.config_button, 2, self.row, 1, 1)
        # self.component_box.attach(self.icon_box, 2, self.row, 1, 1)
        #
        # self.icon_box.set_vexpand(False)

    def configure(self, *_args, **_kwargs):
        print("button clicked!")

    def state_changed(self, *_args, **_kwargs):
        print("change!")

    def link_handler(self, *_args, **_kwargs):
        print("link clicked ", self.name_label.get_text())

def main():
    app = QubesConfigManager()
    app.run()


if __name__ == '__main__':
    main()
