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
    gir1.2-gtk-3.0 imagemagick xdg-utils desktop-file-utils
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

if [ "$MET_CHROME" -eq 1 ]; then
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

maak_desktop() { # id naam commentaar argument
  cat > "$HOME/.local/share/applications/marktplaats-$1.desktop" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=$2
Comment=$3
Exec=$HOME/.local/bin/marktplaats-suite $4
Icon=$PREFIX/icon.png
Terminal=false
StartupNotify=true
StartupWMClass=marktplaats_$1
Categories=Utility;Office;
DESK
}
maak_desktop suite "Marktplaats Suite" "Alle Marktplaats-tools in één" ""
maak_desktop productmanager "Marktplaats Productmanager" "Producten registreren en beheren" productmanager
maak_desktop fotomanager "Marktplaats Fotomanager" "Foto's verwerken" fotomanager
maak_desktop barcode_scanner "Marktplaats Barcode Scanner" "Barcode scannen" scanner
maak_desktop automater_gtk "Marktplaats Automater" "Advertenties automatisch plaatsen" automater
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Tip: voeg ~/.local/bin toe aan je PATH (log opnieuw in).";; esac
echo "==> Klaar. Start 'Marktplaats Suite' vanuit het menu, of: marktplaats-suite"
echo "    Gegevens staan in: $PREFIX"
