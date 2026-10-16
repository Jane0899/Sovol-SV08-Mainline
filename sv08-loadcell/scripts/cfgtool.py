#!/usr/bin/env python3
# Hilfswerkzeug für printer.cfg (sv08-loadcell Installer)
#   cfgtool.py dedupe-autosave printer.cfg
#       Optionen im Hauptteil, die auch im SAVE_CONFIG-Block stehen, auskommentieren.
#       Klipper lässt beim Laden den Hauptteil gewinnen - ohne das würden übernommene
#       Messwerte (position_endstop, z_offset, ...) stillschweigend ignoriert.
import re, sys

MARK = "#*# <---------------------- SAVE_CONFIG ---------------------->"

def split(text):
    i = text.find(MARK)
    if i < 0:
        return text, ""
    return text[:i], text[i:]

def autosave_options(autosave):
    opts, sec = set(), None
    for line in autosave.splitlines():
        if not line.startswith("#*#"):
            continue
        l = line[3:].strip()
        m = re.match(r"\[(.+)\]$", l)
        if m:
            sec = m.group(1).strip()
            continue
        m = re.match(r"([A-Za-z0-9_]+)\s*[:=]", l)
        if m and sec:
            opts.add((sec, m.group(1)))
    return opts

def dedupe(text):
    body, autosave = split(text)
    opts = autosave_options(autosave)
    out, sec, changed = [], None, []
    for line in body.splitlines(keepends=True):
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            sec = m.group(1).strip()
        else:
            m = re.match(r"^([A-Za-z0-9_]+)\s*[:=]", line)
            if m and sec and (sec, m.group(1)) in opts:
                changed.append("[%s] %s" % (sec, m.group(1)))
                line = "#" + line.rstrip("\n") + "  # -> Wert im SAVE_CONFIG-Block\n"
        out.append(line)
    return "".join(out) + autosave, changed

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "dedupe-autosave":
        sys.exit("Aufruf: cfgtool.py dedupe-autosave printer.cfg")
    path = sys.argv[2]
    new, changed = dedupe(open(path).read())
    if changed:
        open(path, "w").write(new)
    for c in changed:
        print("auskommentiert: " + c)
