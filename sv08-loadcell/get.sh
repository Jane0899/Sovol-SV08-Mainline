#!/bin/bash
# sv08-loadcell: Einstieg per Einzeiler
#
#   curl -fsSL https://raw.githubusercontent.com/Jane0899/Sovol-SV08-Mainline/main/sv08-loadcell/get.sh | bash
#
# Klont das Repo nach ~/Sovol-SV08-Mainline (oder aktualisiert es) und startet
# sv08-loadcell/install.sh. Optionen für install.sh: ... | bash -s -- -y
# Umgebung: SV08_BRANCH=<branch>  anderen Branch als main installieren (Tests)

set -euo pipefail

REPO_URL="https://github.com/Jane0899/Sovol-SV08-Mainline.git"
BRANCH="${SV08_BRANCH:-main}"
DIR="$HOME/Sovol-SV08-Mainline"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mFEHLER:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" != 0 ] || die "Nicht als root ausführen, sondern als normaler Benutzer (z.B. biqu/sovol)."
command -v git >/dev/null || die "git fehlt (sudo apt install git)."

if [ -d "$DIR/.git" ]; then
    origin="$(git -C "$DIR" remote get-url origin 2>/dev/null || true)"
    if [ "$origin" = "$REPO_URL" ]; then
        say "Aktualisiere $DIR ($BRANCH)"
        git -C "$DIR" fetch origin
        git -C "$DIR" checkout -q "$BRANCH"
        git -C "$DIR" merge -q --ff-only "origin/$BRANCH"
    else
        # z.B. ein Klon von Rappetors Original-Repo aus der Anleitung
        old="$DIR.old-$(date +%Y%m%d-%H%M%S)"
        say "$DIR ist ein anderer Klon ($origin) - verschoben nach $old"
        mv "$DIR" "$old"
    fi
elif [ -e "$DIR" ]; then
    die "$DIR existiert, ist aber kein Git-Repo. Bitte umbenennen und neu starten."
fi
if [ ! -d "$DIR/.git" ]; then
    say "Klone $REPO_URL ($BRANCH)"
    git clone -b "$BRANCH" "$REPO_URL" "$DIR"
fi

# Bei "curl | bash" ist stdin das Skript selbst - Rückfragen vom Terminal lesen
if [ -t 0 ]; then
    exec "$DIR/sv08-loadcell/install.sh" "$@"
elif { : < /dev/tty; } 2>/dev/null; then
    exec "$DIR/sv08-loadcell/install.sh" "$@" < /dev/tty
else
    exec "$DIR/sv08-loadcell/install.sh" -y "$@"
fi
