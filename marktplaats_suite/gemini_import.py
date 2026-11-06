"""Leest een Gemini-antwoord (titel, omschrijving, 'Details:', 'Geschatte waarde') in velden.

Verwacht formaat (zoals in je prompt):

    <titel>

    <beschrijving ...>

    Details:
    * Merk: ...
    * Materiaal: ...
    * Kleur: ...

    Geschatte waarde: € 25,- tot € 50,-

De omschrijving bevat, net als bij het handmatig plakken, ook het 'Details:'-blok; alleen de
regel 'Geschatte waarde' wordt eruit gehaald.
"""
import re

MAX_TITEL = 60

_BULLET = re.compile(r"^\s*(?:[*\-•]|\d+[.)])\s+(.*\S)\s*$")
_GETAL = re.compile(r"\d+(?:[.,]\d+)?")


def _kort_titel(titel):
    titel = titel.strip().strip("*#").strip()
    if len(titel) <= MAX_TITEL:
        return titel
    knip = titel[:MAX_TITEL].rsplit(" ", 1)[0]
    return (knip or titel[:MAX_TITEL]).strip()


def _getal(s):
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _fmt(x):
    return f"{x:g}"


def _kort(waarde):
    """'Hout (donker gebeitst) met vilten onderzijde' -> 'Hout' (handig voor lijsten op Whoppah/Vinted)."""
    w = re.sub(r"\([^)]*\)", "", waarde)
    w = re.split(r"\s+(?:met|met een|inclusief|en bijbehorende)\s+", w, maxsplit=1)[0]
    return re.sub(r"\s{2,}", " ", w).strip(" ,;.") or waarde


def _conditie(tekst):
    t = tekst.lower()
    if "beschadigd" in t or "defect" in t or "kapot" in t:
        return "Beschadigd"
    if "zo goed als nieuw" in t or "als nieuw" in t or "bijna nieuw" in t:
        return "Zo goed als nieuw"
    if "nieuwstaat" in t or t.strip().startswith("nieuw"):
        return "Nieuwstaat"
    if any(w in t for w in ("goed", "gebruikt", "patina", "gebruikssporen", "redelijk")):
        return "Gebruikt"
    return ""


def parse(tekst):
    """Geeft (velden, meldingen). velden bevat alleen wat gevonden is."""
    velden, meld = {}, []
    regels = [r.rstrip() for r in (tekst or "").replace("\r", "").split("\n")]
    # titel = eerste niet-lege regel
    i = 0
    while i < len(regels) and not regels[i].strip():
        i += 1
    if i >= len(regels):
        return velden, ["Geen tekst gevonden."]
    titel = _kort_titel(regels[i])
    if len(regels[i].strip().strip("*#").strip()) > MAX_TITEL:
        meld.append(f"Titel was langer dan {MAX_TITEL} tekens en is ingekort.")
    velden["titel"] = titel
    rest = regels[i + 1:]

    # geschatte waarde (eigen regel, wordt uit de omschrijving gehaald)
    behoud = []
    for r in rest:
        if re.match(r"\s*(?:\*\*)?\s*geschatte\s+waarde", r, re.I):
            nrs = [_getal(x) for x in _GETAL.findall(r)]
            nrs = [x for x in nrs if x is not None]
            if len(nrs) >= 2:
                velden["waarde_min"], velden["waarde_max"] = _fmt(min(nrs[:2])), _fmt(max(nrs[:2]))
            elif len(nrs) == 1:
                velden["waarde_min"] = velden["waarde_max"] = _fmt(nrs[0])
            continue
        behoud.append(r)
    omschr = "\n".join(behoud).strip("\n")
    omschr = re.sub(r"\n{3,}", "\n\n", omschr).strip()
    velden["omschrijving"] = omschr
    if "waarde_min" not in velden:
        meld.append("Geen 'Geschatte waarde' gevonden.")

    # details-blok
    in_details = False
    for r in behoud:
        if re.match(r"\s*details\s*:?\s*$", r, re.I):
            in_details = True
            continue
        if not in_details:
            continue
        m = _BULLET.match(r)
        if not m:
            if r.strip():
                in_details = False
            continue
        sleutel, _, waarde = m.group(1).partition(":")
        sleutel, waarde = sleutel.strip().lower(), waarde.strip()
        if not waarde:
            continue
        if sleutel in ("merk", "fabrikant", "handelsnaam", "handelsnaam fabrikant", "uitgever"):
            velden.setdefault("merk", waarde)
        elif sleutel in ("materiaal", "materialen"):
            velden.setdefault("materiaal", _kort(waarde))
        elif sleutel in ("kleur", "kleuren"):
            velden.setdefault("kleur", _kort(waarde))
        elif sleutel in ("stijl", "design", "stijlperiode"):
            velden.setdefault("stijl", waarde)
        elif sleutel in ("staat", "conditie", "toestand"):
            c = _conditie(waarde)
            if c:
                velden.setdefault("conditie", c)
        elif sleutel in ("afmeting", "afmetingen", "maat", "maten", "formaat"):
            nrs = [_getal(x) for x in _GETAL.findall(waarde.split("kg")[0])]
            nrs = [x for x in nrs if x is not None]
            if len(nrs) >= 3 and not re.search(r"1\s*:\s*\d", waarde):
                velden.setdefault("lengte", _fmt(nrs[0]))
                velden.setdefault("breedte", _fmt(nrs[1]))
                velden.setdefault("hoogte", _fmt(nrs[2]))
        elif sleutel in ("gewicht",):
            nrs = _GETAL.findall(waarde)
            if nrs:
                g = _getal(nrs[0])
                if g is not None:
                    if re.search(r"\bg\b|gram", waarde) and "kg" not in waarde:
                        g = g / 1000
                    velden.setdefault("gewicht", _fmt(g))
        elif sleutel in ("tijdsperiode", "periode", "leeftijd", "jaar"):
            velden.setdefault("tijdsperiode", waarde)
    return velden, meld
