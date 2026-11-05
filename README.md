# Marktplaats Suite

<p align="center"><img src="marktplaats_suite/assets/icon.png" width="160" alt="Marktplaats Suite logo"></p>

Eén app met alle Marktplaats-tools van HerNieuw, voor **Debian en Ubuntu** (en afgeleiden):

Alles in **één venster** met tabs:

| Tab | Was | Doel |
|---|---|---|
| 📝 Nieuw Product / 📊 Product Management / 📈 Sales Dashboard | MarktplaatsProductmanager | Producten registreren, labels/barcodes, verkocht/retour/gereserveerd, statistieken |
| 📷 Product Studio | MarktplaatsFotoManager | Foto's verwerken (achtergrond, watermerk, logo, mappenstructuur) |
| 🔍 Product Scanner | MarktplaatsScanner | USB-barcodescanner met productinfo en foto |
| 🤖 Product Uploader | MarktplaatsAutomater | Advertenties automatisch plaatsen, nu alleen voor Marktplaats (Selenium + Chrome/Chromium) |

Start met `marktplaats-suite` of via het applicatiemenu.

**Centrale instellingen** (⚙️ rechtsboven): het XML-bestand wordt maar op één plek ingesteld en geldt voor alle tabs.
Algemene voorwaarden bewerk je in een eigen tekstvak met vet/schuin (knoppen of Ctrl+B / Ctrl+I), met import
uit .docx/.txt, een voorbeeld zoals het op Marktplaats verschijnt, en een vinkje om voorwaarden wel of niet
onder advertenties te plaatsen.

## Installeren

```bash
git clone <deze-repo>
cd marktplaats-suite
./install.sh                 # basis
./install.sh --met-chrome    # + Google Chrome (amd64) voor de Automater
./install.sh --met-ai        # + AI-achtergrondverwijdering (groot: torch/onnx)
```

Wat het doet: apt-pakketten (`python3-gi`, `gir1.2-gtk-3.0`, `imagemagick`, …), een eigen
virtuele omgeving in `~/.local/share/marktplaats-suite/venv` (met `--system-site-packages`,
dus geen conflict met PEP 668), starters in `~/.local/bin` en het applicatiemenu.
Verwijderen: `./uninstall.sh` (`--alles` wist ook je gegevens).

## Gegevens

Alles (producten.xml, `suite_config.json` met XML-pad en voorwaarden, instellingen, input/output van de fotomanager, thumbnail-cache) staat in
`~/.local/share/marktplaats-suite/`, of in `$MARKTPLAATS_DATA_DIR`. Bestaande bestanden uit de
losse apps (`producten.xml`, `productmanager_config.json`, `scanner_config.json`) kopieer je
naar die map; de fotomanager-instellingen heten nu `fotomanager_config.json`
(was `~/.marktplaats_manager_config.json`).

## Verschillen met Ubuntu-only installers

- Geen `chromium-chromedriver` (Ubuntu-snap): Selenium haalt zelf de passende driver op; `chromium-driver` (Debian) wordt als reserve geprobeerd.
- Geen `apt-key` (verwijderd in recente Debian): Chrome via het officiële `.deb`.
- Geen `pip --user` / `--break-system-packages`: alles in een venv.

## Bekende beperkingen

- GTK3 onder X11/XWayland (starters zetten `GDK_BACKEND=x11`).
- De thumbnail-fallback in de scanner leest Marktplaats-pagina's uit en kan breken als de site verandert.
- Getest op syntax en installeerbaarheid; de GUI zelf moet op een echt Debian/Ubuntu-bureaublad worden uitgeprobeerd.

## Verzendadvies en slimme Automater

- In **Registreren** verschijnt onder afmetingen/gewicht een live **verzendadvies**: welke pakketklasse en
  vervoerder passen (inclusief 2 cm / 0,3 kg verpakkingsmarge) en wat het kost. Limieten en prijzen staan in
  `verzendtabel.json` in de datamap en zijn aanpasbaar.
- Het veld **Marktplaats-categorie** bepaalt welke suggestie de Automater kiest (anders de eerste). Je krijgt
  een waarschuwing als de gekozen categorie alleen Brenger toont terwijl het product in een pakket past.
- De **Automater** vinkt passende vervoerders aan en kiest de pakketgrootte (uit te zetten in zijn voorkeuren).
  Dit is experimenteel: controleer de advertentie altijd voor je op "Plaats advertentie" klikt.
- Alle onderdelen delen één kolomlijst voor `producten.xml`; de Scanner past bij "verkocht" alleen dat ene
  product aan en wist geen velden van andere onderdelen meer.
