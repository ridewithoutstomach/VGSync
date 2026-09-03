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


# Al Overlays are saved in "all_ovls = self._overlay_manager.get_all_overlays()"

#

from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QPushButton,
    QSpinBox, QLineEdit, QFileDialog, QHBoxLayout, QDialogButtonBox, QMessageBox
)
import os
import copy

class OverlayManager(QObject):
    """
    Verwaltet Overlays und malt sie in die Timeline (blau). 
    Bietet die Public-Methode:
      ask_user_for_overlay(marker_s, parent)
    Darin kann der User ein 'overlay 1..3' (aus QSettings) wählen 
    ODER ein neues Overlay (Bild+Scale+Corner+dx+dy+Duration+FadeIn/Out) anlegen,
    das sofort in die Timeline gemalt wird.
    """

    overlaysChanged = Signal()

    #: Wird VOR jeder vom Anwender ausgeloesten Aenderung gesendet und traegt
    #: den Stand davor. Daran haengt das globale Strg+Z: das Hauptfenster legt
    #: sich daraus eine Ruecknahmefunktion auf seinen Stapel.
    #:
    #: Absichtlich nur beim Anlegen und beim Aendern. Das Leeren beim Laden
    #: eines Projekts oder bei "New Project" ist keine Bearbeitung - dafuer
    #: einen Ruecknahmeschritt anzubieten, waere irrefuehrend.
    vorAenderung = Signal(list)

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self._overlays = []

    def add_overlay(self, ovl_dict):
        """
        ovl_dict z.B.:
        {
          "start":  30,
          "end":    50,
          "fade_in":2,
          "fade_out":1,
          "image":  "C:/temp/logo.png",
          "scale":  1.0,
          "x":      "(W-w)/2",
          "y":      "(H-h)-10"
        }
        => Vor dem Speichern: HARTE Validierung gegen Cuts + xfade-Ränder.
        => Bei OK: speichern + timeline.add_overlay_interval(...)
        """
        start_s = float(ovl_dict.get("start", 0.0))
        end_s   = float(ovl_dict.get("end", 0.0))

        mw = self.parent()  # OverlayManager wurde mit parent=MainWindow erzeugt
        if mw is None:
            print("[ERR] add_overlay => missing MainWindow parent; abort.")
            return

        ok, grund = self.zeiten_pruefen(start_s, end_s)
        if not ok:
            QMessageBox.warning(mw, "Overlay not possible", grund)
            return

        # --- Alles gut -> speichern + Timeline markieren ---
        import copy
        self.vorAenderung.emit(copy.deepcopy(self._overlays))
        self._overlays.append(ovl_dict)
        self.timeline.add_overlay_interval(start_s, end_s)
        self.overlaysChanged.emit()
        print("[OverlayManager] => Overlay ADDED:", ovl_dict)


    # ------------------------------------------------------------------
    # Zeiten: pruefen, Grenzen, verschieben
    # ------------------------------------------------------------------
    def _blendenrand(self, mw, zeit_s) -> float:
        """Wie viel Platz die Blende an dieser Keep-Grenze braucht.

        Seit 6.03 kann jeder Schnitt seine eigene Blendenlaenge haben; der
        Rand haengt deshalb am jeweiligen Schnitt und nicht mehr an einem
        globalen Wert. _blende_am_rand() im Fenster weiss das. Der Rueckfall
        auf encoder/xfade gilt nur, falls die Funktion einmal fehlt.
        """
        holen = getattr(mw, "_blende_am_rand", None)
        if callable(holen):
            try:
                return float(holen(zeit_s))
            except Exception as e:
                print(f"[WARN] Blendenrand: {e}")
        try:
            wert = float(QSettings("KVRouite", "KVRouite").value(
                "encoder/xfade", 2, type=int))
        except Exception:
            wert = 2.0
        return max(0.0, wert)

    def _keep_fuer(self, mw, start_s, end_s):
        """Das Keep-Segment, das [start, end] vollstaendig enthaelt, oder None."""
        total = float(getattr(mw, "real_total_duration", 0.0))
        if total <= 0.0:
            return None
        try:
            cuts = list(mw.cut_manager.get_cut_intervals())
            keeps = mw._compute_keep_intervals(cuts, total)
        except Exception as e:
            print(f"[ERR] Keep-Segmente: {e}")
            return None
        for (ks, ke) in keeps:
            if start_s >= ks - 1e-9 and end_s <= ke + 1e-9:
                return (float(ks), float(ke))
        return None

    def zeiten_pruefen(self, start_s, end_s):
        """Duerfen Anfang und Ende so liegen? Rueckgabe (ok, grund).

        Herausgeloest aus add_overlay(), weil jetzt auch das Verschieben und
        das Ziehen an den Raendern durch dieselbe Pruefung muessen. Zwei
        Regeln, und beide sind hart:

          1. Das Overlay muss vollstaendig in EINEM Keep-Segment liegen. Ueber
             einen Schnitt hinweg gibt es kein durchgehendes Bild.
          2. Zu beiden Enden des Segments muss der Platz der dortigen Blende
             frei bleiben. Sonst laege das Overlay im ueberblendeten Bereich.
        """
        mw = self.parent()
        if mw is None:
            return False, "Internal error: no main window."
        start_s, end_s = float(start_s), float(end_s)
        if end_s <= start_s:
            return False, "The overlay must end after it starts."

        total = float(getattr(mw, "real_total_duration", 0.0))
        if total <= 0.0:
            return False, "No video loaded."

        keep = self._keep_fuer(mw, start_s, end_s)
        if keep is None:
            return False, (f"The overlay [{start_s:.2f}s - {end_s:.2f}s] crosses "
                           "a cut or a video boundary.\nMove it or shorten it.")

        ks, ke = keep
        rand_links = self._blendenrand(mw, ks)
        rand_rechts = self._blendenrand(mw, ke)
        frueh = ks + rand_links
        spaet = ke - rand_rechts
        if start_s < frueh - 1e-9 or end_s > spaet + 1e-9:
            moeglich = max(0.0, spaet - frueh)
            return False, (
                f"The crossfades next to this segment need "
                f"{rand_links:.1f}s at its start and {rand_rechts:.1f}s at its "
                f"end.\n\n"
                f"Allowed here: {frueh:.2f}s - {spaet:.2f}s "
                f"(at most {moeglich:.2f}s long)\n"
                f"Your overlay:  {start_s:.2f}s - {end_s:.2f}s "
                f"({end_s - start_s:.2f}s long)")
        return True, ""

    def grenzen_fuer(self, start_s, end_s):
        """In welchem Bereich darf dieses Overlay liegen? (frueh, spaet).

        Fuer die Anschlaege beim Ziehen. Gibt (start, end) zurueck, wenn sich
        kein passendes Keep-Segment finden laesst - dann bewegt sich nichts.
        """
        mw = self.parent()
        keep = None if mw is None else self._keep_fuer(mw, start_s, end_s)
        if keep is None:
            return float(start_s), float(end_s)
        ks, ke = keep
        return (ks + self._blendenrand(mw, ks),
                ke - self._blendenrand(mw, ke))

    def _finde(self, start_s, end_s):
        """Platz des Overlays mit diesen Zeiten, oder -1."""
        for i, ovl in enumerate(self._overlays):
            if (abs(float(ovl.get("start", 0.0)) - start_s) < 0.001
                    and abs(float(ovl.get("end", 0.0)) - end_s) < 0.001):
                return i
        return -1

    def overlay_verschieben(self, alt_start, alt_ende, neu_start, neu_ende):
        """Anfang und Ende eines Overlays aendern. Rueckgabe (ok, grund).

        Der einzige Weg, auf dem sich die Zeiten aendern - update_overlay()
        laesst sie bewusst nicht zu, weil es die Pruefung nicht leisten kann.

        Die Blendenlaengen werden mitgezogen, wenn das Overlay kuerzer wird
        als sie: eine Einblendung, die laenger dauert als das Overlay, waere
        im Export nicht darstellbar.
        """
        i = self._finde(float(alt_start), float(alt_ende))
        if i < 0:
            return False, "This overlay no longer exists."

        ok, grund = self.zeiten_pruefen(neu_start, neu_ende)
        if not ok:
            return False, grund

        self.vorAenderung.emit(copy.deepcopy(self._overlays))
        ovl = self._overlays[i]
        ovl["start"] = float(neu_start)
        ovl["end"] = float(neu_ende)
        dauer = float(neu_ende) - float(neu_start)
        ein = float(ovl.get("fade_in", 0) or 0)
        aus = float(ovl.get("fade_out", 0) or 0)
        if ein + aus > dauer:
            faktor = dauer / (ein + aus) if (ein + aus) > 0 else 0.0
            ovl["fade_in"] = round(ein * faktor, 2)
            ovl["fade_out"] = round(aus * faktor, 2)
            print(f"[OverlayManager] Blenden mitgekuerzt: "
                  f"{ein:.2f}/{aus:.2f} -> {ovl['fade_in']:.2f}/"
                  f"{ovl['fade_out']:.2f}")
        self._timeline_neu()
        self.overlaysChanged.emit()
        print(f"[OverlayManager] verschoben: {alt_start:.2f}-{alt_ende:.2f} "
              f"-> {neu_start:.2f}-{neu_ende:.2f}")
        return True, ""

    def blenden_setzen(self, start_s, end_s, fade_in, fade_out):
        """Ein- und Ausblendlaenge eines Overlays setzen. Rueckgabe (ok, grund)."""
        i = self._finde(float(start_s), float(end_s))
        if i < 0:
            return False, "This overlay no longer exists."
        ein = max(0.0, float(fade_in))
        aus = max(0.0, float(fade_out))
        dauer = float(end_s) - float(start_s)
        if ein + aus > dauer + 1e-9:
            return False, (f"Fade in and fade out together ({ein + aus:.2f}s) "
                           f"do not fit into the overlay ({dauer:.2f}s).")

        self.vorAenderung.emit(copy.deepcopy(self._overlays))
        self._overlays[i]["fade_in"] = ein
        self._overlays[i]["fade_out"] = aus
        self.overlaysChanged.emit()
        print(f"[OverlayManager] Blenden {start_s:.2f}-{end_s:.2f}: "
              f"ein {ein:.2f}s, aus {aus:.2f}s")
        return True, ""

    def _timeline_neu(self):
        """Die blauen Balken neu setzen - nach jeder Zeitaenderung noetig."""
        self.timeline.clear_overlay_intervals()
        for ovl in self._overlays:
            self.timeline.add_overlay_interval(ovl["start"], ovl["end"])

    def clear_overlays(self):
        self._overlays.clear()
        self.timeline.clear_overlay_intervals()
        self.overlaysChanged.emit()
        
        
    def get_all_overlays(self):
        return self._overlays

    def update_overlay(self, index, **werte):
        """Einzelne Felder eines vorhandenen Overlays aendern.

        Gedacht fuer das Verschieben und Skalieren im Vorschaubild: dort
        aendern sich nur Lage und Groesse, nie Anfang oder Ende. Deshalb
        werden hier auch die Markierungen in der Timeline nicht angefasst -
        die haengen an der Zeit.

        Der vorherige Stand kommt wie bei add_overlay auf den Verlaufsstapel,
        damit "Undo Overlay" auch ein Verschieben zuruecknimmt.
        """
        if not isinstance(index, int) or not (0 <= index < len(self._overlays)):
            print(f"[WARN] update_overlay: Platz {index} gibt es nicht.")
            return False
        if not werte:
            return False
        if "start" in werte or "end" in werte:
            # Zeiten muessen gegen Schnitte und Blendenraender geprueft
            # werden; das kann diese Methode nicht leisten.
            print("[WARN] update_overlay: Zeiten aendert diese Methode nicht.")
            return False

        self.vorAenderung.emit(copy.deepcopy(self._overlays))
        self._overlays[index].update(werte)
        self.overlaysChanged.emit()
        return True

    def set_all_overlays(self, liste):
        """Den kompletten Stand ersetzen - fuer das Zuruecknehmen.

        Die Markierungen in der Timeline werden mitgezogen, sonst blieben
        blaue Balken stehen, zu denen es kein Overlay mehr gibt.
        """
        self._overlays = [dict(o) for o in (liste or [])]
        self.timeline.clear_overlay_intervals()
        for ovl in self._overlays:
            try:
                self.timeline.add_overlay_interval(ovl["start"], ovl["end"])
            except (KeyError, TypeError):
                continue
        self.overlaysChanged.emit()
        return True

    # -------------------------------------------------------------------------
    # Public-Methode: ask_user_for_overlay(marker_s, parent)
    # Öffnet InsertOverlayDialog => user:
    #   A) Wählt "overlay 1..3" => Duration + fadeIn/Out => OK
    #   B) Klickt "Add New" => FullOverlayDialog => eingeben (Bild, corner, dx,dy, scale, Dauer, fadeIn/Out)
    #      => wir rufen add_overlay(...) direkt => und schließen InsertOverlayDialog
    # -------------------------------------------------------------------------
    def ask_user_for_overlay(self, marker_s: float, parent=None):
        """Overlay einfuegen: erst das Bild waehlen, dann die Zeitwerte.

        Frueher stand hier die Auswahl zwischen drei festen Plaetzen aus den
        Einstellungen. Jetzt uebernimmt das der OverlayInsertDialog, der die
        Bilder dieses Projekts, die Bibliothek und den Dateidialog in einer
        Liste zusammenfasst.

        Die Pruefung gegen Schnitte und Blendenraender bleibt unveraendert in
        add_overlay - sie ist der Grund, warum Vorschau und Export nicht
        auseinanderlaufen koennen.

        Der alte InsertOverlayDialog steht weiter unten unveraendert; wer
        zurueck will, ersetzt hier nur die eine Zeile.
        """
        from views.overlay_insert_dialog import OverlayInsertDialog

        dlg = OverlayInsertDialog(marker_s, self, parent)
        if dlg.exec() == QDialog.Accepted and dlg.ergebnis:
            self.add_overlay(dlg.ergebnis)
        elif getattr(dlg, "bereits_hinzugefuegt", False):
            # "Erweitert…" hat das Overlay selbst eingetragen.
            pass
        else:
            print("[OverlayManager] => Einfuegen abgebrochen")


    # =========================================================================
    # 1) InsertOverlayDialog
    #    => Zeigt Combobox mit overlay 1..3 + Button "Add New"
    #    => Evtl. (Dauer, fadeIn/Out) => OK
    # =========================================================================
    class InsertOverlayDialog(QDialog):
        def __init__(self, marker_s, overlay_manager, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Insert Overlay")

            self._manager = overlay_manager
            self.marker_s = marker_s

            self.chosen_overlay_id = None
            self.duration_s = 5.0
            self.fade_in_s  = 1.0
            self.fade_out_s = 1.0

            layout = QVBoxLayout(self)

            lbl_info = QLabel(
                "Pick an existing Overlay from QSettings (1..3)\n"
                "Or click 'Add New' to define everything (image, dx, corner, + duration etc.)."
            )
            layout.addWidget(lbl_info)

            # => Combo overlay i
            self.combo = QComboBox()
            s = QSettings("KVRouite", "KVRouite")
            count_found = 0
            for i in [1,2,3]:
                image_path = s.value(f"overlay/{i}/image","",str).strip()
                if image_path:
                    self.combo.addItem(f"overlay {i}")
                    count_found += 1
            layout.addWidget(self.combo)

            # => Button "Add New"
            btn_new = QPushButton("Add New")
            btn_new.clicked.connect(self._on_add_new_clicked)
            layout.addWidget(btn_new)

            # => Duration
            lbl_dur = QLabel("Duration (s):")
            layout.addWidget(lbl_dur)

            self.spin_dur = QDoubleSpinBox()
            self.spin_dur.setRange(0.1,30.0)
            self.spin_dur.setValue(15.0)
            self.spin_dur.setDecimals(2)
            layout.addWidget(self.spin_dur)

            # => fade in/out
            fade_h = QHBoxLayout()
            lbl_in = QLabel("Fade In(s):")
            self.spin_in = QDoubleSpinBox()
            self.spin_in.setRange(0.0,5.0)
            self.spin_in.setValue(1.0)
            self.spin_in.setDecimals(2)
            fade_h.addWidget(lbl_in)
            fade_h.addWidget(self.spin_in)

            lbl_out= QLabel("Fade Out(s):")
            self.spin_out = QDoubleSpinBox()
            self.spin_out.setRange(0.0,5.0)
            self.spin_out.setValue(1.0)
            self.spin_out.setDecimals(2)
            fade_h.addWidget(lbl_out)
            fade_h.addWidget(self.spin_out)

            layout.addLayout(fade_h)

            # => Ok / Cancel
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
            layout.addWidget(btn_box)
            btn_box.accepted.connect(self._on_ok_clicked)
            btn_box.rejected.connect(self.reject)
            
        


        def _on_add_new_clicked(self):
            """
            Öffnet FullOverlayDialog => prompt user => 
            wenn ok => dort sofort add_overlay(...) 
            => wir schließen uns hier.
            """
            dlg = OverlayManager.FullOverlayDialog(self.marker_s, self._manager, parent=self)
            if dlg.exec() == QDialog.Accepted:
                # => Overlay ist bereits angelegt + Timeline gemalt
                self.reject()  
                return
            # => user abgebrochen => bleibe hier => user kann weiter die combo (1..3) nutzen

        def _on_ok_clicked(self):
            # => user wählt overlay i
            idx = self.combo.currentIndex()
            if idx < 0:
                self.reject()
                return

            text_ = self.combo.itemText(idx).lower().strip()
            if text_.startswith("overlay"):
                arr = text_.split()
                if len(arr)>=2:
                    self.chosen_overlay_id = arr[1]
                else:
                    self.chosen_overlay_id = "1"
            else:
                self.chosen_overlay_id = "1"

            self.duration_s = self.spin_dur.value()
            self.fade_in_s  = self.spin_in.value()
            self.fade_out_s = self.spin_out.value()

            self.accept()
            
    
        

    # =========================================================================
    # 2) FullOverlayDialog
    #    => EIGENER Dialog: (Bild, scale, corner, dx, dy, + Duration, fade_in, fade_out)
    #    => Auf OK: timeline-> add_overlay => Schließen
    # =========================================================================
    class FullOverlayDialog(QDialog):
        def __init__(self, marker_s, overlay_manager, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Add new Overlay (Full)")

            self.marker_s = marker_s
            self._manager = overlay_manager

            layout = QVBoxLayout(self)

            lbl_info = QLabel(
                "Define your new Overlay:\n"
                "Image, scale, corner, dx/dy,\n"
                "plus Duration, FadeIn, FadeOut."
            )
            layout.addWidget(lbl_info)

            # (A) Bild
            row_img = QHBoxLayout()
            lbl_img = QLabel("Image path:")
            row_img.addWidget(lbl_img)
            self.line_img = QLineEdit()
            row_img.addWidget(self.line_img)

            def on_browse(checked=None):
                f, _ = QFileDialog.getOpenFileName(self, "Select overlay image")
                if f:
                    self.line_img.setText(f)

            btn_browse = QPushButton("...")
            btn_browse.clicked.connect(on_browse)
            row_img.addWidget(btn_browse)
            layout.addLayout(row_img)

            # (B) Scale
            row_scale = QHBoxLayout()
            lbl_scale = QLabel("Scale:")
            row_scale.addWidget(lbl_scale)
            self.spin_scale = QDoubleSpinBox()
            self.spin_scale.setRange(0.0,10.0)
            self.spin_scale.setValue(1.0)
            self.spin_scale.setDecimals(3)
            row_scale.addWidget(self.spin_scale)
            layout.addLayout(row_scale)

            # (C) corner
            row_corner = QHBoxLayout()
            lbl_corner= QLabel("Corner:")
            row_corner.addWidget(lbl_corner)
            self.combo_corner= QComboBox()
            self.combo_corner.addItems([
                "top-left","top-right","bottom-left","bottom-right","center"
            ])
            row_corner.addWidget(self.combo_corner)
            layout.addLayout(row_corner)

            # (D) dx, dy
            row_offset = QHBoxLayout()
            lbl_dx = QLabel("dx:")
            self.spin_dx = QSpinBox()
            self.spin_dx.setRange(0,9999)
            self.spin_dx.setValue(10)
            row_offset.addWidget(lbl_dx)
            row_offset.addWidget(self.spin_dx)

            lbl_dy = QLabel("dy:")
            self.spin_dy = QSpinBox()
            self.spin_dy.setRange(0,9999)
            self.spin_dy.setValue(10)
            row_offset.addWidget(lbl_dy)
            row_offset.addWidget(self.spin_dy)
            layout.addLayout(row_offset)

            # (E) Duration, fade_in/out
            row_dur = QHBoxLayout()
            lbl_d = QLabel("Duration (s):")
            self.spin_dur = QDoubleSpinBox()
            self.spin_dur.setRange(0.1,99999.0)
            self.spin_dur.setValue(5.0)
            self.spin_dur.setDecimals(2)

            row_dur.addWidget(lbl_d)
            row_dur.addWidget(self.spin_dur)
            layout.addLayout(row_dur)

            row_fade = QHBoxLayout()
            lbl_in = QLabel("FadeIn(s):")
            self.spin_in = QDoubleSpinBox()
            self.spin_in.setRange(0.0,9999.0)
            self.spin_in.setValue(1.0)
            self.spin_in.setDecimals(2)
            row_fade.addWidget(lbl_in)
            row_fade.addWidget(self.spin_in)

            lbl_out= QLabel("FadeOut(s):")
            self.spin_out = QDoubleSpinBox()
            self.spin_out.setRange(0.0,9999.0)
            self.spin_out.setValue(1.0)
            self.spin_out.setDecimals(2)
            row_fade.addWidget(lbl_out)
            row_fade.addWidget(self.spin_out)
            layout.addLayout(row_fade)

            # (F) OK/Cancel
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(btn_box)
            btn_box.accepted.connect(self._on_ok)
            btn_box.rejected.connect(self.reject)

        def _on_ok(self):
            """
            Liest alle Felder, baut ein Overlay-Dict,
            ruft overlay_manager.add_overlay => timeline blau,
            dann accept()
            """
            image_val = self.line_img.text().strip()
            scale_val = self.spin_scale.value()
            corner_val= self.combo_corner.currentText()
            dx_val    = self.spin_dx.value()
            dy_val    = self.spin_dy.value()

            dur_val   = self.spin_dur.value()
            fade_in   = self.spin_in.value()
            fade_out  = self.spin_out.value()

            start_s   = self.marker_s
            end_s     = start_s + dur_val

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

            ovl_dict = {
                "start":    start_s,
                "end":      end_s,
                "fade_in":  fade_in,
                "fade_out": fade_out,
                "image":    image_val,
                "scale":    scale_val,
                "x":        x_expr,
                "y":        y_expr
            }
            self._manager.add_overlay(ovl_dict)

            self.accept()
    def remove_overlay_interval(self, start_s, end_s):
        if not self._overlays:
            return
        import copy
        # Damit Strg+Z auch das Loeschen zuruecknimmt.
        self.vorAenderung.emit(copy.deepcopy(self._overlays))

        found_i = -1
        for i, ovl in enumerate(self._overlays):
            # ovl hat "start", "end"
            if abs(ovl["start"] - start_s) < 0.001 and abs(ovl["end"] - end_s) < 0.001:
                found_i = i
                break
        if found_i >= 0:
            self._overlays.pop(found_i)
            self.timeline.clear_overlay_intervals()
            for ovl in self._overlays:
                self.timeline.add_overlay_interval(ovl["start"], ovl["end"])
            self.overlaysChanged.emit()
            print(f"[OverlayManager] removed overlay {start_s:.2f}..{end_s:.2f}")

