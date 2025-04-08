# views/encoder_setup_dialog.py

"""
"encoder/resolution"  -> String wie "1920x1080" (oder "1280x720" etc.)
"encoder/container"   -> "x264" oder "x265" (String)
"encoder/hwaccel"     -> z. B. "none", "nvidia_h264", "nvidia_hevc", "amd_h264", "intel_hevc" etc.
"encoder/crf"         -> (float oder int, z. B. 20)
"encoder/preset"      -> z. B. "fast", "medium", "slow" usw. (String)
"encoder/fps"         -> z. B. 30 (int)
"encoder/xfade"       -> xfade-Zeit in Sekunden (float oder int, z. B. 2

"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QDialogButtonBox, QPushButton, QCheckBox, QLineEdit
)
from PySide6.QtCore import QSettings, Qt

from core.hardware_detect import detect_available_hw_encoders

class EncoderSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Encoder Setup")

        self.settings = QSettings("VGSync", "VGSync")

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        main_layout.addLayout(form_layout)

        # (A) Resolution
        self.resolution_combo = QComboBox()
        # Format: ( (w,h), "Label" )
        self.resolution_options = [
            ((640, 360),  "640x360 (SD)"),
            ((854, 480),  "854x480 (nHD)"),
            ((1280, 720), "1280x720 (HD)"),
            ((1920,1080), "1920x1080 (Full HD)"),
            ((2560,1440), "2560x1440 (QHD 2K)"),
            ((3840,2160), "3840x2160 (4K UHD)")
        ]
        for wh, label in self.resolution_options:
            self.resolution_combo.addItem(label, userData=wh)

        form_layout.addRow("Resolution:", self.resolution_combo)

        # (B) Container: x264 / x265
        self.container_combo = QComboBox()
        self.container_combo.addItem("x264")
        self.container_combo.addItem("x265")
        form_layout.addRow("Container:", self.container_combo)

        # (C) Hardware
        self.hw_combo = QComboBox()
        form_layout.addRow("Hardware:", self.hw_combo)

        # (D) CRF
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(12, 50)
        form_layout.addRow("CRF (Quality):", self.crf_spin)

        # (E) Preset
        self.preset_combo = QComboBox()
        cpu_presets = ["ultrafast", "superfast", "veryfast", "faster",
                       "fast", "medium", "slow", "slower", "veryslow"]
        for p in cpu_presets:
            self.preset_combo.addItem(p)
        form_layout.addRow("Preset:", self.preset_combo)

        # (F) FPS
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        form_layout.addRow("FPS:", self.fps_spin)

        # (G) Xfade
        self.xfade_spin = QSpinBox()
        self.xfade_spin.setRange(0, 30)
        form_layout.addRow("X-Fade (s):", self.xfade_spin)

        # Buttons (OK/Cancel)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        main_layout.addWidget(btns, alignment=Qt.AlignRight)

        btns.accepted.connect(self.on_ok_clicked)
        btns.rejected.connect(self.reject)

        # Signale
        self.container_combo.currentIndexChanged.connect(self.update_hw_options)

        # Laden aus QSettings
        self.load_from_settings()

        # Hardware aktualisieren => Filter x264/x265
        self.update_hw_options()

    def load_from_settings(self):
        """Liest QSettings und setzt die GUI-Felder."""
        # Auflösung
        wdef = self.settings.value("encoder/res_w", 1920, type=int)
        hdef = self.settings.value("encoder/res_h", 1080, type=int)
        stored_res = (wdef, hdef)

        # resolution_options durchsuchen
        found_idx = 0
        for i, (wh, label) in enumerate(self.resolution_options):
            if wh == stored_res:
                found_idx = i
                break
        self.resolution_combo.setCurrentIndex(found_idx)

        # Container
        container_val = self.settings.value("encoder/container", "x265", type=str)
        idx_c = self.container_combo.findText(container_val)
        if idx_c < 0: idx_c = 0
        self.container_combo.setCurrentIndex(idx_c)

        # CRF
        crf_val = self.settings.value("encoder/crf", 20, type=int)
        self.crf_spin.setValue(crf_val)

        # Preset
        preset_val = self.settings.value("encoder/preset", "fast", type=str)
        idx_p = self.preset_combo.findText(preset_val)
        if idx_p < 0: idx_p = 0
        self.preset_combo.setCurrentIndex(idx_p)

        # FPS
        fps_val = self.settings.value("encoder/fps", 30, type=int)
        self.fps_spin.setValue(fps_val)

        # Xfade
        xfade_val = self.settings.value("encoder/xfade", 2, type=int)
        self.xfade_spin.setValue(xfade_val)

        # HW => erst in update_hw_options
        # da wir davon Container abh. machen

    def update_hw_options(self):
        """Befüllt das hw_combo je nach Container (x264/x265) und realer Erkennung."""
        container = self.container_combo.currentText()  # "x264" / "x265"

        # ffmpeg-Check
        hw_encoders = detect_available_hw_encoders()  # set(...) => z.B. {"none", "nvidia_h264"}

        # je nach Container
        x264_allowed = {"none", "nvidia_h264", "amd_h264", "intel_h264"}
        x265_allowed = {"none", "nvidia_hevc", "amd_hevc", "intel_hevc"}

        if container == "x264":
            allowed = x264_allowed
        else:
            allowed = x265_allowed

        final_hw = hw_encoders.intersection(allowed)
        if not final_hw:
            final_hw = {"none"}

        self.hw_combo.clear()
        sorted_list = sorted(list(final_hw))
        for hw in sorted_list:
            self.hw_combo.addItem(hw)

        # Gucken, was in QSettings gespeichert war
        stored_hw = self.settings.value("encoder/hw", "none", type=str)
        idx_hw = self.hw_combo.findText(stored_hw)
        if idx_hw < 0:
            idx_hw = 0
        self.hw_combo.setCurrentIndex(idx_hw)

    def on_ok_clicked(self):
        """Speichert die Werte in QSettings und schließt."""
        # resolution
        w,h = self.resolution_combo.currentData()
        self.settings.setValue("encoder/res_w", w)
        self.settings.setValue("encoder/res_h", h)

        # container
        container = self.container_combo.currentText()
        self.settings.setValue("encoder/container", container)

        # hardware
        hw = self.hw_combo.currentText()
        self.settings.setValue("encoder/hw", hw)

        # crf
        self.settings.setValue("encoder/crf", self.crf_spin.value())

        # preset
        preset = self.preset_combo.currentText()
        self.settings.setValue("encoder/preset", preset)

        # fps
        self.settings.setValue("encoder/fps", self.fps_spin.value())

        # xfade
        self.settings.setValue("encoder/xfade", self.xfade_spin.value())

        self.accept()
