#!/usr/bin/env python3
# Hilfswerkzeug für printer.cfg (sv08-loadcell Installer)
#   cfgtool.py dedupe-autosave printer.cfg
#       Optionen im Hauptteil, die auch im SAVE_CONFIG-Block stehen, auskommentieren.
#       Klipper lässt beim Laden den Hauptteil gewinnen - ohne das würden übernommene
#       Messwerte (position_endstop, z_offset, ...) stillschweigend ignoriert.
#   cfgtool.py serials printer.cfg
#       "mcu=<serial>" und "extra_mcu=<serial>" aus einer bestehenden printer.cfg
#   cfgtool.py fill-template vorlage.cfg ziel.cfg MCU_SERIAL EXTRA_MCU_SERIAL
#   cfgtool.py moonraker-add moonraker.conf REPO_PATH ORIGIN BRANCH
#       [update_manager sv08-loadcell] eintragen, falls noch nicht vorhanden
#   cfgtool.py moonraker-timelapse moonraker.conf
#       [timelapse] und [update_manager timelapse] eintragen, falls noch nicht vorhanden
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

def serials(text):
    body, _ = split(text)
    res, sec = {}, None
    for line in body.splitlines():
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            sec = m.group(1).strip()
            continue
        m = re.match(r"^serial\s*[:=]\s*(\S+)", line)
        if m and sec in ("mcu", "mcu extra_mcu"):
            res["mcu" if sec == "mcu" else "extra_mcu"] = m.group(1)
    return res

UPDATE_SECTION = "[update_manager sv08-loadcell]"

def moonraker_add(text, repo, origin, branch):
    if UPDATE_SECTION in text:
        return text, False
    block = ("\n# sv08-loadcell (Wägezellen-Homing, Makros, Config-Vorlage)\n"
             "%s\ntype: git_repo\npath: %s\norigin: %s\nprimary_branch: %s\n"
             "managed_services: klipper\n" % (UPDATE_SECTION, repo, origin, branch))
    return text.rstrip("\n") + "\n" + block, True

TIMELAPSE_BLOCKS = [
    ("[update_manager timelapse]",
     "[update_manager timelapse]\ntype: git_repo\nprimary_branch: main\n"
     "path: ~/moonraker-timelapse\n"
     "origin: https://github.com/mainsail-crew/moonraker-timelapse.git\n"
     "managed_services: klipper moonraker\n"),
    ("[timelapse]", "[timelapse]\n"),
]

def moonraker_timelapse(text):
    added = []
    for section, block in TIMELAPSE_BLOCKS:
        if not re.search(r"^" + re.escape(section), text, re.M):
            text = text.rstrip("\n") + "\n\n" + block
            added.append(section)
    return text, added

def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "dedupe-autosave" and len(argv) == 3:
        path = argv[2]
        new, changed = dedupe(open(path).read())
        if changed:
            open(path, "w").write(new)
        for c in changed:
            print("auskommentiert: " + c)
    elif cmd == "serials" and len(argv) == 3:
        for k, v in sorted(serials(open(argv[2]).read()).items()):
            print("%s=%s" % (k, v))
    elif cmd == "fill-template" and len(argv) == 6:
        t = open(argv[2]).read()
        t = t.replace("__MCU_SERIAL__", argv[4])
        t = t.replace("__EXTRA_MCU_SERIAL__", argv[5])
        open(argv[3], "w").write(t)
    elif cmd == "moonraker-add" and len(argv) == 6:
        new, added = moonraker_add(open(argv[2]).read(), argv[3], argv[4],
                                   argv[5])
        if added:
            open(argv[2], "w").write(new)
        print("eingetragen" if added else "schon vorhanden")
    elif cmd == "moonraker-timelapse" and len(argv) == 3:
        new, added = moonraker_timelapse(open(argv[2]).read())
        if added:
            open(argv[2], "w").write(new)
        print("eingetragen: " + ", ".join(added) if added else "schon vorhanden")
    else:
        sys.exit(__doc__ or "Aufruf siehe Kopf von cfgtool.py")

if __name__ == "__main__":
    main(sys.argv)
