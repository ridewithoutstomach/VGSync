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

import os
import sys
import shutil
import platform





# --- Debug/Verbose-Schalter + Konsole behandeln (nur Windows) ---
import sys, platform, builtins

REAL_STDOUT = sys.__stdout__
REAL_STDERR = sys.__stderr__

def force_print(*args, sep=" ", end="\n"):
    REAL_STDOUT.write(sep.join(map(str, args)) + end)
    REAL_STDOUT.flush()

def force_error(*args, sep=" ", end="\n"):
    REAL_STDERR.write(sep.join(map(str, args)) + end)
    REAL_STDERR.flush()
def _is_verbose():
    a = " ".join(sys.argv).lower()
    if " -v" in a or " --verbose" in a:
        return True
    try:
        from PySide6.QtCore import QSettings
        if QSettings("KVRouite","KVRouite").value("app/debug", False, type=bool):
            return True
    except Exception:
        pass
    return False

DEBUG = _is_verbose()

# Python-Prints im Non-Verbose vollständig stummschalten (ohne Performance-Kosten)
if not DEBUG:
    def _noop_print(*args, **kwargs): 
        return None
    builtins.print = _noop_print

    class _NullWriter:
        def write(self, *_args, **_kw): return 0
        def flush(self): pass
    # Nur Python-Ausgaben stumm – ffmpeg/QProcess unaffected
    sys.stdout = _NullWriter()
    sys.stderr = _NullWriter()

if platform.system() == "Windows":
    try:
        import ctypes, ctypes.wintypes as wt
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32

        hwnd = k32.GetConsoleWindow()
        if hwnd:
            # Titel setzen (auch wenn Fenster versteckt ist)
            k32.SetConsoleTitleW("KVRouite DEBUG Konsole" if DEBUG else "KVRouite Konsole - Don’t Close")

            if not DEBUG:
                # Konsole 'optisch leer' machen: Puffer löschen
                # 1) Screen-Buffer-Info holen
                class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                    _fields_ = [
                        ("dwSize", wt._COORD),
                        ("dwCursorPosition", wt._COORD),
                        ("wAttributes", ctypes.c_ushort),
                        ("srWindow", wt.SMALL_RECT),
                        ("dwMaximumWindowSize", wt._COORD),
                    ]
                hStdOut = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                csbi = CONSOLE_SCREEN_BUFFER_INFO()
                if k32.GetConsoleScreenBufferInfo(hStdOut, ctypes.byref(csbi)):
                    buf_cells = csbi.dwSize.X * csbi.dwSize.Y
                    # 2) Zeichen + Attribute mit Leerraum füllen
                    chars_written = wt.DWORD(0)
                    k32.FillConsoleOutputCharacterW(hStdOut, ctypes.c_wchar(' '), buf_cells, wt._COORD(0, 0), ctypes.byref(chars_written))
                    k32.FillConsoleOutputAttribute(hStdOut, csbi.wAttributes, buf_cells, wt._COORD(0, 0), ctypes.byref(chars_written))
                    # 3) Cursor auf 0,0
                    k32.SetConsoleCursorPosition(hStdOut, wt._COORD(0, 0))
                    force_print("====   KVRouite DEBUG Konsole    ====")
                    force_print("====         Don´t Close!        ====")
                    force_print("==== closing will close the APP! ====")
                    
                # 4) Fenster unsichtbar (Konsole bleibt vorhanden → Performance ok)
                
                SW_HIDE = 0
                u32.ShowWindow(hwnd, SW_HIDE)
            else:
                # Debug sichtbar lassen – optional Banner
                try:
                    force_print("==== KVRouite DEBUG Konsole ====")
                except Exception:
                    pass
    except Exception:
        pass




# ++ADD++  (Mac-spezifischer Monkeypatch + locale Setting)
current_os = platform.system()
if current_os == "Darwin":
    import ctypes.util
    import locale

    old_find_library = ctypes.util.find_library

    def custom_find_library(name: str) -> str:
        if name == "mpv":
            # Beispiel: Pfad zur Homebrew-liegenden libmpv.2.dylib
            return "/opt/homebrew/lib/libmpv.2.dylib"
        return old_find_library(name)

    ctypes.util.find_library = custom_find_library
    locale.setlocale(locale.LC_NUMERIC, "C")
