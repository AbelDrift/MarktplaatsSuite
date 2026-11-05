#!/usr/bin/env python3
"""Marktplaats Suite - startscherm. Elke module draait als eigen proces."""
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf

from marktplaats_suite.common import asset, data_dir

MODULES = [
    ("productmanager", "📦 Productmanager",
     "Producten registreren, labels printen, verkocht/retour/gereserveerd, dashboard"),
    ("fotomanager", "📷 Fotomanager",
     "Foto's verwerken: achtergrond, watermerk, logo, mappenstructuur"),
    ("scanner", "🔍 Barcode scanner",
     "Scan een artikelnummer en zie direct productgegevens en foto"),
    ("automater", "🤖 Automater",
     "Advertenties automatisch plaatsen op Marktplaats (Chrome/Chromium)"),
]


def start_module(naam):
    return subprocess.Popen([sys.executable, "-m", f"marktplaats_suite.{naam}"])


class Launcher(Gtk.Window):
    def __init__(self):
        super().__init__(title="Marktplaats Suite")
        self.set_default_size(460, 380)
        self.set_border_width(14)
        self.set_position(Gtk.WindowPosition.CENTER)
        try:
            self.set_icon(GdkPixbuf.Pixbuf.new_from_file_at_size(asset("icon.png"), 64, 64))
        except Exception:
            pass
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)
        kop = Gtk.Label()
        kop.set_markup("<big><b>Marktplaats Suite</b></big>")
        box.pack_start(kop, False, False, 4)
        for naam, titel, uitleg in MODULES:
            knop = Gtk.Button()
            inhoud = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(); t.set_markup(f"<b>{GLib.markup_escape_text(titel)}</b>"); t.set_xalign(0)
            u = Gtk.Label(label=uitleg); u.set_xalign(0); u.set_line_wrap(True)
            inhoud.pack_start(t, False, False, 0); inhoud.pack_start(u, False, False, 0)
            knop.add(inhoud)
            knop.connect("clicked", lambda _b, n=naam: start_module(n))
            box.pack_start(knop, False, False, 0)
        pad = Gtk.Label(label=f"Gegevens: {data_dir()}")
        pad.set_selectable(True); pad.set_xalign(0)
        box.pack_end(pad, False, False, 4)


def main():
    GLib.set_prgname("marktplaats_suite")
    w = Launcher()
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
