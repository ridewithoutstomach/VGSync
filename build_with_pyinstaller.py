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
#####################################################

##    use --build-installer to build the installer!

######################################################
import os
import sys
import platform
import subprocess
import shutil
import importlib.util
import hashlib, zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pfad zu ffmpeg (Original-Quellen), das mit ausgeliefert wird.
LOCAL_FFMPEG = os.path.join(BASE_DIR, "ffmpeg")  # z.B. hier liegt dein ffmpeg/

# mpv wird seit 6.0 NICHT mehr mitgeliefert. Der Ordner mpv/ liegt weiterhin
# im Arbeitsverzeichnis, weil die 5.x-Zweige ihn brauchen - dieser Builder
# fasst ihn aber nicht mehr an. Dass nichts davon in den Build rutscht, prueft
# check_mpv_frei() am Ende.

# gstreamer/ enthaelt KEINE Binaries, nur die Rechtstexte (NOTICE, COMPONENTS,
# COPYING.*). Die GStreamer-DLLs selbst kommen ueber die pip-Wheels
# (gstreamer-bundle) und werden von PyInstaller aus dem venv eingesammelt.
# Der Ordner muss trotzdem mit, sonst liefern wir GPL/LGPL-Binaries ohne die
# zugehoerigen Lizenztexte aus - siehe check_gstreamer_payload().
LOCAL_GSTREAMER = os.path.join(BASE_DIR, "gstreamer")

def write_sha256(path: str) -> str:
    """
    Erzeugt neben <path> eine Datei <path>.sha256 mit Inhalt:
    <sha256>  <dateiname>
    und gibt den Pfad zur .sha256 zurück.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    out_path = path + ".sha256"
    with open(out_path, "w", encoding="ascii") as wf:
        wf.write(f"{h.hexdigest()}  {os.path.basename(path)}\n")

    print("[INFO] SHA256 geschrieben:", out_path)
    return out_path
def ensure_license_txt():
    """
    Erzeugt LICENSE.txt aus deinem Disclaimer-Text,
    falls noch keine existiert.
    """
    license_path = os.path.join(BASE_DIR, "LICENSE.txt")
    if os.path.isfile(license_path):
        print("[INFO] LICENSE.txt existiert bereits.")
        return license_path

    disclaimer_file = os.path.join(BASE_DIR, "disclaimer_dialog.py")
    if not os.path.isfile(disclaimer_file):
        print("[WARN] disclaimer_dialog.py nicht gefunden – kann LICENSE.txt nicht erzeugen.")
        return None

    # Disclaimer-Inhalt extrahieren
    try:
        text = open(disclaimer_file, "r", encoding="utf-8").read()
        # optional: nur zwischen """ ... """ falls du docstrings nutzt
        import re
        match = re.search(r'("""|\'\'\')(.*?)(\1)', text, re.S)
        license_text = match.group(2).strip() if match else text
    except Exception as e:
        print("[ERROR] Konnte disclaimer_dialog.py nicht lesen:", e)
        return None

    header = (
        "KVRouite – License & Disclaimer\n"
        "---------------------------------\n"
        "This software is distributed under the terms of the GNU GPL v3 (or later).\n"
        "By continuing, you agree to the license conditions below.\n\n"
    )

    with open(license_path, "w", encoding="utf-8") as f:
        f.write(header + license_text)

    print("[INFO] LICENSE.txt wurde neu erstellt.")
    return license_path

def check_mpv_frei(target_dir):
    """
    Gegenprobe: es darf KEIN mpv mehr im Build liegen.

    Seit 6.0 laeuft die Wiedergabe allein ueber GStreamer/GES, und libmpv wird
    nicht mehr ausgeliefert. Der Ordner mpv/ liegt aber weiterhin im
    Arbeitsverzeichnis (die 5.x-Zweige brauchen ihn), und python-mpv kann noch
    in einem venv stecken. Beides koennte unbemerkt wieder in ein Bundle
    geraten - und mit 110 MB libmpv wuerde die GPL-Quellcodepflicht wieder
    gelten, obwohl die Rechtstexte dafuer aus dem Build genommen wurden.

    Deshalb wird hier nachgesehen statt darauf zu vertrauen. Rueckgabe ist die
    Liste der Fundstellen, leer heisst sauber.
    """
    funde = []
    for root, dirs, files in os.walk(target_dir):
        rel = os.path.relpath(root, target_dir)
        for d in dirs:
            if d.lower() == "mpv":
                funde.append(os.path.join(rel, d))
        for f in files:
            n = f.lower()
            # libmpv-2.dll, mpv-1.dll, libmpv.so.2, libmpv.dylib ...
            if n.startswith(("libmpv", "mpv-")) and not n.endswith(".txt"):
                funde.append(os.path.join(rel, f))
            # das Python-Modul python-mpv
            elif n in ("mpv.py", "mpv.pyc"):
                funde.append(os.path.join(rel, f))

    print("-" * 70)
    if funde:
        print("[FEHLER] Im Build liegt noch mpv:")
        for p in sorted(set(funde))[:20]:
            print("        ", p)
        if len(set(funde)) > 20:
            print("         ... und %d weitere" % (len(set(funde)) - 20))
        print("         Ab 6.0 darf libmpv nicht mehr mit ausgeliefert werden.")
        print("         Bitte den Build verwerfen und die Ursache beheben.")
    else:
        print("[OK]     Kein mpv im Build - so soll es ab 6.0 sein.")
    print("-" * 70)
    return sorted(set(funde))