# ++ADD++ Ende Mac-Patch

base_dir = os.path.dirname(os.path.abspath(__file__))

## das ist für die map:
os.environ["QSG_RHI_BACKEND"] = "opengl"

def resource_path(rel_path: str) -> str:
    """
    Gibt den absoluten Pfad zu einer Ressource (z.B. Icon) zurück.
    Funktioniert sowohl im normalen Python-Modus als auch im PyInstaller-Bundle.
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.join(base_dir, rel_path)

# ---------------------------------------------------------
# Zuerst mpv-Pfad einstellen, bevor wir "import mpv" machen
import path_manager

# wurde nach untern verschoben, damit wir den Pfad or dem laden angeben können ( mac)
#path_manager.ensure_mpv_library(parent_widget=None, base_dir=base_dir)

# ---------------------------------------------------------
# Jetzt erst den Rest importieren
import urllib.request
import datetime
import config
import path_manager  # zweites Mal import ist okay

# Qt-Sachen
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget, QSystemTrayIcon
from PySide6.QtCore import Qt, QTimer, qInstallMessageHandler

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView #apparently we need to import it before the app starts


def _qt_message_handler(mode, context, message):
    """Qt-Meldungen filtern.

    Beim Detach der Karte wandert die QWebEngineView in ein zweites
    Top-Level-Fenster. Jedes Fenster hat seine eigene QRhi, Chromium haengt
    seine Kompositor-Textur aber an die QWebEnginePage - die Textur des
    alten Fensters wird also im neuen weiterbenutzt. Qt meldet das bei
    jedem Bildaufbau, es sind pro Detach schnell hunderte Zeilen.

    Gemessen: die Karte wird dabei korrekt dargestellt, es ist eine Warnung
    und kein Defekt. Weder AA_ShareOpenGLContexts noch das RHI-Backend noch
    ein Neuaufbau der View aendern etwas daran; nur ein Neuaufbau samt Page
    haette geholfen, der kostet aber je Detach einen Renderer-Prozess.
    Deshalb wird die Meldung im Normalbetrieb geschluckt und ist mit -v
    weiterhin vollstaendig zu sehen. Alle anderen Qt-Meldungen bleiben
    unangetastet - QT_LOGGING_RULES greift hier nicht, weil Qt die Zeile
    ohne Logging-Kategorie ausgibt.
    """
    if not DEBUG and "belongs to QRhi" in message:
        return
    try:
        REAL_STDERR.write(message + "\n")
        REAL_STDERR.flush()
    except Exception:
        pass


qInstallMessageHandler(_qt_message_handler)

# Dein eigenes Zeug:
from config import (
    LOCAL_VERSION,
    TMP_KEYFRAME_DIR,
    MY_GLOBAL_TMP_DIR,
    is_disclaimer_accepted,
    set_disclaimer_accepted
)
from views.disclaimer_dialog import DisclaimerDialog
#from views.mainwindow import MainWindow

# NTP, JSON, etc.
#import ntplib
import json
from datetime import datetime as dt, timezone

# ---------------------------------------------------------
# Funktionen & Main

def clear_temp_segments_dir():
    if os.path.exists(MY_GLOBAL_TMP_DIR):
        try:
            shutil.rmtree(MY_GLOBAL_TMP_DIR)
        except Exception as e:
            print(f"[WARN] Could not remove temp directory: {e}")
    os.makedirs(MY_GLOBAL_TMP_DIR, exist_ok=True)


def center_mainwindow(window):
    frame_geo = window.frameGeometry()
    center_point = window.screen().availableGeometry().center()
    frame_geo.moveCenter(center_point)
    window.move(frame_geo.topLeft())


def _file_arg_from_cli(argv):
    """Erste uebergebene existierende Datei aus der Kommandozeile.

    Wird von der Windows-Dateizuordnung benutzt: der Installer traegt
    "KVRouite.exe" "%1" als Open-Befehl fuer .KVRouiteproj ein, Windows
    haengt beim Doppelklick den Pfad an. Optionen wie -v werden ignoriert.
    """
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        if os.path.isfile(arg):
            return os.path.abspath(arg)
    return None


def main():
    # Workaround bei manchen Grafikkarten
    
    
    if config.is_soft_opengl_enabled():
        QGuiApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)

    # QtWebEngine (Karte) und mpv (Video) leben im selben Prozess und nutzen
    # beide OpenGL. Ohne geteilten Kontext verliert die Karte ab Qt 6.11 ihren
    # Inhalt, sobald sie ueber "Map (detach)" in ein eigenes Fenster wandert -
    # das Fenster bleibt dann schwarz. Muss VOR QApplication(...) gesetzt
    # werden, sonst wirkt es nicht. Unter Qt 6.8 aendert es nichts, es ist also
    # ein Codepfad fuer beide Versionen.
    QGuiApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv)
    
    
    current_os = platform.system()
    
    # Zuerst mpv-Pfad einstellen, bevor wir "import mpv" machen
    #path_manager.ensure_mpv_library(parent_widget=None, base_dir=base_dir)
    # dann erst mainwindow starten:
    
    # mpv und ffmpeg sind KEINE Startbedingungen mehr.
    #
    # Gebraucht werden sie nur noch fuer den mpv-Player, den Copy-Mode und die
    # ffmpeg-Render-Engine. Wiedergabe und Vorschau samt Blenden, Bildraten,
    # Laengen, Drehung, Hardware-Erkennung, GoPro-Telemetrie und der Export
    # laufen ueber GStreamer. Beides wird deshalb nur noch GESUCHT und, wenn
    # vorhanden, in den PATH gelegt. Fehlt es, gibt es eine Zeile im Log und
    # sonst nichts.
    #
    # Bewusst NICHT ueber path_manager.ensure_mpv() / ensure_ffmpeg(): die
    # oeffnen bei Misserfolg einen Ordner-Dialog. Genau das soll beim Start
    # nicht mehr passieren.
    if current_os not in ("Windows", "Darwin", "Linux"):
        QMessageBox.critical(
            None, "Unsupported OS",
            f"Dein Betriebssystem ({current_os}) wird derzeit nicht unterstützt.")
        sys.exit(1)

    if current_os == "Windows":
        mpv_ordner = path_manager.find_mpv_folder()
        if mpv_ordner and path_manager.is_valid_mpv_folder(mpv_ordner):
            os.environ["MPV_LIBRARY_PATH"] = os.path.join(mpv_ordner, "libmpv-2.dll")
            path_manager.add_to_process_path(mpv_ordner)
            print("[DEBUG] MPV_LIBRARY_PATH =", os.environ["MPV_LIBRARY_PATH"])
        else:
            print("[WARN] libmpv nicht gefunden - der mpv-Player steht nicht "
                  "zur Verfuegung, GES laeuft davon unabhaengig.")
    elif current_os == "Darwin":
        mpv_ordner = path_manager.find_mpv_folder_mac()
        if mpv_ordner and path_manager.is_valid_mpv_folder_mac(mpv_ordner):
            for name in ("libmpv.1.dylib", "libmpv.dylib"):
                pfad = os.path.join(mpv_ordner, name)
                if os.path.isfile(pfad):
                    os.environ["MPV_LIBRARY_PATH"] = pfad
                    break
            path_manager.add_to_process_path(mpv_ordner)
            print("[DEBUG] MPV_LIBRARY_PATH =", os.environ.get("MPV_LIBRARY_PATH"))
        else:
            print("[WARN] libmpv nicht gefunden - der mpv-Player steht nicht "
                  "zur Verfuegung, GES laeuft davon unabhaengig.")
    else:
        if not path_manager.ensure_mpv_linux(
                "/usr/lib/x86_64-linux-gnu/libmpv.so.2"):
            print("[WARN] libmpv.so.2 nicht gefunden - der mpv-Player steht "
                  "nicht zur Verfuegung (sudo apt install libmpv-dev).")

    ffmpeg_ordner = (path_manager.find_ffmpeg_folder_mac()
                     if current_os == "Darwin"
                     else path_manager.find_ffmpeg_folder())
    if ffmpeg_ordner and path_manager.is_ffmpeg_in_folder(ffmpeg_ordner):
        path_manager.add_to_process_path(ffmpeg_ordner)
        print("[DEBUG] ffmpeg gefunden in", ffmpeg_ordner)
    elif not shutil.which("ffmpeg"):
        print("[WARN] ffmpeg nicht gefunden - Copy-Mode und der ffmpeg-Export "
              "stehen nicht zur Verfuegung.")
        ##
    # ++ADD++ Ende
    
    
    from views.mainwindow import MainWindow
    
    # Tray-Icon (nur Windows)
    if platform.system() == "Windows":
        # Pfad: icon/icon_icon.ico
        icon_file = resource_path(os.path.join("icon", "icon_icon.ico"))
        print("[DEBUG] Icon-Pfad =", icon_file, "| exists?", os.path.isfile(icon_file))

        app.setWindowIcon(QIcon(icon_file))
        trayIcon = QSystemTrayIcon(QIcon(icon_file), parent=None)
        trayIcon.show()

    # Eigenen Instanz-Ordner anlegen und sperren, dann die Ordner
    # abgestuerzter Vorlaeufer aufraeumen. Erst danach darf irgendetwas in die
    # Temp-Ordner schreiben.
    config.prepare_instance_temp_dir()
    config.cleanup_orphaned_temp_dirs()

    # Temp-Verzeichnisse leeren
    config.clear_temp_directories()


    # Frueher stand hier eine zweite Pruefung, die ohne ffmpeg im PATH
    # das Programm beendet hat. Sie ist weggefallen: ffmpeg ist keine
    # Startbedingung mehr (siehe oben).
    parent_widget = QWidget()
    parent_widget.hide()

    # Disclaimer-Dialog (nur wenn nicht akzeptiert)
    
    config.check_app_version_and_reset_if_necessary()
    if not is_disclaimer_accepted():
        dlg_disclaimer = DisclaimerDialog()
        dlg_disclaimer.show()
        app.processEvents()
        dlg_disclaimer.raise_()
        dlg_disclaimer.activateWindow()

        result = dlg_disclaimer.exec()
        if result == QDialog.Accepted:
            set_disclaimer_accepted()
        else:
            sys.exit(0)

    # Temp Ordner fürs Schneiden
    clear_temp_segments_dir()

    # Video-Editing on/off
    user_wants_editing = False
    if user_wants_editing:
        if os.path.exists(TMP_KEYFRAME_DIR):
            shutil.rmtree(TMP_KEYFRAME_DIR)
        os.makedirs(TMP_KEYFRAME_DIR, exist_ok=True)

    # Hauptfenster
    window = MainWindow(user_wants_editing=user_wants_editing)

    # Dynamische Anpassung an Bildschirm-Seitenverhältnis
    screen = app.primaryScreen()
    geometry = screen.availableGeometry()

    target_ratio = 16 / 9
    screen_ratio = geometry.width() / geometry.height()

    if screen_ratio >= target_ratio:
        new_height = int(geometry.height() * 0.9)
        new_width  = int(new_height * target_ratio)
    else:
        new_width  = int(geometry.width() * 0.9)
        new_height = int(new_width / target_ratio)

    window.resize(new_width, new_height)

    # Hat der Nutzer beim letzten Mal eine eigene Fenstergroesse/-position
    # hinterlassen, gilt die. Sonst bleibt es exakt beim bisherigen Start:
    # Standardgroesse oben, danach mittig setzen.
    restored = window.apply_saved_window_geometry()

    window.show()

    app.processEvents()
    if not restored:
        center_mainwindow(window)
    window.raise_()
    window.activateWindow()

    # Datei aus der Kommandozeile oeffnen (Doppelklick auf ein Projekt im
    # Explorer). open_recent() verzweigt bereits nach Endung und ruft fuer
    # .KVRouiteproj das process_open_project() auf. Erst nach dem Anzeigen
    # ausfuehren, damit Fehlermeldungen ein fertiges Fenster als Eltern haben.
    cli_file = _file_arg_from_cli(sys.argv)
    if cli_file:
        window.open_file_when_map_ready(cli_file)

    exit_code = app.exec()
    # Beim sauberen Beenden den eigenen Temp-Ordner mitnehmen.
    config.release_instance_temp_dir()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
