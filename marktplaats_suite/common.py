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
