import os
import sys
import platform
import subprocess
import shutil
import importlib.util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOCAL_FFMPEG = os.path.join(BASE_DIR, "ffmpeg")  # erwartet ffmpeg/bin
LOCAL_MPV    = os.path.join(BASE_DIR, "mpv")     # erwartet mpv/lib

EXTRA_FILES = [
    "map_page.html",
    "ol.js",
    "ol.css",
]

EXTRA_FOLDERS = [
    "icon",
    "doc",
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

    spec = importlib.util.spec_from_file_location("config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

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
    # Versionsstring laden
    app_version = load_app_version()
    print(f"[INFO] Gefundene APP_VERSION: {app_version}")

    print("[INFO] PyInstaller-Build für Windows")

    # Name des Ausgabe-Unterordners / EXE
    exe_name = "app"

    # Pfad zu ffmpeg/bin/*.*
    ffmpeg_bin_glob = os.path.join(LOCAL_FFMPEG, "bin", "*.*")
    # Pfad zu mpv/lib/*.*
    mpv_lib_glob    = os.path.join(LOCAL_MPV,    "lib", "*.*")

    # PyInstaller-Befehl
    # Hier: --add-binary sorgt dafür, dass alle Dateien (DLL, EXE ...) aus ffmpeg/bin und mpv/lib
    # direkt in das gleiche Verzeichnis wie app.exe kopiert werden. So kann Windows sie sofort laden.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        f"--name={exe_name}",
        "--icon=icon_icon.ico",  # ggf. anpassen/entfernen
        "--add-binary", f"{ffmpeg_bin_glob};.",  # alles aus ffmpeg/bin in Hauptordner
        "--add-binary", f"{mpv_lib_glob};.",     # alles aus mpv/lib in Hauptordner
        "app.py"
    ]
    run_cmd(cmd)

    # PyInstaller legt exe hierhin: dist/app/app.exe
    exe_path = os.path.join("dist", exe_name, f"{exe_name}.exe")
    if not os.path.isfile(exe_path):
        raise RuntimeError(f"{exe_name}.exe nicht gefunden. Prüfe PyInstaller-Ausgabe in dist/{exe_name}.")

    # Zielordner = VGSync_<APP_VERSION>
    target_dirname = f"VGSync_{app_version}"
    target_dir = os.path.join("dist", target_dirname)
    os.makedirs(target_dir, exist_ok=True)

    # EXE umbenennen
    new_exe_path = os.path.join(target_dir, "VGSync.exe")
    shutil.move(exe_path, new_exe_path)

    # Restliche Dateien aus dist/app nach dist/VGSync_<APP_VERSION> kopieren
    app_dist_dir = os.path.join("dist", exe_name)
    for item in os.listdir(app_dist_dir):
        src_item = os.path.join(app_dist_dir, item)
        dst_item = os.path.join(target_dir, item)
        if os.path.basename(src_item) == f"{exe_name}.exe":
            # Die Original-exe ist bereits verschoben
            continue

        if os.path.isdir(src_item):
            shutil.copytree(src_item, dst_item)
        else:
            shutil.copy2(src_item, dst_item)

    # Extra-Dateien ins Ziel kopieren
    for f in EXTRA_FILES:
        src_f = os.path.join(BASE_DIR, f)
        if os.path.isfile(src_f):
            shutil.copy2(src_f, target_dir)
            print("[EXTRA]", f, "->", target_dir)
        else:
            print("[WARN] Datei fehlt:", f)

    # Extra-Ordner ins Ziel kopieren
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
