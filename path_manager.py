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

def is_ffmpeg_in_folder(folder: str) -> bool:
    if not folder or not os.path.isdir(folder):
        return False
    exe_name = "ffmpeg.exe" if platform.system().lower().startswith("win") else "ffmpeg"
    path_exe = os.path.join(folder, exe_name)
    return os.path.isfile(path_exe)

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


def find_ffmpeg_folder() -> str:
    """
    1) QSettings
    2) Standard Windows paths
    3) which("ffmpeg")
    Returns a folder path or "" if none found.
    """
    # 1) QSettings
    s = QSettings("KVRouite", "KVRouite")
    stored_folder = s.value("paths/ffmpeg", "", type=str)
    if is_ffmpeg_in_folder(stored_folder):
        return stored_folder

    # 2) Windows standard paths
    if platform.system().lower().startswith("win"):
        possible_paths = [
            r"C:\Program Files\FFmpeg\bin",
            r"C:\Program Files (x86)\FFmpeg\bin",
            r"C:\ffmpeg\bin"
        ]
        for p in possible_paths:
            if is_ffmpeg_in_folder(p):
                return p

    # 3) which("ffmpeg")
    ffmpeg_exec = shutil.which("ffmpeg")
    if ffmpeg_exec:
        return os.path.dirname(ffmpeg_exec)

    return ""

def ensure_ffmpeg(parent_widget) -> bool:
    """
    Ensures ffmpeg is available. 
    If a folder is auto-detected (standard path or which), 
    we store it in QSettings so it shows up in "Show current path".
    If not found -> prompt user to pick a folder.
    """
    s = QSettings("KVRouite", "KVRouite")
    folder = find_ffmpeg_folder()

    if folder and is_ffmpeg_in_folder(folder):
        # => falls QSettings leer oder ungültig war, aber wir 
        #    jetzt einen standard Pfad gefunden haben => in QSettings packen
        stored_in_settings = s.value("paths/ffmpeg", "", type=str)
        if stored_in_settings != folder:
            s.setValue("paths/ffmpeg", folder)

        add_to_process_path(folder)
        return True
    else:
        # => Show info BEFORE opening folder dialog
        QMessageBox.information(
            parent_widget,
            "FFmpeg Required",
            "Please select the folder where FFmpeg is installed.\n"
            "Example (Windows):\n"
            "  C:\\ffmpeg\\bin\n"
            "  C:\\Program Files\\FFmpeg\\bin\n\n"
            "This is needed for video cutting and export."
        )
        chosen = QFileDialog.getExistingDirectory(parent_widget, "Select FFmpeg Folder")
        if not chosen:
            return False
        if not is_ffmpeg_in_folder(chosen):
            QMessageBox.critical(
                parent_widget,
                "FFmpeg Missing",
                f"No valid ffmpeg executable found in:\n{chosen}"
            )
            return False

        # => store
        s.setValue("paths/ffmpeg", chosen)
        add_to_process_path(chosen)
        return True
        
def find_ffmpeg_folder_mac() -> str:
    """
    macOS: Sucht nach ffmpeg (ohne .exe):
      1) QSettings
      2) which("ffmpeg")
      3) Mehrere Standardpfade (Homebrew, MacPorts, ...)
      4) Falls nichts gefunden -> ""
    """
    s = QSettings("KVRouite", "KVRouite")
    stored_folder = s.value("paths/ffmpeg_mac", "", type=str)
    if is_ffmpeg_in_folder(stored_folder):
        return stored_folder

    # 2) systemweiter PATH prüfen
    ffmpeg_exec = shutil.which("ffmpeg")
    if ffmpeg_exec:
        return os.path.dirname(ffmpeg_exec)

    # 3) Liste mit Standardpfaden (einfach erweiterbar)
    possible_ffmpeg_dirs = [
        "/usr/local/bin",     # Homebrew (Intel)
        "/opt/homebrew/bin",  # Homebrew (Apple Silicon)
        "/opt/local/bin",     # MacPorts
        # Hier kannst du beliebige weitere Pfade ergänzen:
        # "/Applications/ffmpeg/bin",
        # "/User/DeinName/Programme/ffmpeg/bin",
        # usw.
    ]
    for pathdir in possible_ffmpeg_dirs:
        if is_ffmpeg_in_folder(pathdir):
            return pathdir

    # 4) Keiner der Pfade war erfolgreich
    return ""


def ensure_ffmpeg_mac(parent_widget) -> bool:
    """
    Stellt sicher, dass ffmpeg (macOS) verfügbar ist.
    1) Versucht find_ffmpeg_folder_mac().
    2) Falls nicht gefunden -> lässt User den Ordner wählen.
    3) Prüft ffmpeg-Executable -> schreibt in QSettings -> PATH
    """
    s = QSettings("KVRouite", "KVRouite")
    folder = find_ffmpeg_folder_mac()

    if folder and is_ffmpeg_in_folder(folder):
        stored_in_settings = s.value("paths/ffmpeg_mac", "", type=str)
        if stored_in_settings != folder:
            s.setValue("paths/ffmpeg_mac", folder)

        add_to_process_path(folder)
        return True
    else:
        QMessageBox.information(
            parent_widget,
            "FFmpeg Required (macOS)",
            "Please choose the folder that contains ffmpeg.\n\n"
            "Example:\n"
            "  /usr/local/bin\n"
            "  /opt/homebrew/bin\n\n"
            "Without FFmpeg, video cutting and export are not possible."
        )
        chosen = QFileDialog.getExistingDirectory(parent_widget, "Select FFmpeg Folder (macOS)")
        if not chosen:
            return False
        if not is_ffmpeg_in_folder(chosen):
            QMessageBox.critical(
                parent_widget,
                "FFmpeg Missing (macOS)",
                f"No valid ffmpeg executable in:\n{chosen}"
            )
            return False

        s.setValue("paths/ffmpeg_mac", chosen)
        add_to_process_path(chosen)
        return True    
    