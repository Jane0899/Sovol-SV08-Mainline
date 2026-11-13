# SERVICE_RESTART: Klipper-Dienst über systemd neu starten
#
# RESTART und FIRMWARE_RESTART lesen nur die Config neu, geänderte
# Python-Module bleiben im Speicher. Ein Neustart des Dienstes lädt alles.
# Über Moonraker (/machine/services/restart), das Dienste per systemd neu
# starten darf - wie der Knopf "Klipper neu starten" in Mainsail. Braucht
# weder sudo noch eine Zusatzerweiterung.
#
# Abschnitt [service_restart] in sv08-loadcell.cfg. Den Symlink nach
# klippy/extras legt sv08_loadcell.py an (auch nach einem Update).
# Option: moonraker_url (Standard http://127.0.0.1:7125)
#
# Copyright (C) 2026  Jane0899
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import subprocess, sys

# Läuft als eigener Prozess: Klipper wird beim Neustart beendet, die Anfrage
# muss trotzdem bei Moonraker ankommen. argv: Moonraker-URL, Dienste in
# Reihenfolge (klipper zuletzt - beim Neustart von Klipper endet auch dieser
# Prozess)
_SCRIPT = """
import json, sys, time, urllib.request as u
base = sys.argv[1]
time.sleep(1.)
try:
    ids = json.load(u.urlopen(base + "/machine/system_info", timeout=10))[
        "result"]["system_info"]["instance_ids"]
except Exception:
    ids = {}
for svc in sys.argv[2:]:
    try:
        u.urlopen(u.Request(base + "/machine/services/restart?service="
                            + ids.get(svc, svc), method="POST"), timeout=60)
    except Exception:
        pass  # Moonraker antwortet beim eigenen Neustart evtl. nicht mehr
    if svc == "moonraker":
        # warten, bis Moonraker wieder da ist
        time.sleep(3.)
        for i in range(90):
            try:
                u.urlopen(base + "/server/info", timeout=3)
                break
            except Exception:
                time.sleep(1.)
"""

class ServiceRestart:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.url = config.get('moonraker_url', 'http://127.0.0.1:7125')
        self.printer.lookup_object('gcode').register_command(
            'SERVICE_RESTART', self.cmd_SERVICE_RESTART,
            desc="Klipper-Dienst über systemd neu starten - lädt auch"
                 " geänderte Python-Module (RESTART/FIRMWARE_RESTART nicht)")
    def printing(self):
        reactor = self.printer.get_reactor()
        state = self.printer.lookup_object('print_stats').get_status(
            reactor.monotonic())['state']
        return state in ('printing', 'paused')
    def restart(self, *services):
        # Dienste über Moonraker neu starten, z.B. restart('moonraker',
        # 'klipper'). Kehrt sofort zurück
        subprocess.Popen([sys.executable, '-c', _SCRIPT, self.url]
                         + list(services or ('klipper',)),
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    def cmd_SERVICE_RESTART(self, gcmd):
        if self.printing():
            raise gcmd.error("SERVICE_RESTART: nicht während eines Drucks")
        gcmd.respond_info("SERVICE_RESTART: Klipper-Dienst wird neu"
                          " gestartet (lädt auch geänderte Python-Module)")
        self.restart('klipper')

def load_config(config):
    return ServiceRestart(config)
