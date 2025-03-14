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
    """
    Liest aus QSettings ("paths/mpv") den Ordnerpfad. 
    Falls valide -> nutzt diesen. 
    Sonst -> fallback auf mitgelieferte DLL im Ordner mpv/lib.
    
    Richtet dann `os.environ["MPV_LIBRARY_PATH"]` und PATH entsprechend ein.
    """
    s = QSettings("VGSync", "VGSync")
    stored_folder = s.value("paths/mpv", "", type=str)

    # Default (mitgeliefert):
    mpv_default_dir = os.path.join(base_dir, "mpv", "lib")
    mpv_default_dll = os.path.join(mpv_default_dir, "libmpv-2.dll")

    if stored_folder and is_valid_mpv_folder(stored_folder):
        # User hat einen eigenen Pfad angegeben und er ist gültig
        chosen_dir = stored_folder
    else:
        # Fallback: unsere mitgelieferte DLL
        chosen_dir = mpv_default_dir

    # MPV_LIBRARY_PATH + PATH setzen:
    os.environ["MPV_LIBRARY_PATH"] = os.path.join(chosen_dir, "libmpv-2.dll")
    old_path = os.environ.get("PATH", "")
    new_path = chosen_dir + os.pathsep + old_path
    os.environ["PATH"] = new_path

    print("[DEBUG] Final MPV folder =", chosen_dir)
    print("[DEBUG] MPV_LIBRARY_PATH =", os.environ["MPV_LIBRARY_PATH"])    