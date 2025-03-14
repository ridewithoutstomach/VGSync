import os
import sys
import shutil
import subprocess

base_dir = os.path.dirname(os.path.abspath(__file__))

import path_manager
path_manager.ensure_mpv_library(parent_widget=None, base_dir=base_dir)




import urllib.request
import datetime
import config
import fingerprint_collect
import path_manager
import platform

config.clear_temp_directories()  # Jetzt wird die Funktion nur beim Start von `app.py` aufgerufen

## das ist für die map:
os.environ["QSG_RHI_BACKEND"] = "opengl"

from PySide6.QtWidgets import (
    QApplication, QDialog, QMessageBox, QWidget, QSystemTrayIcon
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from config import LOCAL_VERSION  # <= wir lesen die Version aus config

# Für JSON-Parsing und NTP:
import json
import ntplib
from datetime import datetime as dt, timezone

CHECK_URL = "http://vgsync.casa-eller.de/project/check.php?token=SUPER_SECRET_123"

from config import (
    TMP_KEYFRAME_DIR,
    MY_GLOBAL_TMP_DIR,
    is_disclaimer_accepted,
    set_disclaimer_accepted
)
from views.disclaimer_dialog import DisclaimerDialog
#from views.start_dialog import StartDialog
from views.mainwindow import MainWindow

from config import LOCAL_VERSION

PHP_TIME_API_URL = "http://vgsync.casa-eller.de/project/timeserver.php"
NTP_SERVERS = [
    "pool.ntp.org",
    "time.windows.com",
    "time.cloudflare.com",
    "time.google.com",
    "time.nist.gov"
]

def _fetch_time_from_php(url):
    print(f"[DEBUG] Trying primary HTTP timeserver (PHP): {url}")
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    dt_str = data["datetime"]  
    dt_obj = dt.fromisoformat(dt_str.replace("Z", "+00:00"))
    date_only = dt_obj.date()
    print(f"[DEBUG] PHP timeserver succeeded! Date is: {date_only}")
    return date_only

def _fetch_time_from_ntp(server_list):
    c = ntplib.NTPClient()
    last_error = None
    for server in server_list:
        print(f"[DEBUG] Trying NTP server: {server}")
        try:
            response = c.request(server, version=3)
            dt_utc = dt.fromtimestamp(response.tx_time, tz=timezone.utc)
            date_only = dt_utc.date()
            print(f"[DEBUG] NTP server succeeded! UTC time: {dt_utc.isoformat()}")
            return date_only
        except Exception as e:
            print(f"[WARN] NTP server failed ({server}): {e}")
            last_error = e
    raise RuntimeError(f"All NTP servers failed, last error: {last_error}")

def get_server_date():
    try:
        return _fetch_time_from_php(PHP_TIME_API_URL)
    except Exception as e:
        print(f"[WARN] Primary HTTP timeserver failed ({PHP_TIME_API_URL}): {e}")
    try:
        return _fetch_time_from_ntp(NTP_SERVERS)
    except Exception as e:
        print(f"[WARN] NTP fallback also failed: {e}")
        raise RuntimeError("No external timeserver available - Abbruch!")

def check_version_on_server():
    try:
        data_bytes = urllib.request.urlopen(CHECK_URL, timeout=10).read()
    except Exception as e:
        return (False, f"Server not reachable: {e}", "")

    lines = data_bytes.decode("utf-8", errors="replace").splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 3:
            continue

        version_str, status_str, expiry_str = parts[0], parts[1], parts[2]

        if version_str == LOCAL_VERSION:
            if status_str.upper() == "DISABLE":
                return (False, f"Version {LOCAL_VERSION} is deactivated!", expiry_str)

            try:
                today = get_server_date()
            except RuntimeError as err:
                return (False, f"Timeserver-Fehler: {err}", "")

            try:
                dt_expire = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
            except ValueError:
                return (False, f"Invalid date '{expiry_str}' in versioninfo.txt", expiry_str)

            if today > dt_expire:
                return (False, f"Version {LOCAL_VERSION} is expired (Deadline: {expiry_str})", expiry_str)

            return (True, "", expiry_str)

    return (False, f"Version {LOCAL_VERSION} expired! Please install a valid Version!", "")

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

def check_ffmpeg_and_vlc_or_exit():
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    vlc_path    = shutil.which("vlc")

    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return False, "ffmpeg"
   
    return True, ""

def main():
    QGuiApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)
    app = QApplication(sys.argv)
    parent = QWidget()
    parent.hide()
    
    system = platform.system()
    if system == "Windows":
        icon_path = os.path.join(base_dir, "icon", "icon_icon.ico")
        app.setWindowIcon(QIcon(icon_path))  # Taskbar Icon
        trayIcon = QSystemTrayIcon(QIcon(icon_path), parent=None)
        trayIcon.show()
    
    
    new_version_started = config.check_app_version_and_reset_if_necessary()
    if new_version_started:
        QMessageBox.warning(
            None, 
            "New Version Detected",
            f"A new version ({config.APP_VERSION}) was launched. "
            "All your previous settings have been reset."
        )

    # 2) Lokale Lizenz nur prüfen, WENN wir NICHT im "Nur Server-Check"-Modus sind
    if not config.SERVER_VERSION_CHECK_ONLY:
        # (A) Falls konfiguriert -> Fingerprint-Check
        if config.FINGERPRINT_CHECK_ENABLED:
            local_fp = fingerprint_collect.get_fingerprint_universal()
            if local_fp != config.HARDCODED_FINGERPRINT:
                QMessageBox.warning(None, "Demo Mode",
                    "Warning: You are running in DEMO mode, because the license\n"
                    "does not match this PC! The 'Save Buttons' function will be disabled."
                )
                config.DEMO_MODE = True
                

    else:
        # (B) Nur Server-Check-Modus!
        # => keine lokale license.lic - wir gehen direkt weiter
        # => Und wir können optional hier DEMO_MODE auf False erzwingen,
        #    damit wir auf keinen Fall im Demo-Modus sind, wenn nur der Server okay sagt
        config.DEMO_MODE = False
       

    # 3) SERVER-Versions-Check
    ok, msg, expiry_str = check_version_on_server()
    if not ok:
        QMessageBox.critical(None, "Version gesperrt oder abgelaufen", msg)
        sys.exit(1)

    config.EXPIRE_DATE = expiry_str

    # ffmpeg sicherstellen (bzw. Path-Manager check)
    if not path_manager.ensure_ffmpeg(parent):
        QMessageBox.critical(parent, "Missing FFmpeg", "Cannot proceed without FFmpeg.")
        sys.exit(1)
    print("[DEBUG] After ensure_ffmpeg =>", shutil.which("ffmpeg"))
    ok, msg, expiry_str = check_version_on_server()
    if not ok:
        QMessageBox.critical(None, "Version gesperrt oder abgelaufen", msg)
        sys.exit(1)
        
    config.EXPIRE_DATE = expiry_str    

    # Zusätzlicher Check ffmpeg & VLC
    parent_widget = QWidget()
    parent_widget.hide()

    ok2, missing = check_ffmpeg_and_vlc_or_exit()
    if not ok2:
        msg_box = QMessageBox(parent_widget)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Missing Dependency")
        msg_box.setText(
            f"Could not find '{missing}'!\n"
            "Please install it (or provide it) and restart the program.\n\n"
            "Be sure it's in your PATH-Variable."
        )
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        sys.exit(0)

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

    clear_temp_segments_dir()

    user_wants_editing = False
    
    if user_wants_editing:
        if os.path.exists(TMP_KEYFRAME_DIR):
            shutil.rmtree(TMP_KEYFRAME_DIR)
        os.makedirs(TMP_KEYFRAME_DIR, exist_ok=True)

    window = MainWindow(user_wants_editing=user_wants_editing)

    screen = app.primaryScreen()
    geometry = screen.availableGeometry()
    
   
    target_ratio = 16 / 9
    screen_ratio = geometry.width() / geometry.height()

    # Lege fest, ob die Breite oder die Höhe das 'limitierende' Maß ist.
    # Wir nehmen hier z.B. 90% vom verfügbaren Platz.
    # Wenn du stattdessen 95% möchtest, ändere einfach die 0.9 auf 0.95.
    if screen_ratio >= target_ratio:
        # Bildschirm ist eher breit => Höhe bestimmt unsere Fenstergröße
        new_height = int(geometry.height() * 0.9)
        new_width  = int(new_height * target_ratio)
    else:
        # Bildschirm ist schmal => Breite bestimmt unsere Fenstergröße
        new_width  = int(geometry.width() * 0.9)
        new_height = int(new_width / target_ratio)

    window.resize(new_width, new_height)
    

    window.show()
    app.processEvents()
    center_mainwindow(window)
    window.raise_()
    window.activateWindow()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
