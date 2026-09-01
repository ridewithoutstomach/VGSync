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

# widgets/mini_chart_widget.py

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

class MiniChartWidget(QWidget):
    """Hoehenprofil im Ausschnitt - seit 6.02 als Modul "Chart-Flow".

    Zeigt einen Ausschnitt von wenigen GPX-Punkten um den aktuellen herum.
    Der Marker steht fest bei 70 % der Breite, die Punkte laufen darunter
    durch.

    Der Unterschied zum grossen Chart ist nicht der Zoom, sondern die
    Hoehenachse: hier wird sie nur ueber die SICHTBAREN Punkte skaliert.
    Deshalb fuellt jede Kuppe das Bild, auch wenn sie ueber die ganze
    Strecke gesehen nur ein paar Meter hoch ist. Im grossen Chart, dessen
    Achse ueber den kompletten Track laeuft, waere dieselbe Kuppe eine
    flache Linie. Genau dafuer gibt es dieses Diagramm.

    Absichtlich nicht enthalten: Geschwindigkeit, Meereshoehen-Linie,
    "under sea level" - das sind Sachen des grossen Charts.

    Strg+Mausrad stellt ein, wie viele Punkte im Bild sind.
    """

    MIN_PUNKTE = 8
    MAX_PUNKTE = 400

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)

        # Ggf. Hintergrund wie Timeline => #333333
        self.setStyleSheet("background-color: #444444 ;")

        # Interne Daten
        self._gpx_data = []
        self._max_points = 40   # wie viele GPX-Punkte im Bild sind
        self._marker_ratio_x = 0.7  # 70% vom Widget
        self._current_index = 0     # Welcher Punkt ist 'aktuell'?

        # Overlay-Modus: dieselbe Darstellung, aber durchscheinend zum
        # Einblenden ins Videobild.
        self._overlay = False
        # Zweite Ansicht derselben Daten (siehe set_zwilling).
        self._zwilling = None

    def set_zwilling(self, other):
        """Zweite Ansicht anmelden, die dieselben Daten bekommen soll.

        Das Overlay im Video zeigt denselben Ausschnitt wie das Modul. Statt
        die rund 60 vorhandenen Aufrufstellen zu verdoppeln, reicht dieses
        Widget Daten und Index selbst weiter.
        """
        self._zwilling = other

    def set_overlay_modus(self, an: bool):
        """Durchscheinend zeichnen (fuers Einblenden ins Video)."""
        self._overlay = bool(an)
        self.setAutoFillBackground(not self._overlay)
        self.setStyleSheet("" if self._overlay
                           else "background-color: #444444 ;")
        if self._overlay:
            # Sonst laegen Mausklicks auf dem Overlay statt auf dem Video -
            # Ziehen im 360-Modus waere damit an dieser Ecke tot.
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.update()

    def wheelEvent(self, event):
        """Strg+Mausrad: Ausschnitt verbreitern oder verengen.

        Ohne Strg bleibt das Ereignis unangetastet, damit ein Scrollen im
        umgebenden Fenster weiterhin ankommt.
        """
        if not (event.modifiers() & Qt.ControlModifier):
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        schritt = -4 if delta > 0 else 4     # hochdrehen = naeher heran
        self.set_max_points(self._max_points + schritt)
        event.accept()

    def set_max_points(self, punkte: int):
        """Ausschnittbreite in GPX-Punkten setzen (auch fuer den Zwilling).

        Die Einblendung im Video soll denselben Ausschnitt zeigen wie das
        Modul - sonst waeren es zwei verschiedene Diagramme nebeneinander.
        """
        self._max_points = max(self.MIN_PUNKTE,
                               min(self.MAX_PUNKTE, int(punkte)))
        self.update()
        if self._zwilling is not None:
            self._zwilling.set_max_points(self._max_points)


    def set_gpx_data(self, data: list):
        """
        data: Liste von Dicts, z.B. [{'lat':..., 'lon':..., 'ele':..., 
                                     'speed_kmh':..., 'gradient':..., ...}, ...]
        Wir schneiden uns max. _max_points 'vor' dem aktuellen Index heraus 
        und ein paar 'danach', damit die Kurve "scrollt".
        """
        self._gpx_data = data or []
        self.update()
        if self._zwilling is not None:
            self._zwilling.set_gpx_data(data)

    def set_current_index(self, idx: int):
        """Setzt den Index des 'aktuellen' GPX-Punkts."""
        if idx < 0:
            idx = 0
        if idx >= len(self._gpx_data):
            idx = len(self._gpx_data) - 1
        self._current_index = idx
        self.update()
        if self._zwilling is not None:
            self._zwilling.set_current_index(idx)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._gpx_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._overlay:
            # Durchscheinend ueber dem Videobild - dunkel genug, dass die
            # gelbe Kurve steht, hell genug, dass man das Bild noch sieht.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 120))
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        else:
            painter.fillRect(self.rect(), QColor("#333333"))

        rect_ = self.rect()
        w = rect_.width()
        h = rect_.height()

        # 1) Berechne, welche GPX-Punkte wir anzeigen (Fenster um current_index).
        N = len(self._gpx_data)
        if N < 1:
            return

        c_idx = self._current_index
        half_window = self._max_points // 2
        start_i = c_idx - half_window
        end_i   = c_idx + half_window
        if self._max_points % 2 == 0:
            end_i -= 1

        if start_i < 0:
            start_i = 0
        if end_i >= N:
            end_i = N - 1

        # Extrahiere Teilbereich
        relevant_points = self._gpx_data[start_i : end_i+1]
        count_window = len(relevant_points)
        if count_window < 2:
            return

        # Index des c_idx in relevant_points:
        local_idx = c_idx - start_i

        # x-Positionen definieren wir in [0..1], 
        # so dass local_idx => x = self._marker_ratio_x
        step = 1.0 / max(1, (count_window - 1))
        offset_in_data = local_idx * step
        shift_x = self._marker_ratio_x - offset_in_data

        # WICHTIG: Wir verwenden die Höhendaten (ele) für eine natürliche Darstellung
        # statt der Steigung (gradient)
        elevations = [p.get("ele", 0.0) for p in relevant_points]
        
        if not elevations:
            return
            
        min_ele = min(elevations)
        max_ele = max(elevations)

        # Vermeide Division durch Null
        if abs(max_ele - min_ele) < 0.1:
            max_ele = min_ele + 10.0  # 10 Meter Puffer bei flachen Strecken

        # Rand proportional zur Hoehe - als Modul ist das Widget gross, feste
        # 10 px waeren dort ein Nichts.
        rand = max(10, int(h * 0.10))
        nutz_h = max(1, h - 2 * rand)

        pts_screen = []
        for i, p in enumerate(relevant_points):
            x_data = i*step + shift_x
            ele = p.get("ele", 0.0)

            # Y-Berechnung basierend auf Höhe
            # Höhere Punkte weiter oben, niedrigere weiter unten
            frac = (ele - min_ele) / (max_ele - min_ele)
            y_pix = h - rand - (frac * nutz_h)

            x_pix = x_data * w
            pts_screen.append((x_pix, y_pix))

        # Bewusst ohne Hoehenskala: beim Syncen zaehlt allein die Steigung,
        # die man mit dem Bild vergleicht. Meterangaben lenken davon ab.

        # Zeichne die Höhenlinie - gelb wie im grossen Chart
        strich = 3 if h > 200 else 2
        pen_line = QPen(QColor("#ffff00"), strich)
        painter.setPen(pen_line)
        for i in range(len(pts_screen)-1):
            (x1, y1) = pts_screen[i]
            (x2, y2) = pts_screen[i+1]
            painter.drawLine(x1, y1, x2, y2)

        # Zeichne Punkte - das sind die einzelnen GPX-Punkte, an denen man
        # sieht, wie dicht die Aufzeichnung ist.
        r = 3 if h > 200 else 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#cccccc"))
        for (xx, yy) in pts_screen:
            painter.drawEllipse(int(xx)-r, int(yy)-r, 2*r, 2*r)

        # Zeichne Marker-Linie
        x_marker = int(self._marker_ratio_x * w)
        pen_marker = QPen(QColor("white"), 2)
        painter.setPen(pen_marker)
        painter.drawLine(x_marker, 0, x_marker, h)

        # Zeichne aktuellen Punkt und Steigungswert
        if 0 <= local_idx < len(pts_screen):
            xP, yP = pts_screen[local_idx]
            # Rot, nicht gelb: die Hoehenlinie ist jetzt gelb, darin waere der
            # aktuelle Punkt nicht zu finden.
            rp = r + 3
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(QColor("#ff3030"))
            painter.drawEllipse(int(xP)-rp, int(yP)-rp, 2*rp, 2*rp)

            # Hoehe und Steigung direkt ueber dem roten Punkt.
            #
            # Frueher stand der Text am oberen oder unteren Bildrand. Dort
            # kreuzt ihn der Marker-Strich, und man muss ausserdem quer durchs
            # Bild schauen, um den Wert zum Punkt zu finden. Beides faellt weg,
            # wenn der Text am Punkt klebt - mit dunkler Unterlegung, damit er
            # auch ueber dem Strich und der Kurve lesbar bleibt.
            slope_val = relevant_points[local_idx].get("gradient", 0.0)
            info_str = f"{slope_val:.1f} %"

            font_ = QFont()
            font_.setPointSize(10)
            font_.setBold(True)
            painter.setFont(font_)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(info_str)
            text_h = fm.height()

            # Ueber dem Punkt - und wenn dort kein Platz mehr ist, darunter.
            text_x = int(xP) - text_w // 2
            text_y = int(yP) - rp - 8
            if text_y - text_h < 0:
                text_y = int(yP) + rp + text_h + 4
            # Nicht ueber den Rand hinauslaufen lassen.
            text_x = max(2, min(text_x, w - text_w - 2))

            kasten = QRect(text_x - 4, text_y - text_h + 3,
                           text_w + 8, text_h + 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 190))
            painter.drawRoundedRect(kasten, 3, 3)

            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_x, text_y, info_str)