# -*- coding: utf-8 -*-
#
# This file is part of KVRouite.
#
# Copyright (C) 2025 by Bernd Eller
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
#
# path_manager.py
#
# Sucht ffmpeg und legt es in den PATH des Prozesses.
#
# Seit 6.0 wird ffmpeg NICHT mehr mitgeliefert und nur noch vom Copy-Mode
# gebraucht. Gesucht wird deshalb ausschliesslich, was auf dem Rechner des
# Anwenders schon da ist: ein selbst gesetzter Pfad, die ueblichen
# Windows-Installationsorte, sonst der PATH. Der frueher bevorzugte Ordner
# ffmpeg/bin neben der Anwendung ist entfallen - den gibt es nicht mehr.
#
# Die libmpv-Funktionen sind ebenfalls entfallen; die Wiedergabe laeuft ueber
# GStreamer/GES, dessen Bibliotheken kommen ueber das Python-Paket bzw. die
# Distributionspakete.

import os
import platform
import shutil
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QSettings


def add_to_process_path(path_str: str):
    if not path_str:
        return
    old_path = os.environ.get("PATH", "")
    new_path = path_str + os.pathsep + old_path
    os.environ["PATH"] = new_path

#: Die beiden Programme, die der Copy-Mode braucht.
FFMPEG_WERKZEUGE = ("ffmpeg", "ffprobe")


def programmname(name: str) -> str:
    """Der Dateiname des Programms auf diesem System."""
    return name + ".exe" if platform.system() == "Windows" else name


def fehlende_werkzeuge_im_ordner(folder: str):
    """Welche der beiden Programme in `folder` fehlen.

    Leere Liste heisst: beide da. Ein Ordner mit nur ffmpeg taugt nicht -
    ffprobe indiziert die Keyframes und misst die Segmentlaengen. Frueher
    wurde nur auf ffmpeg geprueft: so ein Ordner wurde angenommen, in den PATH
    gelegt, und der Copy-Mode blieb trotzdem aus. Fuer den Anwender sah es
    aus, als haette das Setzen nichts bewirkt.
    """
    if not folder or not os.path.isdir(folder):
        return list(FFMPEG_WERKZEUGE)
    return [n for n in FFMPEG_WERKZEUGE
            if not os.path.isfile(os.path.join(folder, programmname(n)))]


def is_ffmpeg_in_folder(folder: str) -> bool:
    """True nur, wenn BEIDE Programme in dem Ordner liegen."""
    return not fehlende_werkzeuge_im_ordner(folder)

#: Was dem Anwender angezeigt wird, wenn der Copy-Mode nicht zur Verfuegung
#: steht. An einer Stelle formuliert, damit Menue, Werkzeugtipp und Log nicht
#: auseinanderlaufen.
COPY_MODE_FEHLT = ("Copy mode needs ffmpeg and ffprobe. "
                   "They were not found in your PATH.")


def fehlende_ffmpeg_werkzeuge():
    """Welche der beiden Werkzeuge fehlen. Leere Liste heisst: beide da.

    Der Copy-Mode braucht BEIDE: ffmpeg schneidet an den Keyframes mit
    "-c copy", ffprobe indiziert die Keyframes und misst die Segmentlaengen.
    Frueher wurde nur auf ffmpeg geprueft - wer nur eines von beiden hatte,
    landete in einem Modus, der beim Export scheiterte.
    """
    return [n for n in ("ffmpeg", "ffprobe") if not shutil.which(n)]


def copy_mode_moeglich() -> bool:
    return not fehlende_ffmpeg_werkzeuge()


def copy_mode_fehlgrund() -> str:
    """Kurzer Klartext fuers Log. Leer, wenn nichts fehlt."""
    fehlt = fehlende_ffmpeg_werkzeuge()
    if not fehlt:
        return ""
    return " and ".join(fehlt) + " not in PATH"


def ffmpeg_schluessel() -> str:
    """Unter welchem Namen der ffmpeg-Ordner in QSettings steht.

    macOS hat einen eigenen Namen, weil dort ganz andere Orte in Frage kommen
    und ein Rechner nicht beides gleichzeitig ist. Der Name gehoert deshalb
    hierher und nicht in die Oberflaeche: das Menue "Config -> FFmpeg" schrieb
    frueher immer nach "paths/ffmpeg", die Suche auf dem Mac las aber
    "paths/ffmpeg_mac". Wer dort einen Ordner von Hand setzte, sah ihn beim
    naechsten Start nicht wieder.
    """
    return ("paths/ffmpeg_mac"
            if platform.system() == "Darwin"
            else "paths/ffmpeg")


