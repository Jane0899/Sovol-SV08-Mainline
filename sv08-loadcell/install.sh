#!/bin/bash
# sv08-loadcell Installer
#
# Voraussetzung: Rappetors Anleitung bis einschließlich Schritt 8 erledigt
# (Mainline-Klipper, Moonraker, Mainsail per KIAUH, MCUs mit Klipper-Firmware).
#
# Ablauf:
#   1. Prüfen (Klipper-Stack, MCUs mit Klipper-Firmware)
#   2. Sichern + wegräumen: alte Configs und Sovol-Reste -> ~/printer_data/backup/sv08-loadcell-<Zeit>/
#   3. Einspielen: Modul (Symlink), Config-Vorlage, sv08-*.cfg (Symlinks), timelapse
#      (dazu: Sovols USB-Automount härten, falls noch im Werkszustand)
#   4. Updater: [update_manager sv08-loadcell] in moonraker.conf
#   5. Klipper + Moonraker neu starten
#
# Erneuter Aufruf auf einem schon umgestellten Drucker: printer.cfg bleibt,
# es werden nur Symlinks, timelapse und Updater-Eintrag geprüft.
#
# Optionen: -y  keine Rückfragen (Seriennummern müssen dann eindeutig sein)
# Umgebung: SV08_NO_RESTART=1  Dienste nicht neu starten (Tests)

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
[ "${1:-}" = "-y" ] && ASSUME_YES=1

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFEHLER:\033[0m %s\n' "$*" >&2; exit 1; }
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
[ -d "$KLIPPER_DIR/.git" ] || die "~/klipper fehlt. Erst Rappetors Anleitung Schritt 4 (KIAUH) erledigen."
origin="$(git -C "$KLIPPER_DIR" remote get-url origin 2>/dev/null || true)"
[[ "$origin" == *Klipper3d/klipper* ]] || warn "~/klipper kommt nicht von Klipper3d/klipper ($origin) - Mainline erwartet."
[ -d "$HOME/moonraker" ] || die "~/moonraker fehlt. Erst Rappetors Anleitung Schritt 4 (KIAUH) erledigen."
[ -e "$CFG_DIR/moonraker.conf" ] || die "$CFG_DIR/moonraker.conf fehlt."
[ -e "$CFG_DIR/mainsail.cfg" ] || die "$CFG_DIR/mainsail.cfg fehlt (Mainsail per KIAUH installieren)."
systemctl list-unit-files klipper.service >/dev/null 2>&1 || die "Dienst klipper.service fehlt."

mapfile -t DEVS < <(ls /dev/serial/by-id/usb-Klipper_* 2>/dev/null || true)
[ "${#DEVS[@]}" -ge 2 ] || die "Weniger als zwei MCUs mit Klipper-Firmware gefunden (/dev/serial/by-id/usb-Klipper_*). Erst Rappetors Anleitung Schritte 6-8 erledigen."

UPDATE_MODE=0
if [ -f "$CFG_DIR/printer.cfg" ] && grep -q '^\[include sv08-loadcell.cfg\]' "$CFG_DIR/printer.cfg"; then
    UPDATE_MODE=1
    say "Drucker ist schon umgestellt - printer.cfg bleibt unverändert."
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
        echo "Welche ist das MAINBOARD ([mcu], in Rappetors Schritt 8 HOSTSERIAL)?"
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
if [ -f "$AUTOMOUNT" ] && grep -qE 'test\.sh|dpkg|nmcli' "$AUTOMOUNT"; then
    say "Härte Sovols USB-Automount (test.sh, WLAN, .deb-Installation entfernt)"
    mkdir -p "$BACKUP_DIR/usr/bin"
    cp "$AUTOMOUNT" "$BACKUP_DIR/usr/bin/makerbase-automount"
    tmp="$(mktemp)"
    sed -e "s#__UID__#$(id -u)#; s#__GID__#$(id -g)#; s#__HOME__#$HOME#g" \
        "$LC_DIR/system/makerbase-automount" > "$tmp"
    sudo install -m 0755 -o root -g root "$tmp" "$AUTOMOUNT"
    rm -f "$tmp"
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
    echo "   alte Fassung gesichert: $BACKUP_DIR/usr/bin/makerbase-automount"
fi

# ---------------------------------------------------------------- 3. Einspielen
say "Klipper-Modul einbinden"
ln -sfn "$LC_DIR/klippy/sv08_loadcell.py" "$EXTRAS_DIR/sv08_loadcell.py"
# Klipper-Repo sauber halten (Moonraker meldet es sonst als "dirty")
excl="$KLIPPER_DIR/.git/info/exclude"
grep -qx 'klippy/extras/sv08_loadcell.py' "$excl" 2>/dev/null || echo 'klippy/extras/sv08_loadcell.py' >> "$excl"

say "Config-Dateien einbinden"
for f in sv08-macros.cfg sv08-loadcell.cfg sv08-menu.cfg; do
    ln -sfn "$LC_DIR/config/$f" "$CFG_DIR/$f"
done
if [ $UPDATE_MODE = 0 ]; then
    $TOOL fill-template "$LC_DIR/config/printer.cfg" "$CFG_DIR/printer.cfg" "$MCU" "$EXTRA"
    echo "   printer.cfg aus Vorlage erstellt"
fi
[ -e "$CFG_DIR/saved_variables.cfg" ] || printf '[Variables]\n' > "$CFG_DIR/saved_variables.cfg"

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

# ---------------------------------------------------------------- 4. Updater
say "Updater eintragen"
branch="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)"
origin_repo="$(git -C "$REPO_DIR" remote get-url origin)"
$TOOL moonraker-add "$CFG_DIR/moonraker.conf" "${REPO_DIR/#$HOME/~}" "$origin_repo" "$branch" | sed 's/^/   /'

# ---------------------------------------------------------------- 5. Neustart
if [ "${SV08_NO_RESTART:-0}" = 1 ]; then
    warn "SV08_NO_RESTART=1 - Dienste nicht neu gestartet"
else
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
