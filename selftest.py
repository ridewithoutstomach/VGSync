# -*- coding: utf-8 -*-
#
# This file is part of KVRouite.
#
# Copyright (C) 2025-2026 by Bernd Eller
#
# KVRouite is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# KVRouite is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with KVRouite. If not, see <https://www.gnu.org/licenses/>.
"""
Prueft, ob KVRouite tatsaechlich arbeitet - nicht nur startet.

    python3 selftest.py                     im Quellbaum
    KVRouite.app/Contents/MacOS/KVRouite --selftest      im fertigen Buendel
    KVRouite.exe --selftest                             im fertigen Windows-Build

Warum es diese Datei gibt: ein Startversuch beweist nur, dass der Prozess
nicht sofort abstuerzt. Ob die Anwendung ein Video schneiden und ausgeben
kann, ob sie ihre Symbole und die Kartenseite findet, ob GPX gelesen und
wieder geschrieben wird - davon sagt er nichts. Besonders bei einem gepackten
Programm ist das der Unterschied zwischen "laeuft" und "laeuft angeblich":
dort liegen die Dateien woanders als im Quellbaum, und genau daran scheitert
es erfahrungsgemaess.

Dieselben Pruefungen fuer beide Wege, damit sie nicht auseinanderlaufen: der
CI-Lauf gegen den Quellcode und der Aufruf im fertigen Buendel fuehren diesen
Code aus, nicht zwei Fassungen davon.

Rueckgabe: 0 wenn alles stimmt, 1 wenn etwas fehlt. Jeder Schritt sagt, was
er geprueft hat und was dabei herauskam.
"""

import os
import sys
import tempfile
import traceback

#: 8 Sekunden Testmaterial. Genug fuer einen Schnitt in der Mitte, kurz genug
#: fuer einen CI-Lauf.
QUELLE_SEKUNDEN = 8
QUELLE_BREITE = 640
QUELLE_HOEHE = 360
QUELLE_FPS = 30

#: Der Schnitt, der im Export geprueft wird: 3,0 s bis 5,0 s heraus, mit einer
#: Sekunde Ueberblendung. Aus 8 s werden damit rund 6 s.
SCHNITT_VON = 3.0
SCHNITT_BIS = 5.0
SCHNITT_BLENDE = 1.0

GPX_INHALT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="KVRouite-Selftest" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Selftest</name><trkseg>
    <trkpt lat="50.9400" lon="6.9600"><ele>50.0</ele><time>2026-01-01T10:00:00Z</time></trkpt>
    <trkpt lat="50.9410" lon="6.9610"><ele>55.0</ele><time>2026-01-01T10:00:02Z</time></trkpt>
    <trkpt lat="50.9420" lon="6.9620"><ele>60.0</ele><time>2026-01-01T10:00:04Z</time></trkpt>
    <trkpt lat="50.9430" lon="6.9630"><ele>58.0</ele><time>2026-01-01T10:00:06Z</time></trkpt>
    <trkpt lat="50.9440" lon="6.9640"><ele>62.0</ele><time>2026-01-01T10:00:08Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


class Bericht:
    """Sammelt, was geprueft wurde - und was dabei schieflief."""

    def __init__(self):
        self.probleme = []

    def sagen(self, text):
        print("   " + text)

    def pruefen(self, bedingung, was, warum=""):
        if bedingung:
            print("   [ok]     " + was)
        else:
            print("   [FEHLER] " + was + ((" - " + warum) if warum else ""))
            self.probleme.append(was)
        return bool(bedingung)


def schritt(nummer, titel):
    print("")
    print("=" * 70)
    print("%d. %s" % (nummer, titel))
    print("=" * 70)


# --------------------------------------------------------------- 1. Dateien
def dateien_pruefen(b: Bericht):
    """Findet die Anwendung, was mitgeliefert wurde?

    Im Quellbaum ist das selbstverstaendlich. In einem gepackten Programm
    nicht: dort liegen die Symbole neben dem Programm, das Kinomap-Logo unter
    Windows in _internal und im macOS-Buendel in Contents/Resources. Genau
    hier ist frueher jedes Symbol verschwunden, weil relative Pfade gegen das
    Arbeitsverzeichnis aufgeloest wurden.
    """
    from config import finde_datei, programm_ordner, datenordner_liste

    b.sagen("Programmordner: " + programm_ordner())
    for ort in datenordner_liste():
        b.sagen("Suchort: " + ort)

    erwartet = [
        ("map_page.html",),
        ("ol.js",),
        ("ol.css",),
        ("icon", "go_to_end.png"),
        ("icon", "cut_begin.png"),
        ("icon", "vg_sync_ring.png"),
        ("doc", "Kinomap_Logo.png"),
    ]
    for teile in erwartet:
        pfad = finde_datei(*teile)
        b.pruefen(os.path.isfile(pfad), "/".join(teile), "gesucht als " + pfad)


