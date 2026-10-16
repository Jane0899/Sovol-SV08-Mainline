# Sovol SV08: Z-Homing auf der Wägezelle + automatischer Z-Offset
#
# Die Wägezelle hinten rechts (Sovol "probe_pressure", PE12) ist der
# stepper_z-Endstop. Sie reagiert träge (~0,15 s Verzögerung, ~80 ms
# Messtakt), deshalb:
#   LOADCELL_HOME  - induktive Probe grob und schnell über der Zelle, dann
#                    Düse ganz langsam (0,1 mm/s) auf die Zelle
#   AUTO_Z_OFFSET  - Düse auf Zelle (= Z-Referenz), induktive Probe über der
#                    Zelle und am Bett -> SET_GCODE_OFFSET Z
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
                ('RETRACT_TIME', "Dauer einer Z-Fahrt berechnen")]:
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

def load_config(config):
    return SV08Loadcell(config)
