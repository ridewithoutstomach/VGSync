# views/overlay_setup_dialog.py

# In diesesem Dialog werden die QSettings gespichert für die xfades:
"""

"overlay/1/image"    -> Pfad zur Bilddatei (String)
"overlay/1/scale"    -> Skalierungsfaktor (float z. B. 1.0)
"overlay/1/corner"   -> "top-left", "top-right", "bottom-left", "bottom-right", "center" (String)
"overlay/1/dx"       -> Abstand in x-Richtung vom Rand (int oder float)
"overlay/1/dy"       -> Abstand in y-Richtung vom Rand (int oder float)

"overlay/2/image"
"overlay/2/scale"
"overlay/2/corner"
"overlay/2/dx"
"overlay/2/dy"

"overlay/3/image"
"overlay/3/scale"
"overlay/3/corner"
"overlay/3/dx"
"overlay/3/dy"




"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QDialogButtonBox, QHBoxLayout, QFileDialog, QComboBox, QDoubleSpinBox,
    QSpinBox
)
from PySide6.QtCore import QSettings, Qt

class OverlaySetupDialog(QDialog):
    """
    Ein Dialog, in dem wir 3 Overlays definieren können.
    Für jeden Overlay i (1..3) speichern wir:
      - image (Dateiname)
      - scale (float)
      - corner (Enum: top-left, top-right, bottom-left, bottom-right, center)
      - dx, dy (Abstand vom Rand in Pixeln)
    Dazu generieren wir jeweils mapped_x, mapped_y im ffmpeg-kompatiblen Format.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay Setup")

        self.settings = QSettings("VGSync", "VGSync")

        main_layout = QVBoxLayout(self)
        
        info_label = QLabel("Configure up to 3 overlays.\n"
                            "Pick an image, scale it, choose corner, and offset dx,dy.\n"
                            "We store 'mapped_x' and 'mapped_y' so that it is directly\n"
                            "usable in ffmpeg overlay filters.\n"
                            "(Note: W,H = main video; w,h = overlay size)")
        main_layout.addWidget(info_label)

        # Für 3 Overlays je eine Gruppe
        for i in range(1, 4):
            group_label = QLabel(f"Overlay {i}")
            group_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            main_layout.addWidget(group_label)

            # 1) Pfad: QLineEdit + Button "..." 
            row1 = QHBoxLayout()
            lbl_path = QLabel("Image path:")
            row1.addWidget(lbl_path)
            line_edit = QLineEdit()
            # Wir laden den gespeicherten Pfad (falls vorhanden)
            stored_path = self.settings.value(f"overlay/{i}/image", "", type=str)
            line_edit.setText(stored_path)
            row1.addWidget(line_edit)

            btn_browse = QPushButton("...")
            def on_browse():
                f, _ = QFileDialog.getOpenFileName(self, "Select overlay image")
                if f:
                    line_edit.setText(f)
            btn_browse.clicked.connect(on_browse)
            row1.addWidget(btn_browse)
            main_layout.addLayout(row1)

            # Wir speichern Referenzen als Attribut:
            setattr(self, f"img_path_edit_{i}", line_edit)

            # 2) scale (FloatSpinBox)
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

            # 3) corner (ComboBox)
            row3 = QHBoxLayout()
            lbl_corner = QLabel("Corner:")
            row3.addWidget(lbl_corner)
            corner_combo = QComboBox()
            corner_combo.addItems([
                "top-left",
                "top-right",
                "bottom-left",
                "bottom-right",
                "center",
            ])
            stored_corner = self.settings.value(f"overlay/{i}/corner", "top-left", type=str)
            index_corner = corner_combo.findText(stored_corner)
            if index_corner >= 0:
                corner_combo.setCurrentIndex(index_corner)
            row3.addWidget(corner_combo)
            main_layout.addLayout(row3)
            setattr(self, f"corner_combo_{i}", corner_combo)

            # 4) dx,dy (SpinBox)
            row4 = QHBoxLayout()
            lbl_dx = QLabel("dx:")
            row4.addWidget(lbl_dx)
            offset_x_spin = QSpinBox()
            offset_x_spin.setRange(0, 9999)
            stored_dx = self.settings.value(f"overlay/{i}/dx", 10, type=int)
            offset_x_spin.setValue(stored_dx)
            row4.addWidget(offset_x_spin)

            lbl_dy = QLabel("dy:")
            row4.addWidget(lbl_dy)
            offset_y_spin = QSpinBox()
            offset_y_spin.setRange(0, 9999)
            stored_dy = self.settings.value(f"overlay/{i}/dy", 10, type=int)
            offset_y_spin.setValue(stored_dy)
            row4.addWidget(offset_y_spin)
            main_layout.addLayout(row4)

            setattr(self, f"offset_x_spin_{i}", offset_x_spin)
            setattr(self, f"offset_y_spin_{i}", offset_y_spin)

            # ggf. Zwischenlinie
            line = QLabel(" ")
            line.setFrameStyle(QLabel.HLine)
            main_layout.addWidget(line)

        # Buttons: Save (statt OK), Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        ok_button = btn_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setText("Save")

        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)


    def _on_ok_clicked(self):
        """
        Speichert alle Overlays in QSettings und schließt den Dialog mit accept().
        Dabei wird corner+dx+dy in x/y-Expressions umgewandelt (mapped_x, mapped_y).
        """
        # Kleines Mapping: corner -> x,y (Ausdrücke)
        # dx,dy = Abstände vom Rand
        # 
        # ffmpeg overlay Filter:
        #   top-left:        x=dx,        y=dy
        #   top-right:       x=(W-w)-dx,  y=dy
        #   bottom-left:     x=dx,        y=(H-h)-dy
        #   bottom-right:    x=(W-w)-dx,  y=(H-h)-dy
        #   center:          x=(W-w)/2,   y=(H-h)/2
        #
        # Wobei wir dx,dy jeweils +/- anwenden, je nach "Ecke".

        for i in range(1, 4):
            key_prefix = f"overlay/{i}"
            image_key  = f"{key_prefix}/image"
            scale_key  = f"{key_prefix}/scale"
            corner_key = f"{key_prefix}/corner"
            dx_key     = f"{key_prefix}/dx"
            dy_key     = f"{key_prefix}/dy"

            mapped_x_key = f"{key_prefix}/mapped_x"
            mapped_y_key = f"{key_prefix}/mapped_y"

            # Referenzen
            line_edit = getattr(self, f"img_path_edit_{i}")
            scale_spin = getattr(self, f"scale_spin_{i}")
            corner_combo = getattr(self, f"corner_combo_{i}")
            offset_x_spin = getattr(self, f"offset_x_spin_{i}")
            offset_y_spin = getattr(self, f"offset_y_spin_{i}")

            image_val = line_edit.text().strip()
            scale_val = scale_spin.value()
            corner_val = corner_combo.currentText()
            dx_val = offset_x_spin.value()
            dy_val = offset_y_spin.value()

            # => in QSettings speichern
            self.settings.setValue(image_key,  image_val)
            self.settings.setValue(scale_key,  scale_val)
            self.settings.setValue(corner_key, corner_val)
            self.settings.setValue(dx_key,     dx_val)
            self.settings.setValue(dy_key,     dy_val)

            # 1) MAPPING in ffmpeg-Expressions
            # Wir konstruieren mappedX, mappedY als String
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
                # "center"
                # dx,dy => zusätzlicher offset? 
                # Bsp: x=(W-w)/2 - dx, y=(H-h)/2 - dy
                # => du kannst frei entscheiden, ob dx,dy *auf* die Mitte addiert/ subtrahierst
                x_expr = f"((W-w)/2)-{dx_val}"
                y_expr = f"((H-h)/2)-{dy_val}"

            self.settings.setValue(mapped_x_key, x_expr)
            self.settings.setValue(mapped_y_key, y_expr)

            # DEBUG-Ausgabe
            print(f"[DEBUG] Overlay {i}:")
            print(f"   image = '{image_val}'")
            print(f"   scale = {scale_val}")
            print(f"   corner= '{corner_val}'")
            print(f"   dx={dx_val}, dy={dy_val}")
            print(f"   => mapped_x='{x_expr}', mapped_y='{y_expr}'")

        self.settings.sync()
        self.accept()
