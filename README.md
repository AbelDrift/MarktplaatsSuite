# Marktplaats Suite

Eén app met alle Marktplaats-tools van HerNieuw, voor **Debian en Ubuntu** (en afgeleiden):

| Module | Was | Doel |
|---|---|---|
| `productmanager` | MarktplaatsProductmanager | Producten registreren, labels/barcodes, verkocht/retour/gereserveerd, dashboard |
| `fotomanager` | MarktplaatsFotoManager | Foto's verwerken (achtergrond, watermerk, logo, mappenstructuur) |
| `scanner` | MarktplaatsScanner | USB-barcodescanner met productinfo en foto |
| `automater` | MarktplaatsAutomater | Advertenties automatisch plaatsen (Selenium + Chrome/Chromium) |

Start `marktplaats-suite` voor het startscherm, of direct een module: `marktplaats-suite scanner`.

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

Alles (producten.xml, instellingen, input/output van de fotomanager, thumbnail-cache) staat in
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