def gespeicherter_ffmpeg_ordner() -> str:
    """Der von Hand gesetzte Ordner, oder "" wenn keiner (mehr) gilt."""
    s = QSettings("KVRouite", "KVRouite")
    return s.value(ffmpeg_schluessel(), "", type=str) or ""


def ffmpeg_ordner_merken(ordner: str) -> None:
    QSettings("KVRouite", "KVRouite").setValue(ffmpeg_schluessel(), ordner)


def ffmpeg_ordner_vergessen() -> None:
    QSettings("KVRouite", "KVRouite").remove(ffmpeg_schluessel())


def ffmpeg_standardorte():
    """Die ueblichen Orte des jeweiligen Systems."""
    system = platform.system()
    if system == "Windows":
        return [r"C:\Program Files\FFmpeg\bin",
                r"C:\Program Files (x86)\FFmpeg\bin",
                r"C:\ffmpeg\bin"]
    if system == "Darwin":
        return ["/opt/homebrew/bin",   # Homebrew auf Apple Silicon
                "/usr/local/bin",      # Homebrew auf Intel
                "/opt/local/bin"]      # MacPorts
    return ["/usr/bin", "/usr/local/bin", "/snap/bin"]   # Linux


def find_ffmpeg_folder() -> str:
    """Wo ffmpeg liegt - auf jedem System nach derselben Reihenfolge.

    1) der von Hand gesetzte Ordner
    2) der PATH
    3) die ueblichen Orte des Systems

    Frueher gab es hierfuer zwei Funktionen, die sich in der Reihenfolge und
    in den durchsuchten Orten unterschieden; Linux hatte gar keine Liste.
    Rueckgabe ist der Ordner oder "".
    """
    stored_folder = gespeicherter_ffmpeg_ordner()
    if is_ffmpeg_in_folder(stored_folder):
        return stored_folder

    ffmpeg_exec = shutil.which("ffmpeg")
    if ffmpeg_exec:
        return os.path.dirname(ffmpeg_exec)

    for p in ffmpeg_standardorte():
        if is_ffmpeg_in_folder(p):
            return p

    return ""


def find_ffmpeg_folder_mac() -> str:
    """Frueherer Name. find_ffmpeg_folder() kann das jetzt selbst."""
    return find_ffmpeg_folder()

def ensure_ffmpeg(parent_widget) -> bool:
    """
    Ensures ffmpeg is available. 
    If a folder is auto-detected (standard path or which), 
    we store it in QSettings so it shows up in "Show current path".
    If not found -> prompt user to pick a folder.
    """
    folder = find_ffmpeg_folder()

    if folder and is_ffmpeg_in_folder(folder):
        # => falls QSettings leer oder ungültig war, aber wir 
        #    jetzt einen standard Pfad gefunden haben => in QSettings packen
        if gespeicherter_ffmpeg_ordner() != folder:
            ffmpeg_ordner_merken(folder)

        add_to_process_path(folder)
        return True
    else:
        # => Show info BEFORE opening folder dialog
        QMessageBox.information(
            parent_widget,
            "FFmpeg Required",
            "Please select the folder that contains ffmpeg and ffprobe.\n"
            "Example (Windows):\n"
            "  C:\\ffmpeg\\bin\n"
            "  C:\\Program Files\\FFmpeg\\bin\n\n"
            "Both are needed: ffmpeg cuts, ffprobe indexes the keyframes."
        )
        chosen = QFileDialog.getExistingDirectory(parent_widget, "Select FFmpeg Folder")
        if not chosen:
            return False
        fehlt = fehlende_werkzeuge_im_ordner(chosen)
        if fehlt:
            QMessageBox.critical(
                parent_widget,
                "FFmpeg Missing",
                "%s not found in:\n%s\n\n"
                "Copy mode needs %s and %s in the same folder."
                % (" and ".join(programmname(n) for n in fehlt), chosen,
                   programmname("ffmpeg"), programmname("ffprobe"))
            )
            return False

        # => store
        ffmpeg_ordner_merken(chosen)
        add_to_process_path(chosen)
        return True
        