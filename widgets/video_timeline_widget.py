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

# widgets/video_timeline_widget.py
import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (QPainter, QPen, QBrush, QColor, QPolygon,
                          QLinearGradient, QWheelEvent)

def _nice_number(value: float) -> float:
    
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    f = value / (10 ** exp)
    if f < 2:
        nf = 1
    elif f < 5:
        nf = 2
    elif f < 10:
        nf = 5
    else:
        nf = 10
    return nf * (10 ** exp)

class VideoTimelineWidget(QWidget):
    markerMoved = Signal(float)
    overlayRemoveRequested = Signal(float, float)
    # Rechtsklick auf einen schwarzen Block: Blende <-> harte Kante
    cutHardToggleRequested = Signal(float, float)
    #: Zoom, Ausschnitt oder Breite haben sich geaendert - wer Bilder zu den
    #: sichtbaren Stellen vorhaelt, muss nachladen. Bewusst EIN Signal statt
    #: einer Meldung an jeder Stelle, die den Zoom oder den Versatz setzt:
    #: davon gibt es acht, und eine uebersehene waere ein Streifen, der
    #: gelegentlich nicht nachzieht.
    ansichtGeaendert = Signal()
    #: Ein Schnitt wurde mit der Maus verschoben: (alt_start, alt_ende,
    #: neu_start, neu_ende). Gemeldet wird erst beim Loslassen - waehrend des
    #: Ziehens wird nur gezeichnet. Ein Umzug kostet das Neurechnen der
    #: GPX-Spur und womoeglich eine neu gerenderte Blende; das je Pixel zu tun
    #: waere nicht zu bedienen.
    cutMoveRequested = Signal(float, float, float, float)
    #: Rechtsklick auf einen Schnitt: das Fenster soll das Menue dazu zeigen.
    #: Was darin moeglich ist, weiss nur das MainWindow - ob es eine
    #: Aufzeichnung gibt, ob die GPX-Spur zwischenzeitlich bearbeitet wurde.
    cutMenuRequested = Signal(float, float, object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_duration = 0.0
        self._marker_position_s = 0.0
        self.boundaries = []
        self.markB_time_s = -1.0
        self.markE_time_s = -1.0
        self._cut_intervals = []
        # Schluessel der Schnitte, die ohne Blende ausgefuehrt werden.
        # Wird vom VideoCutManager gesetzt, siehe set_hard_cut_keys().
        self._hard_cut_keys = set()
        # Bereich, auf den gerade rechtsgeklickt wurde: (start_s, ende_s).
        # Er wird hervorgehoben, solange das Menue oder die Rueckfrage offen
        # ist - bei mehreren Schnitten dicht beieinander ist sonst nicht zu
        # sehen, welcher gemeint ist.
        self._markierter_bereich = None

        # Bildstreifen im Hintergrund. Gefuellt wird er von aussen (MainWindow
        # kennt die Playlist), hier wird nur gezeichnet.
        # Je Eintrag: (zeit_s in Gesamtzeit, QImage)
        self._vorschaubilder = []
        self._bilder_zeigen = True
        self._dragging_marker = False
        self._dragging_timeline = False
        self._timeline_drag_start_x = 0
        self._horizontal_offset_start = 0
        self._marker_screen_x_at_drag_start = 0
        self._zoom_factor = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 50.0
        self._horizontal_offset = 0
        self._scroll_speed_px = 50
        self.setStyleSheet("background-color: #333333;")
        self._overlay_intervals = []
        # Siehe set_overlays_wirksam: im Copy-Mode nur Rahmen statt Fuellung.
        self._overlays_wirksam = True
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        # ---- Schnitte mit der Maus verschieben --------------------------
        # Der laufende Umzug: welcher Schnitt, welche Kante, wo er gerade
        # laege. Solange _zieh_schnitt steht, wird nur gezeichnet.
        self._zieh_schnitt = None      # (start_s, ende_s) des Originals
        self._zieh_art = None          # "links", "rechts" oder "block"
        self._zieh_zeit_start = 0.0    # Zeit unter dem Zeiger beim Zugriff
        self._zieh_grenzen = (0.0, 0.0)
        self._zieh_neu = None          # (start_s, ende_s) der neuen Lage
        self._zeiger_form = None

        # Zwei Auskuenfte, die nur das MainWindow geben kann: in welchem
        # Bereich ein Schnitt liegen darf und ob er ueberhaupt umziehen darf.
        # Bewusst als schlichte Rueckrufe und nicht als eigene Regeln hier:
        # sonst staenden dieselben Bedingungen an zwei Stellen und wuerden
        # auseinanderlaufen. Gesetzt werden sie im MainWindow.
        self.grenzen_geber = None      # (start, ende) -> (links, rechts, art)
        self.umzug_pruefer = None      # (start, ende) -> (moeglich, grund)

        # Ohne das kommt mouseMoveEvent nur bei gedrueckter Taste - die
        # Zeigerform ueber einer Kante braucht es aber vorher.
        self.setMouseTracking(True)
        
    def clear_all_cuts(self):
        """
        Entfernt alle Cut-Intervalle aus der Timeline.
        """
        self._cut_intervals = []
        self._hard_cut_keys = set()
        self.update()

    def set_hard_cut_keys(self, keys):
        """Schnitte markieren, die ohne Blende ausgefuehrt werden.

        keys enthaelt (start, end)-Paare, gerundet auf 3 Nachkommastellen
        (VideoCutManager._cut_key).
        """
        self._hard_cut_keys = set(keys or ())
        self.update()

    @staticmethod
    def _cut_key(start_s, end_s):
        return (round(float(start_s), 3), round(float(end_s), 3))
    
        
    def add_overlay_interval(self, start_s: float, end_s: float):
        """
        Speichert ein Overlay-Zeitintervall, damit wir es in Blau markieren können.
        """
        self._overlay_intervals.append((start_s, end_s))
        self.update()

    def clear_overlay_intervals(self):
        self._overlay_intervals.clear()
        self.update()

    def set_overlays_wirksam(self, wirksam: bool):
        """Ob die Overlays im aktuellen Modus ueberhaupt im Export landen.

        Nur im Encode-Mode tun sie das. Im Copy-Mode wird das Material
        durchgereicht, ein Logo kommt im Ergebnis nicht vor - dann wird der
        Balken nur als Rahmen gezeichnet, ohne Fuellung. Gleiche Lage,
        gleiche Farbe, aber sichtbar leer: das Overlay ist da, es wirkt hier
        nur nicht.
        """
        wirksam = bool(wirksam)
        if wirksam != self._overlays_wirksam:
            self._overlays_wirksam = wirksam
            self.update()
    

    def set_marker_position(self, time_s: float):
        if self.total_duration <= 0:
            self._marker_position_s = 0.0
            return
        if time_s < 0:
            time_s = 0
        if time_s > self.total_duration:
            time_s = self.total_duration
        self._marker_position_s = time_s
        self._keep_marker_visible()
        self.update()

    def marker_position(self) -> float:
        return self._marker_position_s

    def _update_marker_by_mouse_x(self, x_mouse: int):
        w = self.width()
        if w <= 0 or self.total_duration <= 0:
            return
        timeline_real_width = w * self._zoom_factor
        x_timeline = x_mouse + self._horizontal_offset
        if x_timeline < 0:
            x_timeline = 0
        if x_timeline > timeline_real_width:
            x_timeline = timeline_real_width
        ratio = x_timeline / timeline_real_width if timeline_real_width > 0 else 0.0
        new_time_s = ratio * self.total_duration
        self.set_marker_position(new_time_s)
        self.markerMoved.emit(new_time_s)

    def _keep_marker_visible(self):
        w = self.width()
        if w <= 0 or self.total_duration <= 0:
            return
        timeline_real_width = w * self._zoom_factor
        ratio = self._marker_position_s / self.total_duration
        marker_x = ratio * timeline_real_width - self._horizontal_offset
        if marker_x < 0:
            self._horizontal_offset = ratio * timeline_real_width
            if self._horizontal_offset < 0:
                self._horizontal_offset = 0
            return
        right_threshold = 0.95 * w
        left_position = 0.05 * w
        if marker_x > right_threshold:
            if ratio < 0.95:
                shift = marker_x - left_position
                self._horizontal_offset += shift
                if self._horizontal_offset < 0:
                    self._horizontal_offset = 0

    def set_total_duration(self, dur_s: float):
        self.total_duration = max(0.0, dur_s)
        if self._marker_position_s > self.total_duration:
            self._marker_position_s = self.total_duration
        self._keep_marker_visible()
        self.update()

    def set_boundaries(self, boundary_list):
        self.boundaries = boundary_list
        self.update()

    def set_markB_time(self, time_s: float):
        self.markB_time_s = time_s
        self.update()

    def set_markE_time(self, time_s: float):
        self.markE_time_s = time_s
        self.update()

    def add_cut_interval(self, start_s: float, end_s: float):
        self._cut_intervals.append((start_s, end_s))
        self.update()

    def remove_last_cut_interval(self):
        if self._cut_intervals:
            self._cut_intervals.pop()
            self.update()

    # ------------------------------------------------------------------
    # Schnitte mit der Maus verschieben
    # ------------------------------------------------------------------
    #: Wie nah der Zeiger an einer Kante sein muss, um sie zu fassen.
    _KANTE_PX = 5
    #: Kuerzer darf ein Schnitt beim Ziehen nicht werden. on_cut_clicked()
    #: weist alles unter 0.01 s ohnehin ab; hier etwas mehr Luft, damit ein
    #: Schnitt nicht versehentlich auf Pixelbreite zusammenfaellt.
    _MIN_LAENGE_S = 0.05

    def _zeit_bei_x(self, x_mouse):
        """Bildschirm-x zu Rohzeit, oder None ausserhalb der Zeitleiste."""
        w = self.width()
        if w <= 0 or self.total_duration <= 0:
            return None
        breite = w * self._zoom_factor
        if breite <= 0:
            return None
        x = x_mouse + self._horizontal_offset
        x = max(0.0, min(float(x), breite))
        return (x / breite) * self.total_duration

    def _x_bei_zeit(self, zeit_s):
        """Rohzeit zu Bildschirm-x. Gegenstueck zu _zeit_bei_x()."""
        w = self.width()
        if w <= 0 or self.total_duration <= 0:
            return 0.0
        breite = w * self._zoom_factor
        return (float(zeit_s) / self.total_duration) * breite \
            - self._horizontal_offset

    def _kante_unter(self, x_mouse):
        """Was liegt unter dem Zeiger? ((start, ende), art) oder (None, None).

        art ist "links", "rechts" oder "block". Kanten werden in einem
        eigenen Durchgang zuerst gesucht: stossen zwei Schnitte aneinander,
        laege die gemeinsame Kante sonst im Block des einen und waere nicht
        mehr zu fassen.
        """
        for (a, b) in self._cut_intervals:
            if abs(x_mouse - self._x_bei_zeit(a)) <= self._KANTE_PX:
                return (a, b), "links"
            if abs(x_mouse - self._x_bei_zeit(b)) <= self._KANTE_PX:
                return (a, b), "rechts"
        for (a, b) in self._cut_intervals:
            if self._x_bei_zeit(a) <= x_mouse <= self._x_bei_zeit(b):
                return (a, b), "block"
        return None, None

    def _zeiger_setzen(self, form):
        """Zeigerform nur bei Aenderung setzen - das laeuft bei jeder
        Mausbewegung durch."""
        if form == self._zeiger_form:
            return
        self._zeiger_form = form
        if form is None:
            self.unsetCursor()
        else:
            self.setCursor(form)

    def _hinweis(self, global_pos, text):
        """Kurzer Hinweis am Zeiger, warum gerade nichts passiert.

        Ohne Position - etwa aus einer Pruefung heraus aufgerufen - bleibt es
        beim Protokoll. QToolTip.showText() wirft bei None.
        """
        if global_pos is None:
            print("[CUT-MOVE] " + text.replace(chr(10), " "))
            return
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(global_pos, text, self)

    def _umzug_beginnen(self, schnitt, art, x_mouse, global_pos):
        """Umzug vorbereiten. False heisst: es bleibt beim Marker."""
        if self.grenzen_geber is None:
            return False
        a0, b0 = schnitt

        if self.umzug_pruefer is not None:
            erlaubt, grund = self.umzug_pruefer(a0, b0)
            if not erlaubt:
                # Diese Pruefung rechnet einen Abdruck ueber die ganze
                # GPX-Spur. Fuer jede Mausbewegung waere das zu teuer, deshalb
                # steht sie hier beim Zugriff und nicht schon beim Wechsel der
                # Zeigerform.
                self._hinweis(global_pos,
                              grund or "This cut cannot be moved.")
                return False

        links, rechts, schnittart = self.grenzen_geber(a0, b0)

        # Anfangs- und Endschnitt haben je eine feste Kante. Sie zu loesen
        # hiesse, die Art des Schnitts zu aendern: der Endschnitt wird vor dem
        # Zusammenfuegen weggetrimmt, der Anfangsschnitt verschiebt zusaetzlich
        # die Zeitachse. Beides soll nicht beilaeufig durch Ziehen passieren.
        if schnittart == "ende" and art in ("rechts", "block"):
            self._hinweis(
                global_pos,
                "The last cut always reaches the end of the video.\n"
                "Only its beginning can be moved.")
            return False
        if schnittart == "anfang" and art in ("links", "block"):
            self._hinweis(
                global_pos,
                "The first cut always starts at the beginning of the video.\n"
                "Only its end can be moved.")
            return False

        zeit = self._zeit_bei_x(x_mouse)
        if zeit is None:
            return False

        self._zieh_schnitt = (float(a0), float(b0))
        self._zieh_art = art
        self._zieh_zeit_start = zeit
        self._zieh_grenzen = (float(links), float(rechts))
        self._zieh_neu = (float(a0), float(b0))
        self._zeiger_setzen(Qt.SizeAllCursor if art == "block"
                            else Qt.SizeHorCursor)
        self.update()
        return True

    def _umzug_aktualisieren(self, x_mouse):
        """Neue Lage aus der Mausposition. Rechnet nur, zeichnet nur."""
        zeit = self._zeit_bei_x(x_mouse)
        if zeit is None or self._zieh_schnitt is None:
            return
        a0, b0 = self._zieh_schnitt
        links, rechts = self._zieh_grenzen
        delta = zeit - self._zieh_zeit_start
        mind = self._MIN_LAENGE_S

        if self._zieh_art == "links":
            a = min(max(a0 + delta, links), b0 - mind)
            b = b0
        elif self._zieh_art == "rechts":
            a = a0
            b = max(min(b0 + delta, rechts), a0 + mind)
        else:
            laenge = b0 - a0
            a = min(max(a0 + delta, links), rechts - laenge)
            b = a + laenge

        neu = (a, b)
        if neu != self._zieh_neu:
            self._zieh_neu = neu
            self.update()

    @staticmethod
    def _zeit_kurz(sekunden):
        s = max(0.0, float(sekunden))
        return "%d:%04.1f" % (int(s // 60), s % 60)

    def _draw_umzug(self, painter, w, h):
        """Die neue Lage waehrend des Ziehens: Rahmen und Zeiten.

        Der schwarze Block bleibt derweil an seiner alten Stelle stehen. So
        ist beim Ziehen zu sehen, WOHIN es geht und woher es kam - ein
        mitwanderender Block zeigte nur noch das eine.
        """
        if self._zieh_neu is None or self.total_duration <= 0:
            return
        a, b = self._zieh_neu
        x0 = self._x_bei_zeit(a)
        x1 = self._x_bei_zeit(b)
        if x1 < 0 or x0 > w:
            return

        painter.save()
        try:
            farbe = QColor("#ffcc00")
            painter.setPen(QPen(farbe, 2))
            painter.setBrush(QColor(255, 204, 0, 45))
            painter.drawRect(QRectF(x0, 0, max(1.0, x1 - x0), h - 1))

            text = "%s - %s  (%.1fs)" % (self._zeit_kurz(a),
                                         self._zeit_kurz(b), b - a)
            breite_text = painter.fontMetrics().horizontalAdvance(text) + 8
            x_text = x0 + 4
            if x_text + breite_text > w:
                x_text = max(0.0, w - breite_text)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 170))
            painter.drawRect(QRectF(x_text - 4, 2, breite_text, 16))
            painter.setPen(farbe)
            painter.drawText(QPointF(x_text, 14), text)
        finally:
            painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Zuerst die Schnitte fragen: liegt der Zeiger auf einer Kante
            # oder in einem Block, wird gezogen statt der Marker gesetzt.
            schnitt, art = self._kante_unter(event.pos().x())
            if schnitt is not None and self._umzug_beginnen(
                    schnitt, art, event.pos().x(), event.globalPos()):
                event.accept()
                return
            self._dragging_marker = True
            self._update_marker_by_mouse_x(event.pos().x())
            event.accept()
        elif event.button() == Qt.RightButton:
            self._dragging_timeline = True
            self._timeline_drag_start_x = event.pos().x()
            self._horizontal_offset_start = self._horizontal_offset
            w = self.width()
            if w > 0 and self.total_duration > 0:
                timeline_real_width = w * self._zoom_factor
                marker_x_current = (self._marker_position_s / self.total_duration)*timeline_real_width - self._horizontal_offset
                self._marker_screen_x_at_drag_start = marker_x_current
            else:
                self._marker_screen_x_at_drag_start = 0
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._zieh_schnitt is not None:
            self._umzug_aktualisieren(event.pos().x())
            event.accept()
            return
        if not (self._dragging_marker or self._dragging_timeline):
            # Ohne gedrueckte Taste nur die Zeigerform. Rein geometrisch -
            # ob der Schnitt umziehen DARF, wird erst beim Zugriff geprueft.
            _s, art = self._kante_unter(event.pos().x())
            if art in ("links", "rechts"):
                self._zeiger_setzen(Qt.SizeHorCursor)
            elif art == "block":
                self._zeiger_setzen(Qt.SizeAllCursor)
            else:
                self._zeiger_setzen(None)
        if self._dragging_marker:
            self._update_marker_by_mouse_x(event.pos().x())
            event.accept()
        elif self._dragging_timeline:
            delta_x = event.pos().x() - self._timeline_drag_start_x
            self._horizontal_offset = self._horizontal_offset_start - delta_x
            w = self.width()
            if w > 0 and self.total_duration > 0:
                timeline_real_width = w * self._zoom_factor
                new_marker_x_abs = self._marker_screen_x_at_drag_start + self._horizontal_offset
                ratio = new_marker_x_abs / timeline_real_width
                if ratio < 0:
                    ratio = 0
                elif ratio > 1:
                    ratio = 1
                new_time_s = ratio * self.total_duration
                self._marker_position_s = new_time_s
                self.markerMoved.emit(new_time_s)
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._zieh_schnitt is not None:
            a0, b0 = self._zieh_schnitt
            a, b = self._zieh_neu or (a0, b0)
            unveraendert = abs(a - a0) < 0.001 and abs(b - b0) < 0.001
            self._zieh_schnitt = None
            self._zieh_neu = None
            self._zieh_art = None
            self._zeiger_setzen(None)
            self.update()
            if unveraendert:
                # Nur geklickt, nicht gezogen - dann war der Marker gemeint.
                # Ohne das waere ein Klick in einen Schnitt wirkungslos.
                self._update_marker_by_mouse_x(event.pos().x())
            else:
                self.cutMoveRequested.emit(a0, b0, round(a, 3), round(b, 3))
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._dragging_marker:
            self._dragging_marker = False
            event.accept()
        elif event.button() == Qt.RightButton and self._dragging_timeline:
            self._dragging_timeline = False
            event.accept()
        else:
            event.ignore()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.ShiftModifier:
            if delta > 0:
                self._horizontal_offset = max(0, self._horizontal_offset - self._scroll_speed_px)
            else:
                self._horizontal_offset += self._scroll_speed_px
            self._keep_marker_visible()
            self.update()
            event.accept()
            return
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.1 if delta > 0 else (1.0 / 1.1)
            new_zoom = self._zoom_factor * factor
            if new_zoom < self._min_zoom:
                new_zoom = self._min_zoom
            if new_zoom > self._max_zoom:
                new_zoom = self._max_zoom
            self._zoom_factor = new_zoom
            self._center_marker_at_ratio(0.3)
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def _center_marker_at_ratio(self, widget_ratio: float):
        w = self.width()
        if w <= 0 or self.total_duration <= 0:
            return
        timeline_real_width = w * self._zoom_factor
        marker_x_absolute = (self._marker_position_s / self.total_duration)*timeline_real_width
        desired_x_in_widget = widget_ratio * w
        self._horizontal_offset = marker_x_absolute - desired_x_in_widget
        if self._horizontal_offset < 0:
            self._horizontal_offset = 0

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QBrush, QPolygon
        from PySide6.QtCore import QPoint

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect_ = self.rect()
        w = rect_.width()
        h = rect_.height()
        painter.fillRect(rect_, QColor("#333333"))
        painter.setClipRect(rect_)

        timeline_real_width = w * self._zoom_factor

        # Hat sich der sichtbare Ausschnitt geaendert, Bescheid geben. Der
        # Empfaenger stoesst davon nur einen Zeitgeber an, es kann also nicht
        # zu einer Schleife aus Melden und Neuzeichnen kommen.
        zustand = (round(self._zoom_factor, 4),
                   round(float(self._horizontal_offset), 1), w)
        if zustand != getattr(self, "_letzte_ansicht", None):
            self._letzte_ansicht = zustand
            self.ansichtGeaendert.emit()

        self._draw_vorschaubilder(painter, w, h, timeline_real_width)
        self._draw_time_ticks(painter, w, h, timeline_real_width)
        self._draw_boundaries_and_markers(painter, w, h, timeline_real_width)
        self._draw_umzug(painter, w, h)

    # ------------------------------------------------------------------
    # Bildstreifen
    # ------------------------------------------------------------------
    def set_vorschaubilder(self, bilder):
        """bilder: Liste aus (zeit_s in Gesamtzeit, QImage)."""
        self._vorschaubilder = list(bilder or [])
        self.update()

    def vorschaubilder_zeigen(self, an: bool):
        self._bilder_zeigen = bool(an)
        self.update()

    def _draw_vorschaubilder(self, painter, w, h, timeline_real_width):
        """Die Bilder als Hintergrund, jeweils an ihrer Zeitstelle.

        Sie werden abgedunkelt gezeichnet. Ohne das waeren die Zeitmarken und
        die Beschriftung darauf nicht mehr zu lesen, und die schwarzen
        Schnittbloecke wuerden sich kaum noch abheben.

        Gezeigt wird ROHZEIT, wie die ganze Zeitleiste. Die Schnittbloecke
        liegen also darueber - man sieht dadurch, welches Material
        weggeschnitten wird.
        """
        if (not self._bilder_zeigen or not self._vorschaubilder
                or self.total_duration <= 0 or timeline_real_width <= 0):
            return

        def x_von(zeit_s):
            return (zeit_s / self.total_duration) * timeline_real_width \
                - self._horizontal_offset

        bilder = self._vorschaubilder
        for i, (zeit_s, bild) in enumerate(bilder):
            if bild is None or bild.isNull():
                continue
            x = x_von(zeit_s)
            # Bis zum naechsten Bild reichen - das ergibt einen lueckenlosen
            # Streifen. Wuerde jedes Bild nur in seiner eigenen Breite
            # gezeichnet, klafften dazwischen schwarze Spalten, sobald der
            # Abstand groesser ist als das Bild breit.
            if i + 1 < len(bilder):
                x_ende = x_von(bilder[i + 1][0])
            else:
                x_ende = x + bild.width()
            abschnitt = x_ende - x
            if abschnitt <= 0 or x + abschnitt < 0 or x > w:
                continue

            quelle = None
            if abschnitt < bild.width():
                # Schmaler als das Bild: mittigen Ausschnitt nehmen statt zu
                # stauchen - gestauchte Bilder sind im Streifen nicht mehr zu
                # erkennen.
                links = int((bild.width() - abschnitt) / 2)
                quelle = QRectF(links, 0, abschnitt, bild.height())

            ziel = QRectF(x, 0, abschnitt, min(h, bild.height()))
            if quelle is not None:
                painter.drawImage(ziel, bild, quelle)
            else:
                painter.drawImage(ziel, bild)

        # Gleichmaessig abdunkeln, damit alles Weitere darauf lesbar bleibt.
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 120))

    def _draw_time_ticks(self, painter, w, h, timeline_real_width):
        if self.total_duration <= 0 or timeline_real_width <= 0:
            return
        desired_px_between_major_ticks = 100.0
        num_subticks = 4
        px_per_sec = timeline_real_width / self.total_duration
        raw_step_sec = desired_px_between_major_ticks / px_per_sec
        step_sec = _nice_number(raw_step_sec)
        sub_tick_sec = step_sec / (num_subticks + 1)

        from PySide6.QtGui import QPen
        pen_major = QPen(QColor("#CCCCCC"), 2)
        pen_minor = QPen(QColor("#AAAAAA"), 1)

        main_tick_height = 10
        sub_tick_height  = 6
        text_offset_y = h - main_tick_height - 3
        end_time = self.total_duration
        t = 0.0
        while t <= end_time + 0.0001:
            x_timeline = (t * px_per_sec) - self._horizontal_offset
            if -50 < x_timeline < w + 50:
                index_float = t / step_sec
                is_major = abs(index_float - round(index_float)) < 0.001
                if is_major:
                    painter.setPen(pen_major)
                    y_start = h - main_tick_height
                    painter.drawLine(x_timeline, y_start, x_timeline, h)
                    mm = int(t // 60)
                    ss = int(t % 60)
                    time_label = f"{mm:02d}:{ss:02d}"
                    painter.drawText(x_timeline - 15, text_offset_y, time_label)
                else:
                    painter.setPen(pen_minor)
                    y_start = h - sub_tick_height
                    painter.drawLine(x_timeline, y_start, x_timeline, h)
            t += sub_tick_sec

    #: Abstand der Schraffurlinien in einem Schnittblock.
    SCHRAFFUR_ABSTAND = 9

    def _schraffur(self, painter, x_start, breite, h):
        """Diagonale Linien ueber einen Schnittblock.

        Das Muster macht den Block auch dort erkennbar, wo das Videobild
        selbst dunkel ist. Es wird auf den Block begrenzt, damit die Linien
        nicht in benachbartes Material laufen.
        """
        if breite < 3:
            return
        painter.save()
        painter.setClipRect(QRectF(x_start, 0, breite, h))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        # Von links unten nach rechts oben, um h versetzt - so treffen die
        # Linien den Block unabhaengig von seiner Breite.
        x = x_start - h
        while x < x_start + breite + h:
            painter.drawLine(QPointF(x, h), QPointF(x + h, 0.0))
            x += self.SCHRAFFUR_ABSTAND
        painter.restore()

    def _cut_bloecke(self, eps: float = 0.001):
        """Die Schnitte so, wie sie im Video wirklich aussehen.

        Aneinandergrenzende oder ueberlappende Schnitte sind dort EIN Loch -
        zwischen ihnen liegt kein Bild. Gezeichnet wurde bisher aber jeder
        einzeln, mit einem an beiden Raendern auslaufenden Verlauf. An der
        Stossstelle trafen dadurch zwei helle Kanten aufeinander und sahen
        aus wie ein kurzes Stueck Video.

        Zusammengefasst wird nur fuers Zeichnen. self._cut_intervals bleibt
        unangetastet, damit der Rechtsklick weiterhin den einzelnen Schnitt
        trifft.

        Liefert (start, ende, hart) - hart, wenn irgendein Schnitt der
        Gruppe eine harte Kante ist; im Video ist die Gruppe ja ein Uebergang.
        """
        gueltig = sorted((min(a, b), max(a, b)) for (a, b) in self._cut_intervals
                         if b > a)
        bloecke = []
        for (a, b) in gueltig:
            hart = self._cut_key(a, b) in self._hard_cut_keys
            if bloecke and a <= bloecke[-1][1] + eps:
                vorher = bloecke[-1]
                bloecke[-1] = (vorher[0], max(vorher[1], b), vorher[2] or hart)
            else:
                bloecke.append((a, b, hart))
        return bloecke

    def _draw_boundaries_and_markers(self, painter, w, h, timeline_real_width):
        from PySide6.QtGui import QPen, QBrush, QPolygon
        pen_blue = QPen(QColor("blue"), 3)
        painter.setPen(pen_blue)
        painter.setBrush(Qt.NoBrush)
        if self.total_duration > 0:
            for b_sec in self.boundaries:
                if 0 < b_sec < self.total_duration:
                    ratio_b = b_sec / self.total_duration
                    x_b = ratio_b*timeline_real_width - self._horizontal_offset
                    if -50 < x_b < w+50:
                        painter.drawLine(x_b, 0, x_b, h)

        pen_marker = QPen(QColor("white"), 2)
        painter.setPen(pen_marker)
        painter.setBrush(QBrush(QColor("white")))
        if self.total_duration > 0:
            ratio = self._marker_position_s / self.total_duration
            marker_x = ratio*timeline_real_width - self._horizontal_offset
            if -50 < marker_x < w+50:
                painter.drawLine(marker_x, 0, marker_x, h)
                arrow_height = 10
                arrow_half = 6
                arrow_points = [
                    QPoint(marker_x - arrow_half, 0),
                    QPoint(marker_x + arrow_half, 0),
                    QPoint(marker_x, arrow_height),
                ]
                painter.drawPolygon(QPolygon(arrow_points))

        pen_yellow = QPen(QColor("yellow"), 2)
        painter.setPen(pen_yellow)
        painter.setBrush(Qt.NoBrush)
        xB = xE = -1
        #if 0 <= self.markB_time_s <= self.total_duration:
        if self.markB_time_s is not None and 0 <= self.markB_time_s <= self.total_duration:
            xB = (self.markB_time_s/self.total_duration)*timeline_real_width - self._horizontal_offset
            if -50 < xB < w+50:
                painter.drawLine(xB, 0, xB, h)

        if self.markE_time_s is not None and 0 <= self.markE_time_s <= self.total_duration:
        #if 0 <= self.markE_time_s <= self.total_duration:
            xE = (self.markE_time_s/self.total_duration)*timeline_real_width - self._horizontal_offset
            if -50 < xE < w+50:
                painter.drawLine(xE, 0, xE, h)

        if xB >= 0 and xE >= 0:
            left_x = min(xB, xE)
            right_x = max(xB, xE)
            if right_x > left_x:
                brush_yellow = QBrush(QColor(255,255,0,80))
                painter.fillRect(left_x, 0, right_x-left_x, h, brush_yellow)

        # Deutlich deckender als frueher (150): unter dem Block liegt jetzt
        # das Videobild, und auf dunklem Material war der Schnitt sonst nicht
        # als solcher zu erkennen.
        brush_black = QBrush(QColor(0, 0, 0, 215))
        pen_black = QPen(QColor("black"), 1)
        pen_hard = QPen(QColor("#FF8A3D"), 1)
        painter.setPen(pen_black)
        for (start_s, end_s, gruppe_hart) in self._cut_bloecke():
            if start_s < 0 or end_s <= 0 or self.total_duration <= 0:
                continue
            start_ratio = max(0.0, start_s/self.total_duration)
            end_ratio   = min(1.0, end_s/self.total_duration)
            if end_ratio <= start_ratio:
                continue
            x_start = start_ratio*timeline_real_width - self._horizontal_offset
            x_end   = end_ratio*timeline_real_width - self._horizontal_offset
            if x_end < -50 or x_start > w+50:
                continue
            rect_width = x_end - x_start
            if rect_width < 1:
                rect_width = 1

            if gruppe_hart:
                # Harte Kante: Block bleibt schwarz, die Schnittkanten werden
                # orange markiert. Bei sehr schmalen Bloecken wuerden zwei
                # Linien ineinanderlaufen, deshalb dort nur eine.
                painter.fillRect(QRectF(x_start, 0, rect_width, h), brush_black)
                painter.setPen(pen_hard)
                painter.drawLine(x_start, 0, x_start, h)
                if rect_width >= 4:
                    painter.drawLine(x_start + rect_width, 0,
                                     x_start + rect_width, h)
                painter.setPen(pen_black)
            elif rect_width < 4:
                # Zu schmal fuer einen Verlauf - der Block waere sonst kaum
                # noch zu sehen.
                painter.fillRect(QRectF(x_start, 0, rect_width, h), brush_black)
            else:
                # Blende: der Block laeuft an beiden Raendern weich aus.
                # Der Verlauf ist rund 6 px breit, unabhaengig vom Zoom.
                #
                # Seit dem Bildstreifen laufen die Raender NICHT mehr auf
                # durchsichtig aus, sondern nur noch auf halbe Deckung: auf
                # dunklem Material - Schatten, Mauern, Tunnel - war der Block
                # sonst kaum vom Bild zu unterscheiden. Der Verlauf zeigt
                # weiterhin, dass hier eine Blende liegt.
                edge = min(0.35, 6.0 / rect_width)
                grad = QLinearGradient(x_start, 0.0, x_start + rect_width, 0.0)
                grad.setColorAt(0.0, QColor(0, 0, 0, 90))
                grad.setColorAt(edge, QColor(0, 0, 0, 215))
                grad.setColorAt(1.0 - edge, QColor(0, 0, 0, 215))
                grad.setColorAt(1.0, QColor(0, 0, 0, 90))
                painter.fillRect(QRectF(x_start, 0, rect_width, h),
                                 QBrush(grad))

            # Schraffur und Kanten - erst dadurch ist ein Schnitt auf jedem
            # Untergrund als Schnitt zu erkennen. Eine weitere Vollfarbe waere
            # dafuer untauglich: Blau ist fuer Overlays vergeben, Orange fuer
            # die harte Kante, und jede andere kann im Bild selbst vorkommen.
            # Ein Muster kann das nicht.
            self._schraffur(painter, x_start, rect_width, h)
            if not gruppe_hart:
                # Bei harter Kante sind die Raender bereits orange markiert -
                # weisse Linien wuerden sie nur ueberdecken.
                painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
                painter.drawLine(QPointF(x_start, 0), QPointF(x_start, h))
                painter.drawLine(QPointF(x_start + rect_width, 0),
                                 QPointF(x_start + rect_width, h))
            painter.setPen(pen_black)

        # Zeichnen der Overlay-Intervalle (blau)
        if self.total_duration > 0 and self._overlay_intervals:
            pen_blue = QPen(QColor("blue"), 2)
            painter.setPen(pen_blue)
            if self._overlays_wirksam:
                # halbtransparentes Blau
                painter.setBrush(QBrush(QColor(0, 0, 255, 80)))
            else:
                # Copy-Mode: das Overlay landet nicht im Export. Gleiche Lage,
                # gleiche Farbe, aber ohne Fuellung - der leere Rahmen sagt,
                # dass hier nichts herauskommt.
                painter.setBrush(Qt.NoBrush)
            for (start_s, end_s) in self._overlay_intervals:
                if end_s <= start_s:
                    continue
                start_ratio = start_s / self.total_duration
                end_ratio   = end_s   / self.total_duration
                x_start = (start_ratio * timeline_real_width) - self._horizontal_offset
                x_end   = (end_ratio   * timeline_real_width) - self._horizontal_offset
                if x_end < -50 or x_start > w+50:
                    continue
                rect_w = x_end - x_start
                if rect_w < 2:
                    rect_w = 2
                painter.drawRect(x_start, 0, rect_w, h)

        # Der angeklickte Bereich, solange sein Menue offen ist. Zuletzt
        # gezeichnet, damit er ueber Schnitt und Overlay liegt.
        if self._markierter_bereich and self.total_duration > 0:
            m_start, m_end = self._markierter_bereich
            x_start = (max(0.0, m_start) / self.total_duration
                       ) * timeline_real_width - self._horizontal_offset
            x_end = (min(self.total_duration, m_end) / self.total_duration
                     ) * timeline_real_width - self._horizontal_offset
            breite = max(2.0, x_end - x_start)
            # Leicht aufhellen, damit der Bereich auch auf dem schwarzen
            # Schnittblock zu erkennen ist, dazu ein gestrichelter Rahmen.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 45)))
            painter.drawRect(QRectF(x_start, 0, breite, h))
            stift = QPen(QColor(255, 255, 255, 230), 2, Qt.DashLine)
            painter.setPen(stift)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x_start + 1, 1, breite - 2, h - 2))
                
                    

    def _markieren(self, start_s, end_s=None):
        """Bereich hervorheben (oder mit None die Hervorhebung loeschen)."""
        self._markierter_bereich = None if start_s is None else (start_s, end_s)
        self.update()
        # Sofort neu zeichnen: der Aufrufer oeffnet gleich ein Menue oder eine
        # Rueckfrage und blockiert dabei. Ohne das Durchreichen der Ereignisse
        # erschiene die Markierung erst, wenn alles schon vorbei ist.
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMessageBox
        # 1) Falls kein Video oder Overlays => Abbruch
        if self.total_duration <= 0:
            event.ignore()
            return
        w = self.width()
        if w <= 0:
            event.ignore()
            return
        timeline_real_width = w * self._zoom_factor
        x_timeline = event.pos().x() + self._horizontal_offset
        if x_timeline < 0 or x_timeline > timeline_real_width:
            event.ignore()
            return
        ratio = x_timeline / timeline_real_width
        time_clicked = ratio * self.total_duration
        # 2) Prüfen, ob time_clicked in einem Overlay-Intervall liegt
        found_any = False
        for (start_s, end_s) in self._overlay_intervals:
            if start_s <= time_clicked <= end_s:
                found_any = True

                # Erst hervorheben, dann fragen: die Rueckfrage startet ihre
                # eigene Ereignisschleife, das Neuzeichnen kommt also noch
                # rechtzeitig an.
                self._markieren(start_s, end_s)
                try:
                    reply = QMessageBox.question(
                        None,
                        "Remove Overlay?",
                        f"Remove Overlay from {start_s:.1f}s to {end_s:.1f}s?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                finally:
                    self._markieren(None)
                if reply == QMessageBox.Yes:
                    self.overlayRemoveRequested.emit(start_s, end_s)
                break
        # 3) Sonst pruefen, ob der Klick in einem Schnitt liegt
        #
        # Bis 6.01 schaltete der Rechtsklick sofort zwischen Blende und harter
        # Kante um. Seit dem Zuruecknehmen von Schnitten gibt es dort mehr als
        # eine Moeglichkeit, deshalb ein Menue. Zusammengestellt wird es im
        # MainWindow - nur dort ist bekannt, ob sich der Schnitt zuruecknehmen
        # laesst.
        if not found_any:
            for (start_s, end_s) in self._cut_intervals:
                if start_s <= time_clicked <= end_s:
                    found_any = True
                    # Das Menue laeuft in einer eigenen Ereignisschleife, der
                    # markierte Bereich wird also waehrenddessen gezeichnet.
                    self._markieren(start_s, end_s)
                    try:
                        self.cutMenuRequested.emit(start_s, end_s,
                                                   event.globalPos())
                    finally:
                        self._markieren(None)
                    break

        if not found_any:
            event.ignore()
        else:
            event.accept()

    
            