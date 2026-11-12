# SERVICE_RESTART: Klipper-Dienst über systemd neu starten
#
# RESTART und FIRMWARE_RESTART lesen nur die Config neu, geänderte
# Python-Module bleiben im Speicher. Ein Neustart des Dienstes lädt alles.
# Über Moonraker (/machine/services/restart), das Dienste per systemd neu
# starten darf - wie der Knopf "Klipper neu starten" in Mainsail. Braucht
# weder sudo noch eine Zusatzerweiterung.
#
# Wird von sv08_loadcell.py aus diesem Ordner geladen (kein eigener
# Config-Abschnitt, kein eigener Symlink: ein Update per git pull reicht).
# Option unter [sv08_loadcell]: moonraker_url (Standard http://127.0.0.1:7125)
#
# Copyright (C) 2026  Jane0899
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import subprocess, sys

# Läuft als eigener Prozess: Klipper wird beim Neustart beendet, die Anfrage
# muss trotzdem bei Moonraker ankommen. argv[1] = Moonraker-URL
_SCRIPT = """
import json, sys, time, urllib.request as u
base = sys.argv[1]
time.sleep(1.)
try:
    name = json.load(u.urlopen(base + "/machine/system_info", timeout=10))[
        "result"]["system_info"]["instance_ids"]["klipper"]
except Exception:
    name = "klipper"
u.urlopen(u.Request(base + "/machine/services/restart?service=" + name,
                    method="POST"), timeout=60)
"""

class ServiceRestart:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.url = config.get('moonraker_url', 'http://127.0.0.1:7125')
        self.printer.lookup_object('gcode').register_command(
            'SERVICE_RESTART', self.cmd_SERVICE_RESTART,
            desc="Klipper-Dienst über systemd neu starten - lädt auch"
                 " geänderte Python-Module (RESTART/FIRMWARE_RESTART nicht)")
    def cmd_SERVICE_RESTART(self, gcmd):
        reactor = self.printer.get_reactor()
        state = self.printer.lookup_object('print_stats').get_status(
            reactor.monotonic())['state']
        if state in ('printing', 'paused'):
            raise gcmd.error("SERVICE_RESTART: nicht während eines Drucks")
        gcmd.respond_info("SERVICE_RESTART: Klipper-Dienst wird neu"
                          " gestartet (lädt auch geänderte Python-Module)")
        subprocess.Popen([sys.executable, '-c', _SCRIPT, self.url],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
