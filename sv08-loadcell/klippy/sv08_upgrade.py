# UPGRADE_CONFIG: Config-Upgrade nach einem Update aus dem Klipper-Terminal
#
# Ein Update im Mainsail-Update-Tab holt nur den neuen Stand (git pull) und
# startet Klipper neu - das reicht für Makros und Python-Code. Braucht ein
# Update mehr (Einträge in moonraker.conf oder printer.cfg, Systemdateien),
# erhöht es sv08-loadcell/config-version. Klipper meldet dann beim Start,
# dass UPGRADE_CONFIG nötig ist. Der Befehl führt install.sh --upgrade im
# Hintergrund aus (Ausgabe hier im Terminal und in logs/sv08-upgrade.log)
# und startet danach Moonraker (falls geändert) und Klipper neu.
#
# Abschnitt [sv08_upgrade] in sv08-loadcell.cfg. Den Symlink nach
# klippy/extras legt sv08_loadcell.py an (auch nach einem Update).
#
# Copyright (C) 2026  Jane0899
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import hashlib, logging, os, re, subprocess

ANSI = re.compile(r'\x1b\[[0-9;]*m')

def read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0

def file_hash(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None

class SV08Upgrade:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.lc_dir = os.path.dirname(os.path.dirname(
            os.path.realpath(__file__)))
        cfg_file = self.printer.get_start_args()['config_file']
        self.cfg_dir = os.path.dirname(os.path.abspath(cfg_file))
        data_dir = os.path.dirname(self.cfg_dir)
        # install.sh schreibt hierhin die eingespielte config-version
        self.installed_file = os.path.join(data_dir, '.sv08-loadcell-version')
        self.log_file = os.path.join(data_dir, 'logs', 'sv08-upgrade.log')
        self.done_file = os.path.join(data_dir, 'logs', 'sv08-upgrade.done')
        self.proc = None
        self.log_pos = 0
        self.mr_hash = None
        self.gcode.register_command(
            'UPGRADE_CONFIG', self.cmd_UPGRADE_CONFIG,
            desc="sv08-loadcell: Config nach einem Update anpassen"
                 " (install.sh --upgrade), danach Neustart")
        self.printer.register_event_handler("klippy:ready", self._ready)
    def required(self):
        return read_int(os.path.join(self.lc_dir, 'config-version'))
    def installed(self):
        return read_int(self.installed_file)
    def _ready(self):
        # kurz warten, damit Mainsail nach dem Neustart wieder verbunden ist
        self.reactor.register_timer(self._report,
                                    self.reactor.monotonic() + 3.)
    def _report(self, eventtime):
        if os.path.exists(self.done_file):
            try:
                os.remove(self.done_file)
            except OSError:
                pass
            self.gcode.respond_info("UPGRADE_CONFIG: fertig, Config auf"
                                    " Stand %d" % (self.installed(),))
        if self.installed() < self.required():
            self.gcode.respond_raw(
                "!! sv08-loadcell: Config-Upgrade nötig (Stand %d, Update"
                " braucht %d) - im Terminal UPGRADE_CONFIG eingeben"
                % (self.installed(), self.required()))
        return self.reactor.NEVER
    def cmd_UPGRADE_CONFIG(self, gcmd):
        sr = self.printer.lookup_object('service_restart', None)
        if sr is None:
            raise gcmd.error("UPGRADE_CONFIG braucht [service_restart]")
        if sr.printing():
            raise gcmd.error("UPGRADE_CONFIG: nicht während eines Drucks")
        if self.proc is not None:
            raise gcmd.error("UPGRADE_CONFIG läuft schon")
        self.mr_hash = file_hash(os.path.join(self.cfg_dir, 'moonraker.conf'))
        env = dict(os.environ, SV08_NO_RESTART='1')
        log = open(self.log_file, 'w')
        try:
            self.proc = subprocess.Popen(
                ['bash', os.path.join(self.lc_dir, 'install.sh'),
                 '--upgrade'], env=env, cwd=os.path.expanduser('~'),
                stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True,
                close_fds=True)
        finally:
            log.close()
        self.log_pos = 0
        gcmd.respond_info("UPGRADE_CONFIG: install.sh --upgrade läuft"
                          " (Protokoll: logs/sv08-upgrade.log)")
        self.reactor.register_timer(self._poll, self.reactor.NOW)
    def _relay(self):
        # neue Zeilen aus dem Protokoll ins Terminal
        try:
            with open(self.log_file, 'rb') as f:
                f.seek(self.log_pos)
                data = f.read()
        except OSError:
            return
        end = data.rfind(b'\n') + 1
        self.log_pos += end
        for line in data[:end].decode('utf-8', 'replace').splitlines():
            line = ANSI.sub('', line).rstrip()
            if line:
                self.gcode.respond_info(line)
    def _poll(self, eventtime):
        self._relay()
        rc = self.proc.poll()
        if rc is None:
            return eventtime + .5
        self.proc = None
        self._relay()
        if rc:
            self.gcode.respond_raw(
                "!! UPGRADE_CONFIG fehlgeschlagen (Code %d) - nichts neu"
                " gestartet, Details in logs/sv08-upgrade.log" % (rc,))
            return self.reactor.NEVER
        services = ['klipper']
        if file_hash(os.path.join(self.cfg_dir, 'moonraker.conf')) \
                != self.mr_hash:
            services.insert(0, 'moonraker')
        try:
            open(self.done_file, 'w').close()
        except OSError:
            logging.exception("sv08_upgrade: %s", self.done_file)
        self.gcode.respond_info("UPGRADE_CONFIG: starte %s neu"
                                % (" und ".join(services),))
        self.printer.lookup_object('service_restart').restart(*services)
        return self.reactor.NEVER

def load_config(config):
    return SV08Upgrade(config)