def check_gstreamer_payload(internal_dir):
    """
    Prueft, ob PyInstaller die GStreamer-Runtime tatsaechlich mit eingepackt hat.

    Warum das hier steht: core/ges_backend.py macht "import gi" auf Modulebene,
    deshalb zieht PyInstaller die Wheels aus dem venv automatisch mit - oder
    eben nicht, je nachdem aus welchem venv gebaut wird. Beide Faelle sind
    zulaessig, aber sie muessen unterschiedlich dokumentiert werden:

      - DLLs vorhanden  -> wir verbreiten GPL/LGPL-Binaries. Die Rechtstexte in
                           _internal/gstreamer und das Quellcode-Angebot darin
                           sind dann Pflicht.
      - DLLs fehlen     -> der Build ist UNBRAUCHBAR. Seit 6.0 gibt es keinen
                           zweiten Wiedergabeweg mehr; KVRouite bricht dann
                           beim Start mit einer Meldung ab.

    Die Funktion bricht nicht ab, sie sagt nur klar, welcher Fall vorliegt.
    """
    marker_dirs = [
        d for d in os.listdir(internal_dir)
        if d.startswith("gstreamer_") and os.path.isdir(os.path.join(internal_dir, d))
    ]
    gi_dir = os.path.isdir(os.path.join(internal_dir, "gi"))

    gst_dlls = 0
    for root, _dirs, files in os.walk(internal_dir):
        # den reinen Lizenzordner nicht mitzaehlen
        if os.path.basename(root) == "gstreamer":
            continue
        gst_dlls += sum(1 for f in files if f.lower().startswith("gst") and f.lower().endswith(".dll"))

    print("-" * 70)
    if marker_dirs or gi_dir or gst_dlls:
        print("[LIZENZ] GStreamer WIRD mit ausgeliefert:")
        print(f"         {gst_dlls} gst*.dll, Pakete: {', '.join(sorted(marker_dirs)) or '-'}"
              f"{', gi' if gi_dir else ''}")
        notice = os.path.join(internal_dir, "gstreamer", "NOTICE.txt")
        if os.path.isfile(notice):
            print("         Rechtstexte liegen in _internal/gstreamer - OK.")
        else:
            print("[FEHLER] _internal/gstreamer/NOTICE.txt FEHLT. So darf der Build "
                  "nicht ausgeliefert werden (GPL/LGPL-Verstoss).")
        x264 = os.path.isdir(os.path.join(internal_dir, "gstreamer_plugins_gpl_restricted"))
        print(f"         x264/x265-Plugins (GPL-2.0-or-later): {'ja' if x264 else 'nein'}"
              f"{'' if x264 else '  -> GES-Encoder kann nicht rendern!'}")
    else:
        print("[FEHLER] GStreamer ist NICHT im Build enthalten.")
        print("         Seit 6.0 laeuft Wiedergabe, Schnitt und Export allein")
        print("         darueber - dieses Bundle startet nicht. Bitte aus einem")
        print("         venv bauen, in dem requirements-ges.txt installiert ist.")
    print("-" * 70)


def load_app_version():
    config_path = os.path.join(BASE_DIR, "config.py")
    if not os.path.isfile(config_path):
        print("[ERROR] config.py nicht gefunden!")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    if not hasattr(config_module, "APP_VERSION"):
        print("[ERROR] In config.py fehlt APP_VERSION!")
        sys.exit(1)
    return config_module.APP_VERSION

def run_cmd(cmd_list):
    print("[RUN]", " ".join(cmd_list))
    subprocess.check_call(cmd_list)

