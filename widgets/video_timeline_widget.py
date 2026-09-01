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
from PySide6.QtCore import Qt, QPoint, QRectF, Signal
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
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
        self._draw_time_ticks(painter, w, h, timeline_real_width)
        self._draw_boundaries_and_markers(painter, w, h, timeline_real_width)

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

        brush_black = QBrush(QColor(0, 0, 0, 150))
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
                edge = min(0.35, 6.0 / rect_width)
                grad = QLinearGradient(x_start, 0.0, x_start + rect_width, 0.0)
                grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                grad.setColorAt(edge, QColor(0, 0, 0, 150))
                grad.setColorAt(1.0 - edge, QColor(0, 0, 0, 150))
                grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.fillRect(QRectF(x_start, 0, rect_width, h),
                                 QBrush(grad))

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
                
                reply = QMessageBox.question(
                    None,
                    "Remove Overlay?",
                    f"Remove Overlay from {start_s:.1f}s to {end_s:.1f}s?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
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
                    self.cutMenuRequested.emit(start_s, end_s, event.globalPos())
                    break

        if not found_any:
            event.ignore()
        else:
            event.accept()

    
            