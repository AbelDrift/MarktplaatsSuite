"""Algemene voorwaarden: opmaakeditor (vet/schuin) en omzetting naar Marktplaats-tekst.

Opslag: markdown-achtig (**vet**, *schuin*, ***beide***) in suite_config.json.
Marktplaats kent geen echte opmaak, dus bij gebruik wordt het omgezet naar
Unicode-letters die er vet/schuin uitzien.
"""
import os
import re

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from marktplaats_suite.common import shared_get


# ---------- tekst <-> markdown ----------
def standaard_tekst():
    from marktplaats_suite.productmanager import ALGEMENE_VOORWAARDEN
    return ALGEMENE_VOORWAARDEN


def markdown_naar_unicode(tekst):
    from marktplaats_suite.productmanager import _markdown_naar_unicode
    return _markdown_naar_unicode(tekst)


def voorwaarden_voor_advertentie():
    """Eindtekst voor in de advertentie, of '' als voorwaarden uit staan."""
    if not shared_get("voorwaarden_gebruiken", True):
        return ""
    tekst = shared_get("voorwaarden_tekst", "") or standaard_tekst()
    return markdown_naar_unicode(tekst)


def docx_naar_markdown(pad):
    try:
        import docx
    except ImportError:
        raise RuntimeError("Voor .docx is 'python-docx' nodig (pip install python-docx).")
    regels = []
    for p in docx.Document(pad).paragraphs:
        delen = []
        for r in p.runs:
            t = r.text
            if not t:
                continue
            if r.bold and r.italic:
                t = f"***{t}***"
            elif r.bold:
                t = f"**{t}**"
            elif r.italic:
                t = f"*{t}*"
            delen.append(t)
        regels.append("".join(delen))
    return "\n".join(regels)


def lees_bestand_als_markdown(pad):
    if pad.lower().endswith(".docx"):
        return docx_naar_markdown(pad)
    with open(pad, encoding="utf-8") as f:
        return f.read()


_TOKEN = re.compile(r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*))", re.S)


def _segmenten(markdown):
    """Geeft [(tekst, vet, schuin)] terug."""
    uit = []
    for deel in _TOKEN.split(markdown):
        if not deel:
            continue
        if deel.startswith("***") and deel.endswith("***") and len(deel) > 6:
            uit.append((deel[3:-3], True, True))
        elif deel.startswith("**") and deel.endswith("**") and len(deel) > 4:
            uit.append((deel[2:-2], True, False))
        elif deel.startswith("*") and deel.endswith("*") and len(deel) > 2:
            uit.append((deel[1:-1], False, True))
        else:
            uit.append((deel, False, False))
    return uit