# ------------------------------------------------------------ 2. Oberflaeche
def symbole_pruefen(b: Bericht):
    """Lassen sich die Symbole wirklich laden - nicht nur finden?

    Ein gefundener Pfad heisst noch nicht, dass ein Bild daraus wird. Geprueft
    wird ueber denselben Weg, den die Knoepfe gehen: core.theme.icon().
    """
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])
    from core import theme

    for modus in ("light", "dark"):
        theme.anwenden(QApplication.instance(), modus)
        for name in ("icon/go_to_end.png", "icon/cut_begin.png",
                     "icon/vg_sync_ring.png", "icon/vg_icon_on2.png"):
            symbol = theme.icon(name)
            b.pruefen(not symbol.isNull(), "%s in %s" % (name, modus))


# -------------------------------------------------------------- 3. GStreamer
def gstreamer_pruefen(b: Bericht):
    """Ist die Laufzeit da, die Wiedergabe und Export tragen?"""
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    b.sagen("GStreamer " + ".".join(str(z) for z in Gst.version()[:3]))

    for name in ("x264enc", "videotestsrc", "mp4mux", "qtdemux", "videoconvert"):
        b.pruefen(Gst.ElementFactory.make(name, None) is not None,
                  "Element " + name)

    try:
        gi.require_version("GES", "1.0")
        from gi.repository import GES
        GES.init()
        zeitachse = GES.Timeline.new_audio_video()
        b.pruefen(zeitachse is not None, "GES-Zeitachse anlegen")
    except Exception as exc:
        b.pruefen(False, "GES verfuegbar", str(exc))


# ------------------------------------------------------------------- 4. GPX
def gpx_rundlauf(b: Bericht, ordner):
    """GPX lesen, exportieren, wieder lesen - kommt dasselbe heraus?"""
    from core.gpx_parser import parse_gpx, recalc_gpx_data

    quelle = os.path.join(ordner, "selftest_quelle.gpx")
    with open(quelle, "w", encoding="utf-8") as f:
        f.write(GPX_INHALT)

    punkte = parse_gpx(quelle)
    if not b.pruefen(len(punkte) == 5, "5 Punkte gelesen",
                     "bekommen: %d" % len(punkte)):
        return
    recalc_gpx_data(punkte)

    # Derselbe Schreiber, den der Menuepunkt "Export GPX..." benutzt. Er
    # braucht kein self, laesst sich also ohne Hauptfenster aufrufen.
    from views.mainwindow import MainWindow
    ziel = os.path.join(ordner, "selftest_export.gpx")
    MainWindow._save_gpx_to_file(None, punkte, ziel)
    if not b.pruefen(os.path.isfile(ziel), "GPX geschrieben"):
        return
    b.sagen("%d Bytes" % os.path.getsize(ziel))

    zurueck = parse_gpx(ziel)
    if not b.pruefen(len(zurueck) == len(punkte), "gleiche Punktzahl zurueck",
                     "%d gegen %d" % (len(punkte), len(zurueck))):
        return

    abweichungen = []
    for i, (a, z) in enumerate(zip(punkte, zurueck)):
        for feld in ("lat", "lon", "ele"):
            va, vz = a.get(feld), z.get(feld)
            if va is None or vz is None or abs(float(va) - float(vz)) > 1e-6:
                abweichungen.append("Punkt %d: %s %s != %s" % (i, feld, va, vz))
        if a.get("time") and z.get("time") and a["time"] != z["time"]:
            abweichungen.append("Punkt %d: Zeit %s != %s" % (i, a["time"], z["time"]))
    b.pruefen(not abweichungen, "Werte unveraendert",
              "; ".join(abweichungen[:3]))


