#!/usr/bin/env python3
"""Prueft, ob die GStreamer/GES-Vorschau von KVRouite auf diesem Rechner laufen kann.

Aufruf im aktivierten venv:

    python3 check_ges.py

Jeder Schritt wird einzeln gemeldet, damit bei einem Fehlschlag klar ist,
welches Paket fehlt. Startet die Anwendung nicht und veraendert nichts.
Rueckgabewert 0 = alles vorhanden, 1 = etwas fehlt.
"""

import os
import platform
import shutil
import sys

WINDOWS = platform.system() == "Windows"
LINUX = platform.system() not in ("Windows", "Darwin")

APT = ("sudo apt install python3-gi python3-gi-cairo "
       "gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-ges-1.0 "
       "gstreamer1.0-plugins-base gstreamer1.0-plugins-good "
       "gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly "
       "gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-x")
PIP = "pip install -r requirements-ges.txt"

_warnungen = []


def ok(text):
    print(f"  ok       {text}")


def warnung(text, hinweis=None):
    print(f"  Hinweis  {text}")
    if hinweis:
        print(f"           -> {hinweis}")
    _warnungen.append(text)


def fehler(text, hinweis=None):
    print(f"  FEHLT    {text}")
    print(f"           -> {hinweis if hinweis else (APT if LINUX else PIP)}")
    return False


def main():
    print(f"Python   {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")

    # --- Qt -----------------------------------------------------------------
    try:
        import PySide6
        ok(f"PySide6 {PySide6.__version__}")
    except ImportError:
        return fehler("PySide6", "pip install -r requirements.txt")

    # --- PyGObject ----------------------------------------------------------
    try:
        import gi
    except ImportError:
        return fehler(
            "PyGObject (Modul 'gi')",
            "sudo apt install python3-gi -- und das venv MIT --system-site-packages "
            "anlegen, sonst bleibt das Systempaket unsichtbar" if LINUX else PIP)
    ok(f"PyGObject {getattr(gi, '__version__', '?')}")

    pakete = {"Gst": "gir1.2-gstreamer-1.0",
              "GES": "gir1.2-ges-1.0",
              "GstVideo": "gir1.2-gst-plugins-base-1.0"}
    for name, paket in pakete.items():
        try:
            gi.require_version(name, "1.0")
        except ValueError:
            return fehler(f"Typelib {name}-1.0",
                          f"sudo apt install {paket}" if LINUX else PIP)

    from gi.repository import Gst, GES  # noqa: E402
    Gst.init(None)
    GES.init()

    # --- Version ------------------------------------------------------------
    v = Gst.version()
    ok(f"{Gst.version_string()}")
    if (v.major, v.minor) < (1, 24):
        warnung(f"GStreamer {v.major}.{v.minor} ist aelter als 1.24",
                "ungetestet - Ubuntu 24.04 liefert 1.24, 26.04 liefert 1.28")

    def vorhanden(element):
        # Das gi-Override von ElementFactory.make wirft MissingPluginError,
        # statt None zu liefern.
        try:
            return Gst.ElementFactory.make(element, None) is not None
        except Exception:
            return False

    # --- GES-Engine ---------------------------------------------------------
    registry = Gst.Registry.get()
    for plugin in ("nle", "ges"):
        if registry.find_plugin(plugin) is None:
            return fehler(f"GStreamer-Plugin '{plugin}'",
                          "sudo apt install libges-1.0-0" if LINUX else PIP)
    ok("GES-Engine (nle, ges)")

    if GES.Timeline.new_audio_video() is None:
        return fehler("GES.Timeline liess sich nicht anlegen")
    ok("GES-Timeline")

    # --- Video-Senke --------------------------------------------------------
    kandidaten = (("d3d11videosink", "d3d12videosink", "glimagesink", "autovideosink")
                  if WINDOWS else ("glimagesink", "xvimagesink", "autovideosink"))
    senken = [n for n in kandidaten if vorhanden(n)]
    if not senken:
        return fehler("Video-Senke (" + ", ".join(kandidaten) + ")",
                      "sudo apt install gstreamer1.0-gl gstreamer1.0-x" if LINUX else PIP)
    ok(f"Video-Senke: {', '.join(senken)}")

    # --- 360 Grad -----------------------------------------------------------
    # Die 360-Ansicht rechnet die Equirect-Kugel mit einem Fragment-Shader in
    # ein normales Bild um (core/view360.py). Ohne diese GL-Elemente laeuft
    # alles andere weiter, nur 360 bleibt aus.
    gl_fehlt = [n for n in ("glupload", "glcolorconvert", "glshader", "gldownload")
                if not vorhanden(n)]
    if gl_fehlt:
        warnung("360-Grad-Ansicht nicht moeglich, es fehlt: "
                + ", ".join(gl_fehlt),
                "sudo apt install gstreamer1.0-gl" if LINUX else PIP)
    else:
        ok("360-Grad-Ansicht (glupload, glshader, gldownload)")

    # --- Dekoder ------------------------------------------------------------
    dekoder = [n for n in ("avdec_h264", "openh264dec", "vah264dec", "vaapih264dec",
                           "nvh264dec", "d3d11h264dec") if vorhanden(n)]
    if not dekoder:
        return fehler("H.264-Dekoder",
                      "sudo apt install gstreamer1.0-libav gstreamer1.0-plugins-bad"
                      if LINUX else PIP)
    ok(f"H.264-Dekoder: {', '.join(dekoder)}")
    if dekoder == ["avdec_h264"] and LINUX:
        warnung("nur Software-Dekodierung gefunden",
                "fuer 4K-Material ggf. gstreamer1.0-vaapi bzw. den Treiber "
                "intel-media-va-driver / mesa-va-drivers nachinstallieren")

    # --- ffmpeg -------------------------------------------------------------
    # Seit 6.0 KEIN Abbruchgrund mehr: Wiedergabe, Vorschau samt Blenden und
    # der Export laufen ueber GStreamer. ffmpeg braucht allein der Copy-Mode -
    # und zwar beide Werkzeuge, ffmpeg zum Schneiden mit "-c copy" und ffprobe
    # zum Indizieren der Keyframes. Mitgeliefert wird es nicht mehr.
    fehlende = [w for w in ("ffmpeg", "ffprobe") if not shutil.which(w)]
    if fehlende:
        warnung("Copy-Mode nicht verfuegbar, es fehlt: " + ", ".join(fehlende),
                "sudo apt install ffmpeg" if LINUX else
                "ffmpeg installieren und in den PATH legen")
    else:
        for werkzeug in ("ffmpeg", "ffprobe"):
            ok(f"{werkzeug}: {shutil.which(werkzeug)}")

    # --- Fenstereinbettung --------------------------------------------------
    if LINUX:
        sitzung = os.environ.get("XDG_SESSION_TYPE", "")
        plattform = os.environ.get("QT_QPA_PLATFORM", "")
        if sitzung == "wayland" and plattform != "xcb":
            warnung("Wayland-Sitzung erkannt",
                    "das Video wird ueber ein X11-Fensterhandle eingebettet; "
                    "falls das Bild schwarz bleibt, mit QT_QPA_PLATFORM=xcb starten")
        else:
            ok(f"Sitzung: {sitzung or 'unbekannt'}")

    if _warnungen:
        print(f"\nAlles Noetige vorhanden, {len(_warnungen)} Hinweis(e) oben beachten.")
    else:
        print("\nAlles vorhanden.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