def copy_tree_all(src_dir, dst_dir):
    """
    Kopiert alle Dateien/Ordner rekursiv von src_dir nach dst_dir.
    Existiert src_dir nicht, wird eine Warnung ausgegeben.
    """
    if not os.path.isdir(src_dir):
        print("[WARN] Quellverzeichnis fehlt oder ist kein Ordner:", src_dir)
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
            
            
def copy_only_pdfs(src_dir, dst_dir):
    """
    Kopiert nur PDF-Dateien aus src_dir (rekursiv) nach dst_dir.
    """
    if not os.path.isdir(src_dir):
        print("[WARN] Quellverzeichnis fehlt oder ist kein Ordner:", src_dir)
        return
    os.makedirs(dst_dir, exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                sfile = os.path.join(root, f)
                rel_path = os.path.relpath(sfile, src_dir)
                dfile = os.path.join(dst_dir, rel_path)
                os.makedirs(os.path.dirname(dfile), exist_ok=True)
                print("[COPY PDF]", sfile, "->", dfile)
                shutil.copy2(sfile, dfile)            

def build_windows(build_setup: bool = False):
    license_path = ensure_license_txt()
    app_version = load_app_version()
    print(f"[INFO] APP_VERSION: {app_version}")

    # ---------------- Basis/Ordner ----------------
    artifacts_root = os.path.join("dist", f"KVRouite_{app_version}")     # dist/KVRouite_<ver>
    os.makedirs(artifacts_root, exist_ok=True)

    exe_name_tmp = "KVRTmp"     # temporärer PyInstaller-Ordnername
    main_script  = "KVRouite.py"

    icon_file = os.path.join(BASE_DIR, "icon_icon.ico")
    if os.path.isfile(icon_file):
        print("[INFO] Icon-Datei gefunden:", icon_file)
    else:
        print("[WARN] icon_icon.ico nicht gefunden – PyInstaller nutzt Default-Icon.")

    # ---------------- PyInstaller -----------------
    # WICHTIG: --distpath = artifacts_root → erzeugt <artifacts_root>\KVRTmp
    print("[INFO] Starte PyInstaller (onedir) → Ziel:", artifacts_root)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        f"--name={exe_name_tmp}",
        f"--distpath={artifacts_root}",
        f"--icon={icon_file}" if os.path.isfile(icon_file) else "",
        main_script
    ]
    # leere Strings aus cmd entfernen
    cmd = [c for c in cmd if c]
    run_cmd(cmd)

    # ---------------- Nachbearbeitung -------------
    pyi_out_dir = os.path.join(artifacts_root, exe_name_tmp)               # dist/KVRouite_<ver>/KVRTmp
    exe_path    = os.path.join(pyi_out_dir, f"{exe_name_tmp}.exe")
    if not os.path.isfile(exe_path):
        raise RuntimeError(f"[ERROR] {exe_name_tmp}.exe fehlt in {pyi_out_dir} – PyInstaller-Build fehlgeschlagen.")

    target_dirname = f"KVRouite_{app_version}"
    target_dir     = os.path.join(artifacts_root, target_dirname)          # dist/KVRouite_<ver>/KVRouite_<ver>
    os.makedirs(target_dir, exist_ok=True)

    # EXE umbenennen auf KVRouite.exe (neben den restlichen Dateien)
    new_exe_path = os.path.join(target_dir, "KVRouite.exe")
    print(f"[MOVE] {exe_path} -> {new_exe_path}")
    shutil.move(exe_path, new_exe_path)

    # Rest aus PyInstaller-Ordner nach target_dir kopieren
    print(f"[INFO] Kopiere PyInstaller-Output nach {target_dir} …")
    for item in os.listdir(pyi_out_dir):
        src_item = os.path.join(pyi_out_dir, item)
        dst_item = os.path.join(target_dir, item)
        if item.lower() == f"{exe_name_tmp}.exe":
            continue  # EXE bereits verschoben
        if os.path.isdir(src_item):
            shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
        else:
            shutil.copy2(src_item, dst_item)

    # _internal vorbereiten + ffmpeg hinein
    internal_dir = os.path.join(target_dir, "_internal")
    os.makedirs(internal_dir, exist_ok=True)
    print("[INFO] Kopiere ffmpeg →", os.path.join(internal_dir, "ffmpeg"))
    copy_tree_all(LOCAL_FFMPEG, os.path.join(internal_dir, "ffmpeg"))
    print("[INFO] Kopiere gstreamer (Lizenztexte) →", os.path.join(internal_dir, "gstreamer"))
    if os.path.isdir(LOCAL_GSTREAMER):
        copy_tree_all(LOCAL_GSTREAMER, os.path.join(internal_dir, "gstreamer"))
    else:
        print("[WARN] gstreamer/ fehlt – die GPL/LGPL-Lizenztexte fuer GStreamer "
              "wuerden NICHT mit ausgeliefert.")

    check_gstreamer_payload(internal_dir)

    # Taskbar-Icon zusätzlich in _internal/icon
    if os.path.isfile(icon_file):
        icon_internal_dir = os.path.join(internal_dir, "icon")
        os.makedirs(icon_internal_dir, exist_ok=True)
        icon_target_path = os.path.join(icon_internal_dir, os.path.basename(icon_file))
        print("[COPY TASKBAR ICON]", icon_file, "->", icon_target_path)
        shutil.copy2(icon_file, icon_target_path)

    # GUI-Icons neben EXE (icon/)
    gui_icon_dir_src = os.path.join(BASE_DIR, "icon")
    gui_icon_dir_dst = os.path.join(target_dir, "icon")
    if os.path.isdir(gui_icon_dir_src):
        print("[COPY GUI ICONS]", gui_icon_dir_src, "->", gui_icon_dir_dst)
        copy_tree_all(gui_icon_dir_src, gui_icon_dir_dst)
    else:
        print("[INFO] GUI-Icon-Ordner fehlt – überspringe:", gui_icon_dir_src)

    # doc: nur PDFs in _internal/doc (wie zuvor)
    doc_dir = os.path.join(BASE_DIR, "doc")
    if os.path.isdir(doc_dir):
        doc_target_dir = os.path.join(internal_dir, "doc")
        print(f"[INFO] Kopiere nur PDFs aus doc/ → {doc_target_dir}")
        copy_only_pdfs(doc_dir, doc_target_dir)
        # optionales Bild
        kinomap_logo_src = os.path.join(doc_dir, "Kinomap_Logo.png")
        if os.path.isfile(kinomap_logo_src):
            kinomap_logo_dst = os.path.join(doc_target_dir, "Kinomap_Logo.png")
            os.makedirs(os.path.dirname(kinomap_logo_dst), exist_ok=True)
            print("[COPY KINOMAP LOGO]", kinomap_logo_src, "->", kinomap_logo_dst)
            shutil.copy2(kinomap_logo_src, kinomap_logo_dst)
    else:
        print("[INFO] doc/ nicht vorhanden – überspringe.")

    
    print("[INFO] Kopiere Web-Ressourcen neben die EXE (ol.css, ol.js, map_page.html) …")
    for name in ("ol.css", "ol.js", "map_page.html"):
        candidates = [
            os.path.join(BASE_DIR, name),
            os.path.join(BASE_DIR, "doc", name),
            os.path.join(BASE_DIR, "_internal", name),
            os.path.join(BASE_DIR, "_internal", "doc", name),
        ]
        src = next((p for p in candidates if os.path.isfile(p)), None)
        if src:
            dst = os.path.join(target_dir, name)  # neben KVRouite.exe
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            print("[COPY]", src, "->", dst)
            shutil.copy2(src, dst)
        else:
            print("[INFO]", name, "nicht gefunden – überspringe.")

    # GPL-Lizenz MITLIEFERN (Root-LICENSE → neben die EXE). Agreement NICHT kopieren.
    gpl_license = None
    for cand in ("LICENSE", "LICENSE.txt"):
        p = os.path.join(BASE_DIR, cand)
        if os.path.isfile(p):
            gpl_license = p
            break

    if gpl_license:
        dst = os.path.join(target_dir, "LICENSE")  # bewusst "LICENSE" (nicht Agreement)
        print("[COPY GPL]", gpl_license, "->", dst)
        shutil.copy2(gpl_license, dst)
    else:
        print("[WARN] GPL LICENSE nicht gefunden – bitte LICENSE im Projekt-Root hinterlegen.")

    # README.md NICHT mitliefern
    print("[INFO] README.md wird NICHT in den Zielordner kopiert.")


    print(f"[INFO] PyInstaller-Struktur OK: {os.path.abspath(target_dir)}")
    print("[INFO] Enthält: KVRouite.exe, ol.css, ol.js, map_page.html, icon/, _internal/…")

    # Letzte Gegenprobe, wenn nichts mehr dazukommt: kein mpv im Bundle.
    # Findet sich doch welches, wird hier abgebrochen - ein ZIP oder ein
    # Installer mit libmpv darin waere schon ausgeliefert, bevor es jemand
    # merkt, und zoege die GPL-Quellcodepflicht nach sich.
    if check_mpv_frei(target_dir):
        raise SystemExit("[ABBRUCH] Build enthaelt mpv - nicht ausliefern.")

    # ---------------- portable ZIP + SHA ----------------
    ARCH_SUFFIX = "Win_x64"
    zip_name_wo_ext = f"KVRouite_{app_version}_{ARCH_SUFFIX}"
    zip_base = os.path.join(artifacts_root, zip_name_wo_ext)
    print(f"[INFO] Erzeuge ZIP → {zip_base}.zip (Inhalt = {target_dirname}/)")
    zip_path = shutil.make_archive(
        base_name=zip_base,
        format="zip",
        root_dir=artifacts_root,      # Top ist artifacts_root
        base_dir=target_dirname       # wir packen den Ordner KVRouite_<ver> hinein
    )
    print("[INFO] ZIP erstellt:", zip_path)
    write_sha256(zip_path)

    # ---------------- Inno Setup (optional) + SHA ---------------
    if build_setup:
        print("[INFO] Erzeuge Windows-Installer (Inno Setup) …")
        # Versionstext neben EXE (nice-to-have)
        try:
            with open(os.path.join(target_dir, "version.txt"), "w", encoding="utf-8") as vf:
                vf.write(str(app_version))
        except Exception as e:
            print("[WARN] version.txt konnte nicht geschrieben werden:", e)

        iscc = os.environ.get("ISCC", r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        if not os.path.isfile(iscc):
            print("[ERROR] ISCC.exe nicht gefunden. Setze ENV ISCC oder installiere Inno Setup 6.")
            sys.exit(2)

        iss_file = os.path.join(BASE_DIR, "installer", "KVRouite.iss")
        if not os.path.isfile(iss_file):
            print("[ERROR] installer\\KVRouite.iss fehlt – kann Installer nicht bauen.")
            sys.exit(2)

        icon_in_dist = os.path.join(target_dir, "icon", "icon_icon.ico")
        if not os.path.isfile(icon_in_dist):
            icon_in_dist = icon_file if os.path.isfile(icon_file) else ""

        license_file = None
        for cand in ("LICENSE.txt", "LICENSE"):
            p = os.path.join(BASE_DIR, cand)
            if os.path.isfile(p):
                license_file = p
                break
        eula_path = os.path.join(BASE_DIR, "installer", "AGREEMENT.txt")
        if not os.path.isfile(eula_path):
            print("[ERROR] EULA/AGREEMENT fehlt: installer\\AGREEMENT.txt – ohne diese Datei breche ich den Setup-Build ab.")
            sys.exit(2)


        defines = [
            f"/DMyDistDir={os.path.abspath(target_dir)}",
            f"/DMyAppVersion={app_version}",
        ]
        
        # leere Strings aus defines filtern:
        #defines = [d for d in defines if d]
        
        if icon_in_dist:
            defines.append(f"/DMyIconFile={os.path.abspath(icon_in_dist)}")
        if license_file:
            defines.append(f"/DMyLicense={os.path.abspath(license_file)}")

        # Output nach artifacts_root
        print("[RUN] ISCC → OutputDir =", os.path.abspath(artifacts_root))
        subprocess.run([iscc, "/O" + os.path.abspath(artifacts_root)] + defines + [iss_file], check=True)

        installer_path = os.path.join(artifacts_root, f"KVRouite_v{app_version}_Win_x64_Installer.exe")
        if os.path.isfile(installer_path):
            print("[INFO] Installer erstellt:", installer_path)
            write_sha256(installer_path)
        else:
            print("[WARN] Installer nicht gefunden (erwartet):", installer_path)
    try:
        print("[CLEAN] Entferne temporären PyInstaller-Ordner:", os.path.abspath(pyi_out_dir))
        shutil.rmtree(pyi_out_dir, ignore_errors=True)
    except Exception as e:
        print("[WARN] Konnte Temp-Ordner nicht entfernen:", e)
    print()
    print(f"[INFO] Fertig. Alles liegt in: {os.path.abspath(artifacts_root)}")
    print(f"[INFO] - Ordner: {target_dirname}\\")
    print(f"[INFO] - ZIP   : KVRouite_{app_version}_Win_x64.zip (+ .sha256)")
    if build_setup:
        print(f"[INFO] - SETUP : KVRouite_Setup_v{app_version}_Win_x64.exe (+ .sha256)")




def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--build-installer", action="store_true", help="Build Windows installer via Inno Setup")
    args = p.parse_args()
    if platform.system() != "Windows":
        print("[WARN] Only Windows supported here.")
        sys.exit(1)
    build_windows(build_setup=args.build_installer)

if __name__ == "__main__":
    main()
