# config.py

import os
import sys
import platform
import tempfile
import shutil
from PySide6.QtCore import QSettings

from license_check import load_license  # <-- dein cryptography-basiertes Script


##############################################################################
# 1) Versions-Konfiguration & Modus
##############################################################################

APP_VERSION = "3.25"

# Falls du nur über den Server prüfen willst, ob diese APP_VERSION freigegeben ist,
# setze das hier auf True.
# => Dann wird KEINE license.lic geladen (egal ob vorhanden).
SERVER_VERSION_CHECK_ONLY = False

##############################################################################
# 2) Hilfsfunktionen/Pfade
##############################################################################

def _get_app_base_dir() -> str:
    """
    Gibt den Verzeichnis-Pfad zurück, in dem deine *laufende* Executable liegt.
    Unterscheidet dabei nach Betriebssystem:
    
    - Windows OneFile => sys._MEIPASS
    - Windows OneFolder => sys._MEIPASS oder sys.executable
    - macOS => sys.executable
    - Linux => sys.executable
    - normaler Python => __file__
    """
    if getattr(sys, 'frozen', False):
        # Gefrorene App (PyInstaller, Nuitka, etc.)
        current_system = platform.system()
        if current_system == 'Windows':
            if hasattr(sys, '_MEIPASS'):
                return sys._MEIPASS
            else:
                return os.path.dirname(sys.executable)
        elif current_system == 'Darwin':  # macOS
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _get_license_path() -> str:
    """
    Baut den Pfad zu 'license.lic' auf, basierend auf dem von _get_app_base_dir().
    """
    base_dir = _get_app_base_dir()
    return os.path.join(base_dir, "license.lic")


##############################################################################
# 3) Globale Variablen & Defaults
##############################################################################

# Ob wir einen Lizenz-Fingerprint abgleichen sollen (alter Mechanismus).
FINGERPRINT_CHECK_ENABLED = True

# Zum Umschalten ins Demo-Mode.
DEMO_MODE = False  # Wird ggf. im Hauptprogramm oder hier auf True gesetzt.

# Temp-Ordner
base_temp = tempfile.gettempdir()
TMP_KEYFRAME_DIR = os.path.join(base_temp, "my_vgsync_keyframes")
MY_GLOBAL_TMP_DIR = os.path.join(base_temp, "my_cut_segments_global")

LICENSE_FILE = _get_license_path()

HARDCODED_FINGERPRINT = ""
LOCAL_VERSION = ""
REGISTERED_NAME = ""
REGISTERED_EMAIL = ""

##############################################################################
# 4) Lizenz-Daten laden oder ignorieren - inkl. Demo-Fallback
##############################################################################

def _init_license_data():
    """
    Lädt (falls SERVER_VERSION_CHECK_ONLY=False) die license.lic
    und setzt globale Variablen. Schlägt das Laden fehl und 
    FINGERPRINT_CHECK_ENABLED=True, gehen wir in den DEMO_MODE.
    """
    global HARDCODED_FINGERPRINT, LOCAL_VERSION
    global REGISTERED_NAME, REGISTERED_EMAIL, DEMO_MODE

    if SERVER_VERSION_CHECK_ONLY:
        # Nur Servercheck => license.lic ignorieren
        LOCAL_VERSION = APP_VERSION
        HARDCODED_FINGERPRINT = ""
        REGISTERED_NAME = "ServerCheckUser"
        REGISTERED_EMAIL = "unknown@example.com"
    else:
        # Normale Vorgehensweise: license.lic laden, aber Demo-Fallback falls nicht möglich.
        try:
            licdata = load_license(LICENSE_FILE)
            HARDCODED_FINGERPRINT = licdata["fingerprint"]
            LOCAL_VERSION         = licdata["version"]
            REGISTERED_NAME       = licdata["registered_name"]
            REGISTERED_EMAIL      = licdata["registered_email"]

        except Exception as e:
            print(f"[WARN] License invalid or file missing: {e}")
            if FINGERPRINT_CHECK_ENABLED:
                # => Demomodus erzwingen
                #print("[INFO] FINGERPRINT_CHECK_ENABLED = True => We switch to DEMO_MODE because no valid license was found.")
                DEMO_MODE = True
                # Setze LOCAL_VERSION = APP_VERSION, damit der Servercheck dennoch auf die 
                # in APP_VERSION eingestellte Version geht.
                LOCAL_VERSION = APP_VERSION
                HARDCODED_FINGERPRINT = ""
                REGISTERED_NAME = "DemoUser"
                REGISTERED_EMAIL = "unknown@example.com"
            else:
                # Falls Fingerprint-Check abgeschaltet ist, kannst du hier 
                # entscheiden, was passieren soll. Evtl. kein Demo-Modus?
                print("[INFO] FINGERPRINT_CHECK_ENABLED = False => We'll just run without license.")
                LOCAL_VERSION = APP_VERSION
                HARDCODED_FINGERPRINT = ""
                REGISTERED_NAME = "NoLicenseFile"
                REGISTERED_EMAIL = "unknown@example.com"


_init_license_data()

##############################################################################
# 5) Zusatz-Funktionen für QSettings usw.
##############################################################################

def is_disclaimer_accepted() -> bool:
    """
    Liest aus QSettings (Firma=VGSync, App=VGSync) den Bool-Wert 'disclaimerAccepted'.
    Default = False, falls nicht vorhanden.
    """
    s = QSettings("VGSync", "VGSync")
    val = s.value("disclaimerAccepted", False, type=bool)
    return val


def set_disclaimer_accepted():
    """
    Setzt in QSettings => 'disclaimerAccepted' = True.
    """
    s = QSettings("VGSync", "VGSync")
    s.setValue("disclaimerAccepted", True)


def reset_config():
    """
    Löscht alle in QSettings gespeicherten Werte
    (z. B. disclaimersAccepted, maptilerKey, etc.).
    """
    s = QSettings("VGSync", "VGSync")
    s.clear()


def is_edit_video_enabled() -> bool:
    """
    Beispiel-Funktion: Liest aus QSettings, ob 'video/editEnabled' True/False ist.
    """
    s = QSettings("VGSync", "VGSync")
    val = s.value("video/editEnabled", False, type=bool)
    return val


def set_edit_video_enabled(enabled: bool):
    """
    Schreibt in QSettings, ob 'video/editEnabled' True/False ist.
    """
    s = QSettings("VGSync", "VGSync")
    s.setValue("video/editEnabled", enabled)


def check_app_version_and_reset_if_necessary():
    """
    Überprüft, ob die gespeicherte Version in QSettings der aktuellen APP_VERSION
    entspricht. Falls nicht, werden sämtliche QSettings gelöscht und anschließend
    die neue APP_VERSION eingetragen.

    Gibt True zurück, wenn ein Reset durchgeführt wurde, sonst False.
    """
    s = QSettings("VGSync", "VGSync")
    stored_version = s.value("appVersion", "", type=str)
    if stored_version != APP_VERSION:
        s.clear()
        s.setValue("appVersion", APP_VERSION)
        return True
    else:
        return False
        
        
def clear_temp_directories():
    """Löscht alle Inhalte in den temporären Verzeichnissen."""
    for tmp_dir in [TMP_KEYFRAME_DIR, MY_GLOBAL_TMP_DIR]:
        if os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
                print(f"[INFO] Temp-Verzeichnis geleert: {tmp_dir}")
            except Exception as e:
                print(f"[WARN] Konnte {tmp_dir} nicht löschen: {e}")
        os.makedirs(tmp_dir, exist_ok=True)  # Neu anlegen, falls nötig        
