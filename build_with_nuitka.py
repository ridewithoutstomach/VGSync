import os
import sys
import platform
import subprocess
import shutil
import stat
import importlib.util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pfade anpassen, falls deine Projektstruktur anders aussieht
LOCAL_FFMPEG = os.path.join(BASE_DIR, "ffmpeg")  # erwartet ffmpeg/bin darin
LOCAL_MPV    = os.path.join(BASE_DIR, "mpv")     # erwartet mpv/lib darin

EXTRA_FILES = [
    "map_page.html",
    "ol.js",
    "ol.css",
]

EXTRA_FOLDERS = [
    "icon",  # Icon-Ordner hinzufügen
    "doc",   # <-- Neu dazu, damit PDF und evtl. weitere Dateien kopiert werden
]

def load_app_version():
    """
    Lädt config.py dynamisch und liest daraus die Variable APP_VERSION.
    Erwartet: config.py im selben Verzeichnis wie dieses Skript.
    """
    config_path = os.path.join(BASE_DIR, "config.py")
    if not os.path.isfile(config_path):
        print("[ERROR] config.py nicht gefunden! Bitte sicherstellen, dass config.py existiert.")
        sys.exit(1)

    # Dynamisch das config-Modul laden
    spec = importlib.util.spec_from_file_location("config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    # Prüfen, ob APP_VERSION in config vorhanden ist
    if not hasattr(config_module, "APP_VERSION"):
        print("[ERROR] In config.py wurde keine Variable APP_VERSION gefunden!")
        sys.exit(1)

    return config_module.APP_VERSION

def run_cmd(cmd_list):
    print("[RUN]", " ".join(cmd_list))
    subprocess.check_call(cmd_list)

def copy_tree_all(src_dir, dst_dir):
    """Kopiert rekursiv alle Dateien und Verzeichnisse von src_dir nach dst_dir."""
    if not os.path.isdir(src_dir):
        print("[WARN] Quellverzeichnis fehlt:", src_dir)
        return
    os.makedirs(dst_dir, exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        tgt_sub = os.path.join(dst_dir, rel)
        os.makedirs(tgt_sub, exist_ok=True)
        for f in files:
            sfile = os.path.join(root, f)
            dfile = os.path.join(tgt_sub, f)
            print("[COPY]", sfile, "->", dfile)
            shutil.copy2(sfile, dfile)

def build_windows():
    # Zuerst Versionsstring laden
    app_version = load_app_version()
    print(f"[INFO] Gefundene APP_VERSION: {app_version}")

    print("[INFO] Nuitka-Build für Windows")
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--windows-icon-from-ico=icon_icon.ico",  # Anpassen oder entfernen, wenn kein Icon
        "--output-dir=dist",
        "--include-module=win32com",
        "--include-module=win32com.client",
        "--include-module=pythoncom",
        "--include-module=pywintypes",
        "app.py"
    ]
    run_cmd(cmd)

    # Nuitka legt app.exe evtl. in dist\app.exe ODER dist\app.dist\app.exe ab
    exe_candidates = [
        os.path.join("dist", "app.exe"),
        os.path.join("dist", "app.dist", "app.exe"),
    ]
    exe_path = None
    for c in exe_candidates:
        if os.path.isfile(c):
            exe_path = c
            break
    if not exe_path:
        raise RuntimeError("app.exe nicht gefunden. Prüfe Nuitka-Ausgabe in dist.")

    # Zielordner wird aus der Version gebildet, z.B. "VGSync_1.2.3"
    target_dirname = f"VGSync_{app_version}"
    target_dir = os.path.join("dist", target_dirname)
    os.makedirs(target_dir, exist_ok=True)

    # Verschieben der EXE nach VGSync_<APP_VERSION>
    # Du kannst die EXE-Datei auch umbenennen, wenn gewünscht (z.B. "VGSync.exe").
    shutil.move(exe_path, os.path.join(target_dir, "VGSync.exe"))

    # Falls Nuitka ein dist\app.dist-Verzeichnis angelegt hat, dessen Inhalt nach VGSync_<APP_VERSION> kopieren
    app_dist_dir = os.path.join("dist", "app.dist")
    if os.path.isdir(app_dist_dir):
        for item in os.listdir(app_dist_dir):
            s = os.path.join(app_dist_dir, item)
            d = os.path.join(target_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

    # --- ffmpeg kopieren ---
    # Beispiel: ffmpeg/bin in VGSync_<APP_VERSION>\ffmpeg\bin
    ffmpeg_bin_dir = os.path.join(target_dir, "ffmpeg", "bin")
    src_ffmpeg_bin = os.path.join(LOCAL_FFMPEG, "bin")  # ggf. anpassen
    copy_tree_all(src_ffmpeg_bin, ffmpeg_bin_dir)

    # --- mpv kopieren ---
    # Beispiel: mpv/lib in VGSync_<APP_VERSION>\mpv\lib
    mpv_lib_dir = os.path.join(target_dir, "mpv", "lib")
    src_mpv_lib = os.path.join(LOCAL_MPV, "lib")  # ggf. anpassen
    copy_tree_all(src_mpv_lib, mpv_lib_dir)

    # Extra-Dateien kopieren
    for f in EXTRA_FILES:
        src_f = os.path.join(BASE_DIR, f)
        if os.path.isfile(src_f):
            shutil.copy2(src_f, target_dir)
            print("[EXTRA]", f, "->", target_dir)
        else:
            print("[WARN] Datei fehlt:", f)
            
    for folder in EXTRA_FOLDERS:
        src_folder = os.path.join(BASE_DIR, folder)
        dst_folder = os.path.join(target_dir, folder)
        copy_tree_all(src_folder, dst_folder)        

    print(f"[INFO] Windows-Build fertig => dist/{target_dirname}/")

def main():
    s = platform.system()
    if s == "Windows":
        build_windows()
    else:
        print("[WARN]", s, "nicht unterstützt.")
        sys.exit(1)

if __name__ == "__main__":
    main()
