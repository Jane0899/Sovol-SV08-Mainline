# sv08-loadcell – Wägezellen-Homing und Auto-Z-Offset für den Sovol SV08 (Mainline-Klipper)

Erweiterung zu dieser Anleitung für SV08 mit **Original-Hardware**: induktive Probe und Sovols Wägezelle hinten rechts („probe_pressure“, PE12). Umgebaute Drucker (Eddy, andere Probe …) werden nicht unterstützt.

## Was es macht

- **Z-Homing auf der Wägezelle (`LOADCELL_HOME`)**: Die induktive Probe fährt mit 30 mm/s schnell über die Wägezelle, danach setzt die Düse mit 0,1 mm/s auf. Wiederholgenauigkeit ca. **0,006 mm**.
- **Automatischer Z-Offset vor jedem Druck (`AUTO_Z_OFFSET`)**: Die Düse auf der Wägezelle ist die Z-Referenz. Die induktive Probe misst über der Zelle und am Bett direkt davor. Daraus ergibt sich der Offset. Gemessen wird bei Drucktemperatur, weil sich die Düse ausdehnt.
- **Kalibrierungs-Assistent (`CALIBRATE_SV08`)**: Dialoge in Mainsail führen durch Sensor-Check, automatische Messreihen, Z-Nullpunkt, Papiertest und Input Shaper. Die Ergebnisse landen per `SAVE_CONFIG` in der `printer.cfg`.
- **Erprobte Config** vom Referenzgerät, dazu Makros: Motoren bleiben nach dem Druck an und gehen nach 10 min Leerlauf aus. Homing und QGL laufen nur, wenn nötig. Außerdem `M600`, Abluftlüfter (`M106 P3`) und getrennte Bauteillüfter.
- **Updates über Mainsail** (Moonraker Update-Manager). Der Updater folgt `main`, dort liegt nur der freigegebene Stand. Entwickelt wird im Branch `loadcell-homing`.

### Warum nicht Sovols `Z_OFFSET_CALIBRATION`?

Die Sovol-Wägezelle reagiert träge: im Mittel etwa **0,15 s** nach dem Kontakt, und sie misst nur etwa alle **80 ms**. Die Streuung wächst deshalb ziemlich genau mit der Anfahrgeschwindigkeit (Messreihe am Referenzgerät, je 10 Messungen):

| Anfahrt | Streuung (range) | Standardabweichung |
|---|---|---|
| 0,1 mm/s | 0,007 mm | 0,002 mm |
| 0,25 mm/s | 0,022 mm | 0,007 mm |
| 1 mm/s (Sovol) | 0,079 mm | 0,026 mm |
| 3 mm/s | 0,251 mm | 0,081 mm |

Wer die ganze Strecke mit 0,1 mm/s fährt, wartet ewig. Schnelles Anfahren drückt die Düse dagegen weit in die Zelle, bevor sie meldet: Bei 10 mm/s sind das rund 1,5 mm. Deshalb übernimmt die induktive Probe die Grobannäherung, und nur das letzte Stück fährt die Düse langsam.

### Warum X/Y vorne homen?

Diese Config homt X und Y auf 0, also vorne bzw. links. Hinten liegen die Anschläge ungünstig, sehr nahe an den Riemen, und beim sensorlosen Homing verliert man dort Schritte. Dass Sovol hinten homt, ist kein Argument dafür.

## Voraussetzungen

- Rappetors Anleitung (README im Hauptordner) **bis einschließlich Schritt 8**: Mainline-Klipper, Moonraker und Mainsail per KIAUH, beide MCUs mit Klipper-Firmware.
- Schritt 5 (Configs und Sovol-Addons) kann man auslassen, der Installer ersetzt ihn.

## Installation

Per SSH auf dem Drucker, als normaler Benutzer (nicht root):

```bash
curl -fsSL https://raw.githubusercontent.com/Jane0899/Sovol-SV08-Mainline/main/sv08-loadcell/get.sh | bash
```

Das klont das Repo nach `~/Sovol-SV08-Mainline` und startet den Installer. Liegt dort schon ein Klon von Rappetors Repo, wird er nach `~/Sovol-SV08-Mainline.old-<Datum>` verschoben. Von Hand geht es genauso:

```bash
git clone https://github.com/Jane0899/Sovol-SV08-Mainline.git ~/Sovol-SV08-Mainline
~/Sovol-SV08-Mainline/sv08-loadcell/install.sh
```

