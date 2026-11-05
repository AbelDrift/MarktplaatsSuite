#!/usr/bin/env python3
"""
Marktplaats Product Manager - Registratie & voorraadbeheer
Met dynamische pad zoekfunctie en compacte interface
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
import os
from marktplaats_suite.common import data_dir, asset, shared_get, shared_set, is_shared_key
import sys
import json
import hashlib
import secrets
import shutil
import subprocess
import datetime
import re
import csv
from io import StringIO
from collections import deque

# ============================================
# FIX voor Pillow >= 10.0.0 (ANTIALIAS is verwijderd)
# ============================================
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
        print("✅ PIL fix: ANTIALIAS = LANCZOS")
except ImportError:
    pass

# ============================================
# UNICODE OPMAAK (dikgedrukt/schuin) VOOR PLATTE TEKST
# --------------------------------------------
# Marktplaats.nl ondersteunt geen echte HTML/rich text opmaak in de
# omschrijving - het blijft altijd platte tekst. Om toch dikgedrukte en
# schuine tekst te kunnen tonen, worden gewone letters/cijfers vervangen
# door speciale Unicode-tekens die er visueel vet/schuin uitzien, maar
# gewoon platte tekst blijven (werkt dus overal, ook op Marktplaats).
# ============================================
def _bouw_unicode_letter_map(basis_hoofdletter, basis_kleine_letter, basis_cijfer=None):
    mapping = {}
    for i in range(26):
        mapping[chr(ord('A') + i)] = chr(basis_hoofdletter + i)
        mapping[chr(ord('a') + i)] = chr(basis_kleine_letter + i)
    if basis_cijfer is not None:
        for i in range(10):
            mapping[chr(ord('0') + i)] = chr(basis_cijfer + i)
    return mapping


_UNICODE_BOLD = _bouw_unicode_letter_map(0x1D400, 0x1D41A, 0x1D7CE)
_UNICODE_ITALIC = _bouw_unicode_letter_map(0x1D434, 0x1D44E)
_UNICODE_ITALIC['h'] = '\u210E'  # Unicode-uitzondering: kleine italic-h bestaat niet apart
_UNICODE_BOLD_ITALIC = _bouw_unicode_letter_map(0x1D468, 0x1D482)


def _naar_unicode_stijl(tekst, vet=False, schuin=False):
    if vet and schuin:
        mapping = _UNICODE_BOLD_ITALIC
    elif vet:
        mapping = _UNICODE_BOLD
    elif schuin:
        mapping = _UNICODE_ITALIC
    else:
        return tekst
    return "".join(mapping.get(ch, ch) for ch in tekst)


_MARKDOWN_BOLD_ITALIC_RE = re.compile(r"\*\*\*(.+?)\*\*\*")
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MARKDOWN_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _markdown_naar_unicode(tekst):
    """Zet **vet**, *schuin* en ***vet+schuin*** (getypt in platte .txt) om naar Unicode-opmaak."""
    tekst = _MARKDOWN_BOLD_ITALIC_RE.sub(lambda m: _naar_unicode_stijl(m.group(1), vet=True, schuin=True), tekst)
    tekst = _MARKDOWN_BOLD_RE.sub(lambda m: _naar_unicode_stijl(m.group(1), vet=True), tekst)
    tekst = _MARKDOWN_ITALIC_RE.sub(lambda m: _naar_unicode_stijl(m.group(1), schuin=True), tekst)
    return tekst


def _lees_docx_met_opmaak(pad):
    """Leest een .docx-bestand en zet vet/schuin (uit Word) om naar Unicode platte-tekst-opmaak."""
    try:
        import docx
    except ImportError:
        raise RuntimeError(
            "Voor het importeren van .docx-bestanden is het pakket 'python-docx' nodig.\n"
            "Installeer het met:  pip install python-docx"
        )

    document = docx.Document(pad)
    regels = []
    for paragraaf in document.paragraphs:
        stukken = []
        for run in paragraaf.runs:
            stukken.append(_naar_unicode_stijl(run.text, vet=bool(run.bold), schuin=bool(run.italic)))
        regels.append("".join(stukken))
    return "\n".join(regels)


def lees_algemene_voorwaarden_bestand(pad):
    """Leest het algemene-voorwaarden-bestand, met opmaakondersteuning voor .docx en markdown-achtige .txt."""
    _, ext = os.path.splitext(pad.lower())
    if ext == ".docx":
        return _lees_docx_met_opmaak(pad)
    with open(pad, "r", encoding="utf-8") as f:
        inhoud = f.read()
    return _markdown_naar_unicode(inhoud)

# ============================================
# KOLOMSTRUCTUUR (gedeeld met auto_marktplaats.py)
# ============================================
COLUMNS = [
    "artikelnummer",      # A (0)
    "titel",               # B (1)
    "categorie",            # C (2)
    "omschrijving",          # D (3)
    "online",                 # E (4)
    "lengte",                  # F (5)
    "breedte",                  # G (6)
    "hoogte",                     # H (7)
    "gewicht",                     # I (8)
    "conditie",                     # J (9)
    "staat_details",                 # K (10)
    "waarde_min",                     # L (11)
    "waarde_max",                      # M (12)
    "vraagprijs",                       # N (13)
    "aanmaakdatum",                      # O (14)
    "aanmaaktijd",                       # P (15)
    "tijdsperiode",                       # Q (16)
    "opslaglocatie",                       # R (17)
    "sublocatie",                           # S (18)
    "rij",                                   # T (19)
    "folder_locatie",                         # U (20)
    "verkocht",                                 # V (21)
    "verkoopprijs",                              # W (22)
    "verkoopdatum",                               # X (23)
    "algemene_voorwaarden",                        # Y (24)
    "url_1",                                       # Z (25)
    "url_2",                                       # AA (26)
    "url_3",                                       # AB (27)
    "url_4",                                       # AC (28)
    "url_5",                                       # AD (29)
    "leverwijze",                                   # AE (30)
    "klant_naam",                                   # AF (31)
    "klant_telefoon",                               # AG (32)
    "klant_email",                                   # AH (33)
    "ophaal_afspraak",                               # AI (34)
    "track_trace",                                   # AJ (35)
    "verwerkt_door",                                 # AK (36)
    "toegewezen_aan",                                # AL (37)
    "gereserveerd",                                  # AM (38)
    "reserveprijs",                                  # AN (39)
    "reserveerdatum",                                # AO (40)
    "reservering_klant_naam",                        # AP (41)
]
COL = {name: idx for idx, name in enumerate(COLUMNS)}

# ============================================
# KOLOM LABELS
# ============================================
KOLOM_LABELS = {
    "artikelnummer": "Artikelnummer",
    "titel": "Titel",
    "categorie": "Categorie",
    "omschrijving": "Omschrijving",
    "online": "Online",
    "lengte": "Lengte (cm)",
    "breedte": "Breedte (cm)",
    "hoogte": "Hoogte (cm)",
    "gewicht": "Gewicht (kg)",
    "conditie": "Conditie",
    "staat_details": "Staat details",
    "waarde_min": "Min. waarde (€)",
    "waarde_max": "Max. waarde (€)",
    "vraagprijs": "Vraagprijs (€)",
    "aanmaakdatum": "Aanmaakdatum",
    "aanmaaktijd": "Aanmaaktijd",
    "tijdsperiode": "Tijdsperiode",
    "opslaglocatie": "Opslaglocatie",
    "sublocatie": "Sublocatie",
    "rij": "Rij",
    "folder_locatie": "Folder locatie",
    "verkocht": "Verkocht",
    "verkoopprijs": "Verkoopprijs (€)",
    "verkoopdatum": "Verkoopdatum",
    "algemene_voorwaarden": "Algemene voorwaarden",
    "url_1": "URL 1",
    "url_2": "URL 2",
    "url_3": "URL 3",
    "url_4": "URL 4",
    "url_5": "URL 5",
    "leverwijze": "Leverwijze",
    "klant_naam": "Klant naam",
    "klant_telefoon": "Klant telefoon",
    "klant_email": "Klant e-mail",
    "ophaal_afspraak": "Ophaal afspraak",
    "track_trace": "Track & Trace",
    "verwerkt_door": "Verwerkt door",
    "toegewezen_aan": "Toegewezen aan",
    "gereserveerd": "Gereserveerd",
    "reserveprijs": "Reserveprijs (€)",
    "reserveerdatum": "Reserveerdatum",
    "reservering_klant_naam": "Gereserveerd voor",
}

# Standaard zichtbare kolommen per filter
DEFAULT_ZICHTBARE_KOLOMMEN_ALLES = [
    "artikelnummer", "titel", "categorie", "conditie", "vraagprijs",
    "aanmaakdatum", "aanmaaktijd", "verwerkt_door", "online", "verkocht",
    "gereserveerd", "verkoopprijs", "leverwijze", "klant_naam", "toegewezen_aan"
]

DEFAULT_ZICHTBARE_KOLOMMEN_OFFLINE = [
    "artikelnummer", "titel", "categorie", "conditie", "vraagprijs",
    "aanmaakdatum", "aanmaaktijd", "opslaglocatie", "sublocatie", "rij",
    "verwerkt_door", "toegewezen_aan"
]

DEFAULT_ZICHTBARE_KOLOMMEN_ONLINE = [
    "artikelnummer", "titel", "categorie", "conditie", "vraagprijs",
    "aanmaakdatum", "aanmaaktijd", "url_1", "url_2", "url_3",
    "verwerkt_door", "toegewezen_aan"
]

DEFAULT_ZICHTBARE_KOLOMMEN_VERKOCHT = [
    "artikelnummer", "titel", "categorie", "verkoopprijs", "verkoopdatum",
    "leverwijze", "klant_naam", "klant_telefoon", "klant_email",
    "ophaal_afspraak", "track_trace", "verwerkt_door", "toegewezen_aan"
]

DEFAULT_ZICHTBARE_KOLOMMEN_GERESERVEERD = [
    "artikelnummer", "titel", "categorie", "conditie", "vraagprijs",
    "reserveprijs", "reserveerdatum", "reservering_klant_naam",
    "verwerkt_door", "toegewezen_aan"
]

# Filter types
FILTER_ALLES = "alles"
FILTER_OFFLINE = "offline"
FILTER_ONLINE = "online"
FILTER_VERKOCHT = "verkocht"
FILTER_GERESERVEERD = "gereserveerd"

FILTER_NAMEN = {
    FILTER_ALLES: "Alles",
    FILTER_OFFLINE: "Offline",
    FILTER_ONLINE: "Online",
    FILTER_VERKOCHT: "Verkocht",
    FILTER_GERESERVEERD: "Gereserveerd"
}

DEFAULT_ZICHTBARE_PER_FILTER = {
    FILTER_ALLES: DEFAULT_ZICHTBARE_KOLOMMEN_ALLES,
    FILTER_OFFLINE: DEFAULT_ZICHTBARE_KOLOMMEN_OFFLINE,
    FILTER_ONLINE: DEFAULT_ZICHTBARE_KOLOMMEN_ONLINE,
    FILTER_VERKOCHT: DEFAULT_ZICHTBARE_KOLOMMEN_VERKOCHT,
    FILTER_GERESERVEERD: DEFAULT_ZICHTBARE_KOLOMMEN_GERESERVEERD,
}

CONDITIES = ["Nieuwstaat", "Zo goed als nieuw", "Gebruikt", "Beschadigd"]

STAAT_DETAILS = {
    "Nieuwstaat": ["In verpakking", "Zonder verpakking", "Beschadigde verpakking", "Getest en werkend", "Getest en defect", "Niet getest"],
    "Zo goed als nieuw": ["Lichte gebruikerssporen", "Ongebruikt", "Goede staat", "Getest en werkend", "Getest en defect", "Niet getest"],
    "Gebruikt": ["Gebruikerssporen", "Kleine schades zoals krassen en vlekken", "Mogelijk ontbrekende onderdelen", "Getest en werkend", "Getest en defect", "Niet getest"],
    "Beschadigd": ["Ontbrekende onderdelen", "Zware gebruikerssporen", "Opvallende krassen, sporen en vlekken", "Werking onbekend & niet getest"],
}

DEFAULT_CATEGORIEEN = [
    "Huishouden", "Elektra/Elektronica", "Meubels", "Verlichting", "Speelgoed",
    "Kleding/Textiel", "Boeken/Media", "Sieraden/Accessoires", "Sport & Vrije tijd",
    "Tuin & Buiten", "Gereedschap", "Servies/Keuken", "Kunst & Decoratie", "Overig",
]

DEFAULT_TIJDSPERIODES = [
    "Antiek (100+ jaar)", "Vintage (20-100 jaar)", "Retro", "Klassiek",
    "Modern/Hedendaags", "Onbekend",
]

MAX_TITEL_LENGTE = 60

TEXTVIEW_CSS = b"""
textview {
    border: 1px solid alpha(@borders, 0.6);
    border-radius: 4px;
}
textview text {
    background-color: #3a3a3a;
    color: #e8e8e8;
    padding: 5px;
}
"""

# ============================================
# STANDAARD SNELTOETSEN
# ============================================
DEFAULT_SNELTOETSEN = {
    "verwijderen": ["Delete", "KP_Delete"],
    "ongedaan_maken": ["<Control>z"],
    "weer_gedaan_maken": ["<Control><Alt>z"],
    "online_markeren": ["<Control>o"],
    "bewerken": ["<Control>b"],
    "zoeken": ["<Control>f"],
    "toewijzen": ["<Control>t"],
    "alles_selecteren": ["<Control>a"],
    "print_barcode": ["<Control>p"],
    "verkocht_markeren": ["<Control>s"],
    "retour_melden": ["<Control>r"],
    "gereserveerd_markeren": ["<Control><Shift>r"],
    "open_map": ["<Control>e"],
    "open_fotos": ["<Control>i"],
    "locatie_wijzigen": ["<Control><Shift>l"],
}


def apply_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(TEXTVIEW_CSS)
    screen = Gdk.Screen.get_default()
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

ALGEMENE_VOORWAARDEN = """Algemene voorwaarden:
Wij zijn een kleine kringloopwinkel en proberen z.s.m. te reageren. Soms is het heel druk in de winkel en lukt dit niet dezelfde dag.

De richtprijs van een product baseren wij op bestaand aanbod en staat van het artikel met minimum/maximum schatting.

Graag alleen biedingen plaatsen via de bied optie van marktplaats. Advertenties laten we vaak minimaal 2 weken online staan voordat we akkoord gaan met het hoogste aannemelijke bod. Bedankt voor uw begrip 🙏🏻

Als wij akkoord gaan met uw bod, reserveren wij het product maximaal een week voor u. U kunt het product ophalen en afrekenen in onze winkel of kiezen voor verzending.

U bent altijd welkom in onze winkel, maar langskomen voor de Marktplaats advertenties zonder afspraak wordt niet op prijs gesteld. Dit gaat altijd via specifieke medewerkers.

Let op: Bij ophalen in de winkel vervalt het herroepingsrecht en kun je het product ter plekke testen.

Wij zijn een Stichting en onderdeel van Samen Circulair Hoeksche Waard. Alle inkomsten gaan naar de huur en naar het creëren van plekken voor dagbesteding voor mensen die speciale zorg onvangen o.a. via Pameijer, Cavent en Welzijn Hoeksche Waard. Wij maken geen winst!!!

Ons adres:
Kringloop HerNieuw
Willem Beukelszstraat 6B
3261 LV Oud-Beijerland

