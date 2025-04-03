# -*- coding: utf-8 -*-
#
# This file is part of VGSync.
#
# Copyright (C) 2025 by Bernd Eller
#
# VGSync is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# VGSync is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with VGSync. If not, see <https://www.gnu.org/licenses/>.
#
# path_manager.py

import os
import platform
import shutil
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QSettings
import ctypes



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

def find_ffmpeg_folder() -> str:
    """
    1) QSettings
    2) Standard Windows paths
    3) which("ffmpeg")
    Returns a folder path or "" if none found.
    """
    # 1) QSettings
    s = QSettings("VGSync", "VGSync")
    stored_folder = s.value("paths/ffmpeg", "", type=str)
    if is_ffmpeg_in_folder(stored_folder):
        return stored_folder

    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(base_dir, "ffmpeg", "bin")
    if is_ffmpeg_in_folder(local_path):
        return local_path


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

def ensure_mpv(parent_widget) -> bool:
    """
    Stellt sicher, dass libmpv-2.dll verfügbar ist.
    1) Versucht per find_mpv_folder() etwas zu finden.
    2) Wenn nichts gefunden -> Dialog zum Ordnerauswählen.
    3) Prüft Gültigkeit -> Speichert in QSettings -> passt PATH an.
    
    Gibt True zurück, wenn am Ende alles korrekt gefunden/eingestellt wurde,
    sonst False.
    """
    s = QSettings("VGSync", "VGSync")
    folder = find_mpv_folder()

    if folder and is_valid_mpv_folder(folder):
        # Falls der Pfad aus QSettings oder Fallback kam,
        # und QSettings derzeit etwas anderes gespeichert hat:
        stored_in_settings = s.value("paths/mpv", "", type=str)
        if stored_in_settings != folder:
            s.setValue("paths/mpv", folder)
    else:
        # => Info-Meldung anzeigen, bevor wir den Datei-Dialog öffnen
        QMessageBox.information(
            parent_widget,
            "MPV library required",
            "Please select the folder where libmpv-2.dll is located.\n"
            "Example (Windows):\n"
            "  C:\\mpv\\lib\n\n"
            "This is needed for preview and playback."
        )
        chosen = QFileDialog.getExistingDirectory(parent_widget, "Select MPV Folder")
        if not chosen:
            return False
        if not is_valid_mpv_folder(chosen):
            QMessageBox.critical(
                parent_widget,
                "MPV Missing",
                f"No valid libmpv-2.dll found in:\n{chosen}"
            )
            return False

        # => store
        s.setValue("paths/mpv", chosen)
        folder = chosen

    # Nun folder und libmpv-2.dll in PATH eintragen
    mpv_dll_path = os.path.join(folder, "libmpv-2.dll")
    os.environ["MPV_LIBRARY_PATH"] = mpv_dll_path
    add_to_process_path(folder)

    # Debug-Ausgaben (optional)
    print("[DEBUG] Final MPV folder =", folder)
    print("[DEBUG] MPV_LIBRARY_PATH =", os.environ["MPV_LIBRARY_PATH"])

    return True

    
def find_mpv_folder() -> str:
    """
    Sucht nach libmpv-2.dll:
      1) QSettings
      2) lokaler Fallback mpv/lib
    Gibt einen Ordnerpfad zurück oder "" wenn nichts gefunden.
    """
    s = QSettings("VGSync", "VGSync")
    stored_folder = s.value("paths/mpv", "", type=str)
    if is_valid_mpv_folder(stored_folder):
        return stored_folder

    # Lokaler Fallback, z.B. <base_dir>/mpv/lib
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fallback_dir = os.path.join(base_dir, "mpv", "lib")
    if is_valid_mpv_folder(fallback_dir):
        return fallback_dir

    return ""
    
    

def ensure_ffmpeg(parent_widget) -> bool:
    """
    Ensures ffmpeg is available. 
    If a folder is auto-detected (standard path or which), 
    we store it in QSettings so it shows up in "Show current path".
    If not found -> prompt user to pick a folder.
    """
    s = QSettings("VGSync", "VGSync")
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
        
    def get_license_path():
        """
        Ermittelt license.lic neben app.py (bzw. dist/app).
        """
        base_dir = get_base_dir()
        return os.path.join(base_dir, "license.lic")
        
        
def is_valid_mpv_folder(folder: str) -> bool:
    """
    Prüft, ob in dem Ordner 'folder' eine libmpv-2.dll vorhanden ist 
    und ob sie sich via ctypes laden lässt.
    Gibt True zurück, falls ja.
    """
    if not folder or not os.path.isdir(folder):
        return False
    dll_path = os.path.join(folder, "libmpv-2.dll")
    if not os.path.isfile(dll_path):
        return False

    # Optional: Test via ctypes
    try:
        _ = ctypes.cdll.LoadLibrary(dll_path)
        return True
    except Exception as e:
        print(f"[WARN] libmpv-2.dll in {folder} konnte nicht geladen werden: {e}")
        return False


def ensure_mpv_library(parent_widget, base_dir: str) -> None:
    
    ensure_mpv(parent_widget)