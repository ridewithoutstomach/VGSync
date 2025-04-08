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

# views/overlay_setup_dialog.py
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QDialogButtonBox, QHBoxLayout, QFileDialog, QComboBox, QDoubleSpinBox,
    QSpinBox
)
from PySide6.QtCore import QSettings, Qt

class OverlaySetupDialog(QDialog):
    """
    Dialog zur Konfiguration von bis zu 3 Overlays.

    Zu jedem Overlay i (1..3) werden folgende Keys gespeichert:
      overlay/i/image
      overlay/i/scale
      overlay/i/corner
      overlay/i/dx
      overlay/i/dy
    Außerdem berechnen wir mapped_x/mapped_y aus corner + dx,dy.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay Setup")

        self.settings = QSettings("VGSync", "VGSync")

        main_layout = QVBoxLayout(self)

        info_label = QLabel(
            "Configure up to 3 overlays.\n"
            "Pick an image, scale, corner, dx/dy offsets.\n"
            "We also store mapped_x/mapped_y for direct ffmpeg usage."
        )
        main_layout.addWidget(info_label)

        for i in range(1, 4):
            group_label = QLabel(f"Overlay {i}")
            group_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            main_layout.addWidget(group_label)

            # 1) Image Pfad
            row1 = QHBoxLayout()
            lbl_path = QLabel("Image path:")
            row1.addWidget(lbl_path)

            line_edit = QLineEdit()
            stored_path = self.settings.value(f"overlay/{i}/image", "", type=str)
            line_edit.setText(stored_path)
            row1.addWidget(line_edit)

            # Die kleine Hilfsfunktion, die den bool 'checked' ignoriert 
            # und stattdessen 'edit' benutzt.
            def _make_browse(checked=None, edit=line_edit):
                f, _ = QFileDialog.getOpenFileName(self, "Select overlay image")
                if f:
                    edit.setText(f)

            btn_browse = QPushButton("...")
            # Wichtig: wir verbinden 'clicked' mit _make_browse => 
            # => Param 'checked' landet in 'checked=None'
            btn_browse.clicked.connect(_make_browse)
            row1.addWidget(btn_browse)

            main_layout.addLayout(row1)
            setattr(self, f"img_path_edit_{i}", line_edit)

            # 2) Scale
            row2 = QHBoxLayout()
            lbl_scale = QLabel("Scale:")
            row2.addWidget(lbl_scale)

            scale_spin = QDoubleSpinBox()
            scale_spin.setRange(0.0, 10.0)
            scale_spin.setDecimals(3)
            scale_spin.setSingleStep(0.1)
            stored_scale = self.settings.value(f"overlay/{i}/scale", 1.0, type=float)
            scale_spin.setValue(stored_scale)
            row2.addWidget(scale_spin)
            main_layout.addLayout(row2)
            setattr(self, f"scale_spin_{i}", scale_spin)

            # 3) corner
            row3 = QHBoxLayout()
            lbl_corner = QLabel("Corner:")
            row3.addWidget(lbl_corner)

            corner_combo = QComboBox()
            corner_combo.addItems([
                "top-left",
                "top-right",
                "bottom-left",
                "bottom-right",
                "center"
            ])
            stored_corner = self.settings.value(f"overlay/{i}/corner", "top-left", type=str)
            idx = corner_combo.findText(stored_corner)
            if idx >= 0:
                corner_combo.setCurrentIndex(idx)
            row3.addWidget(corner_combo)
            main_layout.addLayout(row3)
            setattr(self, f"corner_combo_{i}", corner_combo)

            # 4) dx, dy
            row4 = QHBoxLayout()
            lbl_dx = QLabel("dx:")
            row4.addWidget(lbl_dx)
            offset_x_spin = QSpinBox()
            offset_x_spin.setRange(0, 9999)
            dx_val = self.settings.value(f"overlay/{i}/dx", 10, type=int)
            offset_x_spin.setValue(dx_val)
            row4.addWidget(offset_x_spin)

            lbl_dy = QLabel("dy:")
            row4.addWidget(lbl_dy)
            offset_y_spin = QSpinBox()
            offset_y_spin.setRange(0, 9999)
            dy_val = self.settings.value(f"overlay/{i}/dy", 10, type=int)
            offset_y_spin.setValue(dy_val)
            row4.addWidget(offset_y_spin)
            main_layout.addLayout(row4)

            setattr(self, f"offset_x_spin_{i}", offset_x_spin)
            setattr(self, f"offset_y_spin_{i}", offset_y_spin)

            line_sep = QLabel(" ")
            line_sep.setFrameStyle(QLabel.HLine)
            main_layout.addWidget(line_sep)

        # Buttons Save + Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        ok_button = btn_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setText("Save")

        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _on_ok_clicked(self):
        """
        Speichert alle Overlays in QSettings + mapped_x/y.
        """
        for i in range(1, 4):
            image_val  = getattr(self, f"img_path_edit_{i}").text().strip()
            scale_val  = getattr(self, f"scale_spin_{i}").value()
            corner_val = getattr(self, f"corner_combo_{i}").currentText()
            dx_val     = getattr(self, f"offset_x_spin_{i}").value()
            dy_val     = getattr(self, f"offset_y_spin_{i}").value()

            pref = f"overlay/{i}"
            self.settings.setValue(f"{pref}/image",  image_val)
            self.settings.setValue(f"{pref}/scale",  scale_val)
            self.settings.setValue(f"{pref}/corner", corner_val)
            self.settings.setValue(f"{pref}/dx",     dx_val)
            self.settings.setValue(f"{pref}/dy",     dy_val)

            # ffmpeg mapped_x/y
            if corner_val == "top-left":
                x_expr = f"{dx_val}"
                y_expr = f"{dy_val}"
            elif corner_val == "top-right":
                x_expr = f"(W-w)-{dx_val}"
                y_expr = f"{dy_val}"
            elif corner_val == "bottom-left":
                x_expr = f"{dx_val}"
                y_expr = f"(H-h)-{dy_val}"
            elif corner_val == "bottom-right":
                x_expr = f"(W-w)-{dx_val}"
                y_expr = f"(H-h)-{dy_val}"
            else:
                # center
                x_expr = f"((W-w)/2)-{dx_val}"
                y_expr = f"((H-h)/2)-{dy_val}"

            self.settings.setValue(f"{pref}/mapped_x", x_expr)
            self.settings.setValue(f"{pref}/mapped_y", y_expr)

            print(f"[DEBUG] => Overlay {i}: image='{image_val}', scale={scale_val}, corner='{corner_val}', dx={dx_val}, dy={dy_val}")
            print(f"[DEBUG] => Mapped: x='{x_expr}', y='{y_expr}'")

        self.settings.sync()
        self.accept()
