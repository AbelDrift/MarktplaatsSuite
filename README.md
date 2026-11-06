# SellYourShit

<p align="center"><img src="marktplaats_suite/assets/icon.png" width="160" alt="SellYourShit logo"></p>

**SellYourShit** is één app met alle Marktplaats-tools van HerNieuw, voor **Debian en Ubuntu** (en afgeleiden):

Alles in **één venster** met tabs:

| Tab | Was | Doel |
|---|---|---|
| 📝 Nieuw Product / 📊 Product Management / 📈 Sales Dashboard | MarktplaatsProductmanager | Producten registreren, labels/barcodes, verkocht/retour/gereserveerd, statistieken |
| 📷 Product Studio | MarktplaatsFotoManager | Foto's verwerken (achtergrond, watermerk, logo, mappenstructuur) |
| 🔍 Product Scanner | MarktplaatsScanner | USB-barcodescanner met productinfo en foto |
| 🤖 Product Uploader | MarktplaatsAutomater | Advertenties automatisch plaatsen, nu alleen voor Marktplaats (Selenium + Chrome/Chromium) |

Start met `sellyourshit` (of `marktplaats-suite`) of via het applicatiemenu.

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

- **Product Studio** pakt zip-bestanden in de bronmap zelf uit: alle foto's uit elke zip doen mee, zonder dat je iets handmatig uitpakt.

## Whoppah en Vinted (userscripts)

De Product Uploader plaatst op **Marktplaats** (foto's, omschrijving, verzending). Whoppah en Vinted weigeren een
door de Uploader bestuurde browser (veiligheidscontrole), daarom vul je die in je **eigen, ingelogde Firefox** in met
twee userscripts. Foto's voeg je zelf toe, het definitief plaatsen doe je ook zelf.

1. Installeer de Firefox-extensie Violentmonkey of Tampermonkey.
2. Start de Suite en klik in de Product Uploader op **🧩 Userscripts**. Open de links
   (`http://127.0.0.1:8765/whoppah.user.js` en `http://127.0.0.1:8765/vinted.user.js`) in Firefox en bevestig de installatie.
3. Open Whoppah ("Advertentie plaatsen") of `vinted.nl/items/new`, voeg de foto's toe en kies rechtsonder in het paneel je product.
   Lukt ophalen niet, gebruik dan "Kopieer producten (JSON)" in de Suite en plak dat in het paneel.

**Whoppah:** details controleren/overschrijven (merk, titel, stijl, kleur, materiaal, staat), maten, prijs (Marktplaatsprijs x 1,25,
ondergrens x 0,85, Smart Drop 5% elke twee weken) en verzending (Pakket tot 100x50x50 cm, anders Koerier).
Prijsregels aanpassen kan in `automater_config.json` onder `"whoppah"`.

**Vinted:** titel, beschrijving, categorie (uit "Vinted-categorie", anders de suggestie van Vinted), merk (anders "Geen merk"),
staat, kleur (max. 2), materiaal, prijs (= 'Min. waarde', anders 85% van de vraagprijs) en pakketformaat Klein/Middel/Groot.
Verkoop je namens een winkel of kringloop, gebruik dan een Vinted Pro-account.

De brug in de Suite luistert alleen op 127.0.0.1 en accepteert alleen verzoeken met een lokale hostnaam.

## Gemini-tekst plakken

Op *Nieuw Product* staat de knop **📋 Plak Gemini-tekst**. Plak het antwoord van Gemini; de app vult
titel (max. 60 tekens), omschrijving (inclusief 'Details:'), merk, materiaal, kleur, stijl,
afmetingen (bij 'Afmeting: L x B x H'), staat en geschatte waarde (min/max) in. Alleen velden die in
de tekst staan worden overschreven.
