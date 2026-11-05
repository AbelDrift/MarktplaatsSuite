#!/usr/bin/env bash
# Marktplaats Suite - installatie voor Debian (11+) en Ubuntu (20.04+) en afgeleiden.
# Gebruik:  ./install.sh [--met-ai] [--met-chrome]
#   --met-ai      ook AI-achtergrondverwijdering (transparent-background, rembg, opencv; groot!)
#   --met-chrome  Google Chrome installeren (alleen amd64) voor de Automater
set -euo pipefail

MET_AI=0; MET_CHROME=0
for a in "$@"; do
  case "$a" in
    --met-ai) MET_AI=1 ;;
    --met-chrome) MET_CHROME=1 ;;
    -h|--help) sed -n 2,6p "$0"; exit 0 ;;
    *) echo "Onbekende optie: $a" >&2; exit 1 ;;
  esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/marktplaats-suite"
VENV="$PREFIX/venv"

[ "$(id -u)" -ne 0 ] || { echo "Draai dit als gewone gebruiker, niet als root (sudo wordt zelf gebruikt)."; exit 1; }
command -v apt-get >/dev/null || { echo "apt-get niet gevonden: dit script is voor Debian/Ubuntu."; exit 1; }

. /etc/os-release 2>/dev/null || true
echo "==> Systeem: ${PRETTY_NAME:-onbekend} ($(dpkg --print-architecture))"

echo "==> Systeempakketten (apt)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip python3-gi python3-gi-cairo \
    gir1.2-gtk-3.0 imagemagick xdg-utils desktop-file-utils wget ca-certificates
# Optioneel, mag ontbreken op oudere releases
sudo apt-get install -y webp-pixbuf-loader 2>/dev/null || sudo apt-get install -y webp-pixbuf-loader 2>/dev/null || echo "   (webp-pixbuf-loader niet beschikbaar - overgeslagen)"
sudo apt-get install -y gimp 2>/dev/null || echo "   (gimp overgeslagen - optioneel, voor 'Open in GIMP')"

echo "==> Virtuele omgeving: $VENV"
# --system-site-packages: zodat python3-gi (apt) zichtbaar blijft; werkt met PEP 668 (Debian 12+/Ubuntu 23.04+)
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
if [ "$MET_AI" -eq 1 ]; then
  "$VENV/bin/python" -m pip install "$SRC[ai]"
else
  "$VENV/bin/python" -m pip install "$SRC"
fi

echo "==> Starters"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$PREFIX"
cp "$SRC/marktplaats_suite/assets/icon.png" "$PREFIX/icon.png"
cat > "$HOME/.local/bin/marktplaats-suite" <<LAUNCH
#!/usr/bin/env bash
# X11/XWayland forceren voor betrouwbare vensterherkenning
export GDK_BACKEND="\${GDK_BACKEND:-x11}"
exec "$VENV/bin/python" -m marktplaats_suite "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/marktplaats-suite"

cat > "$HOME/.local/share/applications/marktplaats-suite.desktop" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=Marktplaats Suite
Comment=Producten, foto's, scanner en automater in één venster
Exec=$HOME/.local/bin/marktplaats-suite
Icon=$PREFIX/icon.png
Terminal=false
StartupNotify=true
StartupWMClass=marktplaats_suite
Categories=Utility;Office;
DESK
# oude losse starters uit eerdere versies opruimen
rm -f "$HOME"/.local/share/applications/marktplaats-{productmanager,fotomanager,barcode_scanner,automater_gtk}.desktop
# menu-items van de oude losse installers (andere bestandsnamen) opruimen op basis van de naam
for d in "$HOME"/.local/share/applications/*.desktop "$HOME"/Desktop/*.desktop; do
  [ -f "$d" ] || continue
  if grep -qE '^Name=Marktplaats (Automat|Barcode|Foto|Product)' "$d"; then
    echo "   oude starter verwijderd: $d"; rm -f "$d"
  fi
done
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if [ "$MET_CHROME" -eq 1 ]; then
  ( set +e
  echo "==> Browser voor de Automater"
  if command -v google-chrome >/dev/null || command -v google-chrome-stable >/dev/null; then
    echo "   Chrome is al aanwezig"
  elif [ "$(dpkg --print-architecture)" = "amd64" ]; then
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    wget -q -O "$TMP/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y "$TMP/chrome.deb"
  else
    echo "   Geen Google Chrome voor deze architectuur; probeer Chromium."
    sudo apt-get install -y chromium 2>/dev/null || sudo apt-get install -y chromium-browser
  fi
  # Selenium (4.6+) haalt zelf de passende chromedriver op; Debian-pakket als reserve.
  sudo apt-get install -y chromium-driver 2>/dev/null || true
  ) || echo "   Chrome-installatie mislukt; installeer Chrome of Chromium handmatig."
fi

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Tip: voeg ~/.local/bin toe aan je PATH (log opnieuw in).";; esac
echo "==> Klaar. Start 'Marktplaats Suite' vanuit het menu, of: marktplaats-suite"
echo "    Gegevens staan in: $PREFIX"
