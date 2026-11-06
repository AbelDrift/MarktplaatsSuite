"""Lokale brug tussen de Suite en het Whoppah-userscript in je eigen (ingelogde) browser.

Draait alleen op 127.0.0.1. Levert de producten als JSON en het userscript zelf, zodat je
het script kunt installeren door http://127.0.0.1:8765/whoppah.user.js te openen in Firefox
(met Violentmonkey of Tampermonkey).
"""
import json
import math
import os
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from marktplaats_suite.common import get_xml_path, asset

POORT = 8765
_server = None


def _getal(w):
    try:
        return float(str(w).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def _staat(conditie):
    c = (conditie or "").lower()
    if not c:
        return ""
    if "nieuw" in c:
        return "Zo goed als nieuw" if "goed als" in c else "Nieuw"
    if "goed" in c or "gebruikt" in c or "redelijk" in c:
        return "Goed"
    return ""


def whoppah_velden(p, instell):
    """Berekende Whoppah-waarden voor één product (zelfde regels als de Uploader)."""
    uit = {"wp_staat": _staat(p.get("conditie"))}
    basis = _getal(p.get("vraagprijs"))
    if basis is not None:
        prijs = math.ceil(basis * float(instell.get("prijs_factor", 1.25)))
        onder = max(1, round(basis * float(instell.get("ondergrens_factor", 0.85))))
        uit["wp_prijs"], uit["wp_ondergrens"] = prijs, min(onder, prijs)
    dims = [_getal(p.get(k)) for k in ("lengte", "breedte", "hoogte")]
    if None not in dims:
        d = sorted(dims, reverse=True)
        uit["wp_verzending"] = "Pakket" if (d[0] <= 100 and d[1] <= 50 and d[2] <= 50) else "Koerier"
        uit["wp_breedte"], uit["wp_diepte"], uit["wp_hoogte"] = dims[0], dims[1], dims[2]
    uit["wp_stap"] = int(instell.get("stap_procent", 5))
    uit["wp_interval"] = str(instell.get("interval", "twee weken"))
    uit["wp_biedingen"] = bool(instell.get("biedingen", True))
    uit["wp_ophalen"] = bool(instell.get("ophalen", True))
    return uit


def vinted_velden(p, instell):
    """Berekende Vinted-waarden (zelfde regels als de Uploader)."""
    uit = {}
    w = _getal(p.get("waarde_min"))
    if w:
        uit["vinted_prijs"] = max(1, round(w))
    else:
        basis = _getal(p.get("vraagprijs"))
        if basis is not None:
            uit["vinted_prijs"] = max(1, round(basis * float(instell.get("prijs_terugval_factor", 0.85))))
    h, b, l = (_getal(p.get(k)) for k in ("hoogte", "breedte", "lengte"))
    gew = _getal(p.get("gewicht"))
    if None not in (h, b, l):
        d = sorted((h, b, l), reverse=True)
        if d[2] <= 3 and d[0] <= 40 and d[1] <= 30 and (gew is None or gew <= 1):
            uit["vinted_pakket"] = "Klein"          # plat, past in een grote envelop
        elif d[0] <= 35 and d[1] <= 25 and d[2] <= 15 and (gew is None or gew <= 5):
            uit["vinted_pakket"] = "Middel"         # schoenendoos
        else:
            uit["vinted_pakket"] = "Groot"          # verhuisdoos
    try:
        from marktplaats_suite.automater import build_description
        from marktplaats_suite.common import COLUMNS
        uit["vinted_omschrijving"] = build_description({"titel": p.get("titel", ""),
                                                        "row": [p.get(c, "") for c in COLUMNS]})
    except Exception:
        uit["vinted_omschrijving"] = p.get("omschrijving", "")
    return uit


def lees_producten(instell, vinted_instell=None):
    from marktplaats_suite.common import COLUMNS
    pad = get_xml_path()
    if not pad or not os.path.exists(pad):
        return []
    uit = []
    for el in ET.parse(pad).getroot().findall("product"):
        p = {c: ((el.find(c).text or "").strip() if el.find(c) is not None else "") for c in COLUMNS}
        if p.get("verkocht", "").lower() == "ja" or not p.get("artikelnummer"):
            continue
        p["al_online_whoppah"] = p.get("online_whoppah", "").lower() == "ja"
        p["voor_whoppah"] = "whoppah" in [k.strip().lower() for k in p.get("kanalen", "").split(",")]
        p["al_online_vinted"] = p.get("online_vinted", "").lower() == "ja"
        p["voor_vinted"] = "vinted" in [k.strip().lower() for k in p.get("kanalen", "").split(",")]
        p.update(whoppah_velden(p, instell))
        p.update(vinted_velden(p, vinted_instell or {}))
        uit.append(p)
    # eerst de producten die voor Whoppah bedoeld zijn en er nog niet staan
    uit.sort(key=lambda x: (x["al_online_whoppah"], not x["voor_whoppah"]))
    return uit


def start(config):
    """Start de brug (één keer). Geeft True als hij draait."""
    global _server
    if _server:
        return True

    def _sectie(naam):
        d = config.get(naam, {}) if hasattr(config, "get") else {}
        return d if isinstance(d, dict) else {}

    def instell():
        return _sectie("whoppah")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _ok_host(self):
            return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

        def _stuur(self, code, body, ctype):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "https://www.whoppah.com")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if not self._ok_host():
                return self._stuur(403, "host", "text/plain")
            if self.path.startswith("/producten"):
                try:
                    return self._stuur(200, json.dumps(lees_producten(instell(), _sectie("vinted")), ensure_ascii=False),
                                       "application/json; charset=utf-8")
                except Exception as e:
                    return self._stuur(500, str(e), "text/plain")
            if self.path.startswith(("/whoppah.user.js", "/vinted.user.js")):
                try:
                    with open(asset(self.path.split("?")[0].lstrip("/")), "rb") as f:
                        return self._stuur(200, f.read(), "text/javascript; charset=utf-8")
                except OSError:
                    return self._stuur(404, "niet gevonden", "text/plain")
            self._stuur(200, "SellYourShit brug", "text/plain")

    try:
        _server = ThreadingHTTPServer(("127.0.0.1", POORT), H)
    except OSError:
        return False
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return True


def json_voor_klembord(config):
    d = config.get("whoppah", {}) if hasattr(config, "get") else {}
    v = config.get("vinted", {}) if hasattr(config, "get") else {}
    return json.dumps(lees_producten(d if isinstance(d, dict) else {}, v if isinstance(v, dict) else {}),
                      ensure_ascii=False)
