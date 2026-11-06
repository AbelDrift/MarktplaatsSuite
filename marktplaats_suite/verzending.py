"""Verzendadvies voor Marktplaats: welke pakketklasse en vervoerder passen bij een product.

De limieten en prijzen komen uit de Marktplaats-pakketkeuze (stand november 2026) en staan in
`verzendtabel.json` in de datamap. Pas die gerust aan als prijzen of limieten veranderen.
"""
import json
import os

from marktplaats_suite.common import data_dir

# (klasse, vervoerder, variant, max_kg, (l, b, h) in cm, prijs in euro)
STANDAARD_TABEL = [
    ["Brievenbuspakje", "Budbee", "afhaalpunt", 2, [28, 17.5, 6.5], 2.59],
    ["Brievenbuspakje", "DHL", "thuis", 2, [38, 26.5, 3.2], 4.40],
    ["Brievenbuspakje", "PostNL", "thuis", 2, [38, 26.5, 3.2], 4.40],
    ["Klein pakket", "Budbee", "afhaalpunt", 3, [34, 24, 7], 2.89],
    ["Klein pakket", "DHL", "afhaalpunt", 3, [80, 50, 35], 3.99],
    ["Klein pakket", "DHL", "thuis", 3, [80, 50, 35], 6.29],
    ["Klein pakket", "PostNL", "afhaalpunt", 3, [30, 30, 20], 5.39],
    ["Klein pakket", "PostNL", "thuis", 3, [30, 30, 20], 6.39],
    ["Gemiddeld pakket", "Budbee", "afhaalpunt", 10, [50, 34, 18], 3.49],
    ["Gemiddeld pakket", "DHL", "afhaalpunt", 10, [80, 50, 35], 4.29],
    ["Gemiddeld pakket", "DHL", "thuis", 10, [80, 50, 35], 6.59],
    ["Gemiddeld pakket", "PostNL", "afhaalpunt", 10, [40, 40, 30], 5.69],
    ["Gemiddeld pakket", "PostNL", "thuis", 10, [40, 40, 30], 6.69],
    ["Groot pakket", "Budbee", "afhaalpunt", 20, [59.8, 40, 25], 4.99],
    ["Groot pakket", "DHL", "afhaalpunt", 20, [80, 50, 35], 5.99],
    ["Groot pakket", "DHL", "thuis", 20, [80, 50, 35], 7.99],
    ["Groot pakket", "PostNL", "afhaalpunt", 23, [50, 50, 40], 7.49],
    ["Groot pakket", "PostNL", "thuis", 23, [50, 50, 40], 8.49],
]

STANDAARD_INSTELLINGEN = {
    # extra cm per afmeting en extra kg voor verpakkingsmateriaal
    "verpakkingsmarge_cm": 2,
    "verpakkingsgewicht_kg": 0.3,
    # categorieën (deel van de naam, hoofdletterongevoelig) waarvoor Marktplaats alleen Brenger toont
    "brenger_categorieen": ["bijzettafel"],
    "alternatieve_categorieen": ["Krukjes", "Overige meubels"],
    "tabel": STANDAARD_TABEL,
}


def _pad():
    return os.path.join(data_dir(), "verzendtabel.json")


def laad_instellingen():
    data = json.loads(json.dumps(STANDAARD_INSTELLINGEN))
    try:
        with open(_pad(), encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data


def sla_standaard_op_als_nodig():
    """Schrijft de standaardtabel weg, zodat de gebruiker hem kan aanpassen."""
    if not os.path.exists(_pad()):
        with open(_pad(), "w", encoding="utf-8") as f:
            json.dump(STANDAARD_INSTELLINGEN, f, indent=2, ensure_ascii=False)


def _getal(tekst):
    try:
        return float(str(tekst).strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def verzendadvies(lengte, breedte, hoogte, gewicht, instellingen=None):
    """Geeft een lijst passende opties (goedkoopste eerst), of None als afmetingen/gewicht ontbreken.

    Elke optie: {"klasse","vervoerder","variant","prijs","ruimte_over": bool_krap}
    """
    ins = instellingen or laad_instellingen()
    l, b, h, kg = (_getal(x) for x in (lengte, breedte, hoogte, gewicht))
    if None in (l, b, h, kg) or min(l, b, h) <= 0 or kg <= 0:
        return None
    marge = float(ins["verpakkingsmarge_cm"])
    product = sorted((l + marge, b + marge, h + marge), reverse=True)
    kg_totaal = kg + float(ins["verpakkingsgewicht_kg"])
    opties = []
    for klasse, vervoerder, variant, max_kg, afm, prijs in ins["tabel"]:
        limiet = sorted(afm, reverse=True)
        if kg_totaal <= max_kg and all(p <= m for p, m in zip(product, limiet)):
            opties.append({"klasse": klasse, "vervoerder": vervoerder, "variant": variant, "prijs": prijs})
    opties.sort(key=lambda o: o["prijs"])
    return opties


def past_in_pakket(lengte, breedte, hoogte, gewicht, instellingen=None):
    adv = verzendadvies(lengte, breedte, hoogte, gewicht, instellingen)
    return bool(adv)


def advies_tekst(lengte, breedte, hoogte, gewicht, mp_categorie="", instellingen=None):
    """Korte tekst voor in het formulier. Lege string als er niets te melden is."""
    ins = instellingen or laad_instellingen()
    adv = verzendadvies(lengte, breedte, hoogte, gewicht, ins)
    if adv is None:
        return ""
    regels = []
    if adv:
        goedkoopst = adv[0]
        per_klasse = {}
        for o in adv:
            per_klasse.setdefault(o["klasse"], []).append(o)
        kleinste = list(per_klasse)[0]
        prijs = f"{goedkoopst['prijs']:.2f}".replace(".", ",")
        regels.append(
            f"📦 Past in een pakket. Goedkoopst: {goedkoopst['vervoerder']} {goedkoopst['klasse'].lower()} "
            f"({goedkoopst['variant']}) €{prijs}"
        )
        vervoerders = sorted({o["vervoerder"] for o in per_klasse[list(per_klasse)[0]]})
        regels.append(f"   Kleinste klasse die past: {kleinste} bij {', '.join(vervoerders)}")
    else:
        regels.append("🚚 Past niet in een standaardpakket: kies een categorie met Brenger/eigen verzending.")
    cat = (mp_categorie or "").lower()
    if adv and cat and any(k in cat for k in ins["brenger_categorieen"]):
        alt = " of ".join(ins["alternatieve_categorieen"])
        regels.append(f"⚠️ In de categorie '{mp_categorie}' toont Marktplaats alleen Brenger. "
                      f"Dit product past in een pakket: overweeg {alt}.")
    return "\n".join(regels)


def kies_automatisch(lengte, breedte, hoogte, gewicht, instellingen=None):
    """Voor de Automater: {"klasse": ..., "vervoerders": [...]} of None (Brenger/handmatig)."""
    adv = verzendadvies(lengte, breedte, hoogte, gewicht, instellingen)
    if not adv:
        return None
    klasse = adv[0]["klasse"]
    vervoerders = []
    for o in adv:
        if o["klasse"] == klasse and o["vervoerder"] not in vervoerders:
            vervoerders.append(o["vervoerder"])
    return {"klasse": klasse, "vervoerders": vervoerders}
