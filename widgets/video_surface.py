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

# widgets/video_surface.py
"""Zeichenflaeche fuer die Vorschau - Qt malt die Bilder selbst.

Warum es das gibt: bisher zeichnet GStreamer direkt in ein Fensterhandle
(d3d11videosink). Das ist schnell, aber es ist eine native Direct3D-Oberflaeche
- Qt kann darueber nicht zuverlaessig zeichnen. Alles, was ueber dem Video
liegen soll (Auswahlrahmen um ein Overlay, Anfasser zum Skalieren, spaeter
Ziehen mit der Maus), waere damit nicht machbar.

Hier liefert GStreamer die fertigen Bilder statt sie selbst anzuzeigen, und
Qt malt sie. Gemessen an 4K-Material in Vorschaugroesse (1280x720, 30 fps):
180 von 180 Bildern angekommen, groesste Luecke 66 ms bei 33 ms Bildabstand,
3,2 ms je Bild fuer die Umwandlung - rund ein Zehntel des Zeitbudgets.

Nebenbei loest das ein zweites Problem: das Einbetten ueber Fensterhandles ist
die Stelle, die unter Linux und besonders unter Wayland Aerger macht. Bilder
abzuholen und selbst zu malen funktioniert ueberall gleich.

`bildbereich()` liefert das Rechteck, in dem das Bild gerade liegt. Damit
laesst sich spaeter zwischen Mausposition und Bildpunkt umrechnen - die
Grundlage fuers Anfassen und Ziehen.
"""

from PySide6.QtCore import Qt, QRect, Slot
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget


class VideoSurface(QWidget):
    """Zeigt die von GStreamer gelieferten Bilder, seitenverhaeltnistreu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bild = None
        self._bildbereich = QRect()
        # Der Hintergrund wird selbst gemalt; ohne das blitzt beim Groesse-
        # aendern kurz die Fensterfarbe durch.
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)
        self.setMinimumSize(1, 1)

    # ------------------------------------------------------------------
    @Slot(object)
    def bild_setzen(self, bild):
        """Neues Bild anzeigen. Wird aus dem Hauptthread aufgerufen.

        Das Backend schickt es ueber ein Qt-Signal herueber - GStreamer
        liefert auf einem eigenen Thread, und Qt-Widgets duerfen nur aus dem
        Hauptthread angefasst werden. Ein Signal wird dabei von Qt selbst in
        die Warteschlange des Hauptthreads gelegt.
        """
        if isinstance(bild, QImage) and not bild.isNull():
            self._bild = bild
            self.update()

    def bild_leeren(self):
        self._bild = None
        self.update()

    def bildbereich(self):
        """Rechteck, in dem das Bild zuletzt gezeichnet wurde (Widget-Koordinaten)."""
        return QRect(self._bildbereich)

    def zu_bildpunkt(self, punkt):
        """Mausposition -> Bildpunkt im Video, oder None ausserhalb.

        Fuer das spaetere Anfassen und Ziehen von Overlays.
        """
        if self._bild is None or self._bildbereich.isEmpty():
            return None
        if not self._bildbereich.contains(punkt):
            return None
        rel_x = (punkt.x() - self._bildbereich.x()) / self._bildbereich.width()
        rel_y = (punkt.y() - self._bildbereich.y()) / self._bildbereich.height()
        return (rel_x * self._bild.width(), rel_y * self._bild.height())

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        maler = QPainter(self)
        maler.fillRect(self.rect(), QColor(0, 0, 0))
        if self._bild is None or self._bild.isNull():
            self._bildbereich = QRect()
            return

        flaeche = self.rect()
        bw, bh = self._bild.width(), self._bild.height()
        if bw <= 0 or bh <= 0 or flaeche.width() <= 0 or flaeche.height() <= 0:
            return

        # Seitenverhaeltnis halten, mittig, schwarze Balken aussen.
        skala = min(flaeche.width() / bw, flaeche.height() / bh)
        zw, zh = max(1, int(bw * skala)), max(1, int(bh * skala))
        ziel = QRect((flaeche.width() - zw) // 2, (flaeche.height() - zh) // 2,
                     zw, zh)
        self._bildbereich = ziel
        maler.setRenderHint(QPainter.SmoothPixmapTransform, True)
        maler.drawImage(ziel, self._bild)
