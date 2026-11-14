# TAP_TEST (experimentell): Plausibilitätsprüfung der induktiven Probe mit
# der Düse und dem Beschleunigungssensor im Druckkopf
#
# Abschnitt [sv08_tap] in sv08-loadcell.cfg. Den Symlink nach klippy/extras
# legt sv08_loadcell.py an (auch nach einem Update). Braucht [sv08_loadcell]
# für Probe, Homing und Reinigung.
#
# Copyright (C) 2026  Jane0899
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import math, time

class SV08Tap:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command(
            'TAP_TEST', self.cmd_TAP_TEST,
            desc="Experiment: Düsenkontakt an X,Y mit dem Beschleunigungs"
                 "sensor gegen die Vorhersage der induktiven Probe prüfen")
    def cmd_TAP_TEST(self, gcmd):
        # Stimmt die induktive Probe an Stelle X,Y? Vorhersage der
        # Kontakthöhe wie AUTO_Z_OFFSET (Probe über Bett und Zelle, genau
        # gehomt), dann fährt die kalte Düse bis OVERTRAVEL unter die
        # Vorhersage, der ADXL345 im Druckkopf erkennt den Aufprall. EIN
        # Versuch: kein Aufprall heißt, die Vorhersage oder die Methode stimmt
        # nicht - dann nicht tiefer fahren. CELL=1: auf das Wägezellen-Pad
        # (Kontakthöhe bekannt = position_endstop), zur Prüfung der Methode.
        # Auf dem nachgiebigen Bett nur relativ zwischen Stellen auswerten
        # Erst hier nachschlagen: [sv08_loadcell] lädt dieses Modul selbst,
        # beim Laden gibt es das Objekt noch nicht
        lc = self.printer.lookup_object('sv08_loadcell')
        th = lc.toolhead
        cell = gcmd.get_int('CELL', 0, minval=0, maxval=1)
        v = gcmd.get_float('TAP_SPEED', 30., above=0., maxval=50.)
        above = gcmd.get_float('ABOVE', 1., above=.2, maxval=3.)
        # Tiefer nur bei langsamer Fahrt (Lüfter-Methode): die Düse drückt
        # dann sanft in die Platte statt aufzuschlagen
        over = gcmd.get_float('OVERTRAVEL', .08, above=0.,
                              maxval=.3 if v <= 1. else .15)
        # Z-Beschleunigung nur für die Tippfahrt: kurze Bremsrampe, damit die
        # Düse mit fast voller Geschwindigkeit aufsetzt. Bis 50000: die Probe
        # stoppt bis 50 mm/s schlagartig ohne Schrittverlust (Messreihe Okt.
        # 2026), ein Bremsweg von v²/2a ist dagegen sanft
        tap_accel = gcmd.get_float('TAP_ACCEL', 10000., above=0.,
                                   maxval=50000.)
        min_peak = gcmd.get_float('MIN_PEAK', 5000., above=0.)
        # Aufprall erst ab so weit über der Vorhersage suchen: davor liegt
        # die Anfahrt mit ihrem Ruck
        window = gcmd.get_float('WINDOW', .3, above=0.)
        dump = gcmd.get_int('DUMP', 0, minval=0, maxval=1)
        if lc._nozzle_dirty():
            # Nach einem Druck vor dem Antippen reinigen, dann kalt blasen
            gcmd.respond_info("TAP_TEST: seit dem Druck nicht gereinigt -"
                              " reinige und kühle ab")
            if 'z' not in lc._homed():
                self.gcode.run_script_from_command("G28")
            lc._run_clean()
            for c in ("M106 S255", "M106 P1 S255",
                      "TEMPERATURE_WAIT SENSOR=extruder MAXIMUM=55",
                      "M106 S0", "M106 P1 S0"):
                self.gcode.run_script_from_command(c)
        # Kalt, weil eine heiße Düse nachläuft (der Tropfen dämpft den
        # Aufprall und bleibt kleben) und PEI ab ~217 °C weich wird. Für
        # Messreihen zur Wärmedrift MAX_TEMP anheben - dann an einer Stelle
        # abseits des Messpunkts von AUTO_Z_OFFSET tippen
        max_temp = gcmd.get_float('MAX_TEMP', 60., minval=0., maxval=230.)
        if lc._nozzle_temp() > max_temp:
            raise gcmd.error("TAP_TEST nur mit kalter Düse (unter %.0f °C,"
                             " MAX_TEMP)" % (max_temp,))
        chip = self.printer.lookup_object('adxl345', None)
        if chip is None:
            raise gcmd.error("TAP_TEST: kein [adxl345]")
        homed = lc._homed()
        if 'x' not in homed or 'y' not in homed:
            self.gcode.run_script_from_command("G28")
        # Z genau auf der Wägezelle (normales G28 homt nur grob). Nur wenn
        # nötig: Die Düsenhöhe ändert sich nur bei Schrittverlust, und den
        # prüft jeder Test danach mit der Probe
        if (gcmd.get_int('HOME', 0, minval=0, maxval=1) or not lc.z_precise
                or 'z' not in lc._homed()):
            self.gcode.run_script_from_command(
                "LOADCELL_HOME ROUGH=0 ON_BLOB=error BLOB_TOL=%.3f"
                % (gcmd.get_float('BLOB_TOL', lc.TAP_BLOB_TOL, above=0.),))
        home_gap = lc.last_result.get('probe_contact_gap')
        endstop = lc._settings()['stepper_z']['position_endstop']
        if cell:
            x, y = lc.loadcell_xy
            predicted = endstop
            bed_z = lc._probe_at(gcmd, x, y)
        else:
            x = gcmd.get_float('X'); y = gcmd.get_float('Y')
            sensor_z = lc._probe_at(gcmd, *lc.loadcell_xy)
            bed_z = lc._probe_at(gcmd, x, y)
            predicted = bed_z - sensor_z + endstop - lc.z_correction
        kin = th.get_kinematics()
        accel = tap_accel
        z_start = predicted + above
        z_end = predicted - over
        lc._lift_to(z_start + 2.)
        th.manual_move([x, y, None], lc.travel_speed)
        th.manual_move([None, None, z_start], lc.lift_speed)
        th.dwell(.3)
        aclient = chip.start_internal_client()
        th.dwell(.2)
        th.wait_moves()
        t0 = th.get_last_move_time()
        # Nur für diese eine Fahrt: Z- und Kopf-Beschleunigung hoch (die
        # Fahrt holt sich max_accel vom Kopf, gedeckelt durch max_z_accel)
        old_accel = kin.max_z_accel, th.max_accel
        kin.max_z_accel = th.max_accel = accel
        try:
            th.manual_move([None, None, z_end], v)
            t1 = th.get_last_move_time()
            th.wait_moves()
        finally:
            kin.max_z_accel, th.max_accel = old_accel
        th.dwell(.2)
        aclient.finish_measurements()
        th.manual_move([None, None, z_start + 2.], lc.lift_speed)
        contact, diag = self._find_tap(
            aclient.get_samples(), t0, t1, z_start, z_end, v, accel,
            min_peak, predicted + window,
            "/tmp/tap_test_%s.csv" % (time.strftime("%Y%m%d_%H%M%S"),)
            if dump else None)
        # Schrittverlust? Dieselbe Stelle noch einmal mit der Probe messen
        shift = lc._probe_at(gcmd, x, y) - bed_z
        if abs(shift) > .02:
            lc.z_precise = False
            raise gcmd.error("TAP_TEST: Z hat sich beim Tippen um %+.3f mm"
                             " verschoben (Schrittverlust) - Messung ungültig"
                             % (shift,))
        if contact is None:
            raise gcmd.error(
                "TAP_TEST X%.1f Y%.1f: kein Aufprall bis %.3f mm unter der"
                " Vorhersage %.3f - Vorhersage oder Methode stimmt nicht (%s)"
                % (x, y, over, predicted, diag))
        z_contact, sigma, peak = contact
        lc.last_result['tap'] = (x, y, predicted, z_contact)
        gcmd.respond_info(
            "TAP_TEST X%.1f Y%.1f: Vorhersage %.3f, Düse berührt bei %.3f ->"
            " Abweichung %+.3f mm (Aufprall mit %.1f mm/s, Rauschen %.0f,"
            " Ausschlag %.0f mm/s², Z-Kontrolle danach %+.3f mm, Abstand"
            " Probe/Kontakt beim Homing %.3f mm)" % (
                x, y, predicted, z_contact, z_contact - predicted,
                min(v, math.sqrt(2. * accel * max(0., z_contact - z_end))),
                sigma, peak, shift, home_gap or 0.)
            + (" - " + diag if dump else ""))
    def _find_tap(self, samples, t0, t1, z_start, z_end, v, accel, min_peak,
                  z_window, dump_path):
        # Fahrkurve (trapezförmig oder dreieckig: beschleunigen, ggf. konstant,
        # bremsen) für die Zeit -> Z-Zuordnung
        dist = z_start - z_end
        if dist < v * v / accel:
            v = math.sqrt(accel * dist)
        ta = v / accel
        da = .5 * accel * ta * ta
        tc = (dist - 2. * da) / v
        def z_at(t):
            t = t - t0
            if t <= 0:
                return z_start
            if t < ta:
                return z_start - .5 * accel * t * t
            if t < ta + tc:
                return z_start - da - v * (t - ta)
            t = min(t - ta - tc, ta)
            return z_start - da - v * tc - (v * t - .5 * accel * t * t)
        def med(vals):
            vals = sorted(vals)
            return vals[len(vals) // 2]
        # Grundlinie: Ruhe direkt vor der Fahrt (nur Schwerkraft)
        rest = [s for s in samples if t0 - .2 < s.time < t0]
        if len(rest) < 20:
            return None, "zu wenige Messwerte (%d)" % (len(samples),)
        axes = ('accel_x', 'accel_y', 'accel_z')
        base = [med([getattr(s, a) for s in rest]) for a in axes]
        def dev(s):
            return math.sqrt(sum((getattr(s, a) - b) ** 2
                                 for a, b in zip(axes, base)))
        sigma = med([dev(s) for s in rest]) * 1.5 + 1.
        # Anfahrt und Bremsen liegen außerhalb des Suchfensters, dazwischen
        # fährt die Düse gleichförmig: feste Schwelle über dem Rauschen
        thresh = max(8. * sigma, min_peak)
        if dump_path:
            with open(dump_path, 'w') as f:
                f.write("t,z,ax,ay,az,dev\n")
                for s in samples:
                    if t0 - .2 < s.time <= t1 + .2:
                        f.write("%.5f,%.4f,%.0f,%.0f,%.0f,%.0f\n" % (
                            s.time - t0, z_at(s.time), s.accel_x, s.accel_y,
                            s.accel_z, dev(s)))
        # Nur bis zum Beginn der Bremsrampe: das Bremsen selbst ruckt auch
        t_brake = t0 + ta + tc
        cand = [s for s in samples if t0 < s.time <= t_brake
                and z_at(s.time) <= z_window]
        if not cand:
            return None, "keine Messwerte während der Fahrt"
        top = max(cand, key=dev)
        diag = "Rauschen %.0f, größter Ausschlag %.0f mm/s² bei Z %.3f%s" % (
            sigma, dev(top), z_at(top.time),
            ", Messwerte in " + dump_path if dump_path else "")
        for i in range(len(cand) - 1):
            if dev(cand[i]) > thresh and dev(cand[i + 1]) > thresh:
                peak = max(dev(c) for c in cand[i:i + 20])
                return (z_at(cand[i].time), sigma, peak), diag
        return None, diag

def load_config(config):
    return SV08Tap(config)
