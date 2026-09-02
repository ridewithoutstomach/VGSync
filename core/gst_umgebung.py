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
# You should have received a copy of the GNU General Public License
# along with KVRouite. If not, see <https://www.gnu.org/licenses/>.
"""
GStreamer im gepackten Programm auffindbar machen - ohne die Wheels zu fragen.

Normalerweise erledigt das gstreamer_libs.setup_python_environment(): sie
rechnet die Pfade aus der Lage der Pakete in site-packages aus. In einem
gepackten Programm gibt es kein site-packages mehr, und im macOS-Buendel
scheitert sie deshalb mit

    Couldn't find site-packages prefix inside .../Contents/Frameworks/gstreamer_python

Die Folge ist nicht harmlos: ohne GI_TYPELIB_PATH findet "import gi" die
Typelibs nicht, und damit faellt alles aus - Wiedergabe, Vorschau, Export.
Gemessen am ersten macOS-Buendel vom 02.09.2026: "Typelib file for namespace
'GObject', version '2.0' not found".

Hier wird dieselbe Umgebung aus dem aufgebaut, was tatsaechlich da ist: den
Ordnern der gstreamer-Pakete neben dem Programm. Unter Windows springt das
nicht ein - dort funktioniert der Weg der Wheels.
"""

import os
import sys

#: Pakete, die Typelibs mitbringen (lib/girepository-1.0).
TYPELIB_PAKETE = ("gstreamer_python", "gstreamer_gtk", "gstreamer_libs")

#: Pakete, die Plugins mitbringen (lib/gstreamer-1.0).
PLUGIN_PAKETE = (
    "gstreamer_cli", "gstreamer_plugins_gpl_restricted", "gstreamer_plugins_gpl",
    "gstreamer_plugins_restricted", "gstreamer_plugins_libs", "gstreamer_plugins",
    "gstreamer_python", "gstreamer_gtk", "gstreamer_libs",
)

#: Wo die Bibliotheken liegen. Windows legt sie nach bin/, die anderen nach lib/.
BIBLIOTHEK_ORDNER = ("bin", "lib")


def _wurzeln():
    """Wo die gstreamer-Pakete im gepackten Programm liegen koennen.

    sys._MEIPASS ist im macOS-Buendel Contents/Frameworks und unter Windows
    der Ordner _internal - in beiden Faellen genau dort, wo --collect-all die
    Pakete abgelegt hat.
    """
    orte = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        orte.append(meipass)
    orte.append(os.path.dirname(os.path.abspath(sys.executable)))
    return [o for o in orte if o and os.path.isdir(o)]


def _sammeln(pakete, *unterordner):
    """Alle vorhandenen <wurzel>/<paket>/<unterordner> - Reihenfolge bleibt."""
    gefunden = []
    for wurzel in _wurzeln():
        for paket in pakete:
            pfad = os.path.join(wurzel, paket, *unterordner)
            if os.path.isdir(pfad) and pfad not in gefunden:
                gefunden.append(pfad)
    return gefunden


def umgebung_aufbauen():
    """Die Umgebungsvariablen setzen. Rueckgabe: was gesetzt wurde.

    Bereits gesetzte Werte werden nicht ueberschrieben, sondern ergaenzt: wer
    von aussen einen eigenen Plugin-Pfad mitgibt, soll ihn behalten.
    """
    gesetzt = {}

    def dazu(name, pfade):
        if not pfade:
            return
        vorher = os.environ.get(name, "")
        teile = [p for p in pfade if p not in vorher.split(os.pathsep)]
        if not teile:
            return
        neu = os.pathsep.join(teile + ([vorher] if vorher else []))
        os.environ[name] = neu
        gesetzt[name] = neu

    typelibs = _sammeln(TYPELIB_PAKETE, "lib", "girepository-1.0")
    dazu("GI_TYPELIB_PATH", typelibs)

    plugins = _sammeln(PLUGIN_PAKETE, "lib", "gstreamer-1.0")
    dazu("GST_PLUGIN_PATH_1_0", plugins)
    dazu("GST_PLUGIN_SYSTEM_PATH_1_0", plugins)

    bibliotheken = []
    for ordner in BIBLIOTHEK_ORDNER:
        bibliotheken += _sammeln(PLUGIN_PAKETE + TYPELIB_PAKETE, ordner)
    if sys.platform == "win32":
        dazu("PATH", bibliotheken)
        dll_ordner = _sammeln(("gstreamer_libs",), "bin")
        dazu("PYGI_DLL_DIRS", dll_ordner)
    else:
        # macOS und Linux suchen ueber den dynamischen Lader.
        dazu("DYLD_LIBRARY_PATH" if sys.platform == "darwin"
             else "LD_LIBRARY_PATH", bibliotheken)

    # Der Plugin-Scanner ist ein eigenes Programm. Fehlt er, meldet GStreamer
    # "External plugin loader failed" und laedt die Plugins im eigenen Prozess
    # weiter - unschoen, aber kein Abbruch.
    for wurzel in _wurzeln():
        scanner = os.path.join(wurzel, "gstreamer_libs", "libexec",
                               "gstreamer-1.0", "gst-plugin-scanner")
        if sys.platform == "win32":
            scanner += ".exe"
        if os.path.isfile(scanner):
            os.environ["GST_PLUGIN_SCANNER_1_0"] = scanner
            gesetzt["GST_PLUGIN_SCANNER_1_0"] = scanner
            # Ohne Ausfuehrungsrecht nuetzt er nichts - im Wheel fehlt es
            # gelegentlich, gemeldet als "isn't executable".
            try:
                if not os.access(scanner, os.X_OK):
                    os.chmod(scanner, 0o755)
            except Exception:
                pass
            break

    return gesetzt


def bericht():
    """Was gerade gilt - fuer die Fehlersuche."""
    zeilen = []
    for name in ("GI_TYPELIB_PATH", "GST_PLUGIN_PATH_1_0",
                 "GST_PLUGIN_SCANNER_1_0", "PYGI_DLL_DIRS",
                 "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
        wert = os.environ.get(name)
        if wert:
            zeilen.append("%s = %s" % (name, wert))
    return zeilen