Openingstijden Kringloop:
Dinsdag t/m vrijdag 10.00 – 16.00 uur
Zaterdag 10:00-13:00 uur
Zondag en maandag Gesloten"""


def config_dir():
    return data_dir()


def config_path():
    return os.path.join(config_dir(), "productmanager_config.json")


def users_path():
    return os.path.join(config_dir(), "productmanager_users.json")


def user_settings_path(gebruikersnaam):
    """Pad voor gebruikersspecifieke instellingen."""
    settings_dir = os.path.join(config_dir(), "user_settings")
    os.makedirs(settings_dir, exist_ok=True)
    return os.path.join(settings_dir, f"{gebruikersnaam}_settings.json")


# ============================================
# DYNAMISCHE MAP ZOEKFUNCTIE
# ============================================
def vind_marktplaats_map(config=None):
    """
    Zoek dynamisch naar de Marktplaats map in de home directory.
    Prioriteit: 1. ~/HERNIEUW/Marktplaats/  2. ~/kDrive/HERNIEUW/Marktplaats/
    3. ~/GDrive/HERNIEUW/Marktplaats/  4. ~/Sync/HERNIEUW/Marktplaats/
    5. config base_folder als fallback
    """
    home = os.path.expanduser("~")

    # Eerst zoeken naar ~/HERNIEUW/Marktplaats/ (directe structuur)
    direct_pad = os.path.join(home, "HERNIEUW", "Marktplaats")
    if os.path.isdir(direct_pad):
        return direct_pad

    # Dan zoeken in verschillende cloud/drive mappen
    mogelijke_paden = [
        os.path.join(home, "kDrive", "HERNIEUW", "Marktplaats"),
        os.path.join(home, "GDrive", "HERNIEUW", "Marktplaats"),
        os.path.join(home, "Sync", "HERNIEUW", "Marktplaats"),
        os.path.join(home, "OneDrive", "HERNIEUW", "Marktplaats"),
        os.path.join(home, "Nextcloud", "HERNIEUW", "Marktplaats"),
        os.path.join(home, "Google Drive", "HERNIEUW", "Marktplaats"),
    ]

    for pad in mogelijke_paden:
        if os.path.isdir(pad):
            return pad

    # Als niets gevonden, gebruik de basismap uit instellingen als fallback
    if config:
        base_folder = config.get("base_folder")
        if base_folder and os.path.isdir(base_folder):
            return base_folder

    # Laatste fallback: maak een map aan in de home directory
    fallback_pad = os.path.join(home, "HERNIEUW", "Marktplaats")
    try:
        os.makedirs(fallback_pad, exist_ok=True)
        print(f"INFO: Nieuwe Marktplaats map aangemaakt op: {fallback_pad}")
        return fallback_pad
    except Exception as e:
        print(f"ERROR: Kon Marktplaats map niet aanmaken: {e}")
        return home


def vind_product_map(artikelnummer, config=None):
    """
    Vind de volledige product map voor een artikelnummer.
    Zoekt in de dynamisch gevonden Marktplaats map.
    """
    basis_map = vind_marktplaats_map(config)

    # Probeer het pad in de Marktplaats map
    pad = os.path.join(basis_map, artikelnummer)
    if os.path.isdir(pad):
        return pad

    # Als niet gevonden, zoek in submappen (voor compatibiliteit)
    for root, dirs, files in os.walk(basis_map):
        if artikelnummer in dirs:
            return os.path.join(root, artikelnummer)

    # Fallback: geef het pad terug (ook al bestaat het niet)
    return pad


# ============================================
# GEBRUIKERSBEHEER
# ============================================
def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, digest


class UserManager:
    def __init__(self):
        self.path = users_path()
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def heeft_gebruikers(self):
        return len(self.data) > 0

    def gebruikersnamen(self):
        return sorted(self.data.keys())

    def voeg_toe(self, gebruikersnaam, wachtwoord):
        salt, digest = _hash_password(wachtwoord)
        self.data[gebruikersnaam] = {"salt": salt, "hash": digest}
        self.save()

    def verwijder(self, gebruikersnaam):
        if gebruikersnaam in self.data:
            del self.data[gebruikersnaam]
            self.save()
        settings_path = user_settings_path(gebruikersnaam)
        if os.path.exists(settings_path):
            try:
                os.remove(settings_path)
            except Exception:
                pass

    def controleer(self, gebruikersnaam, wachtwoord):
        info = self.data.get(gebruikersnaam)
        if not info:
            return False
        _, digest = _hash_password(wachtwoord, info["salt"])
        return digest == info["hash"]


# ============================================
# GEBRUIKERSINSTELLINGEN
# ============================================
class UserSettings:
    """Slaat gebruikersspecifieke instellingen op zoals kolomvolgorde en zichtbare kolommen per filter."""

    def __init__(self, gebruikersnaam):
        self.gebruikersnaam = gebruikersnaam
        self.path = user_settings_path(gebruikersnaam)
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._get_defaults()

    def _get_defaults(self):
        return {
            "zichtbare_kolommen": DEFAULT_ZICHTBARE_PER_FILTER.copy(),
            "kolom_volgorde": {},  # {filter: [kolomnamen]}
            "kolom_breedtes": {},  # {kolomnaam: breedte_in_pixels}
            "actieve_filter": FILTER_OFFLINE,
            "sneltoetsen": DEFAULT_SNELTOETSEN.copy(),
        }

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def get_zichtbare_kolommen(self, filter_type=FILTER_OFFLINE):
        return self.data.get("zichtbare_kolommen", {}).get(filter_type, DEFAULT_ZICHTBARE_PER_FILTER.get(filter_type, []))

    def set_zichtbare_kolommen(self, filter_type, kolommen):
        if "zichtbare_kolommen" not in self.data:
            self.data["zichtbare_kolommen"] = {}
        self.data["zichtbare_kolommen"][filter_type] = kolommen
        self.save()

    def get_kolom_volgorde(self, filter_type=FILTER_OFFLINE):
        return self.data.get("kolom_volgorde", {}).get(filter_type, [])

    def set_kolom_volgorde(self, filter_type, volgorde):
        if "kolom_volgorde" not in self.data:
            self.data["kolom_volgorde"] = {}
        self.data["kolom_volgorde"][filter_type] = volgorde
        self.save()

    def get_kolom_breedte(self, kolomnaam, default=100):
        return self.data.get("kolom_breedtes", {}).get(kolomnaam, default)

    def set_kolom_breedte(self, kolomnaam, breedte):
        if "kolom_breedtes" not in self.data:
            self.data["kolom_breedtes"] = {}
        self.data["kolom_breedtes"][kolomnaam] = breedte
        self.save()

    def get_actieve_filter(self):
        return self.data.get("actieve_filter", FILTER_OFFLINE)

    def set_actieve_filter(self, filter_type):
        self.data["actieve_filter"] = filter_type
        self.save()

    def get_sneltoets(self, actie, default=None):
        return self.data.get("sneltoetsen", {}).get(actie, default)

    def set_sneltoets(self, actie, toetscombinatie):
        if "sneltoetsen" not in self.data:
            self.data["sneltoetsen"] = {}
        self.data["sneltoetsen"][actie] = toetscombinatie
        self.save()


# ============================================
# CONFIGURATIE
# ============================================
class ConfigManager:
    DEFAULTS = {
        "xml_path": os.path.join(config_dir(), "producten.xml"),
        "base_folder": os.path.expanduser("~/HERNIEUW/Marktplaats"),
        "categorieen": DEFAULT_CATEGORIEEN,
        "tijdsperiodes": DEFAULT_TIJDSPERIODES,
        "opslaglocatie_codes": {"Locatie A": "A", "Locatie B": "B"},
        "sublocatie_codes": {"Sublocatie 1": "1", "Sublocatie 2": "2"},
        "rij_codes": {"Rij 1": "1", "Rij 2": "2"},
        "volgnummers": {},
        "algemene_voorwaarden_pad": "",
        "printer": {
            "enabled": False,
            "print_method": "cups",
            "printer_name": "",
            "brother_ql_model": "QL-500",
            "brother_ql_label": "62",
            "brother_ql_identifier": "",
            "auto_cut": True,
        },
        "barcode": {
            "module_width_mm": 0.4,
            "module_height_mm": 7.0,
            "quiet_zone_mm": 2.0,
        },
    }

    def __init__(self):
        self.path = config_path()
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = json.loads(json.dumps(self.DEFAULTS))
                merged.update(loaded)
                return merged
            except Exception:
                pass
        return json.loads(json.dumps(self.DEFAULTS))

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        if is_shared_key(key):
            return shared_get(key, default)
        return self.data.get(key, default)

    def set(self, key, value):
        if is_shared_key(key):
            shared_set(key, value)
            return
        self.data[key] = value
        self.save()


# ============================================
# OPSLAG-BACKENDS
# ============================================
class StorageBackend:
    def load_products(self):
        raise NotImplementedError

    def add_product(self, product):
        raise NotImplementedError

    def update_product(self, artikelnummer, product):
        raise NotImplementedError

    def delete_product(self, artikelnummer):
        raise NotImplementedError


class XmlBackend(StorageBackend):
    def __init__(self, xml_path):
        self.xml_path = xml_path

    def _ensure_file(self):
        if not os.path.exists(self.xml_path):
            import xml.etree.ElementTree as ET
            root = ET.Element("producten")
            tree = ET.ElementTree(root)
            os.makedirs(os.path.dirname(self.xml_path), exist_ok=True)
            tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    def load_products(self):
        import xml.etree.ElementTree as ET
        self._ensure_file()
        tree = ET.parse(self.xml_path)
        root = tree.getroot()
        products = []
        for prod_el in root.findall("product"):
            product = {}
            for col in COLUMNS:
                el = prod_el.find(col)
                product[col] = el.text if el is not None and el.text else ""
            products.append(product)
        return products

    def _write_all(self, products):
        import xml.etree.ElementTree as ET
        root = ET.Element("producten")
        for product in products:
            prod_el = ET.SubElement(root, "product")
            for col in COLUMNS:
                el = ET.SubElement(prod_el, col)
                el.text = str(product.get(col, ""))
        tree = ET.ElementTree(root)
        os.makedirs(os.path.dirname(self.xml_path), exist_ok=True)
        tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    def add_product(self, product):
        products = self.load_products()
        products.append(product)
        self._write_all(products)

    def update_product(self, artikelnummer, product):
        products = self.load_products()
        for i, p in enumerate(products):
            if p.get("artikelnummer") == artikelnummer:
                products[i] = product
                break
        self._write_all(products)

    def delete_product(self, artikelnummer):
        products = self.load_products()
        products = [p for p in products if p.get("artikelnummer") != artikelnummer]
        self._write_all(products)


def get_backend(config):
    return XmlBackend(config.get("xml_path"))


def get_cups_printers():
    """Haal een lijst van beschikbare CUPS printers op."""
    try:
        result = subprocess.run(["lpstat", "-p"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        printers = []
        for line in result.stdout.decode("utf-8", errors="ignore").splitlines():
            if line.startswith("printer "):
                printers.append(line.split()[1])
        return printers
    except Exception:
        return []


# ============================================
# HELPERS
# ============================================
def generate_artikelnummer(config, storage, opslaglocatie_code, sublocatie_code, rij_code):
    prefix = f"{opslaglocatie_code}{sublocatie_code}{rij_code}"
    datum_deel = datetime.date.today().strftime("%d%m")
    teller_sleutel = f"{prefix}{datum_deel}"

    volgnummers = config.get("volgnummers", {})
    laatste = volgnummers.get(teller_sleutel, 0)

    try:
        bestaande = storage.load_products()
        for p in bestaande:
            nr = p.get("artikelnummer", "")
            if nr.startswith(teller_sleutel) and len(nr) == len(teller_sleutel) + 2:
                try:
                    val = int(nr[len(teller_sleutel):])
                    laatste = max(laatste, val)
                except ValueError:
                    pass
    except Exception:
        pass

    nieuw_nummer = laatste + 1
    if nieuw_nummer > 99:
        raise ValueError(
            f"Maximaal 99 artikelen per dag bereikt voor locatie '{prefix}' op {datum_deel}."
        )
    volgnummers[teller_sleutel] = nieuw_nummer
    config.set("volgnummers", volgnummers)

    return f"{teller_sleutel}{nieuw_nummer:02d}"


def build_txt_beschrijving(product, config=None):
    """Genereert omschrijving.txt in het mapje van het artikelnummer."""
    parts = []

    titel = product.get("titel", "")
    if titel:
        parts.append(titel)

    omschrijving = product.get("omschrijving", "")
    if omschrijving:
        parts.append(omschrijving)

    specs = []
    lengte = product.get("lengte", "")
    breedte = product.get("breedte", "")
    hoogte = product.get("hoogte", "")
    gewicht = product.get("gewicht", "")
    if lengte or breedte or hoogte or gewicht:
        dims = [f"{x}cm" for x in (lengte, breedte, hoogte) if x]
        line = f"Afmeting (LxBxH & G): {' x '.join(dims)}"
        if gewicht:
            line += f" & {gewicht} kg"
        specs.append(line)
    if product.get("conditie"):
        specs.append(f"Conditie/Staat: {product.get('conditie')}")
    if product.get("staat_details"):
        specs.append(f"Schades: {product.get('staat_details')}")
    waarde_min = product.get("waarde_min", "")
    waarde_max = product.get("waarde_max", "")
    if waarde_min:
        line = f"Waarde: {waarde_min}"
        if waarde_max:
            line += f" ~{waarde_max}"
        specs.append(line)
    if product.get("artikelnummer"):
        specs.append(f"Artikelnummer: {product.get('artikelnummer')}")
    if specs:
        parts.append("\n".join(specs))

    # Algemene voorwaarden
    from marktplaats_suite.voorwaarden import voorwaarden_voor_advertentie
    voorwaarden = product.get("algemene_voorwaarden") or voorwaarden_voor_advertentie()
    if voorwaarden:
        parts.append(voorwaarden)

    return "\n\n".join(parts)


def maak_product_map(config, product):
    """Maakt (of hergebruikt) de map voor dit artikelnummer."""
    basis_map = vind_marktplaats_map(config)
    artikelnummer = product["artikelnummer"]
    folder = os.path.join(basis_map, artikelnummer)
    bestond_al = os.path.exists(folder)
    os.makedirs(folder, exist_ok=True)

    txt_path = os.path.join(folder, "omschrijving.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(build_txt_beschrijving(product, config))

    # Sla alleen het relatieve pad op in de folder_locatie
    product["folder_locatie"] = os.path.join("Marktplaats", artikelnummer)

    return folder, bestond_al


def genereer_barcode(artikelnummer, output_folder, barcode_config=None, count_label=None):
    """Genereert een Code128-barcode-afbeelding met het artikelnummer."""
    try:
        import barcode
        from barcode.writer import ImageWriter
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError(
            "python-barcode of PIL is niet geïnstalleerd. Installeer met:\n"
            "pip install python-barcode pillow --break-system-packages"
        )

    # FIX: Zorg dat ANTIALIAS bestaat voor compatibiliteit
    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.LANCZOS

    barcode_config = barcode_config or {}
    writer_options = {
        "module_width": barcode_config.get("module_width_mm", 0.4),
        "module_height": barcode_config.get("module_height_mm", 7.0),
        "quiet_zone": barcode_config.get("quiet_zone_mm", 2.0),
        "font_size": 8,
        "text_distance": 3.0,
        "dpi": 300,
    }

    code128 = barcode.get("code128", artikelnummer, writer=ImageWriter())
    output_path = os.path.join(output_folder, f"{artikelnummer}_barcode")
    saved_path = code128.save(output_path, options=writer_options)

    if count_label:
        try:
            img = Image.open(saved_path)
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
            except:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), count_label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            new_height = img.height + text_height + 20
            new_img = Image.new('RGB', (img.width, new_height), 'white')
            new_img.paste(img, (0, text_height + 10))

            draw = ImageDraw.Draw(new_img)
            text_x = (img.width - text_width) // 2
            draw.text((text_x, 5), count_label, fill='black', font=font)

            new_img.save(saved_path)
        except Exception as e:
            print(f"Waarschuwing: Kon count_label niet toevoegen: {e}")

    return saved_path


def print_barcode(image_path, printer_config, auto_cut=True):
    """Print de barcode-afbeelding met optionele auto-cut."""
    methode = printer_config.get("print_method", "cups")

    if methode == "brother_ql":
        _print_barcode_brother_ql(image_path, printer_config, auto_cut)
    else:
        _print_barcode_cups(image_path, printer_config.get("printer_name", ""))


def _print_barcode_brother_ql(image_path, printer_config, auto_cut=True):
    """Print barcode met brother_ql Python API (directe communicatie)."""
    try:
        from brother_ql.conversion import convert
        from brother_ql.backends.helpers import send
        from brother_ql.raster import BrotherQLRaster
    except ImportError:
        raise RuntimeError("brother_ql is niet geïnstalleerd.")

    model = printer_config.get("brother_ql_model", "QL-560")
    label_size = printer_config.get("brother_ql_label", "62")
    identifier = printer_config.get("brother_ql_identifier", "")

    if not identifier:
        raise RuntimeError(
            "Geen USB-identifier ingesteld voor brother_ql.\n"
            "Vind 'm met: lsusb | grep -i brother"
        )

    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS

    print(f"🖨️ Python API - Model: {model}, Label: {label_size}")
    print(f"🔍 Identifier: {identifier}")
    print(f"✂️ Auto-cut: {'AAN' if auto_cut else 'UIT'}")

    with Image.open(image_path) as img:
        qlr = BrotherQLRaster(model)
        qlr.exception_on_warning = True

        instructions = convert(
            qlr=qlr,
            images=[img],
            label=label_size,
            rotate="0",
            threshold=70.0,
            dither=False,
            compress=False,
            red=False,
            cut=auto_cut,
        )

        send(instructions=instructions, printer_identifier=identifier, backend_identifier="pyusb", blocking=True)

        # Extra: stuur een apart cut commando voor de zekerheid
        if auto_cut:
            try:
                import time
                time.sleep(0.5)
                qlr_cut = BrotherQLRaster(model)
                cut_instructions = qlr_cut.get_instructions('cut')
                send(instructions=cut_instructions, printer_identifier=identifier, backend_identifier="pyusb", blocking=True)
                print("✂️ Auto-cut uitgevoerd")
            except Exception as e:
                print(f"⚠️ Extra cut commando mislukt: {e}")

    print("✅ Barcode geprint")


def _print_barcode_cups(image_path, printer_name):
    """Print barcode via CUPS."""
    cmd = ["lp"]
    if printer_name:
        cmd += ["-d", printer_name]
    cmd += [image_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore"))


# ============================================
# FUNCTIE OM LOCATIE TE WIJZIGEN
# ============================================
def wijzig_artikelnummer_locatie(config, oud_artikelnummer, nieuwe_locatie_code):
    """
    Wijzig de locatie van een product (eerste 3 tekens van artikelnummer).
    Als het nieuwe artikelnummer al bestaat, wordt automatisch het volgende vrije
    volgnummer gebruikt (laatste 2 cijfers lopen op).
    """
    import shutil

    storage = get_backend(config)
    producten = storage.load_products()

    # Vind het product
    product = next((p for p in producten if p.get("artikelnummer") == oud_artikelnummer), None)
    if not product:
        raise ValueError(f"Product {oud_artikelnummer} niet gevonden")

    # Bouw het nieuwe artikelnummer
    if len(oud_artikelnummer) >= 8:
        datum_deel = oud_artikelnummer[3:7]  # ddmm
    else:
        raise ValueError(f"Ongeldig artikelnummer formaat: {oud_artikelnummer}")

    # ========================================
    # BEPALEN VAN HET NIEUWE ARTIKELNUMMER
    # ========================================
    # Bouw de basis zonder volgnummer
    basis_zonder_volg = f"{nieuwe_locatie_code}{datum_deel}"

    # Zoek alle bestaande artikelnummers met deze prefix
    bestaande_nrs = []
    for p in producten:
        nr = p.get("artikelnummer", "")
        if nr.startswith(basis_zonder_volg) and len(nr) == len(basis_zonder_volg) + 2:
            try:
                volg = int(nr[len(basis_zonder_volg):])
                bestaande_nrs.append(volg)
            except ValueError:
                pass

    # Bepaal het hoogste bestaande volgnummer
    hoogste_volg = max(bestaande_nrs) if bestaande_nrs else 0

    # Nieuw volgnummer = hoogste + 1 (of 1 als er geen zijn)
    nieuw_volg = hoogste_volg + 1

    # Check of we niet boven de 99 komen
    if nieuw_volg > 99:
        raise ValueError(
            f"Maximaal 99 artikelen per dag bereikt voor locatie '{nieuwe_locatie_code}' op {datum_deel}.\n"
            f"Kies een andere locatie of wacht tot morgen."
        )

    # Maak het nieuwe artikelnummer
    nieuw_artikelnummer = f"{basis_zonder_volg}{nieuw_volg:02d}"

    print(f"📝 Nieuw artikelnummer: {nieuw_artikelnummer} (volgnummer {nieuw_volg:02d})")

    # Vind de map
    oude_map = vind_product_map(oud_artikelnummer, config)
    if not os.path.isdir(oude_map):
        raise ValueError(f"Map niet gevonden voor {oud_artikelnummer}: {oude_map}")

    # Nieuwe map locatie
    basis_map = vind_marktplaats_map(config)
    nieuwe_map = os.path.join(basis_map, nieuw_artikelnummer)

    # ALS DE NIEUWE MAP AL BESTAAT, VERWIJDEREN WE DIE EERST (FORCED)
    if os.path.exists(nieuwe_map):
        try:
            shutil.rmtree(nieuwe_map)
            print(f"⚠️ Bestaande map verwijderd: {nieuwe_map}")
        except Exception as e:
            raise RuntimeError(f"Kon bestaande map niet verwijderen: {e}")

    # Hernoem de map met shutil.move
    try:
        shutil.move(oude_map, nieuwe_map)
        print(f"📁 Map verplaatst: {oude_map} -> {nieuwe_map}")
    except Exception as e:
        raise RuntimeError(f"Kon map niet verplaatsen: {e}")

    # Hernoem barcode bestanden
    for bestand in os.listdir(nieuwe_map):
        if oud_artikelnummer in bestand and "_barcode" in bestand:
            oud_bestand = os.path.join(nieuwe_map, bestand)
            nieuw_bestand = os.path.join(nieuwe_map, bestand.replace(oud_artikelnummer, nieuw_artikelnummer))
            try:
                os.rename(oud_bestand, nieuw_bestand)
                print(f"🏷️ Barcode hernoemd: {os.path.basename(oud_bestand)} -> {os.path.basename(nieuw_bestand)}")
            except Exception as e:
                print(f"⚠️ Waarschuwing: Kon barcode niet hernoemen: {e}")

    # Update omschrijving.txt met nieuw artikelnummer
    txt_path = os.path.join(nieuwe_map, "omschrijving.txt")
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                inhoud = f.read()
            inhoud = inhoud.replace(oud_artikelnummer, nieuw_artikelnummer)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(inhoud)
            print(f"📄 omschrijving.txt geüpdatet")
        except Exception as e:
            print(f"⚠️ Waarschuwing: Kon omschrijving.txt niet updaten: {e}")

    # Verwijder het OUDE product uit de database
    try:
        storage.delete_product(oud_artikelnummer)
        print(f"🗑️ Oud product {oud_artikelnummer} verwijderd uit database")
    except Exception as e:
        print(f"⚠️ Waarschuwing: Kon oud product niet verwijderen: {e}")

    # Update het product met het nieuwe artikelnummer
    product["artikelnummer"] = nieuw_artikelnummer
    product["folder_locatie"] = os.path.join("Marktplaats", nieuw_artikelnummer)

    # Update opslaglocatie, sublocatie, rij in product
    if len(nieuwe_locatie_code) >= 3:
        opslag_codes = config.get("opslaglocatie_codes", {})
        for naam, code in opslag_codes.items():
            if code == nieuwe_locatie_code[0]:
                product["opslaglocatie"] = naam
                break

        sub_codes = config.get("sublocatie_codes", {})
        for naam, code in sub_codes.items():
            if code == nieuwe_locatie_code[1]:
                product["sublocatie"] = naam
                break

        rij_codes = config.get("rij_codes", {})
        for naam, code in rij_codes.items():
            if code == nieuwe_locatie_code[2]:
                product["rij"] = naam
                break

    # Voeg het nieuwe product toe aan de database
    try:
        storage.add_product(product)
        print(f"✅ Product {nieuw_artikelnummer} toegevoegd aan database")
    except Exception as e:
        # Rollback: probeer map terug te zetten
        try:
            shutil.move(nieuwe_map, oude_map)
            print(f"↩️ Map teruggezet: {nieuwe_map} -> {oude_map}")
        except:
            pass
        raise RuntimeError(f"Kon product niet opslaan: {e}")

    print(f"\n✅ {oud_artikelnummer} -> {nieuw_artikelnummer} succesvol gewijzigd!")

    return nieuw_artikelnummer, nieuwe_map


# ============================================
# LOCATIE WIJZIGEN DIALOOG
# ============================================
class LocatieWijzigDialog(Gtk.Dialog):
    def __init__(self, parent, artikelnummer, config):
        super().__init__(title=f"Locatie wijzigen - {artikelnummer}", transient_for=parent, flags=0)
        self.artikelnummer = artikelnummer
        self.config = config
        self.set_default_size(400, 200)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Wijzigen", Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(15)

        # Huidige artikelnummer tonen
        label = Gtk.Label()
        label.set_markup(f"<b>Huidig artikelnummer:</b> {artikelnummer}")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        box.pack_start(Gtk.Label(label="Nieuwe locatie code (3 tekens, bijv. A11):", xalign=0), False, False, 0)

        self.locatie_entry = Gtk.Entry()
        self.locatie_entry.set_placeholder_text("bijv. A11")
        self.locatie_entry.set_max_length(3)
        self.locatie_entry.connect("changed", self._on_locatie_changed)
        box.pack_start(self.locatie_entry, False, False, 0)

        # Voorbeeld van nieuw artikelnummer
        self.voorbeeld_label = Gtk.Label()
        self.voorbeeld_label.set_markup("<small><i>Voorbeeld: A11080801</i></small>")
        self.voorbeeld_label.set_xalign(0)
        box.pack_start(self.voorbeeld_label, False, False, 0)

        # Waarschuwing
        self.warning_label = Gtk.Label()
        self.warning_label.set_markup("<span foreground='orange'>⚠️ Dit hernoemt de map, barcode en update de omschrijving.txt</span>")
        self.warning_label.set_xalign(0)
        self.warning_label.set_line_wrap(True)
        box.pack_start(self.warning_label, False, False, 0)

        self.show_all()

    def _on_locatie_changed(self, widget):
        locatie = self.locatie_entry.get_text().strip()
        if len(locatie) == 3 and len(self.artikelnummer) >= 8:
            datum_deel = self.artikelnummer[3:7]
            volg_deel = self.artikelnummer[7:9]
            nieuw = f"{locatie}{datum_deel}{volg_deel}"
            self.voorbeeld_label.set_markup(f"<small><i>Nieuw artikelnummer: {nieuw}</i></small>")
        else:
            self.voorbeeld_label.set_markup("<small><i>Voer 3 tekens in (bijv. A11)</i></small>")

    def get_nieuwe_locatie(self):
        return self.locatie_entry.get_text().strip()


# ============================================
# LOGIN & GEBRUIKERSBEHEER-DIALOGEN
# ============================================
class NieuweGebruikerDialog(Gtk.Dialog):
    def __init__(self, parent, titel="Nieuwe gebruiker"):
        super().__init__(title=titel, transient_for=parent, flags=0)
        self.set_default_size(320, 180)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        box.pack_start(Gtk.Label(label="Gebruikersnaam:", xalign=0), False, False, 0)
        self.naam_entry = Gtk.Entry()
        box.pack_start(self.naam_entry, False, False, 0)

        box.pack_start(Gtk.Label(label="Wachtwoord:", xalign=0), False, False, 0)
        self.wachtwoord_entry = Gtk.Entry()
        self.wachtwoord_entry.set_visibility(False)
        box.pack_start(self.wachtwoord_entry, False, False, 0)

        box.pack_start(Gtk.Label(label="Herhaal wachtwoord:", xalign=0), False, False, 0)
        self.wachtwoord2_entry = Gtk.Entry()
        self.wachtwoord2_entry.set_visibility(False)
        box.pack_start(self.wachtwoord2_entry, False, False, 0)

        self.foutlabel = Gtk.Label()
        self.foutlabel.set_markup("<span foreground='red'></span>")
        box.pack_start(self.foutlabel, False, False, 0)

        self.show_all()

    def get_invoer(self):
        return (
            self.naam_entry.get_text().strip(),
            self.wachtwoord_entry.get_text(),
            self.wachtwoord2_entry.get_text(),
        )

    def toon_fout(self, msg):
        self.foutlabel.set_markup(f"<span foreground='red'>{msg}</span>")


class LoginDialog(Gtk.Dialog):
    def __init__(self, user_manager):
        super().__init__(title="Inloggen - Marktplaats Product Manager")
        self.user_manager = user_manager
        self.set_default_size(320, 220)
        self.set_position(Gtk.WindowPosition.CENTER)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(20)

        titel = Gtk.Label()
        titel.set_markup("<b>Marktplaats Product Manager</b>")
        box.pack_start(titel, False, False, 0)

        box.pack_start(Gtk.Label(label="Gebruikersnaam:", xalign=0), False, False, 0)
        self.naam_combo = Gtk.ComboBoxText.new_with_entry()
        for naam in user_manager.gebruikersnamen():
            self.naam_combo.append_text(naam)
        box.pack_start(self.naam_combo, False, False, 0)

        box.pack_start(Gtk.Label(label="Wachtwoord:", xalign=0), False, False, 0)
        self.wachtwoord_entry = Gtk.Entry()
        self.wachtwoord_entry.set_visibility(False)
        self.wachtwoord_entry.connect("activate", lambda w: self.response(Gtk.ResponseType.OK))
        box.pack_start(self.wachtwoord_entry, False, False, 0)

        self.foutlabel = Gtk.Label()
        box.pack_start(self.foutlabel, False, False, 0)

        nieuw_btn = Gtk.Button(label="Nieuwe gebruiker aanmaken")
        nieuw_btn.connect("clicked", self._on_nieuwe_gebruiker)
        box.pack_start(nieuw_btn, False, False, 5)

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Inloggen", Gtk.ResponseType.OK)

        self.show_all()

    def get_naam(self):
        tekst = self.naam_combo.get_active_text()
        return tekst.strip() if tekst else ""

    def get_wachtwoord(self):
        return self.wachtwoord_entry.get_text()

    def toon_fout(self, msg):
        self.foutlabel.set_markup(f"<span foreground='red'>{msg}</span>")

    def _on_nieuwe_gebruiker(self, widget):
        dialog = NieuweGebruikerDialog(self)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break
            naam, ww1, ww2 = dialog.get_invoer()
            if not naam:
                dialog.toon_fout("Vul een gebruikersnaam in.")
                continue
            if naam in self.user_manager.gebruikersnamen():
                dialog.toon_fout("Deze gebruikersnaam bestaat al.")
                continue
            if not ww1 or ww1 != ww2:
                dialog.toon_fout("Wachtwoorden komen niet overeen.")
                continue
            self.user_manager.voeg_toe(naam, ww1)
            self.naam_combo.append_text(naam)
            self.naam_combo.set_active(len(self.user_manager.gebruikersnamen()) - 1)
            break
        dialog.destroy()


class UsersDialog(Gtk.Dialog):
    def __init__(self, parent, user_manager, huidige_gebruiker):
        super().__init__(title="Gebruikers beheren", transient_for=parent, flags=0)
        self.user_manager = user_manager
        self.huidige_gebruiker = huidige_gebruiker
        self.set_default_size(320, 300)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        self.store = Gtk.ListStore(str)
        self.tree_view = Gtk.TreeView(model=self.store)
        renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn("Gebruikersnaam", renderer, text=0))
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 180)
        scroll.add(self.tree_view)
        box.pack_start(scroll, True, True, 0)

        knoppen_row = Gtk.Box(spacing=5)
        toevoegen_btn = Gtk.Button(label="➕ Toevoegen")
        toevoegen_btn.connect("clicked", self._on_toevoegen)
        knoppen_row.pack_start(toevoegen_btn, False, False, 0)

        verwijder_btn = Gtk.Button(label="🗑️ Verwijderen")
        verwijder_btn.connect("clicked", self._on_verwijderen)
        knoppen_row.pack_start(verwijder_btn, False, False, 0)
        box.pack_start(knoppen_row, False, False, 0)

        self._herlaad()
        self.show_all()

    def _herlaad(self):
        self.store.clear()
        for naam in self.user_manager.gebruikersnamen():
            self.store.append([naam])

    def _on_toevoegen(self, widget):
        dialog = NieuweGebruikerDialog(self)
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break
            naam, ww1, ww2 = dialog.get_invoer()
            if not naam:
                dialog.toon_fout("Vul een gebruikersnaam in.")
                continue
            if naam in self.user_manager.gebruikersnamen():
                dialog.toon_fout("Deze gebruikersnaam bestaat al.")
                continue
            if not ww1 or ww1 != ww2:
                dialog.toon_fout("Wachtwoorden komen niet overeen.")
                continue
            self.user_manager.voeg_toe(naam, ww1)
            self._herlaad()
            break
        dialog.destroy()

    def _on_verwijderen(self, widget):
        selection = self.tree_view.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        naam = model[treeiter][0]
        if naam == self.huidige_gebruiker:
            confirm = Gtk.MessageDialog(
                transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK, text="Je kan de gebruiker waarmee je nu bent ingelogd niet verwijderen."
            )
            confirm.run()
            confirm.destroy()
            return
        if len(self.user_manager.gebruikersnamen()) <= 1:
            confirm = Gtk.MessageDialog(
                transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK, text="Er moet minstens één gebruiker overblijven."
            )
            confirm.run()
            confirm.destroy()
            return
        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO, text=f"Gebruiker '{naam}' verwijderen?"
        )
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            self.user_manager.verwijder(naam)
            self._herlaad()


# ============================================
# INSTELLINGEN-DIALOOG (WERKT)
# ============================================
class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent, config, user_settings):
        try:
            super().__init__(title="Instellingen", transient_for=parent, flags=0)
            self.config = config
            self.user_settings = user_settings
            self.set_default_size(650, 700)
            self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)

            # Content area met scroll
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_vexpand(True)
            self.get_content_area().pack_start(scrolled, True, True, 0)

            # Main container
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            main_box.set_border_width(15)
            scrolled.add(main_box)

            # --- Dynamische map zoekfunctie uitleg ---
            main_box.pack_start(self._section_label("📁 Dynamische Marktplaats map zoeker"), False, False, 0)

            info_label = Gtk.Label()
            info_label.set_markup(
                "<small><i>🔍 Het programma zoekt automatisch naar de Marktplaats map in jouw home directory.\n"
                "Zoekvolgorde:\n"
                "1. ~/HERNIEUW/Marktplaats/\n"
                "2. ~/kDrive/HERNIEUW/Marktplaats/\n"
                "3. ~/GDrive/HERNIEUW/Marktplaats/\n"
                "4. ~/Sync/HERNIEUW/Marktplaats/\n"
                "5. ~/OneDrive/HERNIEUW/Marktplaats/\n"
                "6. ~/Nextcloud/HERNIEUW/Marktplaats/\n"
                "7. De hieronder ingestelde basismap (fallback)</i></small>"
            )
            info_label.set_xalign(0)
            info_label.set_line_wrap(True)
            main_box.pack_start(info_label, False, False, 0)

            # Huidige gevonden map weergeven
            gevonden_map = vind_marktplaats_map(self.config)
            current_label = Gtk.Label()
            current_label.set_markup(f"<b>📍 Huidige Marktplaats map:</b> {gevonden_map}")
            current_label.set_xalign(0)
            main_box.pack_start(current_label, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Basis-map (fallback) ---
            main_box.pack_start(self._section_label("📂 Basismap (fallback)"), False, False, 0)
            base_warn = Gtk.Label()
            base_warn.set_markup("<small><i>⚠️ Deze map wordt alleen gebruikt als de automatische zoekfunctie niets vindt.</i></small>")
            base_warn.set_xalign(0)
            base_warn.set_line_wrap(True)
            main_box.pack_start(base_warn, False, False, 0)

            self.base_folder_entry = Gtk.Entry()
            self.base_folder_entry.set_text(self.config.get("base_folder", ""))
            main_box.pack_start(self.base_folder_entry, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Opslag ---
            main_box.pack_start(self._section_label("💾 Opslag (XML bestand)"), False, False, 0)

            main_box.pack_start(Gtk.Label(label="XML-bestandspad (geldt voor ALLE onderdelen: producten, scanner, automater):"), False, False, 0)
            self.xml_path_entry = Gtk.Entry()
            self.xml_path_entry.set_text(self.config.get("xml_path", ""))
            main_box.pack_start(self.xml_path_entry, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Algemene voorwaarden ---
            main_box.pack_start(self._section_label("📄 Algemene voorwaarden"), False, False, 0)
            from marktplaats_suite.voorwaarden import VoorwaardenEditor
            self.av_editor = VoorwaardenEditor()
            main_box.pack_start(self.av_editor, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Categorieën ---
            main_box.pack_start(self._section_label("📂 Categorieën (één per regel)"), False, False, 0)
            self.categorieen_view = Gtk.TextView()
            self.categorieen_view.set_wrap_mode(Gtk.WrapMode.WORD)
            self.categorieen_view.get_buffer().set_text("\n".join(self.config.get("categorieen", DEFAULT_CATEGORIEEN)))
            cat_scroll = Gtk.ScrolledWindow()
            cat_scroll.set_size_request(-1, 80)
            cat_scroll.add(self.categorieen_view)
            main_box.pack_start(cat_scroll, False, False, 0)

            # --- Tijdsperiodes ---
            main_box.pack_start(self._section_label("⏰ Tijdsperiodes (één per regel)"), False, False, 0)
            self.tijdsperiodes_view = Gtk.TextView()
            self.tijdsperiodes_view.set_wrap_mode(Gtk.WrapMode.WORD)
            self.tijdsperiodes_view.get_buffer().set_text("\n".join(self.config.get("tijdsperiodes", DEFAULT_TIJDSPERIODES)))
            tp_scroll = Gtk.ScrolledWindow()
            tp_scroll.set_size_request(-1, 80)
            tp_scroll.add(self.tijdsperiodes_view)
            main_box.pack_start(tp_scroll, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Opslaglocatie-codes ---
            main_box.pack_start(self._section_label("🏷️ Locatie codes (naam=code)"), False, False, 0)

            main_box.pack_start(Gtk.Label(label="Opslaglocatie-codes:"), False, False, 0)
            self.opslaglocatie_view = Gtk.TextView()
            self.opslaglocatie_view.get_buffer().set_text(
                "\n".join(f"{k}={v}" for k, v in self.config.get("opslaglocatie_codes", {}).items())
            )
            loc_scroll = Gtk.ScrolledWindow()
            loc_scroll.set_size_request(-1, 60)
            loc_scroll.add(self.opslaglocatie_view)
            main_box.pack_start(loc_scroll, False, False, 0)

            main_box.pack_start(Gtk.Label(label="Sublocatie-codes:"), False, False, 0)
            self.sublocatie_view = Gtk.TextView()
            self.sublocatie_view.get_buffer().set_text(
                "\n".join(f"{k}={v}" for k, v in self.config.get("sublocatie_codes", {}).items())
            )
            sub_scroll = Gtk.ScrolledWindow()
            sub_scroll.set_size_request(-1, 60)
            sub_scroll.add(self.sublocatie_view)
            main_box.pack_start(sub_scroll, False, False, 0)

            main_box.pack_start(Gtk.Label(label="Rij-codes:"), False, False, 0)
            self.rij_view = Gtk.TextView()
            self.rij_view.get_buffer().set_text(
                "\n".join(f"{k}={v}" for k, v in self.config.get("rij_codes", {}).items())
            )
            rij_scroll = Gtk.ScrolledWindow()
            rij_scroll.set_size_request(-1, 60)
            rij_scroll.add(self.rij_view)
            main_box.pack_start(rij_scroll, False, False, 0)

            main_box.pack_start(Gtk.Separator(), False, False, 5)

            # --- Labelprinter ---
            main_box.pack_start(self._section_label("🖨️ Labelprinter (barcode)"), False, False, 0)
            printer_hint = Gtk.Label()
            printer_hint.set_markup("<small><i>Indien uitgeschakeld wordt alleen een barcode-afbeelding opgeslagen.</i></small>")
            printer_hint.set_xalign(0)
            printer_hint.set_line_wrap(True)
            main_box.pack_start(printer_hint, False, False, 0)

            self.printer_enabled_check = Gtk.CheckButton(label="Direct printen inschakelen")
            self.printer_enabled_check.set_active(self.config.get("printer", {}).get("enabled", False))
            main_box.pack_start(self.printer_enabled_check, False, False, 0)

            self.auto_cut_check = Gtk.CheckButton(label="Auto-cut inschakelen (snijden na printen)")
            self.auto_cut_check.set_active(self.config.get("printer", {}).get("auto_cut", True))
            main_box.pack_start(self.auto_cut_check, False, False, 0)

            printer_cfg = self.config.get("printer", {})

            method_row = Gtk.Box(spacing=5)
            method_row.pack_start(Gtk.Label(label="Methode:"), False, False, 0)
            self.print_method_combo = Gtk.ComboBoxText()
            self.print_method_combo.append("cups", "CUPS (lp)")
            self.print_method_combo.append("brother_ql", "Brother QL")
            self.print_method_combo.set_active_id(printer_cfg.get("print_method", "cups"))
            self.print_method_combo.connect("changed", self._on_print_method_changed)
            method_row.pack_start(self.print_method_combo, False, False, 0)
            main_box.pack_start(method_row, False, False, 0)

            self.cups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            main_box.pack_start(self.cups_box, False, False, 0)

            printer_row = Gtk.Box(spacing=5)
            printer_row.pack_start(Gtk.Label(label="Printer:"), False, False, 0)
            self.printer_combo = Gtk.ComboBoxText()
            for p in get_cups_printers():
                self.printer_combo.append_text(p)
            huidige_printer = printer_cfg.get("printer_name", "")
            if huidige_printer:
                self.printer_combo.prepend_text(huidige_printer)
            self.printer_combo.set_active(0)
            printer_row.pack_start(self.printer_combo, True, True, 0)

            refresh_btn = Gtk.Button(label="🔄")
            refresh_btn.connect("clicked", self._refresh_printers)
            printer_row.pack_start(refresh_btn, False, False, 0)

            self.cups_box.pack_start(printer_row, False, False, 0)

            self.brother_ql_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            main_box.pack_start(self.brother_ql_box, False, False, 0)

            bq_grid = Gtk.Grid()
            bq_grid.set_column_spacing(10)
            bq_grid.set_row_spacing(5)
            self.brother_ql_box.pack_start(bq_grid, False, False, 0)

            bq_grid.attach(Gtk.Label(label="Model:", xalign=0), 0, 0, 1, 1)
            self.bq_model_entry = Gtk.Entry()
            self.bq_model_entry.set_text(printer_cfg.get("brother_ql_model", "QL-560"))
            bq_grid.attach(self.bq_model_entry, 1, 0, 1, 1)

            bq_grid.attach(Gtk.Label(label="Labelformaat:", xalign=0), 0, 1, 1, 1)
            self.bq_label_entry = Gtk.Entry()
            self.bq_label_entry.set_text(printer_cfg.get("brother_ql_label", "62"))
            bq_grid.attach(self.bq_label_entry, 1, 1, 1, 1)

            bq_grid.attach(Gtk.Label(label="USB-identifier:", xalign=0), 0, 2, 1, 1)
            self.bq_identifier_entry = Gtk.Entry()
            self.bq_identifier_entry.set_text(printer_cfg.get("brother_ql_identifier", ""))
            self.bq_identifier_entry.set_placeholder_text("bijv. usb://0x04f9:0x2015")
            bq_grid.attach(self.bq_identifier_entry, 1, 2, 1, 1)

            self._on_print_method_changed(self.print_method_combo)

            # --- Barcode-afmetingen ---
            size_hint = Gtk.Label()
            size_hint.set_markup("<small><i>Afmetingen van de gegenereerde barcode-afbeelding</i></small>")
            size_hint.set_xalign(0)
            size_hint.set_line_wrap(True)
            size_hint.set_margin_top(8)
            main_box.pack_start(size_hint, False, False, 0)

            barcode_cfg = self.config.get("barcode", {})

            size_grid = Gtk.Grid()
            size_grid.set_column_spacing(10)
            size_grid.set_row_spacing(5)
            main_box.pack_start(size_grid, False, False, 0)

            size_grid.attach(Gtk.Label(label="Streepdikte (mm):", xalign=0), 0, 0, 1, 1)
            self.module_width_entry = Gtk.Entry()
            self.module_width_entry.set_text(str(barcode_cfg.get("module_width_mm", 0.4)))
            size_grid.attach(self.module_width_entry, 1, 0, 1, 1)

            size_grid.attach(Gtk.Label(label="Streephoogte (mm):", xalign=0), 0, 1, 1, 1)
            self.module_height_entry = Gtk.Entry()
            self.module_height_entry.set_text(str(barcode_cfg.get("module_height_mm", 7.0)))
            size_grid.attach(self.module_height_entry, 1, 1, 1, 1)

            size_grid.attach(Gtk.Label(label="Marge (mm):", xalign=0), 0, 2, 1, 1)
            self.quiet_zone_entry = Gtk.Entry()
            self.quiet_zone_entry.set_text(str(barcode_cfg.get("quiet_zone_mm", 2.0)))
            size_grid.attach(self.quiet_zone_entry, 1, 2, 1, 1)

            self.show_all()

        except Exception as e:
            import traceback
            print(f"❌ Fout in SettingsDialog.__init__: {traceback.format_exc()}")
            dialog = Gtk.MessageDialog(
                transient_for=parent, flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"❌ Fout bij het laden van instellingen:\n\n{str(e)}"
            )
            dialog.format_secondary_text(
                f"Details:\n{traceback.format_exc()[:1000]}"
            )
            dialog.run()
            dialog.destroy()
            raise


    def _on_print_method_changed(self, widget):
        is_brother_ql = self.print_method_combo.get_active_id() == "brother_ql"
        self.cups_box.set_visible(not is_brother_ql)
        self.brother_ql_box.set_visible(is_brother_ql)

    def _refresh_printers(self, widget):
        self.printer_combo.remove_all()
        for p in get_cups_printers():
            self.printer_combo.append_text(p)
        self.printer_combo.set_active(0)

    def _section_label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label

    def _parse_key_value_lines(self, textview):
        buf = textview.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def _parse_lines(self, textview):
        buf = textview.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        return [l.strip() for l in text.splitlines() if l.strip()]

    def _toon_info_dialoog(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=msg
        )
        dialog.run()
        dialog.destroy()

    def apply_to_config(self):
        self.config.set("xml_path", self.xml_path_entry.get_text().strip())
        self.config.set("base_folder", self.base_folder_entry.get_text().strip())
        self.config.set("categorieen", self._parse_lines(self.categorieen_view))
        self.config.set("tijdsperiodes", self._parse_lines(self.tijdsperiodes_view))
        self.config.set("opslaglocatie_codes", self._parse_key_value_lines(self.opslaglocatie_view))
        self.config.set("sublocatie_codes", self._parse_key_value_lines(self.sublocatie_view))
        self.config.set("rij_codes", self._parse_key_value_lines(self.rij_view))
        self.av_editor.opslaan()

        printer_name = self.printer_combo.get_active_text() or ""
        self.config.set("printer", {
            "enabled": self.printer_enabled_check.get_active(),
            "print_method": self.print_method_combo.get_active_id() or "cups",
            "printer_name": printer_name,
            "brother_ql_model": self.bq_model_entry.get_text().strip(),
            "brother_ql_label": self.bq_label_entry.get_text().strip(),
            "brother_ql_identifier": self.bq_identifier_entry.get_text().strip(),
            "auto_cut": self.auto_cut_check.get_active(),
        })

        def _safe_float(entry, default):
            try:
                return float(entry.get_text().strip().replace(",", "."))
            except ValueError:
                return default

        self.config.set("barcode", {
            "module_width_mm": _safe_float(self.module_width_entry, 0.4),
            "module_height_mm": _safe_float(self.module_height_entry, 7.0),
            "quiet_zone_mm": _safe_float(self.quiet_zone_entry, 2.0),
        })


# ============================================
# TAB 1: REGISTREREN
# ============================================
_TUTORIAL_CSS_GELADEN = False

# Transparantie van de ballon-achtergrond: 0.0 = volledig doorzichtig, 1.0 = volledig dekkend.
# 0.75 = 25% transparant. Pas dit getal aan (bijv. 0.50 voor 50% transparant) om de mate van
# doorzichtigheid te wijzigen.
TUTORIAL_BALLON_DEKKING = 0.75


def _laad_tutorial_css():
    """Laadt de CSS voor de tutorial-overlay (ballon + knop). Wordt maar 1x echt toegepast."""
    global _TUTORIAL_CSS_GELADEN
    if _TUTORIAL_CSS_GELADEN:
        return
    css = f"""
    .tutorial-bubble {{
        background-color: rgba(245, 224, 80, {TUTORIAL_BALLON_DEKKING});
        color: #2b2200;
        border: 2px solid rgba(201, 162, 39, {TUTORIAL_BALLON_DEKKING});
        border-radius: 10px;
    }}
    .tutorial-stap-label {{
        color: #6b5400;
    }}
    .tutorial-tekst-label {{
        color: #2b2200;
        font-weight: bold;
    }}
    .tutorial-toggle-btn {{
        font-weight: bold;
    }}
    .tutorial-toggle-aan {{
        background-color: #f5e050;
        color: #2b2200;
        border-color: #c9a227;
    }}
    """.encode("utf-8")
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        _TUTORIAL_CSS_GELADEN = True
    except Exception as e:
        print(f"⚠️ Kon tutorial-CSS niet laden: {e}")


class RegistreerTab(Gtk.Box):
    # Volgorde en inhoud van de overlay-tutorial. Elke stap wijst naar een
    # widget die al bestaat in het (ongewijzigde) formulier hieronder.
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.set_border_width(15)

        self.condition_checks = {}
        self.condition_box = None

        # --- Tutorial-status ---
        self.tutorial_actief = False
        self.tutorial_stap_index = 0
        self.tutorial_stappen = []  # gevuld onderaan __init__, na het bouwen van het formulier
        self.tutorial_popover = None
        _laad_tutorial_css()

        # --- Bovenste rij: alleen de Tutorial-knop, rechts uitgelijnd. Dit is een gewone,
        # eigen rij (GEEN overlay) die zijn eigen ruimte claimt — daardoor kan de knop nooit
        # meer over het Titel-veld heen vallen, en is er geen fragiele positioneringscode
        # meer nodig voor de knop zelf. ---
        basis_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.pack_start(basis_box, True, True, 0)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        basis_box.pack_start(top_row, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        basis_box.pack_start(scrolled, True, True, 0)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        form.set_border_width(5)
        scrolled.add(form)
        self._tutorial_form = form
        self._tutorial_scrolled = scrolled

        # Titel
        form.pack_start(self._label("Titel (max 60 tekens)"), False, False, 0)
        title_row = Gtk.Box(spacing=5)
        self.titel_entry = Gtk.Entry()
        self.titel_entry.set_max_length(MAX_TITEL_LENGTE)
        self.titel_entry.connect("changed", self._on_titel_changed)
        title_row.pack_start(self.titel_entry, True, True, 0)
        self.titel_counter = Gtk.Label(label=f"0/{MAX_TITEL_LENGTE}")
        title_row.pack_start(self.titel_counter, False, False, 0)
        form.pack_start(title_row, False, False, 0)

        # Omschrijving
        form.pack_start(self._label("Omschrijving"), False, False, 0)
        self.omschrijving_view = Gtk.TextView()
        self.omschrijving_view.set_wrap_mode(Gtk.WrapMode.WORD)
        omschrijving_scroll = Gtk.ScrolledWindow()
        omschrijving_scroll.set_size_request(-1, 100)
        omschrijving_scroll.add(self.omschrijving_view)
        form.pack_start(omschrijving_scroll, False, False, 0)

        # Categorie & Tijdsperiode
        cat_row = Gtk.Box(spacing=10)
        cat_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        cat_col.pack_start(self._label("Categorie"), False, False, 0)
        self.categorie_combo = Gtk.ComboBoxText.new_with_entry()
        for c in self.config.get("categorieen", DEFAULT_CATEGORIEEN):
            self.categorie_combo.append_text(c)
        cat_col.pack_start(self.categorie_combo, False, False, 0)
        cat_row.pack_start(cat_col, True, True, 0)

        tp_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        tp_col.pack_start(self._label("Tijdsperiode"), False, False, 0)
        self.tijdsperiode_combo = Gtk.ComboBoxText.new_with_entry()
        for t in self.config.get("tijdsperiodes", DEFAULT_TIJDSPERIODES):
            self.tijdsperiode_combo.append_text(t)
        tp_col.pack_start(self.tijdsperiode_combo, False, False, 0)
        cat_row.pack_start(tp_col, True, True, 0)
        form.pack_start(cat_row, False, False, 0)

        # Conditie
        form.pack_start(self._label("Staat van het artikel"), False, False, 0)
        self.conditie_combo = Gtk.ComboBoxText()
        for c in CONDITIES:
            self.conditie_combo.append_text(c)
        self.conditie_combo.connect("changed", self._on_conditie_changed)
        form.pack_start(self.conditie_combo, False, False, 0)

        self.condition_details_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        form.pack_start(self.condition_details_container, False, False, 0)

        self.staat_details_extra_entry = Gtk.Entry()
        self.staat_details_extra_entry.set_placeholder_text("Overige staat-details (optioneel, vrije tekst)")
        form.pack_start(self.staat_details_extra_entry, False, False, 0)

        # Afmetingen & gewicht
        form.pack_start(self._label("Afmetingen (cm) en gewicht (kg)"), False, False, 0)
        dim_row = Gtk.Box(spacing=5)
        self.lengte_entry = self._number_entry("Lengte")
        self.breedte_entry = self._number_entry("Breedte")
        self.hoogte_entry = self._number_entry("Hoogte")
        self.gewicht_entry = self._number_entry("Gewicht")
        for e in (self.lengte_entry, self.breedte_entry, self.hoogte_entry, self.gewicht_entry):
            dim_row.pack_start(e, True, True, 0)
        form.pack_start(dim_row, False, False, 0)

        # Waarde & vraagprijs
        form.pack_start(self._label("Geschatte waarde en vraagprijs (€)"), False, False, 0)
        waarde_row = Gtk.Box(spacing=5)
        self.waarde_min_entry = self._number_entry("Min. waarde")
        self.waarde_max_entry = self._number_entry("Max. waarde")
        self.vraagprijs_entry = self._number_entry("Vraagprijs")
        for e in (self.waarde_min_entry, self.waarde_max_entry, self.vraagprijs_entry):
            waarde_row.pack_start(e, True, True, 0)
        form.pack_start(waarde_row, False, False, 0)

        # Opslaglocatie / Sublocatie / Rij
        form.pack_start(self._label("Opslaglocatie (bepaalt de eerste 3 tekens van het artikelnummer)"), False, False, 0)
        loc_row = Gtk.Box(spacing=5)
        self.opslaglocatie_combo = Gtk.ComboBoxText()
        for naam in self.config.get("opslaglocatie_codes", {}).keys():
            self.opslaglocatie_combo.append_text(naam)
        loc_row.pack_start(self.opslaglocatie_combo, True, True, 0)

        self.sublocatie_combo = Gtk.ComboBoxText()
        for naam in self.config.get("sublocatie_codes", {}).keys():
            self.sublocatie_combo.append_text(naam)
        loc_row.pack_start(self.sublocatie_combo, True, True, 0)

        self.rij_combo = Gtk.ComboBoxText()
        for naam in self.config.get("rij_codes", {}).keys():
            self.rij_combo.append_text(naam)
        loc_row.pack_start(self.rij_combo, True, True, 0)
        form.pack_start(loc_row, False, False, 0)

        # Info over dynamische map
        info_label = Gtk.Label()
        info_label.set_markup(
            f"<small><i>📁 Productmap wordt aangemaakt in: {vind_marktplaats_map(self.config)}</i></small>"
        )
        info_label.set_xalign(0)
        info_label.set_line_wrap(True)
        form.pack_start(info_label, False, False, 5)

        # Barcode opties
        barcode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        barcode_box.set_border_width(5)
        barcode_box.set_margin_top(5)

        self.barcode_check = Gtk.CheckButton(label="Barcode genereren bij opslaan")
        self.barcode_check.set_active(True)
        barcode_box.pack_start(self.barcode_check, False, False, 0)

        self.meerdere_barcodes_check = Gtk.CheckButton(label="Meerdere barcodes printen (bijv. voor sets)")
        self.meerdere_barcodes_check.connect("toggled", self._on_meerdere_barcodes_toggled)
        barcode_box.pack_start(self.meerdere_barcodes_check, False, False, 0)

        self.aantal_barcodes_row = Gtk.Box(spacing=5)
        self.aantal_barcodes_row.set_visible(False)
        self.aantal_barcodes_row.pack_start(Gtk.Label(label="Aantal barcodes:"), False, False, 0)
        self.aantal_barcodes_entry = Gtk.Entry()
        self.aantal_barcodes_entry.set_text("3")
        self.aantal_barcodes_entry.set_width_chars(5)
        self.aantal_barcodes_row.pack_start(self.aantal_barcodes_entry, False, False, 0)
        barcode_box.pack_start(self.aantal_barcodes_row, False, False, 0)

        form.pack_start(barcode_box, False, False, 0)

        # Opslaan-knop
        self.opslaan_btn = Gtk.Button(label="💾 Product registreren")
        self.opslaan_btn.connect("clicked", self._on_opslaan)
        form.pack_start(self.opslaan_btn, False, False, 10)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        self.status_label.set_line_wrap(True)
        form.pack_start(self.status_label, False, False, 0)

        self._on_conditie_changed(self.conditie_combo)

        # --- Tutorial: aan/uit-knop, eigen rij rechtsboven ---
        self.tutorial_toggle_btn = Gtk.Button(label="🎓 Tutorial")
        self.tutorial_toggle_btn.get_style_context().add_class("tutorial-toggle-btn")
        self.tutorial_toggle_btn.connect("clicked", self._on_tutorial_toggle)
        top_row.pack_end(self.tutorial_toggle_btn, False, False, 8)

        # --- Tutorial: stappen (wijzen naar de widgets hierboven, ongewijzigd formulier) ---
        self.tutorial_stappen = [
            {"target": self.titel_entry, "tekst": "Vul hier de titel in."},
            {
                "target": omschrijving_scroll,
                "tekst": (
                    "Vul hier de omschrijving in met de volgende opmaak.\n\n"
                    "Omschrijving van het object.\n\n"
                    "Details:\n"
                    "* Detail 1\n"
                    "* Detail 2\n"
                    "* Detail 3\n\n"
                    "Gebruik voor het gemak de foto's van het object om een omschrijving in Gemini op te \n"
                    "vragen, met de prompt van de opmaakstijl; \"*\" als opsommingtekens onder \"details:\", \n"
                    "een omschrijving van het artikel zonder het woord \"omschrijving\", een titel van \n"
                    "maximaal 60 lees-tekens zonder het woord \"titel\", een geschatte minimum & maximum \n"
                    "richtprijs tweedehands."
                ),
            },
            {
                "target": cat_col,
                "tekst": "Kies de categorie die het beste past.",
            },
            {
                "target": tp_col,
                "tekst": "Vul de geschatte tijdsperiode in \n"
                "(bijv. bij antiek/vintage).",
            },
            {
                "target": self.conditie_combo,
                "tekst": "In welke staat is het object?\n"
                "Kies de bijpassende conditie en vul eventuele schades,\n"
                "bijzonderheden, of ontbrekende onderdelen in.",
            },
            {
                "target": dim_row,
                "tekst": "Meet de afmetingen op van de gehele listing (totaalpakket),\n"
                "of wanneer het om meerdere identieke objecten gaat; meet er dan 1 van op\n"
                "en zet daarbij bijvoorbeeld de afkorting ps voor per stuk of * het aantal.",
            },
            {
                "target": self.gewicht_entry,
                "tekst": "Weeg het object op de weegschaal.\n"
                "Zijn het meerdere identieke objecten?\n"
                "Weeg er dan 1 en zet er weer bij of het per\n"
                "is of totaal.",
            },
            {
                "target": waarde_row,
                "tekst": "Schat de minimale en maximale waarde\n"
                "in en bepaal de een gemidddelde vraagprijs.",
            },
            {
                "target": self.opslaglocatie_combo,
                "tekst": "Kijk naar de beschikbare stellingen en kies de letter van de stelling. (Vloer = F)",
            },
            {
                "target": self.sublocatie_combo,
                "tekst": "Kijk naar de beschikbare planken in de stelling en \n"
                "voer het nummer van de plank in. (Staat het op de grond? = 0)",
            },
            {
                "target": self.rij_combo,
                "tekst": "Is er plek aan de linkerzijde = 1 \n"
                "het midden = 2 \n"
                "of rechts van de plank = 3. \n"
                "(Staat het op de grond? = 0)",
            },
            {
                "target": barcode_box,
                "tekst": (
                    "Bestaat het object uit meerdere delen? \n"
                    "En is het nodig dat elk deel een barcode krijgt? \n"
                    "Zo ja? Vink dit vakje dan aan en vul het aantal delen in. \n"
                    "Er worden nu meerdere van dezelfde barcode geprint."
                ),
            },
        ]

        # Zorgt dat er bij opstarten geen popover actief/aanwezig is.
        self._tutorial_update()

    # ------------------------------------------------------------------
    # Tutorial: opbouw van de ballon, als Gtk.Popover — GTK berekent zelf, betrouwbaar,
    # de juiste positie/richting t.o.v. de doelwidget (ook binnen een scroll-venster).
    # Dat vervangt al het eigen handmatige reken-/positioneerwerk van hiervoor, dat
    # herhaaldelijk net verkeerd bleek uit te pakken.
    # ------------------------------------------------------------------
    def _bouw_tutorial_popover(self, target):
        popover = Gtk.Popover()
        popover.set_relative_to(target)
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.set_modal(False)  # nooit ongevraagd sluiten, alleen via onze eigen knoppen

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_border_width(12)
        inner.get_style_context().add_class("tutorial-bubble")
        inner.set_size_request(340, -1)
        popover.add(inner)

        self.tutorial_stap_label = Gtk.Label()
        self.tutorial_stap_label.set_xalign(0)
        self.tutorial_stap_label.get_style_context().add_class("tutorial-stap-label")
        inner.pack_start(self.tutorial_stap_label, False, False, 0)

        self.tutorial_tekst_label = Gtk.Label()
        self.tutorial_tekst_label.set_xalign(0)
        self.tutorial_tekst_label.set_line_wrap(True)
        self.tutorial_tekst_label.get_style_context().add_class("tutorial-tekst-label")
        inner.pack_start(self.tutorial_tekst_label, False, False, 0)

        nav_row = Gtk.Box(spacing=6)
        self.tutorial_vorige_btn = Gtk.Button(label="◀ Vorige")
        self.tutorial_vorige_btn.connect("clicked", self._tutorial_vorige)
        nav_row.pack_start(self.tutorial_vorige_btn, False, False, 0)

        self.tutorial_volgende_btn = Gtk.Button(label="Volgende ▶")
        self.tutorial_volgende_btn.connect("clicked", self._tutorial_volgende)
        nav_row.pack_start(self.tutorial_volgende_btn, False, False, 0)

        sluiten_btn = Gtk.Button(label="✕ Sluiten")
        sluiten_btn.connect("clicked", self._tutorial_sluiten)
        nav_row.pack_start(sluiten_btn, False, False, 0)

        inner.pack_start(nav_row, False, False, 0)

        popover.show_all()
        return popover

    # ------------------------------------------------------------------
    # Tutorial: gedrag
    # ------------------------------------------------------------------
    def _on_tutorial_toggle(self, widget):
        self.tutorial_actief = not self.tutorial_actief
        self.tutorial_stap_index = 0
        stijl = self.tutorial_toggle_btn.get_style_context()
        if self.tutorial_actief:
            stijl.add_class("tutorial-toggle-aan")
        else:
            stijl.remove_class("tutorial-toggle-aan")
        self._tutorial_update()

    def _tutorial_vorige(self, widget):
        if self.tutorial_stap_index > 0:
            self.tutorial_stap_index -= 1
            self._tutorial_update()

    def _tutorial_volgende(self, widget):
        if self.tutorial_stap_index < len(self.tutorial_stappen) - 1:
            self.tutorial_stap_index += 1
            self._tutorial_update()
        else:
            self._tutorial_sluiten(widget)

    def _tutorial_sluiten(self, widget=None):
        self.tutorial_actief = False
        self._tutorial_update()

    def _tutorial_sluit_popover(self):
        if self.tutorial_popover is not None:
            self.tutorial_popover.popdown()
            self.tutorial_popover.destroy()
            self.tutorial_popover = None

    def _tutorial_update(self):
        if not self.tutorial_actief or not self.tutorial_stappen:
            self._tutorial_sluit_popover()
            return

        aantal = len(self.tutorial_stappen)
        stap = self.tutorial_stappen[self.tutorial_stap_index]
        target = stap["target"]

        # Scrol het doelveld eerst in beeld (relevant als het formulier niet volledig past).
        self._tutorial_scroll_naar(target)
        while Gtk.events_pending():
            Gtk.main_iteration()

        # Vorige popover altijd volledig weggooien en een nieuwe, tegen het NIEUWE doelveld
        # aangemaakte popover tonen — betrouwbaarder dan proberen 1 popover te verplaatsen.
        self._tutorial_sluit_popover()
        self.tutorial_popover = self._bouw_tutorial_popover(target)

        self.tutorial_stap_label.set_markup(
            f"<b>Stap {self.tutorial_stap_index + 1} van {aantal}</b>"
        )
        self.tutorial_tekst_label.set_text(stap["tekst"])

        self.tutorial_vorige_btn.set_sensitive(self.tutorial_stap_index > 0)
        laatste = (self.tutorial_stap_index == aantal - 1)
        self.tutorial_volgende_btn.set_label("✅ Klaar" if laatste else "Volgende ▶")

        self.tutorial_popover.popup()

    def _tutorial_y_positie(self, target):
        """Berekent de y-positie van het doelveld binnen 'form' door zelf de hoogtes van
        alle widgets ERVOOR op te tellen — bewust GEEN translate_coordinates gebruikt,
        want die bleek op sommige systemen structureel onbetrouwbaar (velden verspringen
        dan naar de verkeerde plek). Deze methode steunt alleen op get_allocated_height()
        en get_parent(), wat wél betrouwbaar is."""
        form = self._tutorial_form
        kinderen = form.get_children()
        v_spacing = 10  # moet overeenkomen met de spacing waarmee 'form' is opgebouwd
        rand = 5        # idem met form.set_border_width(5)

        # Zoek de directe 'form'-rij die het doelveld bevat (of het doelveld IS die rij)
        doel_rij = target
        while doel_rij not in kinderen and doel_rij.get_parent() is not None:
            doel_rij = doel_rij.get_parent()

        y = rand
        for kind in kinderen:
            if kind is doel_rij:
                break
            y += kind.get_allocated_height() + v_spacing
        return y

    def _tutorial_scroll_naar(self, target):
        """Scrolt het formulier zodat de doelwidget van de huidige stap in beeld komt."""
        y = self._tutorial_y_positie(target)
        adj = self._tutorial_scrolled.get_vadjustment()
        adj.set_value(max(0, y - 60))

    def _on_meerdere_barcodes_toggled(self, widget):
        self.aantal_barcodes_row.set_visible(widget.get_active())

    def _label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label

    def _number_entry(self, placeholder):
        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        return entry

    def _on_titel_changed(self, widget):
        length = len(widget.get_text())
        self.titel_counter.set_text(f"{length}/{MAX_TITEL_LENGTE}")

    def _on_conditie_changed(self, widget):
        for child in self.condition_details_container.get_children():
            self.condition_details_container.remove(child)
        self.condition_checks = {}

        conditie = widget.get_active_text()
        opties = STAAT_DETAILS.get(conditie, [])
        for optie in opties:
            check = Gtk.CheckButton(label=optie)
            self.condition_checks[optie] = check
            self.condition_details_container.pack_start(check, False, False, 0)
        self.condition_details_container.show_all()

    def _verzamel_staat_details(self):
        geselecteerd = [naam for naam, check in self.condition_checks.items() if check.get_active()]
        extra = self.staat_details_extra_entry.get_text().strip()
        if extra:
            geselecteerd.append(extra)
        return ", ".join(geselecteerd)

    def _reset_form(self):
        self.titel_entry.set_text("")
        self.omschrijving_view.get_buffer().set_text("")
        self.categorie_combo.get_child().set_text("")
        self.tijdsperiode_combo.get_child().set_text("")
        self.conditie_combo.set_active(0)
        self.staat_details_extra_entry.set_text("")
        for e in (self.lengte_entry, self.breedte_entry, self.hoogte_entry, self.gewicht_entry,
                  self.waarde_min_entry, self.waarde_max_entry, self.vraagprijs_entry):
            e.set_text("")
        self.meerdere_barcodes_check.set_active(False)
        self.aantal_barcodes_entry.set_text("2")
        if self.tutorial_actief:
            self.tutorial_stap_index = 0
            self._tutorial_update()

    def _on_opslaan(self, widget):
        titel = self.titel_entry.get_text().strip()
        if not titel:
            self._toon_fout("Titel is verplicht.")
            return
        if len(titel) > MAX_TITEL_LENGTE:
            self._toon_fout(f"Titel mag maximaal {MAX_TITEL_LENGTE} tekens zijn.")
            return

        opslaglocatie_naam = self.opslaglocatie_combo.get_active_text()
        sublocatie_naam = self.sublocatie_combo.get_active_text()
        rij_naam = self.rij_combo.get_active_text()
        if not (opslaglocatie_naam and sublocatie_naam and rij_naam):
            self._toon_fout("Kies een opslaglocatie, sublocatie en rij.")
            return

        opslaglocatie_code = self.config.get("opslaglocatie_codes", {}).get(opslaglocatie_naam, "X")
        sublocatie_code = self.config.get("sublocatie_codes", {}).get(sublocatie_naam, "X")
        rij_code = self.config.get("rij_codes", {}).get(rij_naam, "X")

        buf = self.omschrijving_view.get_buffer()
        omschrijving = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)

        storage = get_backend(self.config)

        try:
            artikelnummer = generate_artikelnummer(
                self.config, storage, opslaglocatie_code, sublocatie_code, rij_code
            )
        except Exception as e:
            self._toon_fout(f"Kon artikelnummer niet genereren: {e}")
            return

        product = {col: "" for col in COLUMNS}
        product.update({
            "artikelnummer": artikelnummer,
            "titel": titel,
            "categorie": self.categorie_combo.get_active_text() or "",
            "omschrijving": omschrijving,
            "lengte": self.lengte_entry.get_text().strip(),
            "breedte": self.breedte_entry.get_text().strip(),
            "hoogte": self.hoogte_entry.get_text().strip(),
            "gewicht": self.gewicht_entry.get_text().strip(),
            "conditie": self.conditie_combo.get_active_text() or "",
            "staat_details": self._verzamel_staat_details(),
            "waarde_min": self.waarde_min_entry.get_text().strip(),
            "waarde_max": self.waarde_max_entry.get_text().strip(),
            "vraagprijs": self.vraagprijs_entry.get_text().strip(),
            "aanmaakdatum": datetime.date.today().isoformat(),
            "aanmaaktijd": datetime.datetime.now().strftime("%H:%M:%S"),
            "tijdsperiode": self.tijdsperiode_combo.get_active_text() or "",
            "opslaglocatie": opslaglocatie_naam,
            "sublocatie": sublocatie_naam,
            "rij": rij_naam,
            "verkocht": "nee",
            "online": "nee",
            "algemene_voorwaarden": "",
            "verwerkt_door": self.main_window.gebruikersnaam,
            "toegewezen_aan": "",
            "url_1": "",
            "url_2": "",
            "url_3": "",
            "url_4": "",
            "url_5": "",
        })

        try:
            folder, bestond_al = maak_product_map(self.config, product)
            print(f"DEBUG - Product opgeslagen met folder_locatie: '{product['folder_locatie']}'")
        except Exception as e:
            self._toon_fout(f"Kon productmap niet aanmaken: {e}")
            return

        barcode_msg = ""
        if self.barcode_check.get_active():
            try:
                meerdere = self.meerdere_barcodes_check.get_active()
                if meerdere:
                    try:
                        aantal = int(self.aantal_barcodes_entry.get_text().strip())
                    except ValueError:
                        aantal = 2
                    if aantal < 1:
                        aantal = 1
                    if aantal > 99:
                        aantal = 99
                else:
                    aantal = 1

                barcode_paths = []
                for i in range(1, aantal + 1):
                    count_label = f"{i}/{aantal}" if meerdere else None
                    path = genereer_barcode(
                        artikelnummer, folder, self.config.get("barcode", {}), count_label
                    )
                    barcode_paths.append(path)

                    printer_cfg = self.config.get("printer", {})
                    if printer_cfg.get("enabled"):
                        auto_cut = printer_cfg.get("auto_cut", True)
                        print_barcode(path, printer_cfg, auto_cut)

                if len(barcode_paths) == 1:
                    barcode_msg = f"\n📊 Barcode opgeslagen: {barcode_paths[0]}"
                else:
                    barcode_msg = f"\n📊 {len(barcode_paths)} barcodes opgeslagen in: {folder}"

                if printer_cfg.get("enabled"):
                    methode = printer_cfg.get("print_method", "cups")
                    doel = printer_cfg.get("printer_name") if methode == "cups" else "Brother QL (USB)"
                    barcode_msg += f"\n🖨️ Verstuurd naar printer '{doel}'"
                    if printer_cfg.get("auto_cut", True):
                        barcode_msg += " (met auto-cut)"

            except Exception as e:
                barcode_msg = f"\n⚠️ Barcode-fout: {e}"

        try:
            storage.add_product(product)
        except Exception as e:
            self._toon_fout(f"Kon niet opslaan naar opslag-backend: {e}")
            return
        # ============================================
        # KOPIEER HET ARTIKELNUMMER NAAR HET KLEMBORD
        # ============================================
        try:
            klembord = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            klembord.set_text(artikelnummer, -1)
            klembord.store()
            kopieer_msg = f"\n📋 Artikelnummer gekopieerd naar klembord: {artikelnummer}"
        except Exception as e:
            kopieer_msg = f"\n⚠️ Kon niet kopiëren naar klembord: {e}"

        map_msg = "Bestaande map hergebruikt" if bestond_al else "Nieuwe map aangemaakt"
        self.status_label.set_markup(
            f"<span foreground='green'>✅ Product <b>{artikelnummer}</b> geregistreerd.\n"
            f"📁 {map_msg}: {folder}{barcode_msg}{kopieer_msg}</span>"
        )
        self._reset_form()
        self.main_window.overzicht_tab.herlaad()
        self.main_window.notebook.set_current_page(1)

    def _toon_fout(self, msg):
        self.status_label.set_markup(f"<span foreground='red'>❌ {msg}</span>")


# ============================================
# TAB 2: OVERZICHT (compacte actieknoppen)
# ============================================
class OverzichtTab(Gtk.Box):
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.user_settings = main_window.user_settings
        self.set_border_width(15)

        # Undo/Redo stacks
        self.undo_stack = deque(maxlen=50)
        self.redo_stack = deque(maxlen=50)

        # Huidige filter
        self.huidige_filter = self.user_settings.get_actieve_filter()
        self.zoekterm = ""

        # --- Tutorial: aan/uit-knop, eigen rij rechtsboven (zelfde opzet als Registreren) ---
        self.tutorial_actief = False
        self.tutorial_stap_index = 0
        self.tutorial_stappen = []  # gevuld onderaan __init__
        self.tutorial_popover = None
        _laad_tutorial_css()

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.tutorial_toggle_btn = Gtk.Button(label="🎓 Tutorial")
        self.tutorial_toggle_btn.get_style_context().add_class("tutorial-toggle-btn")
        self.tutorial_toggle_btn.connect("clicked", self._on_tutorial_toggle)
        top_row.pack_end(self.tutorial_toggle_btn, False, False, 0)
        self.pack_start(top_row, False, False, 0)

        # Filter-knoppen
        filter_row = Gtk.Box(spacing=5)
        self.filter_alles_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Alles")
        self.filter_offline_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Offline")
        self.filter_online_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Online")
        self.filter_verkocht_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Verkocht")
        self.filter_gereserveerd_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Gereserveerd")

        if self.huidige_filter == FILTER_ALLES:
            self.filter_alles_btn.set_active(True)
        elif self.huidige_filter == FILTER_ONLINE:
            self.filter_online_btn.set_active(True)
        elif self.huidige_filter == FILTER_VERKOCHT:
            self.filter_verkocht_btn.set_active(True)
        elif self.huidige_filter == FILTER_GERESERVEERD:
            self.filter_gereserveerd_btn.set_active(True)
        else:
            self.filter_offline_btn.set_active(True)

        for btn, filter_type in [
            (self.filter_alles_btn, FILTER_ALLES),
            (self.filter_offline_btn, FILTER_OFFLINE),
            (self.filter_online_btn, FILTER_ONLINE),
            (self.filter_verkocht_btn, FILTER_VERKOCHT),
            (self.filter_gereserveerd_btn, FILTER_GERESERVEERD)
        ]:
            btn.connect("toggled", self._on_filter_changed, filter_type)
            filter_row.pack_start(btn, False, False, 0)

        # Zoekveld
        self.zoek_entry = Gtk.Entry()
        self.zoek_entry.set_placeholder_text("🔍 Zoek...")
        self.zoek_entry.connect("changed", self._on_zoek_changed)
        self.zoek_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        self.zoek_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "Wissen")
        self.zoek_entry.connect("icon-press", self._on_zoek_icon_press)
        self._update_zoek_clear_icon()
        filter_row.pack_start(self.zoek_entry, True, True, 5)

        refresh_btn = Gtk.Button(label="🔄")
        refresh_btn.set_tooltip_text("Vernieuwen")
        refresh_btn.connect("clicked", lambda w: self.herlaad())
        filter_row.pack_start(refresh_btn, False, False, 0)

        self.pack_start(filter_row, False, False, 0)

        # Tabel
        self.store = Gtk.ListStore(*([str] * len(COLUMNS)))
        self.tree_view = Gtk.TreeView(model=self.store)
        self.tree_view.set_search_column(0)
        self.tree_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree_view.connect("row-activated", self._on_row_dubbelklik)
        self.tree_view.connect("columns-changed", self._on_columns_changed)

        self._update_tree_columns()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.tree_view)
        self.pack_start(scrolled, True, True, 0)

        # ============================================
        # COMPACTE ACTIE-KNOPPEN RIJ met submenu's
        # ============================================
        actie_row = Gtk.Box(spacing=5)

        # Kolommen submenu
        kolom_btn = Gtk.MenuButton(label="📋 Kolommen")
        kolom_menu = Gtk.Menu()

        item_kolom_kies = Gtk.MenuItem(label="📋 Kolommen kiezen")
        item_kolom_kies.connect("activate", self._open_kolomkiezer)
        kolom_menu.append(item_kolom_kies)

        item_kolom_save = Gtk.MenuItem(label="💾 Kolominstellingen opslaan")
        item_kolom_save.connect("activate", self._save_column_settings)
        kolom_menu.append(item_kolom_save)

        kolom_menu.show_all()
        kolom_btn.set_popup(kolom_menu)
        actie_row.pack_start(kolom_btn, False, False, 0)

        # Export submenu
        export_btn = Gtk.MenuButton(label="📊 Exporteer")
        export_menu = Gtk.Menu()

        item_csv = Gtk.MenuItem(label="📄 CSV")
        item_csv.connect("activate", self._export_csv)
        export_menu.append(item_csv)

        item_excel = Gtk.MenuItem(label="📊 Excel")
        item_excel.connect("activate", self._export_excel)
        export_menu.append(item_excel)

        export_menu.show_all()
        export_btn.set_popup(export_menu)
        actie_row.pack_start(export_btn, False, False, 0)

        # Acties submenu (Bewerken, Verwijderen, Online, etc.)
        acties_btn = Gtk.MenuButton(label="⚡ Acties")
        acties_menu = Gtk.Menu()

        item_bewerk = Gtk.MenuItem(label="✏️ Bewerken")
        item_bewerk.connect("activate", self._on_bewerken)
        acties_menu.append(item_bewerk)

        item_verwijder = Gtk.MenuItem(label="🗑️ Verwijderen")
        item_verwijder.connect("activate", self._on_verwijderen)
        acties_menu.append(item_verwijder)

        acties_menu.append(Gtk.SeparatorMenuItem())

        item_online = Gtk.MenuItem(label="🌐 Markeer als online")
        item_online.connect("activate", self._on_markeer_online)
        acties_menu.append(item_online)

        item_offline = Gtk.MenuItem(label="📴 Markeer als offline")
        item_offline.connect("activate", self._on_markeer_offline)
        acties_menu.append(item_offline)

        item_verkocht = Gtk.MenuItem(label="💰 Markeer als verkocht")
        item_verkocht.connect("activate", self._on_markeer_verkocht)
        acties_menu.append(item_verkocht)

        item_retour = Gtk.MenuItem(label="↩️ Retour melden")
        item_retour.connect("activate", self._on_retour_melden)
        acties_menu.append(item_retour)

        item_gereserveerd = Gtk.MenuItem(label="📌 Markeer als gereserveerd")
        item_gereserveerd.connect("activate", self._on_markeer_gereserveerd)
        acties_menu.append(item_gereserveerd)

        item_annuleer_reservering = Gtk.MenuItem(label="🚫 Reservering annuleren")
        item_annuleer_reservering.connect("activate", self._on_reservering_annuleren)
        acties_menu.append(item_annuleer_reservering)

        acties_menu.append(Gtk.SeparatorMenuItem())

        item_toewijs = Gtk.MenuItem(label="👤 Toewijzen")
        item_toewijs.connect("activate", self._on_toewijzen)
        acties_menu.append(item_toewijs)

        item_print = Gtk.MenuItem(label="🏷️ Print barcode")
        item_print.connect("activate", self._on_print_barcodes)
        acties_menu.append(item_print)

        item_locatie = Gtk.MenuItem(label="📍 Locatie wijzigen")
        item_locatie.connect("activate", self._on_locatie_wijzigen)
        acties_menu.append(item_locatie)

        acties_menu.show_all()
        acties_btn.set_popup(acties_menu)
        actie_row.pack_start(acties_btn, False, False, 0)

        self.pack_start(actie_row, False, False, 0)

        # Status / Omzet label
        self.omzet_label = Gtk.Label()
        self.omzet_label.set_xalign(0)
        self.omzet_label.set_line_wrap(True)
        self.pack_start(self.omzet_label, False, False, 0)

        # Context menu (rechtermuisknop)
        self._setup_context_menu()

        # --- Tutorial: stappen (wijzen naar de knoppen hierboven) ---
        self.tutorial_stappen = [
            {
                "target": self.filter_alles_btn,
                "tekst": (
                    "Met deze knoppen filter je de lijst: 'Alles', 'Offline' (nog niet "
                    "online gezet), 'Online' (staat er nu op), of 'Verkocht'."
                ),
            },
            {
                "target": self.zoek_entry,
                "tekst": (
                    "Typ hier om te zoeken in de lijst (bijv. op titel of artikelnummer). "
                    "Klik op het kruisje rechts in het veld om de zoekterm in 1 klik te wissen."
                ),
            },
            {
                "target": refresh_btn,
                "tekst": "Vernieuwt de lijst — handig als er elders (bijv. via Registreren) iets is gewijzigd.",
            },
            {
                "target": scrolled,
                "tekst": (
                    "Dit is de productlijst. Klik op een kolomkop om te sorteren. Dubbelklik "
                    "op een rij om 'm te bewerken. Selecteer meerdere rijen (Ctrl- of Shift-klik) "
                    "om ze samen te bewerken via 'Acties'. Met de rechtermuisknop krijg je ook "
                    "snel toegang tot de bestandslocatie, de foto's en de Marktplaats-URL."
                ),
            },
            {
                "target": kolom_btn,
                "tekst": (
                    "Kies welke kolommen je wilt zien in de lijst, of sla je huidige "
                    "kolomindeling op als standaard voor volgende keer."
                ),
            },
            {
                "target": export_btn,
                "tekst": "Exporteert de huidige lijst (met de actieve filter/zoekopdracht) naar een CSV- of Excel-bestand.",
            },
            {
                "target": acties_btn,
                "tekst": (
                    "Voer een actie uit op de geselecteerde rij(en): bewerken, verwijderen, "
                    "markeren als online/offline/verkocht, toewijzen aan een medewerker, "
                    "barcode(s) printen, of de opslaglocatie wijzigen. Selecteer eerst 1 of "
                    "meerdere rijen in de tabel."
                ),
            },
        ]

        self.herlaad()

    # ------------------------------------------------------------------
    # Tutorial: opbouw van de ballon, als Gtk.Popover (zelfde aanpak als Registreren-tab)
    # ------------------------------------------------------------------
    def _bouw_tutorial_popover(self, target):
        popover = Gtk.Popover()
        popover.set_relative_to(target)
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.set_modal(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_border_width(12)
        inner.get_style_context().add_class("tutorial-bubble")
        inner.set_size_request(340, -1)
        popover.add(inner)

        self.tutorial_stap_label = Gtk.Label()
        self.tutorial_stap_label.set_xalign(0)
        self.tutorial_stap_label.get_style_context().add_class("tutorial-stap-label")
        inner.pack_start(self.tutorial_stap_label, False, False, 0)

        self.tutorial_tekst_label = Gtk.Label()
        self.tutorial_tekst_label.set_xalign(0)
        self.tutorial_tekst_label.set_line_wrap(True)
        self.tutorial_tekst_label.get_style_context().add_class("tutorial-tekst-label")
        inner.pack_start(self.tutorial_tekst_label, False, False, 0)

        nav_row = Gtk.Box(spacing=6)
        self.tutorial_vorige_btn = Gtk.Button(label="◀ Vorige")
        self.tutorial_vorige_btn.connect("clicked", self._tutorial_vorige)
        nav_row.pack_start(self.tutorial_vorige_btn, False, False, 0)

        self.tutorial_volgende_btn = Gtk.Button(label="Volgende ▶")
        self.tutorial_volgende_btn.connect("clicked", self._tutorial_volgende)
        nav_row.pack_start(self.tutorial_volgende_btn, False, False, 0)

        sluiten_btn = Gtk.Button(label="✕ Sluiten")
        sluiten_btn.connect("clicked", self._tutorial_sluiten)
        nav_row.pack_start(sluiten_btn, False, False, 0)

        inner.pack_start(nav_row, False, False, 0)

        popover.show_all()
        return popover

    # ------------------------------------------------------------------
    # Tutorial: gedrag
    # ------------------------------------------------------------------
    def _on_tutorial_toggle(self, widget):
        self.tutorial_actief = not self.tutorial_actief
        self.tutorial_stap_index = 0
        stijl = self.tutorial_toggle_btn.get_style_context()
        if self.tutorial_actief:
            stijl.add_class("tutorial-toggle-aan")
        else:
            stijl.remove_class("tutorial-toggle-aan")
        self._tutorial_update()

    def _tutorial_vorige(self, widget):
        if self.tutorial_stap_index > 0:
            self.tutorial_stap_index -= 1
            self._tutorial_update()

    def _tutorial_volgende(self, widget):
        if self.tutorial_stap_index < len(self.tutorial_stappen) - 1:
            self.tutorial_stap_index += 1
            self._tutorial_update()
        else:
            self._tutorial_sluiten(widget)

    def _tutorial_sluiten(self, widget=None):
        self.tutorial_actief = False
        self._tutorial_update()

    def _tutorial_sluit_popover(self):
        if self.tutorial_popover is not None:
            self.tutorial_popover.popdown()
            self.tutorial_popover.destroy()
            self.tutorial_popover = None

    def _tutorial_update(self):
        if not self.tutorial_actief or not self.tutorial_stappen:
            self._tutorial_sluit_popover()
            return

        aantal = len(self.tutorial_stappen)
        stap = self.tutorial_stappen[self.tutorial_stap_index]
        target = stap["target"]

        # Vorige popover altijd volledig weggooien en een nieuwe, tegen het NIEUWE doelveld
        # aangemaakte popover tonen — betrouwbaarder dan proberen 1 popover te verplaatsen.
        self._tutorial_sluit_popover()
        self.tutorial_popover = self._bouw_tutorial_popover(target)

        self.tutorial_stap_label.set_markup(
            f"<b>Stap {self.tutorial_stap_index + 1} van {aantal}</b>"
        )
        self.tutorial_tekst_label.set_text(stap["tekst"])

        self.tutorial_vorige_btn.set_sensitive(self.tutorial_stap_index > 0)
        laatste = (self.tutorial_stap_index == aantal - 1)
        self.tutorial_volgende_btn.set_label("✅ Klaar" if laatste else "Volgende ▶")

        self.tutorial_popover.popup()

    def _setup_context_menu(self):
        """Maak het context menu voor de rechtermuisknop."""
        self.context_menu = Gtk.Menu()

        item_map = Gtk.MenuItem(label="📂 Open bestandslocatie")
        item_map.connect("activate", self._on_open_map)
        self.context_menu.append(item_map)

        item_fotos = Gtk.MenuItem(label="🖼️ Open foto's")
        item_fotos.connect("activate", self._on_open_fotos)
        self.context_menu.append(item_fotos)

        # URL submenu
        self._add_url_submenu()

        sep = Gtk.SeparatorMenuItem()
        self.context_menu.append(sep)

        item_bewerk = Gtk.MenuItem(label="✏️ Bewerken")
        item_bewerk.connect("activate", lambda w: self._on_bewerken(None))
        self.context_menu.append(item_bewerk)

        item_verwijder = Gtk.MenuItem(label="🗑️ Verwijderen")
        item_verwijder.connect("activate", lambda w: self._on_verwijderen(None))
        self.context_menu.append(item_verwijder)

        item_online = Gtk.MenuItem(label="🌐 Markeer als online")
        item_online.connect("activate", lambda w: self._on_markeer_online(None))
        self.context_menu.append(item_online)

        item_verkocht = Gtk.MenuItem(label="💰 Markeer als verkocht")
        item_verkocht.connect("activate", lambda w: self._on_markeer_verkocht(None))
        self.context_menu.append(item_verkocht)

        item_retour = Gtk.MenuItem(label="↩️ Retour melden")
        item_retour.connect("activate", lambda w: self._on_retour_melden(None))
        self.context_menu.append(item_retour)

        item_gereserveerd = Gtk.MenuItem(label="📌 Markeer als gereserveerd")
        item_gereserveerd.connect("activate", lambda w: self._on_markeer_gereserveerd(None))
        self.context_menu.append(item_gereserveerd)

        item_annuleer_reservering = Gtk.MenuItem(label="🚫 Reservering annuleren")
        item_annuleer_reservering.connect("activate", lambda w: self._on_reservering_annuleren(None))
        self.context_menu.append(item_annuleer_reservering)

        item_toewijs = Gtk.MenuItem(label="👤 Toewijzen")
        item_toewijs.connect("activate", lambda w: self._on_toewijzen(None))
        self.context_menu.append(item_toewijs)

        item_print = Gtk.MenuItem(label="🏷️ Print barcode")
        item_print.connect("activate", lambda w: self._on_print_barcodes(None))
        self.context_menu.append(item_print)

        item_locatie = Gtk.MenuItem(label="📍 Locatie wijzigen")
        item_locatie.connect("activate", lambda w: self._on_locatie_wijzigen(None))
        self.context_menu.append(item_locatie)

        self.context_menu.show_all()
        self.tree_view.connect("button-press-event", self._on_treeview_button_press)

    def _add_url_submenu(self):
        """Voeg een submenu toe met alle gevulde URLs van het geselecteerde product."""
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            item_no_url = Gtk.MenuItem(label="🌐 Open URL (geen product geselecteerd)")
            item_no_url.set_sensitive(False)
            self.context_menu.append(item_no_url)
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummers[0]), None)
        if not product:
            item_no_url = Gtk.MenuItem(label="🌐 Open URL (product niet gevonden)")
            item_no_url.set_sensitive(False)
            self.context_menu.append(item_no_url)
            return

        urls = []
        for i in range(1, 6):
            url_key = f"url_{i}"
            url = product.get(url_key, "").strip()
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f"https://{url}"
                urls.append(url)

        if not urls:
            item_no_url = Gtk.MenuItem(label="🌐 Open URL (geen URL gevonden)")
            item_no_url.set_sensitive(False)
            self.context_menu.append(item_no_url)
            return

        if len(urls) == 1:
            item_url = Gtk.MenuItem(label=f"🌐 Open URL")
            item_url.connect("activate", lambda w, url=urls[0]: self._on_open_url(w, url))
            self.context_menu.append(item_url)
        else:
            url_submenu = Gtk.MenuItem(label="🌐 Open URL")
            submenu = Gtk.Menu()
            for i, url in enumerate(urls, 1):
                display_url = url[:47] + "..." if len(url) > 50 else url
                item = Gtk.MenuItem(label=f"URL {i}: {display_url}")
                item.connect("activate", lambda w, url=url: self._on_open_url(w, url))
                submenu.append(item)
            submenu.show_all()
            url_submenu.set_submenu(submenu)
            self.context_menu.append(url_submenu)

    def _on_treeview_button_press(self, widget, event):
        """Rechtermuisknop toont context menu."""
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            path, column, cell_x, cell_y = widget.get_path_at_pos(int(event.x), int(event.y))
            if path is not None:
                selection = widget.get_selection()
                if not selection.path_is_selected(path):
                    selection.unselect_all()
                    selection.select_path(path)
                self.context_menu.popup_at_pointer(event)
            return True
        return False

    def _on_open_url(self, widget, url=None):
        """Open een URL in de standaard webbrowser."""
        if url:
            try:
                subprocess.Popen(["xdg-open", url])
            except Exception as e:
                self._toon_foutdialoog(f"Kon URL niet openen: {e}")
        else:
            artikelnummers = self._geselecteerde_artikelnummers()
            if not artikelnummers:
                self._toon_foutdialoog("Selecteer eerst een product.")
                return
            storage = get_backend(self.config)
            producten = storage.load_products()
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummers[0]), None)
            if not product:
                self._toon_foutdialoog("Product niet gevonden.")
                return
            for i in range(1, 6):
                url_key = f"url_{i}"
                url = product.get(url_key, "").strip()
                if url:
                    try:
                        subprocess.Popen(["xdg-open", url])
                        return
                    except Exception as e:
                        self._toon_foutdialoog(f"Kon URL niet openen: {e}")
                        return
            self._toon_foutdialoog("Geen URL gevonden voor dit product.")

    def _on_open_map(self, widget):
        """Open de productmap van geselecteerde producten."""
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()

        for artikelnummer in artikelnummers:
            pad = vind_product_map(artikelnummer, self.config)
            if os.path.isdir(pad):
                try:
                    subprocess.Popen(["xdg-open", pad])
                except Exception as e:
                    self._toon_foutdialoog(f"Kon map niet openen: {e}")
            else:
                product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                if product:
                    opgeslagen = product.get("folder_locatie", "")
                    if opgeslagen and os.path.isdir(opgeslagen):
                        try:
                            subprocess.Popen(["xdg-open", opgeslagen])
                        except Exception as e:
                            self._toon_foutdialoog(f"Kon map niet openen: {e}")
                        continue
                self._toon_foutdialoog(f"Map niet gevonden voor {artikelnummer}\nGezocht op: {pad}")

    def _on_open_fotos(self, widget):
        """Open de eerste foto uit de originelen map van geselecteerde producten."""
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()

        for artikelnummer in artikelnummers:
            pad = vind_product_map(artikelnummer, self.config)
            originelen_pad = None

            if os.path.isdir(pad):
                originelen_pad = os.path.join(pad, "originelen")
                if not os.path.isdir(originelen_pad):
                    product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                    if product:
                        opgeslagen = product.get("folder_locatie", "")
                        if opgeslagen and os.path.isdir(opgeslagen):
                            originelen_pad = os.path.join(opgeslagen, "originelen")
                            if not os.path.isdir(originelen_pad):
                                originelen_pad = None

            if originelen_pad and os.path.isdir(originelen_pad):
                fotos = []
                for root, dirs, files in os.walk(originelen_pad):
                    for file in files:
                        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                            fotos.append(os.path.join(root, file))

                if fotos:
                    try:
                        subprocess.Popen(["shotwell", fotos[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except FileNotFoundError:
                        try:
                            subprocess.Popen(["eog", fotos[0]])
                        except FileNotFoundError:
                            try:
                                subprocess.Popen(["gthumb", fotos[0]])
                            except FileNotFoundError:
                                try:
                                    subprocess.Popen(["xdg-open", fotos[0]])
                                except Exception as e:
                                    self._toon_foutdialoog(f"Kon foto niet openen: {e}")
                else:
                    try:
                        subprocess.Popen(["xdg-open", originelen_pad])
                    except Exception as e:
                        self._toon_foutdialoog(f"Geen foto's gevonden en kon map niet openen: {e}")
            else:
                if os.path.isdir(pad):
                    fotos = []
                    for root, dirs, files in os.walk(pad):
                        for file in files:
                            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                                fotos.append(os.path.join(root, file))

                    if fotos:
                        try:
                            subprocess.Popen(["shotwell", fotos[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except FileNotFoundError:
                            try:
                                subprocess.Popen(["eog", fotos[0]])
                            except FileNotFoundError:
                                try:
                                    subprocess.Popen(["gthumb", fotos[0]])
                                except FileNotFoundError:
                                    try:
                                        subprocess.Popen(["xdg-open", fotos[0]])
                                    except Exception as e:
                                        self._toon_foutdialoog(f"Kon foto niet openen: {e}")
                    else:
                        try:
                            subprocess.Popen(["xdg-open", pad])
                        except Exception as e:
                            self._toon_foutdialoog(f"Geen foto's gevonden en kon map niet openen: {e}")
                else:
                    self._toon_foutdialoog(f"Map niet gevonden voor {artikelnummer}\nGezocht op: {pad}")

    def _on_locatie_wijzigen(self, widget):
        """Wijzig de locatie (eerste 3 tekens) van een product."""
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return

        if len(artikelnummers) > 1:
            self._toon_foutdialoog("Locatie wijzigen kan alleen voor één product tegelijk.")
            return

        artikelnummer = artikelnummers[0]

        if len(artikelnummer) < 8:
            self._toon_foutdialoog(f"Ongeldig artikelnummer formaat: {artikelnummer}")
            return

        dialog = LocatieWijzigDialog(self.main_window, artikelnummer, self.config)
        response = dialog.run()
        nieuwe_locatie = dialog.get_nieuwe_locatie() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if nieuwe_locatie is None:
            return

        if len(nieuwe_locatie) != 3:
            self._toon_foutdialoog("Voer precies 3 tekens in (bijv. A11)")
            return

        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=f"Weet je zeker dat je de locatie wilt wijzigen?"
        )
        confirm.format_secondary_text(
            f"Product: {artikelnummer}\n"
            f"Nieuwe locatie: {nieuwe_locatie}\n"
            f"Nieuw artikelnummer: {nieuwe_locatie}{artikelnummer[3:7]}{artikelnummer[7:9]}\n\n"
            f"⚠️ De map, barcode en omschrijving.txt worden aangepast."
        )
        bevestiging = confirm.run()
        confirm.destroy()

        if bevestiging != Gtk.ResponseType.YES:
            return

        try:
            nieuw_artikelnummer, nieuwe_map = wijzig_artikelnummer_locatie(
                self.config, artikelnummer, nieuwe_locatie
            )
            self._toon_info_dialoog(
                f"✅ Locatie succesvol gewijzigd!\n\n"
                f"Oud: {artikelnummer}\n"
                f"Nieuw: {nieuw_artikelnummer}\n"
                f"Map: {nieuwe_map}"
            )
            self.herlaad()
        except Exception as e:
            self._toon_foutdialoog(f"Fout bij wijzigen: {e}")

    def _on_filter_changed(self, button, filter_type):
        if button.get_active():
            self.huidige_filter = filter_type
            self.user_settings.set_actieve_filter(filter_type)
            self._update_tree_columns()
            self.herlaad()

    def _on_zoek_changed(self, widget):
        self.zoekterm = widget.get_text().strip().lower()
        self._update_zoek_clear_icon()
        self.herlaad()

    def _update_zoek_clear_icon(self):
        heeft_tekst = bool(self.zoek_entry.get_text())
        icon = "edit-clear-symbolic" if heeft_tekst else None
        self.zoek_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, icon)

    def _on_zoek_icon_press(self, widget, icon_pos, event):
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            widget.set_text("")
            widget.grab_focus()

    def _update_tree_columns(self):
        for col in self.tree_view.get_columns():
            self.tree_view.remove_column(col)

        volgorde = self.user_settings.get_kolom_volgorde(self.huidige_filter)
        zichtbaar = self.user_settings.get_zichtbare_kolommen(self.huidige_filter)

        if not volgorde:
            volgorde = [k for k in COLUMNS if k in zichtbaar]
        else:
            volgorde = [k for k in volgorde if k in zichtbaar]
            for k in zichtbaar:
                if k not in volgorde:
                    volgorde.append(k)

        for kolom in volgorde:
            if kolom in COLUMNS:
                col_idx = COLUMNS.index(kolom)
                label = KOLOM_LABELS.get(kolom, kolom)
                renderer = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(label, renderer, text=col_idx)
                column.set_sort_column_id(col_idx)
                column.set_resizable(True)
                column.set_reorderable(True)
                breedte = self.user_settings.get_kolom_breedte(kolom, 100)
                column.set_fixed_width(breedte)
                column.set_min_width(50)
                self.tree_view.append_column(column)

    def _on_columns_changed(self, widget):
        pass

    def _save_column_settings(self, widget):
        columns = self.tree_view.get_columns()
        volgorde = []
        breedtes = {}

        for col in columns:
            title = col.get_title()
            for kolom, label in KOLOM_LABELS.items():
                if label == title:
                    volgorde.append(kolom)
                    breedtes[kolom] = col.get_width()
                    break

        self.user_settings.set_kolom_volgorde(self.huidige_filter, volgorde)

        for kolom, breedte in breedtes.items():
            self.user_settings.set_kolom_breedte(kolom, breedte)

        self.omzet_label.set_markup(
            f"<span foreground='green'>✅ Kolominstellingen opgeslagen voor filter '{FILTER_NAMEN[self.huidige_filter]}'</span>"
        )
        GLib.timeout_add(3000, self._herstel_omzet_label)

    def _open_kolomkiezer(self, widget):
        dialog = KolomKiezerDialog(self.main_window, self.user_settings, self.huidige_filter)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            dialog.apply_to_settings()
            self._update_tree_columns()
            self.herlaad()
        dialog.destroy()

    def _huidige_producten(self):
        storage = get_backend(self.config)
        try:
            return storage.load_products()
        except Exception as e:
            self._toon_foutdialoog(f"Kon producten niet laden: {e}")
            return []

    def herlaad(self):
        self.store.clear()
        producten = self._huidige_producten()

        if self.huidige_filter == FILTER_OFFLINE:
            producten = [p for p in producten
                         if p.get("verkocht", "nee").lower() != "ja"
                         and p.get("online", "nee").lower() != "ja"
                         and p.get("gereserveerd", "nee").lower() != "ja"]
        elif self.huidige_filter == FILTER_ONLINE:
            producten = [p for p in producten
                         if p.get("verkocht", "nee").lower() != "ja"
                         and p.get("online", "nee").lower() == "ja"
                         and p.get("gereserveerd", "nee").lower() != "ja"]
        elif self.huidige_filter == FILTER_VERKOCHT:
            producten = [p for p in producten if p.get("verkocht", "nee").lower() == "ja"]
        elif self.huidige_filter == FILTER_GERESERVEERD:
            producten = [p for p in producten
                         if p.get("gereserveerd", "nee").lower() == "ja"
                         and p.get("verkocht", "nee").lower() != "ja"]

        if self.zoekterm:
            producten = [p for p in producten
                         if self.zoekterm in p.get("artikelnummer", "").lower()
                         or self.zoekterm in p.get("titel", "").lower()]

        for p in producten:
            row = [p.get(col, "") for col in COLUMNS]
            self.store.append(row)

        if self.zoekterm:
            self.omzet_label.set_markup(f"<small>🔍 {len(producten)} resultaten gevonden voor '{self.zoekterm}'</small>")
        elif self.huidige_filter == FILTER_VERKOCHT:
            totaal = 0.0
            for p in producten:
                try:
                    prijs = p.get("verkoopprijs", "").replace("€", "").replace(",", ".").strip()
                    totaal += float(prijs) if prijs else 0.0
                except ValueError:
                    pass
            self.omzet_label.set_markup(
                f"<b>Totale omzet (verkocht, {len(producten)} items): €{totaal:.2f}</b>"
            )
        elif self.huidige_filter == FILTER_GERESERVEERD:
            totaal = 0.0
            for p in producten:
                try:
                    prijs = p.get("reserveprijs", "").replace("€", "").replace(",", ".").strip()
                    totaal += float(prijs) if prijs else 0.0
                except ValueError:
                    pass
            self.omzet_label.set_markup(
                f"<b>Verwachte inkomsten (gereserveerd, {len(producten)} items): €{totaal:.2f}</b> "
                f"<small>— telt nog niet mee in de omzet</small>"
            )
        else:
            self.omzet_label.set_markup(f"<small>📊 {len(producten)} producten in deze weergave</small>")

    def _geselecteerde_artikelnummers(self):
        selection = self.tree_view.get_selection()
        model, paths = selection.get_selected_rows()
        artikelnummers = []
        for path in paths:
            treeiter = model.get_iter(path)
            if treeiter:
                artikelnummers.append(model[treeiter][0])
        return artikelnummers

    def _on_row_dubbelklik(self, tree_view, path, column):
        artikelnummer = self.store[path][0]
        klembord = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        klembord.set_text(artikelnummer, -1)
        klembord.store()
        self.omzet_label.set_markup(f"<small>📋 Artikelnummer <b>{artikelnummer}</b> gekopieerd naar klembord</small>")
        GLib.timeout_add(1500, self._herstel_omzet_label)

    def _herstel_omzet_label(self):
        self.herlaad()
        return False

    def _toon_foutdialoog(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=msg
        )
        dialog.run()
        dialog.destroy()

    def _toon_info_dialoog(self, msg, title="Informatie"):
        dialog = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=msg
        )
        dialog.set_title(title)
        dialog.run()
        dialog.destroy()

    def _get_first_selected(self):
        nummers = self._geselecteerde_artikelnummers()
        return nummers[0] if nummers else None

    def _push_undo(self, actie, data):
        self.undo_stack.append({"actie": actie, "data": data})
        self.redo_stack.clear()

    def _on_bewerken(self, widget):
        artikelnummer = self._get_first_selected()
        if not artikelnummer:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        if not product:
            self._toon_foutdialoog("Product niet gevonden.")
            return

        oude_product = dict(product)

        dialog = BewerkDialog(self.main_window, product, self.config)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            bijgewerkt = dialog.get_product()
            try:
                storage.update_product(artikelnummer, bijgewerkt)
                self._push_undo("bewerken", {"artikelnummer": artikelnummer, "oud": oude_product, "nieuw": bijgewerkt})
                self.herlaad()
            except Exception as e:
                self._toon_foutdialoog(f"Kon niet opslaan: {e}")
        dialog.destroy()

    def _on_verwijderen(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        if len(artikelnummers) == 1:
            msg = f"Product {artikelnummers[0]} verwijderen?"
        else:
            msg = f"{len(artikelnummers)} producten verwijderen?"

        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=msg
        )
        if len(artikelnummers) > 1:
            confirm.format_secondary_text(f"Weet je zeker dat je deze {len(artikelnummers)} producten wilt verwijderen?")
        response = confirm.run()
        confirm.destroy()

        if response == Gtk.ResponseType.YES:
            storage = get_backend(self.config)
            verwijderde_products = []
            for artikelnummer in artikelnummers:
                try:
                    producten = storage.load_products()
                    product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)

                    storage.delete_product(artikelnummer)
                    verwijderde_products.append({"artikelnummer": artikelnummer, "product": product})

                    pad = vind_product_map(artikelnummer, self.config)
                    if os.path.isdir(pad):
                        try:
                            from send2trash import send2trash
                            send2trash(pad)
                        except ImportError:
                            pass
                        except Exception:
                            pass
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij verwijderen {artikelnummer}: {e}")
                    return

            self._push_undo("verwijderen", verwijderde_products)
            self.herlaad()

    def _on_markeer_online(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        dialog = OnlineDialog(self.main_window, artikelnummers)
        response = dialog.run()
        urls = dialog.get_urls() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if urls is None:
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        oude_producten = {}

        for artikelnummer in artikelnummers:
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if not product:
                continue

            oude_producten[artikelnummer] = dict(product)

            product["online"] = "ja"
            for i in range(1, 6):
                if i <= len(urls):
                    product[f"url_{i}"] = urls[i-1]
                else:
                    product[f"url_{i}"] = ""

            try:
                storage.update_product(artikelnummer, product)
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij updaten {artikelnummer}: {e}")
                return

        self._push_undo("online_markeren", {"artikelnummers": artikelnummers, "oud": oude_producten})
        self.herlaad()
        self._toon_info_dialoog(f"{len(artikelnummers)} product(en) gemarkeerd als online.")

    def _on_markeer_offline(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        if len(artikelnummers) == 1:
            msg = f"Markeer {artikelnummers[0]} als offline?"
        else:
            msg = f"Markeer {len(artikelnummers)} producten als offline?"

        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=msg
        )
        if len(artikelnummers) > 1:
            confirm.format_secondary_text(f"Alle advertentie-URLs worden verwijderd.")
        response = confirm.run()
        confirm.destroy()

        if response == Gtk.ResponseType.YES:
            storage = get_backend(self.config)
            producten = storage.load_products()
            oude_producten = {}

            for artikelnummer in artikelnummers:
                product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                if not product:
                    continue

                oude_producten[artikelnummer] = dict(product)

                product["online"] = "nee"
                for i in range(1, 6):
                    product[f"url_{i}"] = ""

                try:
                    storage.update_product(artikelnummer, product)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij updaten {artikelnummer}: {e}")
                    return

            self._push_undo("offline_markeren", {"artikelnummers": artikelnummers, "oud": oude_producten})
            self.herlaad()
            self._toon_info_dialoog(f"{len(artikelnummers)} product(en) gemarkeerd als offline.")

    def _on_markeer_verkocht(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        if len(artikelnummers) > 1:
            self._toon_foutdialoog("Markeer als verkocht kan alleen voor één product tegelijk.")
            return

        artikelnummer = artikelnummers[0]

        dialog = VerkochtDialog(self.main_window, artikelnummer)
        response = dialog.run()
        gegevens = dialog.get_gegevens() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if gegevens is None:
            return

        if not gegevens["verkoopprijs"]:
            self._toon_foutdialoog("Vul een verkoopprijs in.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        if not product:
            self._toon_foutdialoog("Product niet gevonden.")
            return

        oud_product = dict(product)
        product["verkocht"] = "ja"
        product.update(gegevens)
        # Een verkoop rondt een eventuele reservering af: reserveringsgegevens wissen
        # zodat het product niet dubbel meetelt (als 'gereserveerd' én 'verkocht').
        product["gereserveerd"] = "nee"
        product["reserveprijs"] = ""
        product["reserveerdatum"] = ""
        product["reservering_klant_naam"] = ""
        try:
            storage.update_product(artikelnummer, product)
            self._push_undo("verkocht_markeren", {"artikelnummer": artikelnummer, "oud": oud_product, "nieuw": dict(product)})
            self.herlaad()
            self._toon_info_dialoog(f"Product {artikelnummer} gemarkeerd als verkocht.")
        except Exception as e:
            self._toon_foutdialoog(f"Kon niet opslaan: {e}")

    def _on_retour_melden(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()

        # Alleen producten die daadwerkelijk als 'verkocht' staan kunnen een retour krijgen.
        verkochte_artikelen = []
        niet_verkocht_aantal = 0
        for artikelnummer in artikelnummers:
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if product and product.get("verkocht", "nee").lower() == "ja":
                verkochte_artikelen.append(artikelnummer)
            else:
                niet_verkocht_aantal += 1

        if not verkochte_artikelen:
            self._toon_foutdialoog("Geen van de geselecteerde producten staat op 'verkocht' — retour melden is hier niet nodig.")
            return

        if len(verkochte_artikelen) == 1:
            msg = f"Retour melden voor {verkochte_artikelen[0]}?"
        else:
            msg = f"Retour melden voor {len(verkochte_artikelen)} producten?"

        toelichting = (
            "Het product gaat terug naar 'online' en de status 'verkocht' plus alle "
            "verkoopgegevens (prijs, datum, koper, leverwijze) worden gewist. De omzet "
            "wordt hierdoor automatisch bijgewerkt: dit product telt niet langer mee."
        )
        if niet_verkocht_aantal:
            toelichting += (
                f"\n\nLet op: {niet_verkocht_aantal} geselecteerd(e) product(en) sto(nd/en) "
                "niet op 'verkocht' en wordt/worden overgeslagen."
            )

        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=msg
        )
        confirm.format_secondary_text(toelichting)
        response = confirm.run()
        confirm.destroy()

        if response != Gtk.ResponseType.YES:
            return

        oude_producten = {}
        nieuwe_producten = {}
        retour_velden = [
            "verkoopprijs", "verkoopdatum", "leverwijze", "klant_naam",
            "klant_telefoon", "klant_email", "ophaal_afspraak", "track_trace",
        ]

        for artikelnummer in verkochte_artikelen:
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if not product:
                continue

            oude_producten[artikelnummer] = dict(product)

            product["verkocht"] = "nee"
            product["online"] = "ja"
            for veld in retour_velden:
                product[veld] = ""

            try:
                storage.update_product(artikelnummer, product)
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij updaten {artikelnummer}: {e}")
                return

            nieuwe_producten[artikelnummer] = dict(product)

        self._push_undo("retour_melden", {
            "artikelnummers": verkochte_artikelen,
            "oud": oude_producten,
            "nieuw": nieuwe_producten,
        })
        self.herlaad()
        self._toon_info_dialoog(
            f"{len(verkochte_artikelen)} product(en) gemarkeerd als retour: terug naar online, uit de omzet gehaald."
        )

    def _on_markeer_gereserveerd(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        if len(artikelnummers) > 1:
            self._toon_foutdialoog("Markeer als gereserveerd kan alleen voor één product tegelijk.")
            return

        artikelnummer = artikelnummers[0]

        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        if not product:
            self._toon_foutdialoog("Product niet gevonden.")
            return

        if product.get("verkocht", "nee").lower() == "ja":
            self._toon_foutdialoog("Dit product staat al op 'verkocht' — reserveren is hier niet van toepassing.")
            return

        dialog = ReserveerDialog(self.main_window, artikelnummer)
        response = dialog.run()
        gegevens = dialog.get_gegevens() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if gegevens is None:
            return

        if not gegevens["reserveprijs"]:
            self._toon_foutdialoog("Vul een (verwachte) reserveprijs in.")
            return

        oud_product = dict(product)
        product["gereserveerd"] = "ja"
        product.update(gegevens)
        try:
            storage.update_product(artikelnummer, product)
            self._push_undo("gereserveerd_markeren", {"artikelnummer": artikelnummer, "oud": oud_product, "nieuw": dict(product)})
            self.herlaad()
            self._toon_info_dialoog(f"Product {artikelnummer} gemarkeerd als gereserveerd.")
        except Exception as e:
            self._toon_foutdialoog(f"Kon niet opslaan: {e}")

    def _on_reservering_annuleren(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()

        # Alleen producten die daadwerkelijk als 'gereserveerd' staan kunnen geannuleerd worden.
        gereserveerde_artikelen = []
        niet_gereserveerd_aantal = 0
        for artikelnummer in artikelnummers:
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if product and product.get("gereserveerd", "nee").lower() == "ja":
                gereserveerde_artikelen.append(artikelnummer)
            else:
                niet_gereserveerd_aantal += 1

        if not gereserveerde_artikelen:
            self._toon_foutdialoog("Geen van de geselecteerde producten staat op 'gereserveerd'.")
            return

        if len(gereserveerde_artikelen) == 1:
            msg = f"Reservering annuleren voor {gereserveerde_artikelen[0]}?"
        else:
            msg = f"Reservering annuleren voor {len(gereserveerde_artikelen)} producten?"

        toelichting = (
            "De reservering wordt opgeheven en de reserveringsgegevens (prijs, datum, "
            "klant) worden gewist. Het product blijft verder ongewijzigd (online/offline-"
            "status verandert niet) en telt niet langer mee bij de verwachte inkomsten."
        )
        if niet_gereserveerd_aantal:
            toelichting += (
                f"\n\nLet op: {niet_gereserveerd_aantal} geselecteerd(e) product(en) sto(nd/en) "
                "niet op 'gereserveerd' en wordt/worden overgeslagen."
            )

        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=msg
        )
        confirm.format_secondary_text(toelichting)
        response = confirm.run()
        confirm.destroy()

        if response != Gtk.ResponseType.YES:
            return

        oude_producten = {}
        nieuwe_producten = {}
        reservering_velden = ["gereserveerd", "reserveprijs", "reserveerdatum", "reservering_klant_naam"]

        for artikelnummer in gereserveerde_artikelen:
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if not product:
                continue

            oude_producten[artikelnummer] = dict(product)

            product["gereserveerd"] = "nee"
            for veld in ("reserveprijs", "reserveerdatum", "reservering_klant_naam"):
                product[veld] = ""

            try:
                storage.update_product(artikelnummer, product)
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij updaten {artikelnummer}: {e}")
                return

            nieuwe_producten[artikelnummer] = dict(product)

        self._push_undo("reservering_annuleren", {
            "artikelnummers": gereserveerde_artikelen,
            "oud": oude_producten,
            "nieuw": nieuwe_producten,
        })
        self.herlaad()
        self._toon_info_dialoog(
            f"Reservering van {len(gereserveerde_artikelen)} product(en) geannuleerd."
        )


    def _on_toewijzen(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        eerste_product = next((p for p in producten if p.get("artikelnummer") == artikelnummers[0]), None)
        if not eerste_product:
            self._toon_foutdialoog("Product niet gevonden.")
            return

        dialog = ToewijzenDialog(self.main_window, eerste_product, self.main_window.user_manager, self.main_window.gebruikersnaam)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            toegewezen_aan = dialog.get_toegewezen_aan()
            oude_producten = {}
            for artikelnummer in artikelnummers:
                product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                if product:
                    oude_producten[artikelnummer] = dict(product)
                    product["toegewezen_aan"] = toegewezen_aan
                    try:
                        storage.update_product(artikelnummer, product)
                    except Exception as e:
                        self._toon_foutdialoog(f"Fout bij updaten {artikelnummer}: {e}")
                        return
            self._push_undo("toewijzen", {"artikelnummers": artikelnummers, "oud": oude_producten, "nieuw_toegewezen": toegewezen_aan})
            self.herlaad()
            self._toon_info_dialoog(f"{len(artikelnummers)} product(en) toegewezen aan {toegewezen_aan or 'niemand'}.")
        dialog.destroy()

    def _on_print_barcodes(self, widget):
        artikelnummers = self._geselecteerde_artikelnummers()
        if not artikelnummers:
            self._toon_foutdialoog("Selecteer eerst een of meerdere producten.")
            return

        dialog = Gtk.Dialog(
            title="Barcodes printen",
            transient_for=self.main_window,
            flags=0
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Printen", Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)

        box.pack_start(Gtk.Label(label=f"Print barcodes voor {len(artikelnummers)} product(en):", xalign=0), False, False, 0)

        multi_check = Gtk.CheckButton(label="Meerdere barcodes per product (voor sets)")
        multi_check.set_active(False)
        box.pack_start(multi_check, False, False, 0)

        count_row = Gtk.Box(spacing=5)
        count_row.set_visible(False)
        count_row.pack_start(Gtk.Label(label="Aantal per product:"), False, False, 0)
        count_entry = Gtk.Entry()
        count_entry.set_text("3")
        count_entry.set_width_chars(5)
        count_row.pack_start(count_entry, False, False, 0)
        box.pack_start(count_row, False, False, 0)

        multi_check.connect("toggled", lambda w: count_row.set_visible(w.get_active()))

        dialog.show_all()
        response = dialog.run()

        meerdere = multi_check.get_active()
        if meerdere:
            try:
                aantal = int(count_entry.get_text().strip())
            except ValueError:
                aantal = 3
            if aantal < 1:
                aantal = 1
            if aantal > 99:
                aantal = 99
        else:
            aantal = 1

        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            return

        storage = get_backend(self.config)
        producten = storage.load_products()
        printer_cfg = self.config.get("printer", {})

        if not printer_cfg.get("enabled"):
            self._toon_foutdialoog("Printen is niet ingeschakeld in de instellingen.")
            return

        success_count = 0
        error_count = 0

        for artikelnummer in artikelnummers:
            pad = vind_product_map(artikelnummer, self.config)
            if not os.path.isdir(pad):
                pad = os.path.join(self.config.get("base_folder", ""), artikelnummer)
                os.makedirs(pad, exist_ok=True)

            try:
                auto_cut = printer_cfg.get("auto_cut", True)
                for i in range(1, aantal + 1):
                    count_label = f"{i}/{aantal}" if meerdere else None
                    barcode_path = genereer_barcode(
                        artikelnummer, pad, self.config.get("barcode", {}), count_label
                    )

                    print_barcode(barcode_path, printer_cfg, auto_cut)
                success_count += 1
            except Exception as e:
                error_count += 1
                self._toon_foutdialoog(f"Fout bij printen {artikelnummer}: {e}")

        if success_count > 0:
            msg = f"{success_count} product(en) succesvol geprint."
            if error_count > 0:
                msg += f" {error_count} fout(en)."
            self._toon_info_dialoog(msg)

    def _export_csv(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="CSV opslaan",
            transient_for=self.main_window,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name(f"producten_{datetime.date.today().isoformat()}.csv")

        filter_csv = Gtk.FileFilter()
        filter_csv.set_name("CSV-bestanden (*.csv)")
        filter_csv.add_pattern("*.csv")
        dialog.add_filter(filter_csv)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            bestandspad = dialog.get_filename()
            if not bestandspad.endswith('.csv'):
                bestandspad += '.csv'
            self._exporteer_naar_csv(bestandspad)
        dialog.destroy()

    def _exporteer_naar_csv(self, bestandspad):
        try:
            storage = get_backend(self.config)
            producten = storage.load_products()

            if self.huidige_filter == FILTER_OFFLINE:
                producten = [p for p in producten
                             if p.get("verkocht", "nee").lower() != "ja"
                             and p.get("online", "nee").lower() != "ja"
                             and p.get("gereserveerd", "nee").lower() != "ja"]
            elif self.huidige_filter == FILTER_ONLINE:
                producten = [p for p in producten
                             if p.get("verkocht", "nee").lower() != "ja"
                             and p.get("online", "nee").lower() == "ja"
                             and p.get("gereserveerd", "nee").lower() != "ja"]
            elif self.huidige_filter == FILTER_VERKOCHT:
                producten = [p for p in producten if p.get("verkocht", "nee").lower() == "ja"]
            elif self.huidige_filter == FILTER_GERESERVEERD:
                producten = [p for p in producten
                             if p.get("gereserveerd", "nee").lower() == "ja"
                             and p.get("verkocht", "nee").lower() != "ja"]

            if self.zoekterm:
                producten = [p for p in producten
                             if self.zoekterm in p.get("artikelnummer", "").lower()
                             or self.zoekterm in p.get("titel", "").lower()]

            kolommen = self.user_settings.get_zichtbare_kolommen(self.huidige_filter)

            with open(bestandspad, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                headers = [KOLOM_LABELS.get(k, k) for k in kolommen]
                writer.writerow(headers)
                for p in producten:
                    row = [p.get(k, "") for k in kolommen]
                    writer.writerow(row)

            self._toon_info_dialoog(f"CSV geëxporteerd naar:\n{bestandspad}")

        except Exception as e:
            self._toon_foutdialoog(f"Fout bij exporteren: {e}")

    def _export_excel(self, widget):
        try:
            import openpyxl
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment
        except ImportError:
            self._toon_foutdialoog(
                "openpyxl is niet geïnstalleerd.\n"
                "Installeer met: pip install openpyxl --break-system-packages\n"
                "CSV wordt geëxporteerd als alternatief."
            )
            self._export_csv(widget)
            return

        dialog = Gtk.FileChooserDialog(
            title="Excel opslaan",
            transient_for=self.main_window,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name(f"producten_{datetime.date.today().isoformat()}.xlsx")

        filter_excel = Gtk.FileFilter()
        filter_excel.set_name("Excel-bestanden (*.xlsx)")
        filter_excel.add_pattern("*.xlsx")
        dialog.add_filter(filter_excel)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            bestandspad = dialog.get_filename()
            if not bestandspad.endswith('.xlsx'):
                bestandspad += '.xlsx'

            try:
                storage = get_backend(self.config)
                producten = storage.load_products()

                if self.huidige_filter == FILTER_OFFLINE:
                    producten = [p for p in producten
                                 if p.get("verkocht", "nee").lower() != "ja"
                                 and p.get("online", "nee").lower() != "ja"
                                 and p.get("gereserveerd", "nee").lower() != "ja"]
                elif self.huidige_filter == FILTER_ONLINE:
                    producten = [p for p in producten
                                 if p.get("verkocht", "nee").lower() != "ja"
                                 and p.get("online", "nee").lower() == "ja"
                                 and p.get("gereserveerd", "nee").lower() != "ja"]
                elif self.huidige_filter == FILTER_VERKOCHT:
                    producten = [p for p in producten if p.get("verkocht", "nee").lower() == "ja"]
                elif self.huidige_filter == FILTER_GERESERVEERD:
                    producten = [p for p in producten
                                 if p.get("gereserveerd", "nee").lower() == "ja"
                                 and p.get("verkocht", "nee").lower() != "ja"]

                if self.zoekterm:
                    producten = [p for p in producten
                                 if self.zoekterm in p.get("artikelnummer", "").lower()
                                 or self.zoekterm in p.get("titel", "").lower()]

                kolommen = self.user_settings.get_zichtbare_kolommen(self.huidige_filter)

                wb = Workbook()
                ws = wb.active
                ws.title = "Producten"

                headers = [KOLOM_LABELS.get(k, k) for k in kolommen]
                for col, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=col, value=header)
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center')

                for row, p in enumerate(producten, 2):
                    for col, k in enumerate(kolommen, 1):
                        ws.cell(row=row, column=col, value=p.get(k, ""))

                for col in range(1, len(headers) + 1):
                    ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 15

                wb.save(bestandspad)
                self._toon_info_dialoog(f"Excel geëxporteerd naar:\n{bestandspad}")

            except Exception as e:
                self._toon_foutdialoog(f"Fout bij exporteren: {e}")

        dialog.destroy()

    def _open_dashboard(self, widget):
        """Open dashboard in de main window (als tab)."""
        self.main_window.notebook.set_current_page(2)

    def undo(self):
        if not self.undo_stack:
            self._toon_info_dialoog("Geen acties om ongedaan te maken.")
            return

        actie = self.undo_stack.pop()
        self.redo_stack.append(actie)

        storage = get_backend(self.config)
        actie_type = actie["actie"]
        data = actie["data"]

        if actie_type == "verwijderen":
            for item in data:
                try:
                    storage.add_product(item["product"])
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {item['artikelnummer']}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"{len(data)} product(en) hersteld.")

        elif actie_type == "bewerken":
            artikelnummer = data["artikelnummer"]
            try:
                storage.update_product(artikelnummer, data["oud"])
                self.herlaad()
                self._toon_info_dialoog(f"Product {artikelnummer} teruggedraaid.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type in ["online_markeren", "offline_markeren"]:
            for artikelnummer, oud in data["oud"].items():
                try:
                    storage.update_product(artikelnummer, oud)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"{len(data['oud'])} product(en) teruggedraaid.")

        elif actie_type == "verkocht_markeren":
            artikelnummer = data["artikelnummer"]
            try:
                storage.update_product(artikelnummer, data["oud"])
                self.herlaad()
                self._toon_info_dialoog(f"Verkoop van {artikelnummer} ongedaan gemaakt.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type == "retour_melden":
            for artikelnummer, oud in data["oud"].items():
                try:
                    storage.update_product(artikelnummer, oud)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Retour van {len(data['oud'])} product(en) ongedaan gemaakt.")

        elif actie_type == "gereserveerd_markeren":
            artikelnummer = data["artikelnummer"]
            try:
                storage.update_product(artikelnummer, data["oud"])
                self.herlaad()
                self._toon_info_dialoog(f"Reservering van {artikelnummer} ongedaan gemaakt.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type == "reservering_annuleren":
            for artikelnummer, oud in data["oud"].items():
                try:
                    storage.update_product(artikelnummer, oud)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Annulering van reservering ({len(data['oud'])} product(en)) ongedaan gemaakt.")

        elif actie_type == "toewijzen":
            for artikelnummer, oud in data["oud"].items():
                try:
                    storage.update_product(artikelnummer, oud)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"{len(data['oud'])} product(en) teruggedraaid in toewijzing.")

    def redo(self):
        if not self.redo_stack:
            self._toon_info_dialoog("Geen acties om opnieuw uit te voeren.")
            return

        actie = self.redo_stack.pop()
        self.undo_stack.append(actie)

        actie_type = actie["actie"]
        data = actie["data"]

        if actie_type == "verwijderen":
            storage = get_backend(self.config)
            for item in data:
                try:
                    storage.delete_product(item["artikelnummer"])
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij verwijderen {item['artikelnummer']}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"{len(data)} product(en) opnieuw verwijderd.")

        elif actie_type == "bewerken":
            artikelnummer = data["artikelnummer"]
            try:
                storage = get_backend(self.config)
                storage.update_product(artikelnummer, data["nieuw"])
                self.herlaad()
                self._toon_info_dialoog(f"Bewerking opnieuw toegepast op {artikelnummer}.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type in ["online_markeren", "offline_markeren"]:
            storage = get_backend(self.config)
            producten = storage.load_products()
            for artikelnummer, oud in data["oud"].items():
                product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                if product:
                    if actie_type == "online_markeren":
                        product["online"] = "ja"
                    else:
                        product["online"] = "nee"
                    try:
                        storage.update_product(artikelnummer, product)
                    except Exception as e:
                        self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Status opnieuw toegepast op {len(data['oud'])} product(en).")

        elif actie_type == "verkocht_markeren":
            artikelnummer = data["artikelnummer"]
            try:
                storage = get_backend(self.config)
                storage.update_product(artikelnummer, data["nieuw"])
                self.herlaad()
                self._toon_info_dialoog(f"Verkoop opnieuw toegepast op {artikelnummer}.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type == "retour_melden":
            storage = get_backend(self.config)
            for artikelnummer, nieuw in data["nieuw"].items():
                try:
                    storage.update_product(artikelnummer, nieuw)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Retour opnieuw toegepast op {len(data['nieuw'])} product(en).")

        elif actie_type == "gereserveerd_markeren":
            artikelnummer = data["artikelnummer"]
            try:
                storage = get_backend(self.config)
                storage.update_product(artikelnummer, data["nieuw"])
                self.herlaad()
                self._toon_info_dialoog(f"Reservering opnieuw toegepast op {artikelnummer}.")
            except Exception as e:
                self._toon_foutdialoog(f"Fout bij herstellen: {e}")

        elif actie_type == "reservering_annuleren":
            storage = get_backend(self.config)
            for artikelnummer, nieuw in data["nieuw"].items():
                try:
                    storage.update_product(artikelnummer, nieuw)
                except Exception as e:
                    self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Annulering opnieuw toegepast op {len(data['nieuw'])} product(en).")

        elif actie_type == "toewijzen":
            storage = get_backend(self.config)
            producten = storage.load_products()
            for artikelnummer, oud in data["oud"].items():
                product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
                if product:
                    product["toegewezen_aan"] = data["nieuw_toegewezen"]
                    try:
                        storage.update_product(artikelnummer, product)
                    except Exception as e:
                        self._toon_foutdialoog(f"Fout bij herstellen {artikelnummer}: {e}")
            self.herlaad()
            self._toon_info_dialoog(f"Toewijzing opnieuw toegepast op {len(data['oud'])} product(en).")


# ============================================
# TAB: DASHBOARD (als tab - gerepareerd)
# ============================================
class DashboardTab(Gtk.Box):
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.set_border_width(15)

        try:
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.pack_start(scrolled, True, True, 0)

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            inner.set_border_width(5)
            scrolled.add(inner)

            refresh_btn = Gtk.Button(label="🔄 Vernieuwen")
            refresh_btn.connect("clicked", lambda w: self.herlaad())
            inner.pack_start(refresh_btn, False, False, 0)

            self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            inner.pack_start(self.content_box, True, True, 0)

            self.herlaad()
        except Exception as e:
            print(f"❌ Fout in DashboardTab.__init__: {e}")
            label = Gtk.Label()
            label.set_markup(f"<span foreground='red'>❌ Fout bij laden dashboard: {str(e)}</span>")
            self.pack_start(label, True, True, 0)

    def herlaad(self):
        try:
            for child in self.content_box.get_children():
                self.content_box.remove(child)

            storage = get_backend(self.config)
            producten = storage.load_products()

            totaal = len(producten)
            online = len([p for p in producten if p.get("online", "nee").lower() == "ja"])
            offline = len([p for p in producten if p.get("online", "nee").lower() != "ja"
                           and p.get("verkocht", "nee").lower() != "ja"])
            verkocht = len([p for p in producten if p.get("verkocht", "nee").lower() == "ja"])

            # Totaal overzicht
            totaal_label = Gtk.Label()
            totaal_label.set_markup(
                f"<b><big>📊 Overzicht</big></b>\n\n"
                f"<b>Totaal producten:</b> {totaal}\n"
                f"<b>Online:</b> {online}\n"
                f"<b>Offline (in voorraad):</b> {offline}\n"
                f"<b>Verkocht:</b> {verkocht}"
            )
            totaal_label.set_xalign(0)
            self.content_box.pack_start(totaal_label, False, False, 0)

            self.content_box.pack_start(Gtk.Separator(), False, False, 5)

            # Omzet
            totaal_omzet = 0.0
            verkocht_producten = []
            for p in producten:
                if p.get("verkocht", "nee").lower() == "ja":
                    try:
                        prijs = p.get("verkoopprijs", "").replace("€", "").replace(",", ".").strip()
                        if prijs:
                            totaal_omzet += float(prijs)
                            verkocht_producten.append(p)
                    except ValueError:
                        pass

            gem_prijs = totaal_omzet / len(verkocht_producten) if verkocht_producten else 0

            omzet_label = Gtk.Label()
            omzet_label.set_markup(
                f"<b><big>💰 Omzet</big></b>\n\n"
                f"<b>Totale omzet:</b> €{totaal_omzet:.2f}\n"
                f"<b>Aantal verkocht:</b> {len(verkocht_producten)}\n"
                f"<b>Gemiddelde verkoopprijs:</b> €{gem_prijs:.2f}"
            )
            omzet_label.set_xalign(0)
            self.content_box.pack_start(omzet_label, False, False, 0)

            self.content_box.pack_start(Gtk.Separator(), False, False, 5)

            # Gereserveerd - verwachte inkomsten (nadrukkelijk LOS van de echte omzet
            # hierboven, want een reservering is nog geen afgeronde verkoop)
            gereserveerd_totaal = 0.0
            gereserveerde_producten = []
            for p in producten:
                if (p.get("gereserveerd", "nee").lower() == "ja"
                        and p.get("verkocht", "nee").lower() != "ja"):
                    try:
                        prijs = p.get("reserveprijs", "").replace("€", "").replace(",", ".").strip()
                        if prijs:
                            gereserveerd_totaal += float(prijs)
                        gereserveerde_producten.append(p)
                    except ValueError:
                        pass

            gereserveerd_label = Gtk.Label()
            gereserveerd_label.set_markup(
                f"<b><big>📌 Gereserveerd</big></b>\n\n"
                f"<b>Verwachte inkomsten:</b> €{gereserveerd_totaal:.2f} "
                f"<small>(telt niet mee in de omzet hierboven)</small>\n"
                f"<b>Aantal gereserveerd:</b> {len(gereserveerde_producten)}"
            )
            gereserveerd_label.set_xalign(0)
            self.content_box.pack_start(gereserveerd_label, False, False, 0)

            self.content_box.pack_start(Gtk.Separator(), False, False, 5)

            # Geschatte waarde & vraagprijs van alle geregistreerde items
            totaal_waarde_min = 0.0
            totaal_waarde_max = 0.0
            totaal_vraagprijs = 0.0

            def _to_float(tekst):
                tekst = (tekst or "").replace("€", "").replace(",", ".").strip()
                if not tekst:
                    return 0.0
                try:
                    return float(tekst)
                except ValueError:
                    return 0.0

            for p in producten:
                totaal_waarde_min += _to_float(p.get("waarde_min", ""))
                totaal_waarde_max += _to_float(p.get("waarde_max", ""))
                totaal_vraagprijs += _to_float(p.get("vraagprijs", ""))

            waarde_label = Gtk.Label()
            waarde_label.set_markup(
                f"<b><big>📈 Geschatte waarde ({totaal} items)</big></b>\n\n"
                f"<b>Totale min. waarde:</b> €{totaal_waarde_min:.2f}\n"
                f"<b>Totale max. waarde:</b> €{totaal_waarde_max:.2f}\n"
                f"<b>Totale vraagprijs:</b> €{totaal_vraagprijs:.2f}"
            )
            waarde_label.set_xalign(0)
            self.content_box.pack_start(waarde_label, False, False, 0)

            self.content_box.pack_start(Gtk.Separator(), False, False, 5)

            # Categorie verdeling (Top 10)
            cat_label = Gtk.Label()
            cat_label.set_markup("<b><big>📂 Top categorieën</big></b>")
            cat_label.set_xalign(0)
            self.content_box.pack_start(cat_label, False, False, 0)

            cat_count = {}
            for p in producten:
                cat = p.get("categorie", "Onbekend")
                cat_count[cat] = cat_count.get(cat, 0) + 1

            sorted_cats = sorted(cat_count.items(), key=lambda x: x[1], reverse=True)
            cat_text = ""
            for cat, count in sorted_cats[:10]:
                percentage = (count / totaal * 100) if totaal > 0 else 0
                cat_text += f"<b>{cat}:</b> {count} ({percentage:.1f}%)\n"

            if not cat_text:
                cat_text = "Geen categorieën gevonden."

            cat_details = Gtk.Label()
            cat_details.set_markup(cat_text)
            cat_details.set_xalign(0)
            self.content_box.pack_start(cat_details, False, False, 0)

            self.content_box.pack_start(Gtk.Separator(), False, False, 5)

            # Medewerker statistieken
            user_label = Gtk.Label()
            user_label.set_markup("<b><big>👤 Medewerkers</big></b>")
            user_label.set_xalign(0)
            self.content_box.pack_start(user_label, False, False, 0)

            user_count = {}
            for p in producten:
                user = p.get("verwerkt_door", "Onbekend")
                user_count[user] = user_count.get(user, 0) + 1

            user_text = ""
            for user, count in sorted(user_count.items(), key=lambda x: x[1], reverse=True):
                user_text += f"<b>{user}:</b> {count} producten\n"

            if not user_text:
                user_text = "Geen medewerkers gevonden."

            user_details = Gtk.Label()
            user_details.set_markup(user_text)
            user_details.set_xalign(0)
            self.content_box.pack_start(user_details, False, False, 0)

            self.content_box.show_all()
        except Exception as e:
            print(f"❌ Fout in DashboardTab.herlaad: {e}")
            # Toon fout in de content box
            for child in self.content_box.get_children():
                self.content_box.remove(child)
            error_label = Gtk.Label()
            error_label.set_markup(f"<span foreground='red'>❌ Fout bij laden dashboard: {str(e)}</span>")
            self.content_box.pack_start(error_label, True, True, 0)
            self.content_box.show_all()


# ============================================
# TAB: INSTELLINGEN (als tab)
# ============================================
class SettingsTab(Gtk.Box):
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.user_settings = main_window.user_settings
        self.set_border_width(15)

        info_label = Gtk.Label()
        info_label.set_markup(
            "<big><b>⚙️ Instellingen</b></big>\n\n"
            "Klik op de knop hieronder om de instellingen te openen."
        )
        info_label.set_xalign(0)
        self.pack_start(info_label, False, False, 0)

        open_btn = Gtk.Button(label="⚙️ Instellingen openen")
        open_btn.connect("clicked", lambda w: self.main_window._open_settings(w))
        self.pack_start(open_btn, False, False, 0)


# ============================================
# HOOFDVENSTER (aangepast met compacte menu's)
# ============================================
class MainWindow(Gtk.Window):
    def __init__(self, gebruikersnaam, user_manager):
        super().__init__(title="Marktplaats Suite")
        self.set_default_size(1100, 850)
        self.set_position(Gtk.WindowPosition.CENTER)

        icon_path = asset("icon.png")
        if os.path.exists(icon_path):
            try:
                self.set_icon_from_file(icon_path)
            except Exception:
                pass

        self.config = ConfigManager()
        self.gebruikersnaam = gebruikersnaam
        self.user_manager = user_manager
        self.user_settings = UserSettings(gebruikersnaam)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # ============================================
        # MENU RIJ - compact met submenu's
        # ============================================
        menu_row = Gtk.Box(spacing=5)
        menu_row.set_border_width(5)

        gevonden_map = vind_marktplaats_map(self.config)
        backend_label = Gtk.Label()
        backend_label.set_markup(f"<small>📁 {gevonden_map}</small>")
        self.backend_label = backend_label
        menu_row.pack_start(backend_label, False, False, 0)

        right_box = Gtk.Box(spacing=5)
        menu_row.pack_end(right_box, False, False, 0)

        settings_btn = Gtk.Button(label="⚙️")
        settings_btn.set_tooltip_text("Instellingen")
        settings_btn.connect("clicked", self._open_settings)
        right_box.pack_start(settings_btn, False, False, 0)

        user_menu_btn = Gtk.MenuButton(label="👤")
        user_menu_btn.set_tooltip_text("Gebruikersbeheer")
        user_menu = Gtk.Menu()

        item_users = Gtk.MenuItem(label="👥 Gebruikers beheren")
        item_users.connect("activate", self._open_users)
        user_menu.append(item_users)

        item_logout = Gtk.MenuItem(label="🚪 Uitloggen")
        item_logout.connect("activate", self._on_logout)
        user_menu.append(item_logout)

        user_menu.show_all()
        user_menu_btn.set_popup(user_menu)
        right_box.pack_start(user_menu_btn, False, False, 0)

        gebruiker_label = Gtk.Label()
        gebruiker_label.set_markup(f"<small>👤 {GLib.markup_escape_text(gebruikersnaam)}</small>")
        right_box.pack_start(gebruiker_label, False, False, 5)

        vbox.pack_start(menu_row, False, False, 0)

        # ============================================
        # NOTEBOOK (Tabs) - alleen Registreren, Overzicht, Dashboard
        # ============================================
        self.notebook = Gtk.Notebook()
        vbox.pack_start(self.notebook, True, True, 0)

        self.registreer_tab = RegistreerTab(self)
        self.notebook.append_page(self.registreer_tab, Gtk.Label(label="📝 Registreren"))

        self.overzicht_tab = OverzichtTab(self)
        self.notebook.append_page(self.overzicht_tab, Gtk.Label(label="📊 Overzicht"))

        # Dashboard als tab (direct laden, geen placeholder)
        self.dashboard_tab = DashboardTab(self)
        self.notebook.append_page(self.dashboard_tab, Gtk.Label(label="📈 Dashboard"))

        # Overige onderdelen van de Marktplaats Suite als tabs
        self.foto_tab = self._maak_onderdeel_tab("📷 Foto's", "marktplaats_suite.fotomanager", "MarktplaatsApp")
        self.scanner_tab = self._maak_onderdeel_tab("🔍 Scanner", "marktplaats_suite.scanner", "MainWindow")
        self.automater_app = None
        try:
            from marktplaats_suite.automater import App as AutomaterApp
            self.automater_app = AutomaterApp()
            self.notebook.append_page(self.automater_app.window, Gtk.Label(label="🤖 Automater"))
        except (Exception, SystemExit) as e:
            self._voeg_foutmelding_tab_toe("🤖 Automater", e)
        self.connect("delete-event", self._on_delete_event)
        self.connect("destroy", lambda *_: self.automater_app and self.automater_app.sluit())

        self.statusbar = Gtk.Statusbar()
        self.statusbar.set_hexpand(True)
        vbox.pack_start(self.statusbar, False, False, 0)
        self.status_context = self.statusbar.get_context_id("main")
        self.statusbar.push(self.status_context, "✅ Klaar voor gebruik")

        self._setup_global_sneltoetsen()

    def _setup_global_sneltoetsen(self):
        accel_group = Gtk.AccelGroup()

        self._bind_sneltoets(accel_group, "ongedaan_maken", self.overzicht_tab.undo)
        self._bind_sneltoets(accel_group, "weer_gedaan_maken", self.overzicht_tab.redo)
        self._bind_sneltoets(accel_group, "online_markeren", lambda: self.overzicht_tab._on_markeer_online(None))
        self._bind_sneltoets(accel_group, "bewerken", lambda: self.overzicht_tab._on_bewerken(None))
        self._bind_sneltoets(accel_group, "zoeken", self._focus_zoekveld)
        self._bind_sneltoets(accel_group, "toewijzen", lambda: self.overzicht_tab._on_toewijzen(None))
        self._bind_sneltoets(accel_group, "alles_selecteren", self._select_all)
        self._bind_sneltoets(accel_group, "print_barcode", lambda: self.overzicht_tab._on_print_barcodes(None))
        self._bind_sneltoets(accel_group, "verkocht_markeren", lambda: self.overzicht_tab._on_markeer_verkocht(None))
        self._bind_sneltoets(accel_group, "retour_melden", lambda: self.overzicht_tab._on_retour_melden(None))
        self._bind_sneltoets(accel_group, "gereserveerd_markeren", lambda: self.overzicht_tab._on_markeer_gereserveerd(None))
        self._bind_sneltoets(accel_group, "open_map", lambda: self.overzicht_tab._on_open_map(None))
        self._bind_sneltoets(accel_group, "open_fotos", lambda: self.overzicht_tab._on_open_fotos(None))
        self._bind_sneltoets(accel_group, "locatie_wijzigen", lambda: self.overzicht_tab._on_locatie_wijzigen(None))

        self.add_accel_group(accel_group)

    def _bind_sneltoets(self, accel_group, actie, callback):
        toetsen = self.user_settings.get_sneltoets(actie)
        if not toetsen:
            return
        if isinstance(toetsen, str):
            toetsen = [toetsen]
        for toets in toetsen:
            try:
                key, mods = Gtk.accelerator_parse(toets)
                if key != 0:
                    accel_group.connect(key, mods, Gtk.AccelFlags.VISIBLE, callback)
            except Exception as e:
                print(f"Fout bij binden van sneltoets {actie} ({toets}): {e}")

    def _maak_onderdeel_tab(self, titel, module, klasse):
        """Laadt een onderdeel als tab; een ontbrekende afhankelijkheid breekt de rest niet."""
        import importlib
        try:
            tab = getattr(importlib.import_module(module), klasse)()
            self.notebook.append_page(tab, Gtk.Label(label=titel))
            return tab
        except (Exception, SystemExit) as e:
            self._voeg_foutmelding_tab_toe(titel, e)
            return None

    def _voeg_foutmelding_tab_toe(self, titel, fout):
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{GLib.markup_escape_text(titel)} kon niet worden geladen</b>\n\n"
                       f"{GLib.markup_escape_text(str(fout) or type(fout).__name__)}\n\n"
                       "Draai ./install.sh opnieuw om ontbrekende pakketten te installeren.")
        lbl.set_line_wrap(True); lbl.set_selectable(True)
        self.notebook.append_page(lbl, Gtk.Label(label=titel))

    def _on_delete_event(self, *_):
        if self.automater_app and not self.automater_app.kan_sluiten():
            return True
        return False

    def _focus_zoekveld(self):
        self.notebook.set_current_page(1)
        self.overzicht_tab.zoek_entry.grab_focus()

    def _select_all(self):
        self.notebook.set_current_page(1)
        selection = self.overzicht_tab.tree_view.get_selection()
        selection.select_all()

    def _open_settings(self, widget):
        try:
            dialog = SettingsDialog(self, self.config, self.user_settings)
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                dialog.apply_to_config()
                gevonden_map = vind_marktplaats_map(self.config)
                self.backend_label.set_markup(f"<small>📁 {gevonden_map}</small>")
                self._herbouw_registreer_tab()
                self.overzicht_tab._update_tree_columns()
                self.overzicht_tab.herlaad()
                self.dashboard_tab.herlaad()
                if getattr(self, "scanner_tab", None):
                    self.scanner_tab._update_backend_label()
            dialog.destroy()
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            dialog = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"❌ Fout bij het openen van instellingen:\n\n{str(e)}"
            )
            dialog.format_secondary_text(f"Details:\n{error_msg[:1000]}")
            dialog.run()
            dialog.destroy()
            print(f"Fout in instellingen: {error_msg}")

    def _open_users(self, widget):
        dialog = UsersDialog(self, self.user_manager, self.gebruikersnaam)
        dialog.run()
        dialog.destroy()

    def _on_logout(self, widget):
        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text="Weet je zeker dat je wilt uitloggen?"
        )
        confirm.format_secondary_text("Je wordt teruggebracht naar het inlogscherm.")
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            self.destroy()
            main()

    def _herbouw_registreer_tab(self):
        self.notebook.remove_page(0)
        self.registreer_tab = RegistreerTab(self)
        self.notebook.insert_page(self.registreer_tab, Gtk.Label(label="📝 Registreren"), 0)
        self.notebook.show_all()


# ============================================
# DASHBOARD DIALOOG (oude versie, behouden voor compatibiliteit)
# ============================================
class DashboardDialog(Gtk.Dialog):
    def __init__(self, parent, producten):
        super().__init__(title="📈 Dashboard - Statistieken", transient_for=parent, flags=0)
        self.set_default_size(600, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(15)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scrolled, True, True, 0)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_border_width(5)
        scrolled.add(inner)

        totaal = len(producten)
        online = len([p for p in producten if p.get("online", "nee").lower() == "ja"])
        offline = len([p for p in producten if p.get("online", "nee").lower() != "ja"
                       and p.get("verkocht", "nee").lower() != "ja"])
        verkocht = len([p for p in producten if p.get("verkocht", "nee").lower() == "ja"])

        totaal_label = Gtk.Label()
        totaal_label.set_markup(
            f"<b><big>📊 Overzicht</big></b>\n\n"
            f"<b>Totaal producten:</b> {totaal}\n"
            f"<b>Online:</b> {online}\n"
            f"<b>Offline (in voorraad):</b> {offline}\n"
            f"<b>Verkocht:</b> {verkocht}"
        )
        totaal_label.set_xalign(0)
        inner.pack_start(totaal_label, False, False, 0)

        inner.pack_start(Gtk.Separator(), False, False, 5)

        totaal_omzet = 0.0
        verkocht_producten = []
        for p in producten:
            if p.get("verkocht", "nee").lower() == "ja":
                try:
                    prijs = p.get("verkoopprijs", "").replace("€", "").replace(",", ".").strip()
                    if prijs:
                        totaal_omzet += float(prijs)
                        verkocht_producten.append(p)
                except ValueError:
                    pass

        gem_prijs = totaal_omzet / len(verkocht_producten) if verkocht_producten else 0

        omzet_details = Gtk.Label()
        omzet_details.set_markup(
            f"<b>Totale omzet:</b> €{totaal_omzet:.2f}\n"
            f"<b>Aantal verkocht:</b> {len(verkocht_producten)}\n"
            f"<b>Gemiddelde verkoopprijs:</b> €{gem_prijs:.2f}"
        )
        omzet_details.set_xalign(0)
        inner.pack_start(omzet_details, False, False, 0)

        inner.pack_start(Gtk.Separator(), False, False, 5)

        cat_label = Gtk.Label()
        cat_label.set_markup("<b><big>📂 Categorie verdeling</big></b>")
        cat_label.set_xalign(0)
        inner.pack_start(cat_label, False, False, 0)

        cat_count = {}
        for p in producten:
            cat = p.get("categorie", "Onbekend")
            cat_count[cat] = cat_count.get(cat, 0) + 1

        sorted_cats = sorted(cat_count.items(), key=lambda x: x[1], reverse=True)
        cat_text = ""
        for cat, count in sorted_cats[:10]:
            percentage = (count / totaal * 100) if totaal > 0 else 0
            cat_text += f"<b>{cat}:</b> {count} ({percentage:.1f}%)\n"

        if not cat_text:
            cat_text = "Geen categorieën gevonden."

        cat_details = Gtk.Label()
        cat_details.set_markup(cat_text)
        cat_details.set_xalign(0)
        inner.pack_start(cat_details, False, False, 0)

        inner.pack_start(Gtk.Separator(), False, False, 5)

        user_label = Gtk.Label()
        user_label.set_markup("<b><big>👤 Medewerker statistieken</big></b>")
        user_label.set_xalign(0)
        inner.pack_start(user_label, False, False, 0)

        user_count = {}
        for p in producten:
            user = p.get("verwerkt_door", "Onbekend")
            user_count[user] = user_count.get(user, 0) + 1

        user_text = ""
        for user, count in sorted(user_count.items(), key=lambda x: x[1], reverse=True):
            user_text += f"<b>{user}:</b> {count} producten\n"

        if not user_text:
            user_text = "Geen medewerkers gevonden."

        user_details = Gtk.Label()
        user_details.set_markup(user_text)
        user_details.set_xalign(0)
        inner.pack_start(user_details, False, False, 0)

        inner.pack_start(Gtk.Separator(), False, False, 5)

        time_label = Gtk.Label()
        time_label.set_markup("<b><big>📅 Aanmaak per dag (laatste 7 dagen)</big></b>")
        time_label.set_xalign(0)
        inner.pack_start(time_label, False, False, 0)

        from collections import defaultdict
        day_count = defaultdict(int)
        today = datetime.date.today()

        for p in producten:
            datum_str = p.get("aanmaakdatum", "")
            try:
                datum = datetime.date.fromisoformat(datum_str)
                days_ago = (today - datum).days
                if 0 <= days_ago < 7:
                    day_count[datum] += 1
            except (ValueError, TypeError):
                pass

        time_text = ""
        for i in range(6, -1, -1):
            datum = today - datetime.timedelta(days=i)
            count = day_count.get(datum, 0)
            dag_naam = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"][datum.weekday()]
            time_text += f"<b>{dag_naam} {datum.day}/{datum.month}:</b> {count} producten\n"

        if not time_text:
            time_text = "Geen aanmaakgegevens gevonden."

        time_details = Gtk.Label()
        time_details.set_markup(time_text)
        time_details.set_xalign(0)
        inner.pack_start(time_details, False, False, 0)

        self.show_all()


# ============================================
# ANDERE DIALOGEN (OnlineDialog, ToewijzenDialog, VerkochtDialog, BewerkDialog)
# ============================================
class OnlineDialog(Gtk.Dialog):
    def __init__(self, parent, artikelnummers):
        if len(artikelnummers) == 1:
            title = f"Advertentie-URLs - {artikelnummers[0]}"
        else:
            title = f"Advertentie-URLs - {len(artikelnummers)} producten"

        super().__init__(title=title, transient_for=parent, flags=0)
        self.set_default_size(500, 350)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        if len(artikelnummers) == 1:
            msg = f"Voer advertentie-URL(s) in voor {artikelnummers[0]} (max 5):"
        else:
            msg = f"Voer advertentie-URL(s) in voor {len(artikelnummers)} producten (max 5):"

        box.pack_start(Gtk.Label(label=msg, xalign=0), False, False, 0)

        self.url_entries = []
        for i in range(5):
            entry = Gtk.Entry()
            entry.set_placeholder_text(f"URL {i+1} (optioneel)")
            box.pack_start(entry, False, False, 3)
            self.url_entries.append(entry)

        self.show_all()

    def get_urls(self):
        urls = []
        for entry in self.url_entries:
            url = entry.get_text().strip()
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f"https://{url}"
                urls.append(url)
        return urls


class ToewijzenDialog(Gtk.Dialog):
    def __init__(self, parent, product, user_manager, huidige_gebruiker):
        super().__init__(title=f"Toewijzen - {product.get('artikelnummer', '')}", transient_for=parent, flags=0)
        self.set_default_size(320, 150)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        box.pack_start(Gtk.Label(label="Selecteer de medewerker die dit product afhandelt:", xalign=0), False, False, 0)

        self.gebruikers_combo = Gtk.ComboBoxText()
        self.gebruikers_combo.append_text("")
        for naam in user_manager.gebruikersnamen():
            self.gebruikers_combo.append_text(naam)

        huidige = product.get("toegewezen_aan", "")
        if huidige:
            try:
                self.gebruikers_combo.set_active(1 + user_manager.gebruikersnamen().index(huidige))
            except ValueError:
                self.gebruikers_combo.set_active(0)
        else:
            self.gebruikers_combo.set_active(0)

        box.pack_start(self.gebruikers_combo, False, False, 0)

        self.show_all()

    def get_toegewezen_aan(self):
        tekst = self.gebruikers_combo.get_active_text()
        return tekst.strip() if tekst else ""


class VerkochtDialog(Gtk.Dialog):
    def __init__(self, parent, artikelnummer):
        super().__init__(title=f"Markeer als verkocht - {artikelnummer}", transient_for=parent, flags=0)
        self.set_default_size(420, 380)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        box.pack_start(Gtk.Label(label=f"Verkoopprijs voor {artikelnummer}:", xalign=0), False, False, 0)
        self.prijs_entry = Gtk.Entry()
        self.prijs_entry.set_placeholder_text("bijv. 45.00")
        box.pack_start(self.prijs_entry, False, False, 0)

        vandaag = datetime.date.today().isoformat()
        box.pack_start(Gtk.Label(label=f"Verkoopdatum: {vandaag} (automatisch)", xalign=0), False, False, 0)
        self.vandaag = vandaag

        box.pack_start(Gtk.Separator(), False, False, 6)

        box.pack_start(self._bold_label("Leverwijze"), False, False, 0)
        lever_row = Gtk.Box(spacing=10)
        self.ophalen_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Ophalen")
        self.verzenden_btn = Gtk.RadioButton.new_with_label_from_widget(self.ophalen_btn, "Verzenden")
        self.ophalen_btn.connect("toggled", self._on_leverwijze_changed)
        lever_row.pack_start(self.ophalen_btn, False, False, 0)
        lever_row.pack_start(self.verzenden_btn, False, False, 0)
        box.pack_start(lever_row, False, False, 0)

        box.pack_start(Gtk.Label(label="Marktplaatsnaam koper:", xalign=0), False, False, 0)
        self.klant_naam_entry = Gtk.Entry()
        box.pack_start(self.klant_naam_entry, False, False, 0)

        self.ophalen_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(self.ophalen_box, False, False, 0)

        self.ophalen_box.pack_start(Gtk.Label(label="Telefoonnummer:", xalign=0), False, False, 0)
        self.telefoon_entry = Gtk.Entry()
        self.ophalen_box.pack_start(self.telefoon_entry, False, False, 0)

        self.ophalen_box.pack_start(Gtk.Label(label="E-mail:", xalign=0), False, False, 0)
        self.email_entry = Gtk.Entry()
        self.ophalen_box.pack_start(self.email_entry, False, False, 0)

        self.ophalen_box.pack_start(Gtk.Label(label="Afspraak (datum/tijd ophalen):", xalign=0), False, False, 0)
        self.afspraak_entry = Gtk.Entry()
        self.afspraak_entry.set_placeholder_text("bijv. zaterdag 14:00")
        self.ophalen_box.pack_start(self.afspraak_entry, False, False, 0)

        self.verzenden_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(self.verzenden_box, False, False, 0)

        self.verzenden_box.pack_start(Gtk.Label(label="Track & Trace-nummer (optioneel):", xalign=0), False, False, 0)
        self.track_trace_entry = Gtk.Entry()
        self.verzenden_box.pack_start(self.track_trace_entry, False, False, 0)

        self.ophalen_btn.set_active(True)
        self._on_leverwijze_changed(self.ophalen_btn)

        self.show_all()

    def _bold_label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label

    def _on_leverwijze_changed(self, widget):
        is_ophalen = self.ophalen_btn.get_active()
        self.ophalen_box.set_visible(is_ophalen)
        self.verzenden_box.set_visible(not is_ophalen)

    def get_gegevens(self):
        leverwijze = "ophalen" if self.ophalen_btn.get_active() else "verzenden"
        gegevens = {
            "verkoopprijs": self.prijs_entry.get_text().strip(),
            "verkoopdatum": self.vandaag,
            "leverwijze": leverwijze,
            "klant_naam": self.klant_naam_entry.get_text().strip(),
        }
        if leverwijze == "ophalen":
            gegevens["klant_telefoon"] = self.telefoon_entry.get_text().strip()
            gegevens["klant_email"] = self.email_entry.get_text().strip()
            gegevens["ophaal_afspraak"] = self.afspraak_entry.get_text().strip()
            gegevens["track_trace"] = ""
        else:
            gegevens["klant_telefoon"] = ""
            gegevens["klant_email"] = ""
            gegevens["ophaal_afspraak"] = ""
            gegevens["track_trace"] = self.track_trace_entry.get_text().strip()
        return gegevens


class ReserveerDialog(Gtk.Dialog):
    def __init__(self, parent, artikelnummer):
        super().__init__(title=f"Markeer als gereserveerd - {artikelnummer}", transient_for=parent, flags=0)
        self.set_default_size(380, 220)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        box.pack_start(Gtk.Label(label=f"(Verwachte) reserveprijs voor {artikelnummer}:", xalign=0), False, False, 0)
        self.prijs_entry = Gtk.Entry()
        self.prijs_entry.set_placeholder_text("bijv. 45.00")
        box.pack_start(self.prijs_entry, False, False, 0)

        vandaag = datetime.date.today().isoformat()
        box.pack_start(Gtk.Label(label=f"Reserveerdatum: {vandaag} (automatisch)", xalign=0), False, False, 0)
        self.vandaag = vandaag

        box.pack_start(Gtk.Separator(), False, False, 6)

        box.pack_start(Gtk.Label(label="Gereserveerd voor (naam, optioneel):", xalign=0), False, False, 0)
        self.klant_naam_entry = Gtk.Entry()
        box.pack_start(self.klant_naam_entry, False, False, 0)

        self.show_all()

    def get_gegevens(self):
        return {
            "reserveprijs": self.prijs_entry.get_text().strip(),
            "reserveerdatum": self.vandaag,
            "reservering_klant_naam": self.klant_naam_entry.get_text().strip(),
        }


class BewerkDialog(Gtk.Dialog):
    def __init__(self, parent, product, config):
        super().__init__(title=f"Bewerken - {product.get('artikelnummer', '')}", transient_for=parent, flags=0)
        self.product = dict(product)
        self.config = config
        self.set_default_size(500, 600)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scrolled, True, True, 0)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner.set_border_width(5)
        scrolled.add(inner)

        self.entries = {}
        inner.pack_start(Gtk.Label(label=f"Artikelnummer: {self.product.get('artikelnummer', '')}"), False, False, 0)

        bewerkbare_velden = [c for c in COLUMNS if c not in ("artikelnummer", "folder_locatie")]
        for veld in bewerkbare_velden:
            label = Gtk.Label(label=KOLOM_LABELS.get(veld, veld))
            label.set_xalign(0)
            inner.pack_start(label, False, False, 0)

            if veld in ("omschrijving", "algemene_voorwaarden"):
                view = Gtk.TextView()
                view.get_buffer().set_text(self.product.get(veld, ""))
                view_scroll = Gtk.ScrolledWindow()
                view_scroll.set_size_request(-1, 80)
                view_scroll.add(view)
                inner.pack_start(view_scroll, False, False, 0)
                self.entries[veld] = view
            elif veld.startswith("url_"):
                entry = Gtk.Entry()
                entry.set_text(self.product.get(veld, ""))
                entry.set_placeholder_text(f"https://www.marktplaats.nl/v/...")
                inner.pack_start(entry, False, False, 0)
                self.entries[veld] = entry
            else:
                entry = Gtk.Entry()
                entry.set_text(self.product.get(veld, ""))
                inner.pack_start(entry, False, False, 0)
                self.entries[veld] = entry

        self.show_all()

    def get_product(self):
        result = dict(self.product)
        for veld, widget in self.entries.items():
            if isinstance(widget, Gtk.TextView):
                buf = widget.get_buffer()
                result[veld] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            else:
                result[veld] = widget.get_text()
        return result


# ============================================
# KOLOMKIEZER DIALOOG
# ============================================
class KolomKiezerDialog(Gtk.Dialog):
    def __init__(self, parent, user_settings, filter_type):
        super().__init__(title=f"Kies zichtbare kolommen - {FILTER_NAMEN[filter_type]}", transient_for=parent, flags=0)
        self.user_settings = user_settings
        self.filter_type = filter_type
        self.set_default_size(400, 450)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        box.pack_start(Gtk.Label(label=f"Selecteer welke kolommen zichtbaar moeten zijn voor filter '{FILTER_NAMEN[filter_type]}':", xalign=0), False, False, 0)
        box.pack_start(Gtk.Label(label=f"<small>Instellingen voor gebruiker: <b>{parent.gebruikersnaam}</b></small>", xalign=0), False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 350)
        box.pack_start(scrolled, True, True, 0)

        self.kolom_checkboxes = {}
        kolom_grid = Gtk.Grid()
        kolom_grid.set_column_spacing(20)
        kolom_grid.set_row_spacing(3)

        zichtbare = set(user_settings.get_zichtbare_kolommen(filter_type))

        sorted_kolommen = sorted(COLUMNS, key=lambda k: KOLOM_LABELS.get(k, k))

        row = 0
        col = 0
        for kolom in sorted_kolommen:
            if kolom in ["omschrijving", "algemene_voorwaarden", "folder_locatie"]:
                continue
            label = KOLOM_LABELS.get(kolom, kolom)
            check = Gtk.CheckButton(label=label)
            check.set_active(kolom in zichtbare)
            self.kolom_checkboxes[kolom] = check
            kolom_grid.attach(check, col, row, 1, 1)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        scrolled.add(kolom_grid)

        btn_row = Gtk.Box(spacing=5)
        select_all_btn = Gtk.Button(label="Alles selecteren")
        select_all_btn.connect("clicked", self._on_select_all)
        btn_row.pack_start(select_all_btn, False, False, 0)

        select_none_btn = Gtk.Button(label="Niets selecteren")
        select_none_btn.connect("clicked", self._on_select_none)
        btn_row.pack_start(select_none_btn, False, False, 0)

        box.pack_start(btn_row, False, False, 5)

        self.show_all()

    def _on_select_all(self, widget):
        for check in self.kolom_checkboxes.values():
            check.set_active(True)

    def _on_select_none(self, widget):
        for check in self.kolom_checkboxes.values():
            check.set_active(False)

    def apply_to_settings(self):
        zichtbaar = [k for k, check in self.kolom_checkboxes.items() if check.get_active()]
        self.user_settings.set_zichtbare_kolommen(self.filter_type, zichtbaar)


def main():
    GLib.set_prgname("marktplaats_suite")
    apply_css()

    user_manager = UserManager()

    if not user_manager.heeft_gebruikers():
        dialog = NieuweGebruikerDialog(None, titel="Eerste gebruiker aanmaken")
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return
            naam, ww1, ww2 = dialog.get_invoer()
            if not naam:
                dialog.toon_fout("Vul een gebruikersnaam in.")
                continue
            if not ww1 or ww1 != ww2:
                dialog.toon_fout("Wachtwoorden komen niet overeen.")
                continue
            user_manager.voeg_toe(naam, ww1)
            gebruikersnaam = naam
            break
        dialog.destroy()

    login = LoginDialog(user_manager)
    gebruikersnaam = None
    while True:
        response = login.run()
        if response != Gtk.ResponseType.OK:
            login.destroy()
            return
        naam = login.get_naam()
        wachtwoord = login.get_wachtwoord()
        if not naam:
            login.toon_fout("Vul een gebruikersnaam in.")
            continue
        if user_manager.controleer(naam, wachtwoord):
            gebruikersnaam = naam
            break
        login.toon_fout("Onjuiste gebruikersnaam of wachtwoord.")
    login.destroy()

    win = MainWindow(gebruikersnaam, user_manager)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
