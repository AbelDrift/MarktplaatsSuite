"""Gedeelde paden voor alle modules (Debian en Ubuntu, geen distro-aannames)."""
import os

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def data_dir():
    """Map voor configuratie, producten.xml, input/output en caches.

    Volgorde: $MARKTPLAATS_DATA_DIR, anders $XDG_DATA_HOME/marktplaats-suite
    (standaard ~/.local/share/marktplaats-suite).
    """
    pad = os.environ.get("MARKTPLAATS_DATA_DIR")
    if not pad:
        basis = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        pad = os.path.join(basis, "marktplaats-suite")
    os.makedirs(pad, exist_ok=True)
    return pad


def asset(naam):
    return os.path.join(ASSETS_DIR, naam)


# Gedeelde kolomlijst voor producten.xml: ALLE onderdelen gebruiken deze, zodat geen enkel
# onderdeel velden van een ander onderdeel kan wissen. Nieuwe velden alleen achteraan toevoegen.
COLUMNS = [
    "artikelnummer",
    "titel",
    "categorie",
    "omschrijving",
    "online",
    "lengte",
    "breedte",
    "hoogte",
    "gewicht",
    "conditie",
    "staat_details",
    "waarde_min",
    "waarde_max",
    "vraagprijs",
    "aanmaakdatum",
    "aanmaaktijd",
    "tijdsperiode",
    "opslaglocatie",
    "sublocatie",
    "rij",
    "folder_locatie",
    "verkocht",
    "verkoopprijs",
    "verkoopdatum",
    "algemene_voorwaarden",
    "url_1",
    "url_2",
    "url_3",
    "url_4",
    "url_5",
    "leverwijze",
    "klant_naam",
    "klant_telefoon",
    "klant_email",
    "ophaal_afspraak",
    "track_trace",
    "verwerkt_door",
    "toegewezen_aan",
    "gereserveerd",
    "reserveprijs",
    "reserveerdatum",
    "reservering_klant_naam",
    "marktplaats_categorie",
]
COL = {name: idx for idx, name in enumerate(COLUMNS)}


# ---------------------------------------------------------------------
# Gedeelde instellingen: één plek voor XML-pad en algemene voorwaarden
# ---------------------------------------------------------------------
import json

_SHARED_KEYS = ("xml_path", "voorwaarden_gebruiken", "voorwaarden_tekst")


def _shared_path():
    return os.path.join(data_dir(), "suite_config.json")


def _migreer_xml_pad():
    """Neem een bestaand pad over uit de oude losse configs (eenmalig)."""
    for naam, pad_in in (("productmanager_config.json", lambda d: d.get("xml_path")),
                         ("scanner_config.json", lambda d: d.get("storage", {}).get("xml_path")),
                         ("automater_config.json", lambda d: d.get("storage", {}).get("xml_path"))):
        try:
            with open(os.path.join(data_dir(), naam), encoding="utf-8") as f:
                p = pad_in(json.load(f))
            if p:
                return p
        except Exception:
            continue
    return os.path.join(data_dir(), "producten.xml")


def shared_laad():
    try:
        with open(_shared_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not data.get("xml_path"):
        data["xml_path"] = _migreer_xml_pad()
    data.setdefault("voorwaarden_gebruiken", True)
    data.setdefault("voorwaarden_tekst", "")  # leeg = standaardtekst van de app
    return data


def shared_get(sleutel, default=None):
    return shared_laad().get(sleutel, default)


def shared_set(sleutel, waarde):
    assert sleutel in _SHARED_KEYS, sleutel
    data = shared_laad()
    data[sleutel] = waarde
    with open(_shared_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_xml_path():
    return shared_get("xml_path")


def is_shared_key(sleutel):
    return sleutel in _SHARED_KEYS


# ---------------------------------------------------------------------
# Basis voor onderdelen die als tab in het hoofdvenster draaien
# ---------------------------------------------------------------------
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class TabBasis(Gtk.Box):
    """Gtk.Box die de vensterfuncties die de oude losse apps gebruikten negeert,
    zodat bestaande code als tab kan draaien. Dialogen gebruiken top() als parent."""

    def __init__(self, title="", **kw):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.tab_titel = title

    # vensterfuncties die in een tab niets doen
    def set_title(self, *a): pass
    def set_default_size(self, *a): pass
    def set_position(self, *a): pass
    def set_icon_from_file(self, *a): return True
    def set_icon(self, *a): pass
    def set_resizable(self, *a): pass
    def maximize(self, *a): pass
    def present(self, *a): pass

    def add(self, widget):
        self.pack_start(widget, True, True, 0)

    def top(self):
        t = self.get_toplevel()
        return t if isinstance(t, Gtk.Window) else None


def run_standalone(tab_factory, titel, breedte=900, hoogte=700):
    """Draai één tab in een eigen venster (handig voor testen)."""
    from gi.repository import GLib
    GLib.set_prgname("marktplaats_suite")
    win = Gtk.Window(title=titel)
    win.set_default_size(breedte, hoogte)
    win.add(tab_factory())
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