# ---------------------------------------------------------------- 5. Export
def _testvideo_bauen(ziel):
    """8 Sekunden Testbild als MP4 - ohne Ton, wie der Export selbst."""
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    # Der Dateiname wird als EIGENSCHAFT gesetzt und nicht in die
    # Beschreibung geschrieben: parse_launch() liest den Text, und ein
    # Windows-Pfad verliert dabei seine Backslashes - aus C:\Users\... wurde
    # C:Users..., und das Schreiben scheiterte mit "Permission denied".
    rohr = Gst.parse_launch(
        "videotestsrc num-buffers=%d pattern=ball ! "
        "video/x-raw,width=%d,height=%d,framerate=%d/1 ! "
        "x264enc key-int-max=%d ! mp4mux ! filesink name=ziel"
        % (QUELLE_SEKUNDEN * QUELLE_FPS, QUELLE_BREITE, QUELLE_HOEHE,
           QUELLE_FPS, QUELLE_FPS))
    rohr.get_by_name("ziel").set_property("location", ziel)
    rohr.set_state(Gst.State.PLAYING)
    nachricht = rohr.get_bus().timed_pop_filtered(
        60 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    rohr.set_state(Gst.State.NULL)
    if nachricht is None:
        return "Zeitueberschreitung beim Erzeugen des Testvideos"
    if nachricht.type == Gst.MessageType.ERROR:
        return str(nachricht.parse_error())
    return None


def _messen(pfad):
    """Dauer, Codec und Bildgroesse einer Datei."""
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstPbutils", "1.0")
    from gi.repository import Gst, GstPbutils
    disc = GstPbutils.Discoverer.new(30 * Gst.SECOND)
    info = disc.discover_uri(Gst.filename_to_uri(pfad))
    spur = info.get_video_streams()[0]
    codec = spur.get_caps().to_string().split(",")[0]
    return (info.get_duration() / Gst.SECOND, codec,
            spur.get_width(), spur.get_height())


def export_rundlauf(b: Bericht, ordner):
    """Ein Video mit Schnitt und Ueberblendung ausgeben - der eigentliche Test.

    Gegangen wird derselbe Weg wie im Programm: encoder_manager ruft dort
    ges_xfade_main() mit einer JSON-Beschreibung auf.
    """
    import json

    quelle = os.path.join(ordner, "selftest_quelle.mp4")
    fehler = _testvideo_bauen(quelle)
    if not b.pruefen(fehler is None, "Testvideo erzeugt", fehler or ""):
        return
    dauer, codec, breite, hoehe = _messen(quelle)
    b.sagen("Quelle: %.2fs, %s, %dx%d, %d Bytes"
            % (dauer, codec, breite, hoehe, os.path.getsize(quelle)))

    ziel = os.path.join(ordner, "selftest_export.mp4")
    cfg_pfad = os.path.join(ordner, "selftest_cfg.json")
    cfg = {
        "videos": [quelle],
        "skip_instructions": [[SCHNITT_VON, SCHNITT_BIS, SCHNITT_BLENDE]],
        "overlay_instructions": [],
        "final_output": ziel,
        "encoder": "libx264",
        "hardware_encode": "none",
        "crf": 28,
        "fps": "%d/1" % QUELLE_FPS,
        "width": QUELLE_BREITE,
    }
    with open(cfg_pfad, "w", encoding="utf-8") as f:
        json.dump(cfg, f)

    from managers.ges_encoder_manager import ges_xfade_main
    print("   --- Ausgabe des Renderlaufs ---")
    try:
        ges_xfade_main(cfg_pfad)
    except Exception as exc:
        b.pruefen(False, "Export gelaufen", str(exc))
        return
    print("   --- Ende ---")

    if not b.pruefen(os.path.isfile(ziel), "Datei erzeugt"):
        return
    groesse = os.path.getsize(ziel)
    dauer_z, codec_z, breite_z, hoehe_z = _messen(ziel)
    b.sagen("Ergebnis: %.2fs, %s, %dx%d, %d Bytes"
            % (dauer_z, codec_z, breite_z, hoehe_z, groesse))

    erwartet = QUELLE_SEKUNDEN - (SCHNITT_BIS - SCHNITT_VON)
    b.pruefen(groesse > 10000, "Datei nicht leer", "%d Bytes" % groesse)
    b.pruefen(abs(dauer_z - erwartet) <= 1.0,
              "Dauer rund %.0fs nach dem Schnitt" % erwartet,
              "gemessen %.2fs" % dauer_z)
    b.pruefen("h264" in codec_z, "h264 kodiert", codec_z)
    b.pruefen((breite_z, hoehe_z) == (QUELLE_BREITE, QUELLE_HOEHE),
              "Bildgroesse unveraendert", "%dx%d" % (breite_z, hoehe_z))


# ------------------------------------------------------------------- Ablauf
def alles_pruefen(ordner=None):
    """Alle Schritte. Rueckgabe: 0 wenn alles stimmt, sonst 1."""
    eigener_ordner = ordner is None
    if eigener_ordner:
        ordner = tempfile.mkdtemp(prefix="kvrouite_selftest_")

    print("KVRouite Selbsttest")
    print("Arbeitsordner:", ordner)
    print("Programm:", sys.executable)
    print("gepackt:", bool(getattr(sys, "frozen", False)))

    b = Bericht()
    aufgaben = (
        ("Mitgelieferte Dateien", lambda: dateien_pruefen(b)),
        ("Symbole laden", lambda: symbole_pruefen(b)),
        ("GStreamer und GES", lambda: gstreamer_pruefen(b)),
        ("GPX lesen, schreiben, wieder lesen", lambda: gpx_rundlauf(b, ordner)),
        ("Video schneiden und ausgeben", lambda: export_rundlauf(b, ordner)),
    )
    for nummer, (titel, aufgabe) in enumerate(aufgaben, 1):
        schritt(nummer, titel)
        try:
            aufgabe()
        except Exception:
            print("   [FEHLER] Der Schritt brach ab:")
            for zeile in traceback.format_exc().splitlines():
                print("      " + zeile)
            b.probleme.append(titel + " (Abbruch)")

    print("")
    print("=" * 70)
    if b.probleme:
        print("ERGEBNIS: %d Punkt(e) stimmen nicht:" % len(b.probleme))
        for p in b.probleme:
            print("   -", p)
        print("=" * 70)
        return 1
    print("ERGEBNIS: Alles geprueft und in Ordnung.")
    print("=" * 70)
    return 0


def main():
    # Ohne Bildschirm laufen lassen, wenn keiner da ist - der Test braucht
    # kein Fenster, und auf einem Bauserver gibt es keins.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return alles_pruefen()


if __name__ == "__main__":
    sys.exit(main())
