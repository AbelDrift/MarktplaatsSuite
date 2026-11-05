#!/usr/bin/env bash
# Verwijdert programma en starters. Je gegevens (producten.xml e.d.) blijven staan tenzij je --alles geeft.
set -e
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/marktplaats-suite"
rm -rf "$PREFIX/venv" "$PREFIX/icon.png" "$HOME/.local/bin/marktplaats-suite" "$HOME"/.local/share/applications/marktplaats-*.desktop
[ "${1:-}" = "--alles" ] && rm -rf "$PREFIX"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Verwijderd."