# ---------- editor ----------
class VoorwaardenEditor(Gtk.Box):
    """Tekstvak met vet/schuin-knoppen (Ctrl+B / Ctrl+I), import en voorbeeld."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        self.gebruiken_check = Gtk.CheckButton(label="Algemene voorwaarden onder elke advertentie plaatsen")
        self.gebruiken_check.set_active(bool(shared_get("voorwaarden_gebruiken", True)))
        self.gebruiken_check.connect("toggled", self._on_toggle)
        self.pack_start(self.gebruiken_check, False, False, 0)

        self.werkbalk = Gtk.Box(spacing=4)
        self.vet_knop = Gtk.Button(); self.vet_knop.set_tooltip_text("Vet (Ctrl+B)")
        l = Gtk.Label(); l.set_markup("<b>B</b>"); self.vet_knop.add(l)
        self.schuin_knop = Gtk.Button(); self.schuin_knop.set_tooltip_text("Schuin (Ctrl+I)")
        l = Gtk.Label(); l.set_markup("<i>I</i>"); self.schuin_knop.add(l)
        self.vet_knop.connect("clicked", lambda *_: self._wissel("vet"))
        self.schuin_knop.connect("clicked", lambda *_: self._wissel("schuin"))
        self.import_knop = Gtk.Button(label="📂 Importeer .docx/.txt")
        self.import_knop.connect("clicked", self._importeer)
        self.reset_knop = Gtk.Button(label="↺ Standaardtekst")
        self.reset_knop.connect("clicked", lambda *_: self.zet_markdown(standaard_tekst()))
        for w in (self.vet_knop, self.schuin_knop, self.import_knop, self.reset_knop):
            self.werkbalk.pack_start(w, False, False, 0)
        self.pack_start(self.werkbalk, False, False, 0)

        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.view.set_left_margin(6); self.view.set_right_margin(6)
        self.buf = self.view.get_buffer()
        self.buf.create_tag("vet", weight=Pango.Weight.BOLD)
        self.buf.create_tag("schuin", style=Pango.Style.ITALIC)
        self.view.connect("key-press-event", self._toets)
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 200)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.view)
        self.pack_start(scroll, True, True, 0)

        hint = Gtk.Label()
        hint.set_markup("<small><i>Selecteer tekst en klik B of I. Marktplaats kent geen echte opmaak: "
                        "vet/schuin wordt omgezet naar speciale tekens die er vet/schuin uitzien.</i></small>")
        hint.set_xalign(0); hint.set_line_wrap(True)
        self.pack_start(hint, False, False, 0)

        voorb_kop = Gtk.Label(); voorb_kop.set_markup("<small><b>Voorbeeld zoals op Marktplaats:</b></small>")
        voorb_kop.set_xalign(0)
        self.pack_start(voorb_kop, False, False, 0)
        self.voorbeeld = Gtk.Label(); self.voorbeeld.set_xalign(0); self.voorbeeld.set_line_wrap(True)
        self.voorbeeld.set_selectable(True)
        self.pack_start(self.voorbeeld, False, False, 0)
        self.buf.connect("changed", lambda *_: self._ververs_voorbeeld())

        self.zet_markdown(shared_get("voorwaarden_tekst", "") or standaard_tekst())
        self._on_toggle()

    # --- acties ---
    def _on_toggle(self, *_):
        aan = self.gebruiken_check.get_active()
        self.werkbalk.set_sensitive(aan)
        self.view.set_sensitive(aan)

    def _toets(self, _w, ev):
        from gi.repository import Gdk
        if ev.state & Gdk.ModifierType.CONTROL_MASK:
            if ev.keyval in (Gdk.KEY_b, Gdk.KEY_B):
                self._wissel("vet"); return True
            if ev.keyval in (Gdk.KEY_i, Gdk.KEY_I):
                self._wissel("schuin"); return True
        return False

    def _wissel(self, tagnaam):
        if not self.buf.get_has_selection():
            return
        a, b = self.buf.get_selection_bounds()
        tag = self.buf.get_tag_table().lookup(tagnaam)
        if a.has_tag(tag) and all(
                self._iter_op(a, i).has_tag(tag) for i in range(b.get_offset() - a.get_offset())):
            self.buf.remove_tag(tag, a, b)
        else:
            self.buf.apply_tag(tag, a, b)
        self._ververs_voorbeeld()

    def _iter_op(self, start, n):
        it = start.copy(); it.forward_chars(n); return it

    def _importeer(self, *_):
        top = self.get_toplevel()
        dlg = Gtk.FileChooserDialog(title="Kies .docx of .txt", transient_for=top if isinstance(top, Gtk.Window) else None,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        f = Gtk.FileFilter(); f.set_name("Word/tekst (*.docx, *.txt)")
        f.add_pattern("*.docx"); f.add_pattern("*.txt"); dlg.add_filter(f)
        if dlg.run() == Gtk.ResponseType.OK:
            try:
                self.zet_markdown(lees_bestand_als_markdown(dlg.get_filename()))
            except Exception as e:
                m = Gtk.MessageDialog(transient_for=top if isinstance(top, Gtk.Window) else None,
                                      message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK,
                                      text="Bestand kon niet worden gelezen")
                m.format_secondary_text(str(e)); m.run(); m.destroy()
        dlg.destroy()

    # --- (de)serialisatie ---
    def zet_markdown(self, markdown):
        self.buf.set_text("")
        for tekst, vet, schuin in _segmenten(markdown):
            tags = [t for t, aan in (("vet", vet), ("schuin", schuin)) if aan]
            self.buf.insert_with_tags_by_name(self.buf.get_end_iter(), tekst, *tags)
        self._ververs_voorbeeld()

    def get_markdown(self):
        tv = self.buf.get_tag_table()
        vet, schuin = tv.lookup("vet"), tv.lookup("schuin")
        uit, huidig, tekst = [], (False, False), ""
        it = self.buf.get_start_iter()

        def sluit():
            nonlocal tekst
            if not tekst:
                return
            v, s = huidig
            if tekst.strip() == "":
                uit.append(tekst)
            else:
                lead = tekst[:len(tekst) - len(tekst.lstrip())]
                trail = tekst[len(tekst.rstrip()):]
                kern = tekst.strip()
                m = "***" if (v and s) else "**" if v else "*" if s else ""
                uit.append(f"{lead}{m}{kern}{m}{trail}")
            tekst = ""

        while not it.is_end():
            toestand = (it.has_tag(vet), it.has_tag(schuin))
            if toestand != huidig:
                sluit(); huidig = toestand
            tekst += it.get_char()
            it.forward_char()
        sluit()
        return "".join(uit)

    def opslaan(self):
        from marktplaats_suite.common import shared_set
        shared_set("voorwaarden_gebruiken", self.gebruiken_check.get_active())
        md = self.get_markdown()
        shared_set("voorwaarden_tekst", "" if md.strip() == standaard_tekst().strip() else md)

    def _ververs_voorbeeld(self):
        self.voorbeeld.set_text(markdown_naar_unicode(self.get_markdown()))
