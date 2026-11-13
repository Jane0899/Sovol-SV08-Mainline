#!/bin/bash
# sv08-loadcell Installer
#
# Voraussetzung: README im Hauptordner bis einschließlich Schritt 7 erledigt
# (Mainline-Klipper, Moonraker, Mainsail per KIAUH, MCUs mit Klipper-Firmware).
#
# Ablauf:
#   1. Prüfen (Klipper-Stack, MCUs mit Klipper-Firmware)
#   2. Sichern + wegräumen: alte Configs und Sovol-Reste -> ~/printer_data/backup/sv08-loadcell-<Zeit>/
#   3. Einspielen: Modul (Symlink), Config-Vorlage, sv08-*.cfg (Symlinks), timelapse, numpy
#      (dazu: Sovols USB-Automount härten, falls noch im Werkszustand)
#   4. Updater: [update_manager sv08-loadcell] in moonraker.conf
#   5. Klipper + Moonraker neu starten
#
# Erneuter Aufruf auf einem schon umgestellten Drucker: printer.cfg bleibt,
# es werden nur Symlinks, timelapse und Updater-Eintrag geprüft.
#
# Optionen: -y         keine Rückfragen (Seriennummern müssen dann eindeutig sein)
#           --upgrade  nur Config-Upgrade eines schon umgestellten Druckers, ohne
#                      Rückfragen. So ruft es UPGRADE_CONFIG im Klipper-Terminal auf.
#                      Schritte mit sudo werden übersprungen, wenn sudo ein
#                      Passwort will (dann einmal per SSH aufrufen)
# Umgebung: SV08_NO_RESTART=1  Dienste nicht neu starten (Tests, UPGRADE_CONFIG)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
LC_DIR="$REPO_DIR/sv08-loadcell"
CFG_DIR="$HOME/printer_data/config"
KLIPPER_DIR="$HOME/klipper"
EXTRAS_DIR="$KLIPPER_DIR/klippy/extras"
TOOL="python3 $LC_DIR/scripts/cfgtool.py"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$HOME/printer_data/backup/sv08-loadcell-$STAMP"
ASSUME_YES=0
UPGRADE=0
for arg in "$@"; do
    case "$arg" in
        -y) ASSUME_YES=1 ;;
        --upgrade) UPGRADE=1; ASSUME_YES=1 ;;
        *) printf 'Unbekannte Option: %s\n' "$arg" >&2; exit 1 ;;
    esac
