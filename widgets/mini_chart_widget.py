# widgets/mini_chart_widget.py

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

class MiniChartWidget(QWidget):
    """
    Zeigt eine Mini-Chart von maximal 30 GPX-Punkten.
    Hat einen festen Marker bei ca. 70% (x=0.7 * width).
    'darunter' läuft die Kurve, damit immer der aktuelle GPX-Punkt 
    an dieser Marker-Linie auftaucht. 

    Unten am Marker wird der "Slope" (Steigung) des aktuellen Punkts 
    als Text dargestellt.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)

        # Ggf. Hintergrund wie Timeline => #333333
        self.setStyleSheet("background-color: #444444 ;")

        # Interne Daten
        self._gpx_data = []
        self._max_points = 30   # Standard: 30 Gpx-Punkte anzeigen
        self._marker_ratio_x = 0.7  # 70% vom Widget
        self._current_index = 0     # Welcher Punkt ist 'aktuell'?

        

    def set_max_points(self, num: int):
        """Erlaubt es dir, die max. Anzahl von GPX-Punkten (30) zu ändern."""
        self._max_points = max(1, num)
        self.update()

    def set_gpx_data(self, data: list):
        """
        data: Liste von Dicts, z.B. [{'lat':..., 'lon':..., 'ele':..., 
                                     'speed_kmh':..., 'gradient':..., ...}, ...]
        Wir schneiden uns max. _max_points 'vor' dem aktuellen Index heraus 
        und ein paar 'danach', damit die Kurve "scrollt".
        """
        self._gpx_data = data or []
        self.update()

    def set_current_index(self, idx: int):
        """Setzt den Index des 'aktuellen' GPX-Punkts."""
        if idx < 0:
            idx = 0
        if idx >= len(self._gpx_data):
            idx = len(self._gpx_data) - 1
        self._current_index = idx
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._gpx_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        painter.fillRect(self.rect(), QColor("#333333"))
        
        rect_ = self.rect()
        w = rect_.width()
        h = rect_.height()

        # 1) Berechne, welche GPX-Punkte wir anzeigen (Fenster um current_index).
        #    z.B. ± 15 Punkte um den aktuellen herum => max 30
        N = len(self._gpx_data)
        if N < 1:
            return

        c_idx = self._current_index
        half_window = self._max_points // 2
        start_i = c_idx - half_window
        end_i   = c_idx + half_window
        if self._max_points % 2 == 0:
            # z.B. 30 => 15 + 15
            end_i -= 1  # damit wir "mittig" sind

        if start_i < 0:
            start_i = 0
        if end_i >= N:
            end_i = N - 1

        # Extrahiere Teilbereich
        relevant_points = self._gpx_data[start_i : end_i+1]
        # Wir tun so, als ob relevant_points[0] => x=0, relevant_points[-1] => x=someMax
        # => "scroll" => damit der aktuelle Index c_idx immer in der Mitte (marker) landet.

        # 2) Koordinatensystem auf x=0..1 => Mapping => dann "schieben wir" so,
        #    dass c_idx bei marker_ratio_x.
        count_window = len(relevant_points)
        if count_window < 2:
            return

        # Index des c_idx in relevant_points:
        local_idx = c_idx - start_i  # z.B. 15
        # => local_idx => welchen Pkt in relevant_points

        # x-Positionen definieren wir in [0..1], 
        # so dass local_idx => x = self._marker_ratio_x
        # => offset_x => local_idx => marker_ratio_x
        # => 1 step => 1/(count_window-1)

        step = 1.0 / max(1, (count_window - 1))
        offset_in_data = local_idx * step  # z.B. 15*0.0333=0.5
        # => Wir wollen offset_in_data im Diagramm auf marker_ratio_x schieben
        shift_x = self._marker_ratio_x - offset_in_data
        # => x_data => (i*step + shift_x)

        # Finde min & max Ele oder Speed oder was du willst.
        # Hier z.B. nimmst du "ele" oder "speed_kmh" oder "gradient".
        # Du sagst, du willst Slope => wir nehmen "gradient".
        grads = [p.get("gradient", 0.0) for p in relevant_points]
        min_val = min(grads)
        max_val = max(grads)
        if abs(max_val - min_val) < 0.001:
            # Verhindert Division by zero
            max_val += 0.1
            min_val -= 0.1

        # X->Pixel: x_pixel = (x_data)*w
        # Y->Pixel => wir zeichnen => Y=0 oben => wir drehen es => 0 => h, max => 0
        # => y_pixel = h - ( (val - min_val)/(max_val-min_val) * (h-20) ) - 10
        # so haben wir 10px oben/unten

        pts_screen = []
        for i, p in enumerate(relevant_points):
            x_data = i*step + shift_x
            val = p.get("gradient", 0.0)
            frac = (val - min_val) / (max_val - min_val)
            y_ = (h-20)*frac
            y_pix = (h - 10) - y_
            x_pix = x_data * w
            pts_screen.append((x_pix, y_pix))
            
        ###
        painter.setPen(Qt.NoPen)           # kein Rand
        painter.setBrush(QColor("#cccccc"))  # z. B. ein graues "fill"

        for (xx, yy) in pts_screen:
            # z. B. einen kleinen Kreis radius=3
            painter.drawEllipse(int(xx)-1, int(yy)-1, 4, 4)
            # original: painter.drawEllipse(int(xx)-3, int(yy)-3, 6, 6)

        ###

        # 3) Pfad zeichnen
        pen_line = QPen(QColor("#00cccc"), 2)  # z.B. cyan
        painter.setPen(pen_line)
        for i in range(len(pts_screen)-1):
            (x1, y1) = pts_screen[i]
            (x2, y2) = pts_screen[i+1]
            painter.drawLine(x1, y1, x2, y2)

        # 4) Den festen Marker bei x_marker = marker_ratio_x * w
        x_marker = int(self._marker_ratio_x * w)
        pen_marker = QPen(QColor("white"), 2)
        painter.setPen(pen_marker)
        painter.drawLine(x_marker, 0, x_marker, h)

        # 5) Aktueller Punkt => in relevant_points => local_idx. 
        # => screen-Koordinate:
        if 0 <= local_idx < len(pts_screen):
            xP, yP = pts_screen[local_idx]
            # Kleiner Kreis
            painter.setBrush(QColor("#ffff00"))  # gelb
            painter.drawEllipse(int(xP)-3, int(yP)-3, 6, 6)

            # Slope (gradient):
            slope_val = relevant_points[local_idx].get("gradient", 0.0)
            # Unten am Marker => Text
            slope_str = f"{slope_val:.1f}%"
            #slope_str = f"Slope: {slope_val:.1f}%"

            painter.setPen(QColor("#ffffff"))
            font_ = QFont()
            font_.setPointSize(10)
            painter.setFont(font_)

            text_w = painter.fontMetrics().horizontalAdvance(slope_str)
            # -> Mitte am Marker X => wir schieben Text bisschen nach unten:
            painter.drawText(x_marker - text_w//2, h - 5, slope_str)
        # Ende paintEvent
