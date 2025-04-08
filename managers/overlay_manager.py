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

from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QDoubleSpinBox,
    QSpinBox, QLineEdit, QPushButton, QFileDialog, QHBoxLayout,
    QDialogButtonBox
)

class OverlayManager(QObject):
    """
    OverlayManager verwaltet Overlays (Liste von Dicts) 
    und kann über ask_user_for_overlay(...) einen Dialog öffnen,
    in dem der User ein vorhandenes overlay (1..3) aus QSettings auswählt
    ODER per Button "Add new" ein eigenes Overlay (Bild, scale, corner, dx, dy) anlegt.
    Am Ende ruft er add_overlay(...) und markiert das Overlay in der Timeline.
    """

    overlaysChanged = Signal()

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self._overlays = []

    def add_overlay(self, ovl_dict):
        """
        Nimmt den Overlay-Dict entgegen, z.B.:
        {
          "start": start_s,
          "end":   end_s,
          "fade_in": fade_in,
          "fade_out": fade_out,
          "image": "...",
          "scale": 1.0,
          "x": "(W-w)/2",
          "y": "((H-h)/2)-10"
        }
        und malt es in der Timeline blau + speichert in self._overlays.
        """
        start_s = ovl_dict.get("start", 0.0)
        end_s   = ovl_dict.get("end", 0.0)
        if end_s <= start_s:
            print("[WARN OverlayManager] add_overlay => end <= start => ignoring")
            return

        self._overlays.append(ovl_dict)
        self.timeline.add_overlay_interval(start_s, end_s)
        self.overlaysChanged.emit()

    def remove_last_overlay(self):
        if self._overlays:
            self._overlays.pop()
            self.timeline.remove_last_overlay_interval()
            self.overlaysChanged.emit()

    def clear_overlays(self):
        self._overlays.clear()
        self.timeline.clear_overlay_intervals()
        self.overlaysChanged.emit()

    def get_all_overlays(self):
        return self._overlays

    # -------------------------------------------------------------------------
    # Public-Methode: ask_user_for_overlay
    # Ruft InsertOverlayDialog auf => wähle "overlay 1/2/3" oder "Custom #X"
    # plus Duration, FadeIn, FadeOut
    # => Erzeugt ovl-dict => add_overlay
    # -------------------------------------------------------------------------
    def ask_user_for_overlay(self, marker_s: float, parent=None):
        """
        marker_s: float, ab wo das Overlay in der Timeline starten soll.
        z.B. rufst du das auf, wenn du
        self.timeline.marker_position() als 'marker_s' hast.

        => InsertOverlayDialog => user kann existing overlay(1..3) ODER "Add new" => custom
           => chosen_overlay_id = "1","2","3" oder "custom_1", "custom_2", ...
           => fade_in, fade_out, duration => am Ende add_overlay(...)
        """
        dlg = self.InsertOverlayDialog(parent)
        if dlg.exec() != QDialog.Accepted:
            print("[OverlayManager] => user canceled overlay insertion")
            return

        chosen_id = dlg.chosen_overlay_id
        duration_s= dlg.duration_s
        fade_in_s = dlg.fade_in_s
        fade_out_s= dlg.fade_out_s
        start_s   = marker_s
        end_s     = marker_s + duration_s

        if chosen_id.startswith("custom_"):
            # => selbst erstelltes Overlay
            custom_ovl = dlg._custom_overlay_dicts.get(chosen_id)
            if not custom_ovl:
                print(f"[OverlayManager] => custom overlay dict not found: {chosen_id}")
                return
            
            image   = custom_ovl["image"]
            scale   = custom_ovl["scale"]
            x_expr  = custom_ovl["mapped_x"]
            y_expr  = custom_ovl["mapped_y"]

        else:
            # => "1","2","3"
            s = QSettings("VGSync","VGSync")
            image = s.value(f"overlay/{chosen_id}/image","",str)
            scale = s.value(f"overlay/{chosen_id}/scale",1.0,float)
            x_expr= s.value(f"overlay/{chosen_id}/mapped_x","0",str)
            y_expr= s.value(f"overlay/{chosen_id}/mapped_y","0",str)

        ovl_dict = {
            "start":    start_s,
            "end":      end_s,
            "fade_in":  fade_in_s,
            "fade_out": fade_out_s,
            "image":    image,
            "scale":    scale,
            "x":        x_expr,
            "y":        y_expr
        }
        self.add_overlay(ovl_dict)
        print("[OverlayManager] => Overlay added:", ovl_dict)


    # -------------------------------------------------------------------------
    # (A) InsertOverlayDialog
    # Zeigt ComboBox (overlay1..3) + Button "Add new" => SingleOverlayDialog => "Custom #1"
    # plus Duration, FadeIn/Out
    # => chosen_overlay_id,  self._custom_overlay_dicts
    # -------------------------------------------------------------------------
    class InsertOverlayDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Insert Overlay")

            self.chosen_overlay_id = None
            self.duration_s  = 10.0
            self.fade_in_s   = 2.0
            self.fade_out_s  = 0.0

            self._custom_overlay_dicts = {}
            self._custom_count = 0  # Zählt neu angelegte Overlays

            lay = QVBoxLayout(self)

            lbl_head = QLabel("Select an existing Overlay or add a new one.\n"
                              "Then enter Duration, FadeIn, FadeOut.")
            lay.addWidget(lbl_head)

            # -- Combo
            self.combo = QComboBox()
            lay.addWidget(self.combo)

            s = QSettings("VGSync","VGSync")
            for i in [1,2,3]:
                img = s.value(f"overlay/{i}/image","",str).strip()
                if img:
                    self.combo.addItem(f"overlay {i}")

            # -- Button "Add new"
            btn_new = QPushButton("Add new")
            btn_new.clicked.connect(self._on_add_new_overlay)
            lay.addWidget(btn_new)

            # Duration
            lbl_dur = QLabel("Duration (s):")
            lay.addWidget(lbl_dur)
            self.spin_dur = QDoubleSpinBox()
            self.spin_dur.setRange(0.1,99999.0)
            self.spin_dur.setDecimals(2)
            self.spin_dur.setValue(10.0)
            lay.addWidget(self.spin_dur)

            # FadeIn/Out
            row_fade = QHBoxLayout()
            lbl_in = QLabel("Fade In (s):")
            self.spin_in = QDoubleSpinBox()
            self.spin_in.setRange(0.0,9999.0)
            self.spin_in.setDecimals(2)
            row_fade.addWidget(lbl_in)
            row_fade.addWidget(self.spin_in)

            lbl_out = QLabel("Fade Out (s):")
            self.spin_out = QDoubleSpinBox()
            self.spin_out.setRange(0.0,9999.0)
            self.spin_out.setDecimals(2)
            row_fade.addWidget(lbl_out)
            row_fade.addWidget(self.spin_out)

            lay.addLayout(row_fade)

            # Buttons
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            lay.addWidget(btn_box)
            btn_box.accepted.connect(self._on_ok)
            btn_box.rejected.connect(self.reject)

        def _on_add_new_overlay(self):
            """
            Wenn User auf "Add new" klickt => SingleOverlayDialog => 
            => custom_{x} => combo: "Custom #x"
            """
            dlg = OverlayManager.SingleOverlayDialog(self)
            if dlg.exec() == QDialog.Accepted:
                self._custom_count += 1
                key_id = f"custom_{self._custom_count}"
                self._custom_overlay_dicts[key_id] = dlg.overlay_dict

                label = f"Custom #{self._custom_count}"
                # Hinterlegen "userData=key_id" => ComboBox
                self.combo.addItem(label, userData=key_id)

                # auf den neuen Eintrag schalten
                idx = self.combo.count() -1
                self.combo.setCurrentIndex(idx)

        def _on_ok(self):
            self.duration_s = self.spin_dur.value()
            self.fade_in_s  = self.spin_in.value()
            self.fade_out_s = self.spin_out.value()

            # check combo
            idx = self.combo.currentIndex()
            if idx < 0:
                # Nichts gewählt => Cancel
                self.reject()
                return

            text_ = self.combo.itemText(idx)
            user_data = self.combo.itemData(idx)  # Falls custom
            
            if user_data is not None:
                # => "custom_x"
                self.chosen_overlay_id = user_data
            else:
                # => "overlay 1", "overlay 2" ...
                # => parse
                txt_lower = text_.lower().strip()
                if txt_lower.startswith("overlay"):
                    # => "overlay 1"
                    arr = txt_lower.split()
                    if len(arr) >= 2:
                        self.chosen_overlay_id = arr[-1]  # "1"
                    else:
                        self.chosen_overlay_id = "1"
                else:
                    # fallback
                    self.chosen_overlay_id = "1"

            self.accept()

    # -------------------------------------------------------------------------
    # (B) SingleOverlayDialog => 1 Overlay abfragen (Bild,scale,corner,dx,dy)
    #     => mapped_x,y => in overlay_dict
    # -------------------------------------------------------------------------
    class SingleOverlayDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Add new Overlay")
            self.overlay_dict = {}

            layout = QVBoxLayout(self)

            lbl_info = QLabel("Define one custom overlay (image,scale,corner,dx,dy).", self)
            layout.addWidget(lbl_info)

            # (B.1) Image
            row_img = QHBoxLayout()
            lbl_img = QLabel("Image path:")
            row_img.addWidget(lbl_img)
            self.line_img = QLineEdit()
            row_img.addWidget(self.line_img)

            def on_browse(checked=None):
                f, _ = QFileDialog.getOpenFileName(self, "Select Overlay image")
                if f:
                    self.line_img.setText(f)
            btn_browse = QPushButton("...")
            btn_browse.clicked.connect(on_browse)
            row_img.addWidget(btn_browse)
            layout.addLayout(row_img)

            # (B.2) Scale
            row_scale = QHBoxLayout()
            lbl_scale= QLabel("Scale:")
            row_scale.addWidget(lbl_scale)
            self.spin_scale = QDoubleSpinBox()
            self.spin_scale.setRange(0.0, 10.0)
            self.spin_scale.setDecimals(3)
            self.spin_scale.setValue(1.0)
            row_scale.addWidget(self.spin_scale)
            layout.addLayout(row_scale)

            # (B.3) corner
            row_corner = QHBoxLayout()
            lbl_corner = QLabel("Corner:")
            row_corner.addWidget(lbl_corner)
            self.combo_corner = QComboBox()
            self.combo_corner.addItems([
                "top-left","top-right",
                "bottom-left","bottom-right",
                "center"
            ])
            row_corner.addWidget(self.combo_corner)
            layout.addLayout(row_corner)

            # (B.4) dx, dy
            row_offset = QHBoxLayout()
            lbl_dx=QLabel("dx:")
            row_offset.addWidget(lbl_dx)
            self.spin_dx = QSpinBox()
            self.spin_dx.setRange(0,9999)
            self.spin_dx.setValue(10)
            row_offset.addWidget(self.spin_dx)

            lbl_dy=QLabel("dy:")
            row_offset.addWidget(lbl_dy)
            self.spin_dy = QSpinBox()
            self.spin_dy.setRange(0,9999)
            self.spin_dy.setValue(10)
            row_offset.addWidget(self.spin_dy)

            layout.addLayout(row_offset)

            # (B.5) OK/Cancel
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(btn_box)
            btn_box.accepted.connect(self._on_ok)
            btn_box.rejected.connect(self.reject)

        def _on_ok(self):
            image_val  = self.line_img.text().strip()
            scale_val  = self.spin_scale.value()
            corner_val = self.combo_corner.currentText()
            dx_val     = self.spin_dx.value()
            dy_val     = self.spin_dy.value()

            # => overlay_dict
            self.overlay_dict = {
                "image": image_val,
                "scale": scale_val,
                "corner": corner_val,
                "dx": dx_val,
                "dy": dy_val
            }
            # => mapped_x,y
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

            self.overlay_dict["mapped_x"] = x_expr
            self.overlay_dict["mapped_y"] = y_expr

            self.accept()