done

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFEHLER:\033[0m %s\n' "$*" >&2; exit 1; }
SUDO_SKIPPED=0
can_sudo() {
    # can_sudo "Was" -> 0, wenn sudo geht. Beim Upgrade (ohne Terminal) kann
    # niemand ein Passwort eingeben: Schritt dann überspringen
    [ $UPGRADE = 0 ] && return 0
    sudo -n true 2>/dev/null && return 0
    warn "übersprungen (sudo braucht ein Passwort): $1"
    SUDO_SKIPPED=1
    return 1
}
ask()  {
    # ask "Frage" -> 0 bei ja
    [ $ASSUME_YES = 1 ] && return 0
    local a; read -r -p "$1 [j/N] " a; [[ "$a" =~ ^[jJyY] ]]
}
backup() {
    # backup <Pfad> - verschiebt Datei/Ordner ins Backup (Struktur relativ zu $HOME)
    local src="$1" rel dst
    [ -e "$src" ] || [ -L "$src" ] || return 0
    rel="${src#$HOME/}"
    dst="$BACKUP_DIR/$rel"
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    echo "   gesichert + entfernt: ~/$rel"
}

# ---------------------------------------------------------------- 1. Prüfen
say "Prüfe Voraussetzungen"
[ "$(id -u)" != 0 ] || die "Nicht als root ausführen, sondern als normaler Benutzer (z.B. biqu/sovol)."
[ -d "$KLIPPER_DIR/.git" ] || die "~/klipper fehlt. Erst Schritt 4 der Anleitung (KIAUH) erledigen."
origin="$(git -C "$KLIPPER_DIR" remote get-url origin 2>/dev/null || true)"
[[ "$origin" == *Klipper3d/klipper* ]] || warn "~/klipper kommt nicht von Klipper3d/klipper ($origin) - Mainline erwartet."
[ -d "$HOME/moonraker" ] || die "~/moonraker fehlt. Erst Schritt 4 der Anleitung (KIAUH) erledigen."
[ -e "$CFG_DIR/moonraker.conf" ] || die "$CFG_DIR/moonraker.conf fehlt."
[ -e "$CFG_DIR/mainsail.cfg" ] || die "$CFG_DIR/mainsail.cfg fehlt (Mainsail per KIAUH installieren)."
systemctl list-unit-files klipper.service >/dev/null 2>&1 || die "Dienst klipper.service fehlt."

mapfile -t DEVS < <(ls /dev/serial/by-id/usb-Klipper_* 2>/dev/null || true)
[ "${#DEVS[@]}" -ge 2 ] || die "Weniger als zwei MCUs mit Klipper-Firmware gefunden (/dev/serial/by-id/usb-Klipper_*). Erst Schritte 5-7 der Anleitung erledigen."

UPDATE_MODE=0
if [ -f "$CFG_DIR/printer.cfg" ] && grep -q '^\[include sv08-loadcell.cfg\]' "$CFG_DIR/printer.cfg"; then
    UPDATE_MODE=1
    say "Drucker ist schon umgestellt - printer.cfg bleibt unverändert."
fi
[ $UPGRADE = 0 ] || [ $UPDATE_MODE = 1 ] || die "--upgrade geht nur auf einem schon umgestellten Drucker - install.sh ohne --upgrade starten."

# sudo ohne Passwort: UPGRADE_CONFIG läuft ohne Terminal und braucht sudo für
# Systemdateien. Auf einem Drucker egal, viele Images (auch Sovols) machen
# das ohnehin. Eigene Datei, damit es auf allen Druckern gleich ist
SUDOERS="/etc/sudoers.d/90-sv08-$(id -un)-nopasswd"
sudo_rule="$(id -un) ALL=(ALL) NOPASSWD: ALL"
if [ "$(sudo -n cat "$SUDOERS" 2>/dev/null)" != "$sudo_rule" ] && can_sudo "sudo ohne Passwort einrichten"; then
    say "Richte sudo ohne Passwort ein (für UPGRADE_CONFIG)"
    tmp="$(mktemp)"
    echo "$sudo_rule" > "$tmp"
    if sudo visudo -c -q -f "$tmp"; then
        sudo install -m 0440 -o root -g root "$tmp" "$SUDOERS"
        echo "   $SUDOERS"
    else
        warn "sudoers-Regel ungültig - nicht eingerichtet"
    fi
    rm -f "$tmp"
fi
# Sovols Werks-Image hat dieselbe Regel für die Gruppe über 200-mal am Ende
# von /etc/sudoers. Entfernen, sobald die eigene Datei greift
factory_rule="%$(id -gn) ALL=(ALL) NOPASSWD: ALL"
if [ "$(sudo -n cat "$SUDOERS" 2>/dev/null)" = "$sudo_rule" ] &&
        sudo -n grep -qxF "$factory_rule" /etc/sudoers 2>/dev/null; then
    say "Entferne Sovols sudo-Werkszeilen aus /etc/sudoers (ersetzt durch $SUDOERS)"
    tmp="$(mktemp)"; orig="$(mktemp)"
    sudo cat /etc/sudoers > "$orig"
    grep -vxF "$factory_rule" "$orig" > "$tmp"
    if sudo visudo -c -q -f "$tmp"; then
        sudo install -m 0440 -o root -g root "$tmp" /etc/sudoers
        # Gegenprobe ohne zwischengespeichertes Passwort; sonst zurück
        sudo -k
        if ! sudo -n true 2>/dev/null; then
            warn "sudo ohne Passwort geht danach nicht - /etc/sudoers zurückgesetzt (Passwort nötig)"
            sudo install -m 0440 -o root -g root "$orig" /etc/sudoers
        fi
    else
        warn "bereinigte /etc/sudoers ungültig - unverändert gelassen"
    fi
    rm -f "$tmp" "$orig"
fi

# MCU-Seriennummern (nur Neuinstallation)
MCU=""; EXTRA=""
if [ $UPDATE_MODE = 0 ]; then
    if [ -f "$CFG_DIR/printer.cfg" ]; then
        while IFS='=' read -r k v; do
            [ "$k" = mcu ] && MCU="$v"
            [ "$k" = extra_mcu ] && EXTRA="$v"
        done < <($TOOL serials "$CFG_DIR/printer.cfg")
    fi
    [ -n "$MCU" ] && [ -e "$MCU" ] || MCU=""
    [ -n "$EXTRA" ] && [ -e "$EXTRA" ] || EXTRA=""
    if [ -z "$MCU" ] || [ -z "$EXTRA" ]; then
        [ $ASSUME_YES = 0 ] || die "Seriennummern nicht eindeutig aus printer.cfg lesbar - ohne -y starten."
        echo "Gefundene MCUs:"
        for i in "${!DEVS[@]}"; do echo "  $((i+1))) ${DEVS[$i]}"; done
        echo "Welche ist das MAINBOARD ([mcu], in Schritt 7 der Anleitung HOSTSERIAL)?"
        read -r -p "Nummer: " n; MCU="${DEVS[$((n-1))]:-}"
        echo "Welche ist der DRUCKKOPF ([mcu extra_mcu], TOOLHEADSERIAL)?"
        read -r -p "Nummer: " n; EXTRA="${DEVS[$((n-1))]:-}"
        [ -n "$MCU" ] && [ -n "$EXTRA" ] && [ "$MCU" != "$EXTRA" ] || die "Ungültige Auswahl."
    fi
    say "Mainboard:  $MCU"
    say "Druckkopf:  $EXTRA"
    echo
    echo "Alte Configs und Sovol-Reste werden nach $BACKUP_DIR verschoben,"
    echo "dann wird die sv08-loadcell-Vorlage eingespielt."
    ask "Fortfahren?" || die "Abgebrochen."
fi

# ---------------------------------------------------- 2. Sichern + wegräumen
if [ $UPDATE_MODE = 0 ]; then
    say "Sichere und entferne alte Configs und Sovol-Reste"
    mkdir -p "$BACKUP_DIR"
    # Kompletter Config-Ordner zusätzlich als Archiv
    tar -czf "$BACKUP_DIR/config-komplett.tar.gz" -C "$HOME/printer_data" config
    # Config-Ordner aufräumen: alles außer Moonraker-/UI-/Plugin-Dateien
    shopt -s nullglob dotglob
    for f in "$CFG_DIR"/*; do
        b="$(basename "$f")"
        case "$b" in
            moonraker.conf|.moonraker.conf.bkp|mainsail.cfg|crowsnest.conf|KlipperScreen.conf|\
            saved_variables.cfg|timelapse.cfg|moonraker-obico*.cfg|moonraker_obico_macros.cfg|\
            sonar.conf|.theme|.*.swp) ;;
            *) backup "$f" ;;
        esac
    done
    shopt -u nullglob dotglob
    # Sovols Klipper-Extras (von Rappetors Schritt 5) - ersetzt durch sv08_loadcell
    for f in probe_pressure.py z_offset_calibration.py; do backup "$EXTRAS_DIR/$f"; done
    # Sovol-Reste im Home-Verzeichnis (Werks-Image)
    for f in patch patch.base patch.sh plr.sh plr-old.sh clear_plr.sh sovol_plr_height \
             get_ip.sh send_ip.py factory_resets.sh restart_firmware.py ttyS3.py usbmount; do
        backup "$HOME/$f"
    done
fi

# Sovols USB-Automount (Werks-Image) führt beim Einstecken eines Sticks als root
# test.sh aus, verbindet WLAN aus wifi.cfg und installiert .deb-Pakete -> härten
AUTOMOUNT=/usr/bin/makerbase-automount
tmp="$(mktemp)"
sed -e "s#__UID__#$(id -u)#; s#__GID__#$(id -g)#; s#__HOME__#$HOME#g" \
    "$LC_DIR/system/makerbase-automount" > "$tmp"
# auch ältere/abweichende Fassungen ersetzen, damit alle Drucker dasselbe Skript haben
if [ -f "$AUTOMOUNT" ] && ! cmp -s "$tmp" "$AUTOMOUNT" && can_sudo "USB-Automount härten"; then
    say "Härte Sovols USB-Automount (test.sh, WLAN, .deb-Installation entfernt)"
    mkdir -p "$BACKUP_DIR/usr/bin"
    cp "$AUTOMOUNT" "$BACKUP_DIR/usr/bin/makerbase-automount"
    sudo install -m 0755 -o root -g root "$tmp" "$AUTOMOUNT"
    echo "   alte Fassung gesichert: $BACKUP_DIR/usr/bin/makerbase-automount"
fi
rm -f "$tmp"
if [ -f "$AUTOMOUNT" ] && [ ! -f /etc/default/sv08-usbmount ] && can_sudo "USB-Modus festlegen"; then
    usb_mode=move
    if [ $ASSUME_YES = 0 ]; then
        echo "Was soll mit G-Code-Dateien auf einem eingesteckten USB-Stick passieren?"
        echo "  1) auf den Drucker verschieben, Stick wird geleert (Standard)"
        echo "  2) auf den Drucker kopieren, Stick bleibt unverändert"
        echo "  3) nur einbinden: Dateien unter USB/ in der Dateiliste, solange der Stick steckt"
        read -r -p "Auswahl [1]: " n
        case "$n" in 2) usb_mode=copy ;; 3) usb_mode=mount ;; esac
    fi
    printf '# move | copy | mount, siehe /usr/bin/makerbase-automount\nUSB_MODE=%s\n' "$usb_mode" |
        sudo tee /etc/default/sv08-usbmount >/dev/null
    echo "   USB-Modus: $usb_mode (änderbar in /etc/default/sv08-usbmount)"
fi

# ---------------------------------------------------------------- 3. Einspielen
say "Klipper-Module einbinden"
# Alle Module (sv08_loadcell legt fehlende nach einem Update auch selbst an)
excl="$KLIPPER_DIR/.git/info/exclude"
for f in "$LC_DIR"/klippy/*.py; do
    b="$(basename "$f")"
    ln -sfn "$f" "$EXTRAS_DIR/$b"
    # Klipper-Repo sauber halten (Moonraker meldet es sonst als "dirty")
    grep -qx "klippy/extras/$b" "$excl" 2>/dev/null || echo "klippy/extras/$b" >> "$excl"
done

say "Config-Dateien einbinden"
for f in sv08-macros.cfg sv08-loadcell.cfg sv08-menu.cfg; do
    ln -sfn "$LC_DIR/config/$f" "$CFG_DIR/$f"
done
if [ $UPDATE_MODE = 0 ]; then
    $TOOL fill-template "$LC_DIR/config/printer.cfg" "$CFG_DIR/printer.cfg" "$MCU" "$EXTRA"
    echo "   printer.cfg aus Vorlage erstellt"
fi
[ -e "$CFG_DIR/saved_variables.cfg" ] || printf '[Variables]\n' > "$CFG_DIR/saved_variables.cfg"
# Filamentsensor: Meldungen bei Runout/Einlegen (auch für bestehende printer.cfg)
echo "   Filamentsensor: $($TOOL sensor-hooks "$CFG_DIR/printer.cfg")"

say "Timelapse prüfen"
if [ ! -d "$HOME/moonraker-timelapse" ]; then
    git clone https://github.com/mainsail-crew/moonraker-timelapse.git "$HOME/moonraker-timelapse"
    make -C "$HOME/moonraker-timelapse" install
fi
if [ ! -s "$CFG_DIR/timelapse.cfg" ]; then
    # leere Datei (kommt vor) -> Makros fehlen, Moonraker meldet Unknown command
    rm -f "$CFG_DIR/timelapse.cfg"
    ln -sfn "$HOME/moonraker-timelapse/klipper_macro/timelapse.cfg" "$CFG_DIR/timelapse.cfg"
fi
# Ohne [timelapse] lädt Moonraker die Komponente nicht
$TOOL moonraker-timelapse "$CFG_DIR/moonraker.conf" | sed 's/^/   /'

say "Numpy für Input Shaper prüfen"
if "$HOME/klippy-env/bin/python" -c "import numpy" 2>/dev/null; then
    echo "   vorhanden"
elif can_sudo "numpy installieren"; then
    sudo apt-get install -y python3-numpy python3-matplotlib libatlas-base-dev libopenblas-dev
    "$HOME/klippy-env/bin/pip" install numpy
fi

# ---------------------------------------------------------------- 4. Updater
say "Updater eintragen"
branch="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)"
origin_repo="$(git -C "$REPO_DIR" remote get-url origin)"
$TOOL moonraker-add "$CFG_DIR/moonraker.conf" "${REPO_DIR/#$HOME/~}" "$origin_repo" "$branch" | sed 's/^/   /'

# Stand der Config merken: Klipper fordert UPGRADE_CONFIG an, solange er
# unter sv08-loadcell/config-version liegt. Nicht, wenn sudo-Schritte fehlen
if [ $SUDO_SKIPPED = 0 ]; then
    cp "$LC_DIR/config-version" "$HOME/printer_data/.sv08-loadcell-version"
    echo "   Config-Stand: $(cat "$LC_DIR/config-version")"
else
    warn "Nicht alles erledigt - einmal per SSH aufrufen: $LC_DIR/install.sh --upgrade"
fi

# ---------------------------------------------------------------- 5. Neustart
if [ "${SV08_NO_RESTART:-0}" = 1 ]; then
    # UPGRADE_CONFIG startet danach selbst über Moonraker neu
    [ $UPGRADE = 1 ] || warn "SV08_NO_RESTART=1 - Dienste nicht neu gestartet"
elif can_sudo "Moonraker und Klipper neu starten"; then
    say "Starte Moonraker und Klipper neu"
    sudo systemctl restart moonraker
    sudo systemctl restart klipper
fi

echo
say "Fertig."
if [ $UPDATE_MODE = 0 ]; then
    echo "   Backup: $BACKUP_DIR"
    echo "   Nächster Schritt: in Mainsail die Konsole öffnen und CALIBRATE_SV08 ausführen."
    echo "   Der Assistent führt durch Sensor-Check, Messungen und Papiertest."
fi
