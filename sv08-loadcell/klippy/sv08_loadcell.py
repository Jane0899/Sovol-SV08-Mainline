# Sovol SV08: Z-Homing auf der Wägezelle + automatischer Z-Offset
#
# Die Wägezelle hinten rechts (Sovol "probe_pressure", PE12) ist der
# stepper_z-Endstop. Sie reagiert träge (~0,15 s Verzögerung, ~80 ms
# Messtakt), deshalb:
#   LOADCELL_HOME  - induktive Probe grob und schnell über der Zelle, dann
#                    Düse ganz langsam (0,1 mm/s) auf die Zelle
#   AUTO_Z_OFFSET  - Düse auf Zelle (= Z-Referenz), induktive Probe über der
#                    Zelle und am Bett -> SET_GCODE_OFFSET Z
#   CALIBRATE_SV08 - Assistent (Mainsail-Dialoge): Sensor-Check, Messreihen
#                    für Probe und Wägezelle, Z-Nullpunkt, Papiertest,
#                    Input Shaper - Ergebnisse per SAVE_CONFIG
#
# Copyright (C) 2026  Jane0899
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import math
from . import probe as probe_mod

def move_time(dist, speed, accel):
    # Dauer einer Fahrt aus dem Stand in den Stand (Trapez/Dreieck)
    if dist >= speed * speed / accel:
        return 2. * speed / accel + (dist - speed * speed / accel) / speed
    return 2. * math.sqrt(dist / accel)

def move_dist_at(t, dist, speed, accel):
    # Zurückgelegte Strecke nach Zeit t innerhalb dieser Fahrt
    total = move_time(dist, speed, accel)
    if t <= 0.:
        return 0.
    if t >= total:
        return dist
    v_peak = min(speed, math.sqrt(dist * accel))
    t_acc = v_peak / accel
    if t <= t_acc:
        return .5 * accel * t * t
    d_acc = .5 * accel * t_acc * t_acc
    t_cruise = total - 2. * t_acc
    if t <= t_acc + t_cruise:
        return d_acc + v_peak * (t - t_acc)
    td = total - t
    return dist - .5 * accel * td * td

def trigger_speed(dist, speed, accel):
    # Geschwindigkeit nach 'dist' mm Anfahrt aus dem Stand (Ziel weit
    # unterhalb, also noch keine Bremsphase) - bei zu kurzer Anfahrt wird die
    # Sollgeschwindigkeit nicht erreicht
    return min(speed, math.sqrt(2. * accel * max(dist, 0.)))

def stats(values):
    n = len(values)
    avg = sum(values) / n
    srt = sorted(values)
    med = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.
    sd = math.sqrt(sum((v - avg) ** 2 for v in values) / n)
    return min(values), max(values), max(values) - min(values), avg, med, sd