Der Installer:
1. prüft Klipper, Moonraker, Mainsail und die beiden MCUs,
2. **sichert** alle alten Configs und Sovol-Reste nach `~/printer_data/backup/sv08-loadcell-<Datum>/` und räumt sie dann weg (zusätzlich gibt es ein Archiv des kompletten Config-Ordners),
3. spielt das Modul und die Configs ein. Die MCU-Seriennummern liest er aus der alten `printer.cfg` oder fragt nach,
   **härtet Sovols USB-Automount** vom Werks-Image: Das führte beim bloßen Einstecken eines Sticks als root `test.sh` aus, verband sich mit dem WLAN aus `wifi.cfg` und installierte `.deb`-Pakete samt Neustart. Übrig bleibt: Stick mounten (ohne Ausführrechte). Der Installer fragt, was mit den `.gcode`-Dateien passiert: als `USB-…` auf den Drucker **verschieben** (Stick wird geleert), **kopieren** (Stick bleibt unverändert) oder **nur einbinden** (unter `USB/` sichtbar, solange der Stick steckt). Ändern lässt sich das später in `/etc/default/sv08-usbmount` (`USB_MODE=move|copy|mount`),
4. trägt den Updater in `moonraker.conf` ein,
5. startet Klipper und Moonraker neu.

Danach in Mainsail in der Konsole **`CALIBRATE_SV08`** eingeben und den Dialogen folgen. Das dauert ca. 30–40 Minuten. Bett leer räumen und ein Blatt Papier bereitlegen. Für eine andere Drucktemperatur: `CALIBRATE_SV08 TEMP=240`.

### Slicer

Start-G-Code (OrcaSlicer):
```
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]
```
End-G-Code: `END_PRINT`. Für Timelapse unter „Before layer change“: `TIMELAPSE_TAKE_FRAME`.

## Dateien

| Datei | Was | Updates |
|---|---|---|
| `printer.cfg` | **deine** Datei: gerätespezifische Werte, eigene Anpassungen am Ende, darunter der `SAVE_CONFIG`-Block | wird nie überschrieben |
| `sv08-macros.cfg`, `sv08-loadcell.cfg`, `sv08-menu.cfg` | Symlinks ins Repo | kommen mit jedem Update – dort nichts ändern, Overrides in `printer.cfg` |
| `klipper/klippy/extras/sv08_loadcell.py` | Symlink aufs Modul | kommt mit jedem Update |

Eigene Makros oder Änderungen kommen ans Ende der `printer.cfg`. Eine gleichnamige Sektion oder Option dort überschreibt die aus den `sv08-*.cfg`.

## Befehle

| Befehl | Zweck |
|---|---|
| `CALIBRATE_SV08 [TEMP=220]` | Kalibrierungs-Assistent (einzelne Schritte: `STEP=SENSOR`, `HOME`, `PROBE_TUNE`, `LOADCELL_TUNE`, `HEAT`, `ZOFFSET`, `PAPER`, `SHAPER`, `FINISH`) |
| `AUTO_Z_OFFSET` | Z-Offset messen und setzen (läuft in `START_PRINT` automatisch) |
| `AUTO_Z_OFFSET_SAVE_CORRECTION` | Babystep seit dem letzten `AUTO_Z_OFFSET` als Korrektur übernehmen, z.B. nach einer Feinkorrektur im Druck. Danach `SAVE_CONFIG` |
| `MAINTENANCE_CALIBRATE_Z [TEMP=220]` | Z-Nullpunkt neu messen und speichern (ohne Papiertest) |
| `LOADCELL_HOME` | Z homen (macht `G28` automatisch) |
| `LOADCELL_WAIT_RELEASE [TIMEOUT=5]` | warten, bis die Wägezelle wieder frei ist (statt starrem `G4`) |
| `LOADCELL_ACCURACY`, `LOADCELL_RELEASE_TIME`, `PROBE_OVERTRAVEL`, `RETRACT_TIME` | Messwerkzeuge |

## Wichtig

- **Die induktive Probe nie mit 70 mm/s oder mehr fahren.** Die Z-Motoren verlieren beim abrupten Stopp Schritte, am Referenzgerät waren es 1,67 mm, ohne Fehlermeldung. Der Assistent testet höchstens 50 mm/s und prüft nach jeder Geschwindigkeit, ob Z gewandert ist.
- `AUTO_Z_OFFSET` bricht den Druck ab, wenn der gemessene Offset mehr als 1 mm von der Kalibrierung abweicht (`max_offset`).

## Zurück zum alten Stand

Alles, was der Installer weggeräumt hat, liegt in `~/printer_data/backup/sv08-loadcell-<Datum>/` (Pfade relativ zum Home-Verzeichnis). Dazu gibt es `config-komplett.tar.gz`.