class SV08Loadcell:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()
        # Düsenposition über der Wägezelle
        self.loadcell_xy = config.getfloatlist('loadcell_xy_position',
                                               (289., 361.), count=2)
        # Probe-Position am Bett für AUTO_Z_OFFSET (Standard: zero_reference
        # des Meshs) - nahe an der Zelle, damit Gantry-Schräge und
        # Bettwölbung nicht in den Offset eingehen
        self.bed_xy = config.getfloatlist('bed_xy_position', None, count=2)
        self.safe_z = config.getfloat('safe_z', 5., above=0.)
        self.travel_speed = config.getfloat('travel_speed', 100., above=0.)
        self.lift_speed = config.getfloat('lift_speed', 15., above=0.)
        # LOADCELL_HOME
        self.coarse_speed = config.getfloat('coarse_speed', 30., above=0.)
        self.home_speed = config.getfloat('home_speed', .1, above=0.)
        self.home_clearance = config.getfloat('home_clearance', .2, minval=0.)
        self.probe_contact_gap = config.getfloat('probe_contact_gap', .05)
        self.max_slow_travel = config.getfloat('max_slow_travel', 1.5,
                                               above=0.)
        self.xy_lift = config.getfloat('xy_lift', 5., above=0.)
        self.release_timeout = config.getfloat('release_timeout', 2., above=0.)
        # AUTO_Z_OFFSET
        self.z_correction = config.getfloat('z_correction', 0.)
        self.max_offset = config.getfloat('max_offset', 1., above=0.)
        self.last_offset = None
        self.last_result = {}
        self.wizard = {'temp': 220}
        self.z_endstop = None
        self.toolhead = None
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        for cmd, desc in [
                ('LOADCELL_HOME',
                 "Z homen: induktive Probe grob, dann Düse langsam auf die"
                 " Wägezelle"),
                ('AUTO_Z_OFFSET',
                 "Z-Offset messen (Düse auf Wägezelle, Probe über Zelle und"
                 " Bett) und setzen"),
                ('AUTO_Z_OFFSET_SAVE_CORRECTION',
                 "Babystep seit dem letzten AUTO_Z_OFFSET als Korrektur"
                 " übernehmen (danach SAVE_CONFIG)"),
                ('LOADCELL_WAIT_RELEASE',
                 "Warten, bis die Wägezelle wieder frei meldet (statt G4)"),
                ('LOADCELL_ACCURACY',
                 "Wiederholgenauigkeit der Wägezelle messen"),
                ('LOADCELL_RELEASE_TIME',
                 "Abklingzeit der Wägezelle nach dem Antippen messen"),
                ('PROBE_OVERTRAVEL',
                 "Nachlauf der induktiven Probe nach dem Auslösen messen"),
                ('RETRACT_TIME', "Dauer einer Z-Fahrt berechnen"),
                ('CALIBRATE_SV08',
                 "Kalibrierungs-Assistent (Mainsail-Dialoge)")]:
            self.gcode.register_command(cmd, getattr(self, 'cmd_' + cmd),
                                        desc=desc)
    def _handle_connect(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        qe = self.printer.lookup_object('query_endstops')
        for endstop, name in qe.endstops:
            if name in ('stepper_z', 'z'):
                self.z_endstop = endstop
        if self.z_endstop is None:
            raise self.printer.config_error(
                "%s: kein Z-Endstop gefunden ([stepper_z] endstop_pin muss die"
                " Wägezelle sein)" % (self.name,))
        if self.bed_xy is None:
            mesh = self.printer.lookup_object('bed_mesh', None)
            zref = None
            if mesh is not None and hasattr(mesh.bmc, 'probe_mgr'):
                zref = mesh.bmc.probe_mgr.get_zero_ref_pos()
            if zref is None:
                raise self.printer.config_error(
                    "%s: bed_xy_position setzen oder [bed_mesh]"
                    " zero_reference_position konfigurieren" % (self.name,))
            self.bed_xy = list(zref)
    def get_status(self, eventtime):
        return {'z_correction': self.z_correction,
                'last_offset': self.last_offset,
                'last_result': self.last_result}
    # Hilfsfunktionen
    def _settings(self):
        return self.printer.lookup_object('configfile').get_status(
            None)['settings']
    def _z_accel(self):
        return self._settings()['printer'].get('max_z_accel', 100.)
    def _z_min(self):
        kin = self.toolhead.get_kinematics()
        return kin.get_status(self.reactor.monotonic())['axis_minimum'][2]
    def _homed(self):
        return self.toolhead.get_status(
            self.reactor.monotonic())['homed_axes']
    def _check_homed(self, gcmd):
        homed = self._homed()
        if 'x' not in homed or 'y' not in homed or 'z' not in homed:
            raise gcmd.error("Erst homen (G28)")
    def _probe(self):
        probe = self.printer.lookup_object('probe')
        endstop = probe.mcu_probe
        if not hasattr(endstop, 'get_steppers'):
            # Neuere Klipper-Versionen verschachteln den MCU-Endstop
            endstop = endstop.mcu_endstop
        return probe, endstop
    def _query(self):
        mcu = self.z_endstop.get_mcu()
        pt = mcu.estimated_print_time(self.reactor.monotonic())
        return pt, self.z_endstop.query_endstop(pt)
    def _wait_release(self, gcmd, max_wait):
        self.toolhead.wait_moves()
        start = self.reactor.monotonic()
        while 1:
            pt, triggered = self._query()
            now = self.reactor.monotonic()
            if not triggered:
                return now - start
            if now - start > max_wait:
                raise gcmd.error("Wägezelle nach %.1f s immer noch"
                                 " ausgelöst" % (max_wait,))
            self.reactor.pause(now + .001)
    def _lift_to(self, z):
        if self.toolhead.get_position()[2] < z:
            self.toolhead.manual_move([None, None, z], self.lift_speed)
    def _tap(self, gcmd, speed, max_overtravel):
        # Düse von der aktuellen Position auf die Wägezelle
        phoming = self.printer.lookup_object('homing')
        pos = self.toolhead.get_position()
        start_z = pos[2]
        pos[2] = self._z_min()
        trig = phoming.probing_move(self.z_endstop, pos, speed)
        halt = self.toolhead.get_position()[2]
        v_trig = trigger_speed(start_z - trig[2], speed, self._z_accel())
        overtravel = trig[2] - halt
        if overtravel > max_overtravel:
            self.toolhead.manual_move([None, None, trig[2] + 2.], 5.)
            raise gcmd.error("Überfahrweg %.3f mm > MAX_OVERTRAVEL=%.3f -"
                             " Abbruch" % (overtravel, max_overtravel))
        return trig[2], overtravel, v_trig
    def _probe_at(self, gcmd, x, y):
        # Induktive Probe an Bettposition x,y (Probe-Koordinaten), liefert
        # die geschätzte Kontakthöhe (bed_z) wie PROBE
        probe, _ = self._probe()
        px, py, pz = probe.get_offsets()
        self._lift_to(self.safe_z)
        self.toolhead.manual_move([x - px, y - py, None], self.travel_speed)
        return probe_mod.run_single_probe(probe, gcmd).bed_z
    # Z-Homing
    def cmd_LOADCELL_HOME(self, gcmd):
        th = self.toolhead
        kin = th.get_kinematics()
        eventtime = self.reactor.monotonic()
        homed = th.get_status(eventtime)['homed_axes']
        if 'x' not in homed or 'y' not in homed:
            raise gcmd.error("LOADCELL_HOME: erst X und Y homen")
        coarse_speed = gcmd.get_float('COARSE_SPEED', self.coarse_speed,
                                      above=0.)
        speed = gcmd.get_float('SPEED', self.home_speed, above=0.)
        clearance = gcmd.get_float('CLEARANCE', self.home_clearance,
                                   minval=0.)
        gap = gcmd.get_float('GAP', self.probe_contact_gap)
        max_slow = gcmd.get_float('MAX_SLOW_TRAVEL', self.max_slow_travel,
                                  above=0.)
        kstatus = kin.get_status(eventtime)
        z_min = kstatus['axis_minimum'][2]
        z_max = kstatus['axis_maximum'][2]
        pos_endstop = self._settings()['stepper_z']['position_endstop']
        probe, probe_endstop = self._probe()
        px, py, pz = probe.get_offsets()
        cx, cy = self.loadcell_xy
        phoming = self.printer.lookup_object('homing')
        try:
            # Ist Z schon bekannt und der Kopf tief: erst anheben
            pos = th.get_position()
            if 'z' in homed and pos[2] < self.safe_z:
                th.manual_move([None, None, self.safe_z], self.lift_speed)
            # Z gilt als unbekannt: Kopf "ganz oben" annehmen, damit die
            # Probe den gesamten Weg nach unten fahren darf
            pos = th.get_position()
            pos[2] = z_max
            th.set_position(pos, homing_axes="z")
            # 1. Grob: induktive Probe über der Wägezelle, schnell
            th.manual_move([cx - px, cy - py, None], self.travel_speed)
            th.wait_moves()
            if probe_endstop.query_endstop(th.get_last_move_time()):
                raise gcmd.error("LOADCELL_HOME: Probe schon ausgelöst -"
                                 " Kopf zu tief, erst anheben")
            pos = th.get_position()
            pos[2] = z_min
            z_probe = phoming.probing_move(probe_endstop, pos,
                                           coarse_speed)[2]
            # 2. Düse über die Zelle, knapp über erwarteten Kontakt
            th.manual_move([None, None, z_probe + self.xy_lift],
                           self.lift_speed)
            th.manual_move([cx, cy, None], self.travel_speed)
            start = z_probe - gap + clearance
            th.manual_move([None, None, start], 5.)
            self._wait_release(gcmd, self.release_timeout)
            # 3. Fein: Düse ganz langsam auf die Wägezelle
            pos = th.get_position()
            pos[2] = start - clearance - max_slow
            z_cell = phoming.probing_move(self.z_endstop, pos, speed)[2]
            # 4. Z so setzen, dass der Auslösepunkt = position_endstop ist
            pos = th.get_position()
            pos[2] += pos_endstop - z_cell
            th.set_position(pos, homing_axes="z")
            th.manual_move([None, None, pos[2] + self.safe_z],
                           self.lift_speed)
        except:
            kin.clear_homing_state("z")
            raise
        self.last_result['probe_contact_gap'] = z_probe - z_cell
        gcmd.respond_info(
            "LOADCELL_HOME: Probe bei %.4f, Wägezelle bei %.4f -> Abstand"
            " Probe/Kontakt %.4f mm (konfiguriert %.3f), langsame Anfahrt"
            " %.3f mm mit %.2f mm/s, Z=%.3f gesetzt"
            % (z_probe, z_cell, z_probe - z_cell, gap, start - z_cell,
               speed, pos_endstop))
    # Automatischer Z-Offset
    def cmd_AUTO_Z_OFFSET(self, gcmd):
        homed = self._homed()
        if 'x' not in homed or 'y' not in homed:
            self.gcode.run_script_from_command("G28")
        self.gcode.run_script_from_command("SET_GCODE_OFFSET Z=0")
        self.last_offset = None
        # Düse frisch auf die Zelle = Z-Referenz (über homing_override,
        # damit dessen Anheben danach gleich bleibt)
        self.gcode.run_script_from_command("G28 Z")
        probe, _ = self._probe()
        px, py, pz = probe.get_offsets()
        cx, cy = self.loadcell_xy
        bx, by = self.bed_xy
        sensor_z = self._probe_at(gcmd, cx, cy)
        bed_z = self._probe_at(gcmd, bx, by)
        self._lift_to(self.safe_z)
        endstop_z = self._settings()['stepper_z']['position_endstop']
        corr = self.z_correction
        # Bettoberfläche in Maschinen-Z
        offset = bed_z - sensor_z + endstop_z - corr
        self.last_result.update({'bed_z': bed_z, 'sensor_z': sensor_z,
                                 'offset': offset})
        msg = ("Bett=%.4f - Sensor=%.4f + Endstop=%.4f - Korrektur=%.4f ->"
               " Z-Offset=%.4f" % (bed_z, sensor_z, endstop_z, corr, offset))
        max_offset = gcmd.get_float('MAX_OFFSET', self.max_offset, above=0.)
        if abs(offset) > max_offset:
            raise gcmd.error("AUTO_Z_OFFSET: Offset außerhalb +/-%.2f: %s"
                             % (max_offset, msg))
        self.gcode.run_script_from_command("SET_GCODE_OFFSET Z=%.6f"
                                           % (offset,))
        self.last_offset = offset
        gcmd.respond_info("AUTO_Z_OFFSET: " + msg)
    def cmd_AUTO_Z_OFFSET_SAVE_CORRECTION(self, gcmd):
        # Nur der Babystep zählt (homing_origin), nicht die G-Code-Höhe -
        # sonst wäre der Befehl nach einem Druck (Kopf z.B. auf Z25)
        # unbrauchbar
        if self.last_offset is None:
            raise gcmd.error("AUTO_Z_OFFSET_SAVE_CORRECTION: erst"
                             " AUTO_Z_OFFSET ausführen (seit dem letzten"
                             " Neustart)")
        gcode_move = self.printer.lookup_object('gcode_move')
        origin_z = gcode_move.get_status(
            self.reactor.monotonic())['homing_origin'].z
        delta = origin_z - self.last_offset
        old = self.z_correction
        self.z_correction = old - delta
        self.last_offset = origin_z
        configfile = self.printer.lookup_object('configfile')
        configfile.set(self.name, 'z_correction', "%.4f" % (self.z_correction,))
        gcmd.respond_info(
            "AUTO_Z_OFFSET: Babystep %+.4f -> Korrektur %.4f -> %.4f. Mit"
            " SAVE_CONFIG dauerhaft speichern." % (delta, old,
                                                  self.z_correction))
    def cmd_LOADCELL_WAIT_RELEASE(self, gcmd):
        # Wartet nach Bewegungsende, bis der Sensor frei meldet - Fehler nach
        # TIMEOUT. Ersetzt ein starres G4 nach dem Antippen.
        timeout = gcmd.get_float('TIMEOUT', 5., above=0.)
        waited = self._wait_release(gcmd, timeout)
        if gcmd.get_int('VERBOSE', 0):
            gcmd.respond_info("LOADCELL_WAIT_RELEASE: frei nach %.3f s"
                              % (waited,))
    # Messwerkzeuge
    def cmd_RETRACT_TIME(self, gcmd):
        dist = gcmd.get_float('DIST', 10., above=0.)
        speed = gcmd.get_float('SPEED', 15., above=0.)
        accel = gcmd.get_float('ACCEL', self._z_accel(), above=0.)
        t = move_time(dist, speed, accel)
        gcmd.respond_info("RETRACT_TIME: %.2f mm mit %.1f mm/s (accel %.0f)"
                          " dauert %.3f s" % (dist, speed, accel, t))
    def cmd_LOADCELL_ACCURACY(self, gcmd):
        self._check_homed(gcmd)
        x = gcmd.get_float('X', self.loadcell_xy[0])
        y = gcmd.get_float('Y', self.loadcell_xy[1])
        samples = gcmd.get_int('SAMPLES', 10, minval=2)
        speed = gcmd.get_float('SPEED', self.home_speed, above=0.)
        retract = gcmd.get_float('RETRACT', 1., above=0.)
        lift_speed = gcmd.get_float('LIFT_SPEED', self.lift_speed, above=0.)
        max_wait = gcmd.get_float('MAX_WAIT', 10., above=0.)
        max_overtravel = gcmd.get_float('MAX_OVERTRAVEL', .3, above=0.)
        self._lift_to(self.safe_z)
        self.toolhead.manual_move([x, y, None], self.travel_speed)
        trigs, overs, waits, vtrigs = [], [], [], []
        for i in range(samples):
            waits.append(self._wait_release(gcmd, max_wait))
            z, over, v_trig = self._tap(gcmd, speed, max_overtravel)
            trigs.append(z)
            overs.append(over)
            if i:
                # erste Anfahrt startet von safe_z, nicht vom Rückzug
                vtrigs.append(v_trig)
            gcmd.respond_info("loadcell #%d: z=%.6f (gewartet %.3f s,"
                              " Überfahrweg %.3f, v_trig %.1f)"
                              % (i + 1, z, waits[-1], over, v_trig))
            self.toolhead.manual_move([None, None, z + retract], lift_speed)
        self.toolhead.manual_move([None, None, max(trigs) + self.safe_z],
                                  lift_speed)
        mn, mx, rng, avg, med, sd = stats(trigs)
        self.last_result['loadcell_accuracy'] = {
            'speed': speed, 'retract': retract, 'range': rng, 'stddev': sd,
            'average': avg, 'samples': trigs, 'waits': waits}
        gcmd.respond_info(
            "LOADCELL_ACCURACY SPEED=%.2f RETRACT=%.1f LIFT_SPEED=%.1f"
            " SAMPLES=%d: max %.6f, min %.6f, range %.6f, average %.6f,"
            " median %.6f, standard deviation %.6f | Überfahrweg max %.3f |"
            " Warten auf Freigabe max %.3f s | Auslösegeschwindigkeit"
            " %.2f mm/s"
            % (speed, retract, lift_speed, samples, mx, mn, rng, avg, med,
               sd, max(overs), max(waits), min(vtrigs)))
    def cmd_LOADCELL_RELEASE_TIME(self, gcmd):
        self._check_homed(gcmd)
        x = gcmd.get_float('X', self.loadcell_xy[0])
        y = gcmd.get_float('Y', self.loadcell_xy[1])
        speed = gcmd.get_float('SPEED', 1., above=0.)
        retract = gcmd.get_float('RETRACT', 2., above=0.)
        lift_speed = gcmd.get_float('LIFT_SPEED', self.lift_speed, above=0.)
        repeat = gcmd.get_int('REPEAT', 3, minval=1)
        max_wait = gcmd.get_float('MAX_WAIT', 10., above=0.)
        max_overtravel = gcmd.get_float('MAX_OVERTRAVEL', .3, above=0.)
        accel = self._z_accel()
        duration = move_time(retract, lift_speed, accel)
        self._lift_to(self.safe_z)
        self.toolhead.manual_move([x, y, None], self.travel_speed)
        times = []
        for i in range(repeat):
            self._wait_release(gcmd, max_wait)
            z, over, v_trig = self._tap(gcmd, speed, max_overtravel)
            self.toolhead.manual_move([None, None, z + retract], lift_speed)
            end_pt = self.toolhead.get_last_move_time()
            start_pt = end_pt - duration
            polls = 0
            while 1:
                pt, triggered = self._query()
                polls += 1
                if not triggered:
                    break
                if pt > end_pt + max_wait:
                    raise gcmd.error("Wägezelle nach %.1f s immer noch"
                                     " ausgelöst" % (max_wait,))
                self.reactor.pause(self.reactor.monotonic() + .001)
            rel = pt - start_pt
            times.append(rel)
            if pt <= end_pt:
                where = "während des Rückzugs nach %.3f mm" % (
                    move_dist_at(rel, retract, lift_speed, accel),)
            else:
                where = "%.3f s nach Ende des Rückzugs" % (pt - end_pt,)
            gcmd.respond_info(
                "LOADCELL_RELEASE_TIME #%d: getippt bei Z=%.4f (Überfahrweg"
                " %.3f), Rückzug %.1f mm mit %.1f mm/s dauert %.3f s, frei"
                " %.3f s nach Rückzugsbeginn = %s (%d Abfragen)"
                % (i + 1, z, over, retract, lift_speed, duration, rel, where,
                   polls))
            self.toolhead.manual_move([None, None, z + self.safe_z],
                                      lift_speed)
        self.last_result['release_time_max'] = max(times)
    def cmd_PROBE_OVERTRAVEL(self, gcmd):
        # Probing-Fahrt mit dem [probe]-Endstop an der aktuellen XY-Position,
        # meldet den Abstand zwischen Auslöse- und Halteposition
        self._check_homed(gcmd)
        speed = gcmd.get_float('SPEED', 5., above=0.)
        retract = gcmd.get_float('RETRACT', 5., above=0.)
        lift_speed = gcmd.get_float('LIFT_SPEED', 25., above=0.)
        probe, endstop = self._probe()
        phoming = self.printer.lookup_object('homing')
        pos = self.toolhead.get_position()
        start_z = pos[2]
        pos[2] = self._z_min()
        trig = phoming.probing_move(endstop, pos, speed)
        halt = self.toolhead.get_position()[2]
        v_trig = trigger_speed(start_z - trig[2], speed, self._z_accel())
        self.toolhead.manual_move([None, None, trig[2] + retract], lift_speed)
        self.last_result['probe_overtravel'] = trig[2] - halt
        gcmd.respond_info("PROBE_OVERTRAVEL SPEED=%.1f: ausgelöst bei Z=%.4f,"
                          " gehalten bei Z=%.4f, Nachlauf %.4f mm"
                          " (v_trig %.1f mm/s)"
                          % (speed, trig[2], halt, trig[2] - halt, v_trig))

    # ------------------------------------------------------------------
    # Kalibrierungs-Assistent
    # ------------------------------------------------------------------
    # Grenzen der automatischen Messreihen (aus der Testreihe am
    # Referenzgerät): induktive Probe nie >= 70 mm/s (Z verliert Schritte),
    # Wägezelle nie schneller als 1 mm/s (reagiert ~0,15 s verzögert, die
    # Düse drückt sonst zu weit nach)
    PROBE_SPEEDS = (10., 20., 30., 50.)
    PROBE_RETRACTS = (2., 5., 10.)
    PROBE_MAX_OVERTRAVEL = .15
    DRIFT_LIMIT = .01
    LOADCELL_SPEEDS = (.1, .25, .5, 1.)
    LOADCELL_TARGET_RANGE = .01
    def _prompt(self, title, lines, buttons=(), footer=()):
        r = self.gcode.respond_raw
        r("// action:prompt_end")
        r("// action:prompt_begin %s" % (title,))
        for line in lines:
            r("// action:prompt_text %s" % (line,))
        for label, cmd, color in buttons:
            r("// action:prompt_button %s|%s|%s" % (label, cmd, color))
        for label, cmd, color in footer:
            r("// action:prompt_footer_button %s|%s|%s" % (label, cmd, color))
        r("// action:prompt_show")
    def _prompt_end(self):
        self.gcode.respond_raw("// action:prompt_end")
    def _next(self, title, lines, step, label="Weiter"):
        self._prompt(title, lines,
                     [(label, "CALIBRATE_SV08 STEP=%s" % (step,), "primary")],
                     [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL", "error")])
    def _run(self, script):
        self.gcode.run_script_from_command(script)
    def _set(self, section, option, value):
        self.printer.lookup_object('configfile').set(section, option, value)
        self.wizard.setdefault('saved', []).append(
            "[%s] %s = %s" % (section, option, value))
    def _ensure_leveled(self):
        homed = self._homed()
        if 'x' not in homed or 'y' not in homed or 'z' not in homed:
            self._run("G28")
        qgl = self.printer.lookup_object('quad_gantry_level', None)
        if qgl is not None and not qgl.get_status(
                self.reactor.monotonic()).get('applied'):
            self._run("QUAD_GANTRY_LEVEL")
            self._run("G28 Z")
    def _probe_series(self, speed, retract, samples, lift_speed=25.):
        # Induktive Probe an der aktuellen XY-Position, wie PROBE_ACCURACY,
        # zusätzlich mit Nachlauf (Auslöse- minus Halteposition)
        probe, endstop = self._probe()
        phoming = self.printer.lookup_object('homing')
        trigs, overs = [], []
        for i in range(samples):
            pos = self.toolhead.get_position()
            pos[2] = self._z_min()
            trig = phoming.probing_move(endstop, pos, speed)[2]
            overs.append(trig - self.toolhead.get_position()[2])
            trigs.append(trig)
            self.toolhead.manual_move([None, None, trig + retract],
                                      lift_speed)
        return trigs, overs
    def _goto_bed_point(self, z=10.):
        probe, _ = self._probe()
        px, py, pz = probe.get_offsets()
        self._lift_to(z)
        self.toolhead.manual_move([self.bed_xy[0] - px, self.bed_xy[1] - py,
                                   None], self.travel_speed)
        self.toolhead.manual_move([None, None, z], self.lift_speed)
    def cmd_CALIBRATE_SV08(self, gcmd):
        step = gcmd.get('STEP', 'START').upper()
        if 'TEMP' in gcmd.get_command_parameters():
            self.wizard['temp'] = gcmd.get_int('TEMP', 220, minval=150,
                                               maxval=300)
        handler = getattr(self, '_wz_' + step.lower(), None)
        if handler is None:
            raise gcmd.error("CALIBRATE_SV08: unbekannter Schritt %s" % step)
        try:
            handler(gcmd)
        except self.printer.command_error as e:
            self._prompt("SV08 Kalibrierung - Fehler",
                         ["Schritt %s fehlgeschlagen:" % (step,), str(e)],
                         [("Schritt wiederholen",
                           "CALIBRATE_SV08 STEP=%s" % (step,), "warning")],
                         [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL",
                           "error")])
            raise
    def _wz_start(self, gcmd):
        self.wizard = {'temp': self.wizard.get('temp', 220)}
        self._next("SV08 Kalibrierung", [
            "Der Assistent misst deinen Drucker ein und speichert die Werte"
            " am Ende per SAVE_CONFIG:",
            "1. Sensor-Check  2. Homing + QGL  3. Messreihe induktive Probe"
            "  4. Messreihe Wägezelle  5. Düse reinigen + heizen"
            " (%d °C)  6. Z-Nullpunkt  7. Papiertest  8. Input Shaper"
            % (self.wizard['temp'],),
            "Dauer ca. 30-40 Minuten. Bett leer räumen, Düse sauber, ein"
            " Blatt Papier bereitlegen.",
            "Andere Drucktemperatur: CALIBRATE_SV08 TEMP=240"], 'SENSOR',
            "Start")
    def _wz_cancel(self, gcmd):
        self._prompt_end()
        self._run("TURN_OFF_HEATERS")
        gcmd.respond_info("CALIBRATE_SV08 abgebrochen. Bereits übernommene"
                          " Werte werden erst mit SAVE_CONFIG gespeichert.")
    # 1. Sensor-Check
    def _wz_sensor(self, gcmd):
        _, triggered = self._query()
        probe, endstop = self._probe()
        p_trig = endstop.query_endstop(self.toolhead.get_last_move_time())
        if triggered:
            raise gcmd.error("Wägezelle meldet ohne Berührung 'ausgelöst' -"
                             " Pin/Polarität ([stepper_z] endstop_pin) prüfen"
                             " oder Düse liegt auf der Zelle")
        if p_trig:
            raise gcmd.error("Induktive Probe meldet 'ausgelöst' - Kopf zu"
                             " tief oder Probe defekt")
        self._prompt("1. Sensor-Check", [
            "Wägezelle und Probe melden in Ruhe 'frei'.",
            "Drücke jetzt die Wägezelle hinten rechts (der Stift, auf den die"
            " Düse beim Homing drückt) mit dem Finger, halte sie gedrückt und"
            " klicke dabei auf 'Jetzt gedrückt'."],
            [("Jetzt gedrückt", "CALIBRATE_SV08 STEP=SENSOR_PRESSED",
              "primary")],
            [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL", "error")])
    def _wz_sensor_pressed(self, gcmd):
        _, triggered = self._query()
        if not triggered:
            self._prompt("1. Sensor-Check", [
                "Die Wägezelle hat NICHT ausgelöst.",
                "Fester drücken und nochmal versuchen. Bleibt es so: Kabel"
                " und [stepper_z] endstop_pin (^!PE12) prüfen."],
                [("Nochmal", "CALIBRATE_SV08 STEP=SENSOR_PRESSED",
                  "warning")],
                [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL", "error")])
            return
        self._next("1. Sensor-Check", [
            "Wägezelle funktioniert.",
            "Weiter: Homing und QGL. Der Drucker bewegt sich jetzt - Hände"
            " weg."], 'HOME')
    # 2. Homing + QGL
    def _wz_home(self, gcmd):
        self._prompt_end()
        self._run("G28")
        self._run("QUAD_GANTRY_LEVEL")
        self._run("G28 Z")
        self._next("2. Homing + QGL", [
            "Erledigt. Abstand Probe/Kontakt beim Homing: %.3f mm."
            % (self.last_result.get('probe_contact_gap', 0.),),
            "Weiter: Messreihe der induktiven Probe (Geschwindigkeit x"
            " Rückzug, ca. 5-8 Minuten)."], 'PROBE_TUNE')
    # 3. Messreihe induktive Probe
    def _wz_probe_tune(self, gcmd):
        self._prompt_end()
        self._ensure_leveled()
        accel = self._z_accel()
        vmax = self._settings()['printer'].get('max_z_velocity', 100.)
        self._goto_bed_point()
        # Nachlauf je Geschwindigkeit -> Obergrenze
        cap = 0.
        for v in self.PROBE_SPEEDS:
            if v > vmax:
                break
            self.toolhead.manual_move([None, None, 10.], self.lift_speed)
            trigs, overs = self._probe_series(v, 5., 1)
            gcmd.respond_info("Probe-Nachlauf bei %.0f mm/s: %.4f mm"
                              % (v, overs[0]))
            if overs[0] > self.PROBE_MAX_OVERTRAVEL:
                break
            cap = v
        if not cap:
            raise gcmd.error("Probe läuft schon bei %.0f mm/s zu weit nach"
                             % (self.PROBE_SPEEDS[0],))
        def reference():
            self.toolhead.manual_move([None, None, 10.], self.lift_speed)
            t, o = self._probe_series(5., 5., 3)
            return sum(t) / len(t)
        ref = reference()
        results = []
        stop = False
        for v in self.PROBE_SPEEDS:
            if v > cap or stop:
                break
            for r in self.PROBE_RETRACTS:
                if trigger_speed(r, v, accel) < .95 * v:
                    gcmd.respond_info("%.0f mm/s mit %.0f mm Rückzug"
                                      " übersprungen (wird nicht erreicht)"
                                      % (v, r))
                    continue
                self.toolhead.manual_move([None, None, 10.], self.lift_speed)
                trigs, overs = self._probe_series(v, r, 10)
                mn, mx, rng, avg, med, sd = stats(trigs)
                results.append((sd, v, r, rng))
                gcmd.respond_info("Probe %.0f mm/s, Rückzug %.0f mm: range"
                                  " %.4f, stddev %.4f" % (v, r, rng, sd))
            drift = reference() - ref
            gcmd.respond_info("Drift-Check nach %.0f mm/s: %+.4f mm"
                              % (v, drift))
            if abs(drift) > self.DRIFT_LIMIT:
                # Z hat Schritte verloren: diese Geschwindigkeit verwerfen,
                # neu homen + leveln, nicht schneller testen
                results = [x for x in results if x[1] < v]
                self._run("M84")
                self._ensure_leveled()
                self._goto_bed_point()
                stop = True
        if not results:
            raise gcmd.error("Keine brauchbare Probe-Einstellung gefunden")
        results.sort()
        sd, v, r, rng = results[0]
        self._set('probe', 'speed', "%.0f" % (v,))
        self._set('probe', 'sample_retract_dist', "%.0f" % (r,))
        self.wizard['probe'] = (v, r, rng, sd)
        self._next("3. Messreihe induktive Probe", [
            "Bester Wert: %.0f mm/s mit %.0f mm Rückzug (range %.4f, stddev"
            " %.4f mm). Wird mit SAVE_CONFIG gespeichert." % (v, r, rng, sd),
            "Weiter: Messreihe der Wägezelle (ca. 5 Minuten)."],
            'LOADCELL_TUNE')
    # 4. Messreihe Wägezelle
    def _wz_loadcell_tune(self, gcmd):
        self._prompt_end()
        self._ensure_leveled()
        cx, cy = self.loadcell_xy
        self._lift_to(self.safe_z)
        self.toolhead.manual_move([cx, cy, None], self.travel_speed)
        # einmal zügig aufsetzen, damit die langsamen Messungen nur 1 mm
        # Anfahrt haben
        self._wait_release(gcmd, 10.)
        z, over, vt = self._tap(gcmd, 1., .3)
        self.toolhead.manual_move([None, None, z + 1.], self.lift_speed)
        rows = []
        for v in self.LOADCELL_SPEEDS:
            trigs = []
            for i in range(8):
                self._wait_release(gcmd, 10.)
                z, over, vt = self._tap(gcmd, v, .3)
                trigs.append(z)
                self.toolhead.manual_move([None, None, z + 1.],
                                          self.lift_speed)
            mn, mx, rng, avg, med, sd = stats(trigs)
            rows.append((v, rng, sd, avg))
            gcmd.respond_info("Wägezelle %.2f mm/s: range %.4f, stddev %.4f,"
                              " Mittel %.4f" % (v, rng, sd, avg))
        # Verzögerung = Steigung der mittleren Auslösehöhe über der
        # Geschwindigkeit, Messtakt ~ range / v
        n = len(rows)
        mv = sum(r[0] for r in rows) / n
        ma = sum(r[3] for r in rows) / n
        slope = (sum((r[0] - mv) * (r[3] - ma) for r in rows)
                 / sum((r[0] - mv) ** 2 for r in rows))
        latency = -slope
        period = sorted(r[1] / r[0] for r in rows)[n // 2]
        ok = [r for r in rows if r[1] <= self.LOADCELL_TARGET_RANGE]
        speed = max(r[0] for r in ok) if ok else self.LOADCELL_SPEEDS[0]
        # Abklingzeit
        self.toolhead.manual_move([None, None, self.toolhead.get_position()[2]
                                   + 4.], self.lift_speed)
        self._run("LOADCELL_RELEASE_TIME SPEED=0.5 RETRACT=2 REPEAT=3")
        release = self.last_result.get('release_time_max', 1.)
        timeout = max(2., 3. * release)
        self.home_speed = speed
        self.release_timeout = timeout
        self._set(self.name, 'home_speed', "%.2f" % (speed,))
        self._set(self.name, 'release_timeout', "%.1f" % (timeout,))
        self.wizard['loadcell'] = (speed, latency, period, release)
        self._next("4. Messreihe Wägezelle", [
            "Verzögerung ~%.2f s, Messtakt ~%.0f ms, Abklingzeit %.2f s."
            % (latency, period * 1000., release),
            "Feinannäherung: %.2f mm/s (Ziel: Streuung <= %.3f mm)."
            % (speed, self.LOADCELL_TARGET_RANGE),
            "Weiter: Düse reinigen (260 °C) und auf %d °C heizen."
            % (self.wizard['temp'],)], 'HEAT')
    # 5. Düse reinigen + heizen
    def _wz_heat(self, gcmd):
        self._prompt_end()
        self._ensure_leveled()
        if self.printer.lookup_object('gcode_macro CLEAN_NOZZLE', None):
            self._run("CLEAN_NOZZLE")
        self._run("M109 S%d" % (self.wizard['temp'],))
        self._next("5. Düse heiß", [
            "Düse sauber und auf %d °C." % (self.wizard['temp'],),
            "Weiter: Z-Nullpunkt messen."], 'ZOFFSET')
    # 6. Z-Nullpunkt
    def _wz_zoffset(self, gcmd):
        self._prompt_end()
        self._ensure_leveled()
        self._run("AUTO_Z_OFFSET MAX_OFFSET=5")
        gap = self.last_result.get('probe_contact_gap')
        if gap is not None:
            # bei Drucktemperatur gemessen, mit Reserve
            self.probe_contact_gap = max(0., round(gap - .25, 2))
            self._set(self.name, 'probe_contact_gap',
                      "%.2f" % (self.probe_contact_gap,))
        self._wz_paper(gcmd, first=True)
    # 7. Papiertest
    def _wz_paper(self, gcmd, first=False):
        if first:
            # Düse (nicht die Probe - deren Gehäuse sitzt tiefer) auf Z10
            # über den Messpunkt, dann auf Z1 über dem gemessenen Bett
            self._lift_to(10.)
            self.toolhead.manual_move([self.bed_xy[0], self.bed_xy[1],
                                       None], self.travel_speed)
            self._run("G90")
            self._run("G0 Z1 F600")
        adjust = gcmd.get_float('ADJUST', 0.)
        if adjust:
            self._run("SET_GCODE_OFFSET Z_ADJUST=%.3f MOVE=1" % (adjust,))
        gm = self.printer.lookup_object('gcode_move').get_status(
            self.reactor.monotonic())
        height = gm['homing_origin'].z + gm['gcode_position'].z \
            - (self.last_offset or 0.)
        btn = []
        for a in (-.5, -.1, -.05, -.01, .01, .05, .1):
            btn.append(("%+.2f" % (a,), "CALIBRATE_SV08 STEP=PAPER ADJUST=%.2f"
                        % (a,), "secondary"))
        btn.append(("Kratzt leicht - speichern", "CALIBRATE_SV08"
                    " STEP=PAPER_SAVE", "primary"))
        self._prompt("7. Papiertest", [
            "Papier unter die Düse legen (Vorsicht, heiß).",
            "Mit den Knöpfen absenken, bis das Papier beim Hin- und"
            " Herziehen leicht kratzt. Lieber in kleinen Schritten.",
            "Düse aktuell %.3f mm über der Messung." % (height,)],
            btn, [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL", "error")])
    def _wz_paper_save(self, gcmd):
        if self.last_offset is None:
            raise gcmd.error("Erst den Z-Nullpunkt messen (STEP=ZOFFSET)")
        gm = self.printer.lookup_object('gcode_move').get_status(
            self.reactor.monotonic())
        # Bett in Maschinen-Z = Babystep-Offset + G-Code-Höhe der Düse
        bed = gm['homing_origin'].z + gm['gcode_position'].z
        endstop = self._settings()['stepper_z']['position_endstop']
        corr = self.z_correction - (bed - self.last_offset)
        new_endstop = endstop - bed
        self.z_correction = corr
        self._set(self.name, 'z_correction', "%.4f" % (corr,))
        self._set('stepper_z', 'position_endstop', "%.4f" % (new_endstop,))
        self.wizard['paper'] = (bed, corr, new_endstop)
        self._run("G91")
        self._run("G0 Z10 F600")
        self._run("G90")
        self._run("M104 S0")
        self._prompt("7. Papiertest", [
            "Korrektur Zelle/PEI: %.3f mm, Z-Nullpunkt (position_endstop):"
            " %.3f mm." % (corr, new_endstop),
            "Weiter: Input Shaper messen (ADXL im Druckkopf, ca. 3 Minuten,"
            " laut) - oder überspringen."],
            [("Input Shaper messen", "CALIBRATE_SV08 STEP=SHAPER",
              "primary"),
             ("Überspringen", "CALIBRATE_SV08 STEP=FINISH", "secondary")],
            [("Abbrechen", "CALIBRATE_SV08 STEP=CANCEL", "error")])
    # 8. Input Shaper
    def _wz_shaper(self, gcmd):
        self._prompt_end()
        self._ensure_leveled()
        self._run("SHAPER_CALIBRATE")
        self.wizard['shaper'] = True
        self._wz_finish(gcmd)
    def _wz_finish(self, gcmd):
        lines = ["Übernommen (wird mit SAVE_CONFIG gespeichert):"]
        lines += self.wizard.get('saved', [])
        if self.wizard.get('shaper'):
            lines.append("Input Shaper (Werte siehe Konsole)")
        lines.append("SAVE_CONFIG startet Klipper neu.")
        self._prompt("SV08 Kalibrierung fertig", lines,
                     [("Speichern + Neustart", "SAVE_CONFIG", "primary")],
                     [("Schließen ohne Speichern",
                       "CALIBRATE_SV08 STEP=CANCEL", "secondary")])

def load_config(config):
    return SV08Loadcell(config)
