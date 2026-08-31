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

"""
Speed: + beschleunigt, - verlangsamt (mehrere Key-Varianten für Layouts/Numpad). 1 setzt exakt 1.00x. Die aktuelle Rate siehst du oben rechts (dein bestehendes Label).

Viewport:

Zoom mit Ctrl++ / Ctrl+-, Reset Ctrl+0.

Pan mit Ctrl + Pfeiltasten (links/rechts/hoch/runter).

Das funktioniert für normale Videos sofort. Zoomen > 0 macht das Panning sichtbar sinnvoll.
"""

import platform
import math

from core import view360
from core.ges_backend import GesPlayerBackend
from widgets.video_surface import VideoSurface

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QFrame, QLabel, QVBoxLayout
)
from PySide6.QtCore import Qt, QTimer, Signal

from PySide6.QtGui import QShortcut, QKeySequence

class VideoEditorWidget(QWidget):
     #Signal MUSS als Klassenattribut definiert werden
    videosDropped = Signal(list)  # list[str]
    
    """
    Video-Player-Widget. Die Wiedergabe selbst macht der GES-Player
    (core/ges_backend.py); hier liegen die Oberflaeche und die Zeitrechnung
    ueber mehrere Clips. Es kann mehrere Videos als Playlist laden und
    nacheinander abspielen.
    
    Zusätzlich mit 360°-Video-Unterstützung, die mit Taste 'V' umgeschaltet werden kann.
    """

    play_ended = Signal()  # z.B. wenn das letzte Video fertig ist

    #: Ein Overlay wurde im Vorschaubild verschoben oder skaliert:
    #: Platz in der Overlay-Liste, x, y in Exportpixeln, neue Skalierung.
    overlayImBildGeaendert = Signal(int, int, int, float)
    # 360-Blickwinkel des Videos mit diesem Index hat sich
    # geaendert: (index, yaw, pitch, fov) - alle drei in Radiant.
    blick360Geaendert = Signal(int, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        
       # --- Drag&Drop: Videos ---
        self.setAcceptDrops(True)
        self._dnd_overlay = QLabel("Drop videos to import…", self)
        self._dnd_overlay.setStyleSheet(
            "background: rgba(0,0,0,0.55); color: white; border: 2px dashed #ddd;"
            "border-radius: 12px; font-size: 18px; padding: 16px;"
        )
        self._dnd_overlay.setAlignment(Qt.AlignCenter)
        self._dnd_overlay.hide()
        self._dnd_overlay.setGeometry(self.rect())
        self._dnd_overlay.setText("Drop video file(s) here")
        self._dnd_overlay.show()  # beim Start leer -> Hinweis sichtbar
        
        self._cut_intervals = []
    
    
        
        self._time_mode = "global"  # default
        self._final_time_callback = None   # optional
        
        # 360°-Video Status
        self._is_360_mode = False
        self._360_label = None
        
        # Haupt-Layout
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Ein Frame als Video-Anzeige
        self.video_frame = QFrame(self)
        self.video_frame.setStyleSheet("background:black;")
        layout.addWidget(self.video_frame, 0, 0)

        # Zeichenflaeche fuer den Fall, dass Qt die Bilder selbst malt (GES).
        # Sie liegt in derselben Zelle ueber dem Frame und wird nur gezeigt,
        # wenn der Player Bilder liefert.
        # Wichtig ist die Reihenfolge: sie kommt VOR den Beschriftungen und
        # dem Ablegebereich, damit die weiterhin darueber liegen.
        self.video_surface = VideoSurface(self)
        self.video_surface.hide()
        self.video_surface.overlayGeaendert.connect(self.overlayImBildGeaendert)
        self.video_surface.blick360Gezogen.connect(self._auf_blick_zug)
        self.video_surface.blick360Gezoomt.connect(self._auf_blick_zoom)
        layout.addWidget(self.video_surface, 0, 0)
        layout.setRowStretch(0, 1)
        layout.setColumnStretch(0, 1)
        # Overlay deckt die Fläche
        self._dnd_overlay.raise_()
        
        # Oben Rechts: Speed-Label
        self.speed_label = QLabel("", self)
        self.speed_label.setStyleSheet("color:white; background-color:rgba(0,0,0,120); padding:2px;")
        self.speed_label.hide()
        layout.addWidget(self.speed_label, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)

        # Oben Rechts: Aktuelle Zeit
        self.current_time_widget = QWidget(self)
        vbox_time = QVBoxLayout(self.current_time_widget)
        vbox_time.setContentsMargins(0,20,0,0)
        vbox_time.setSpacing(0)
        vbox_time.setAlignment(Qt.AlignTop | Qt.AlignRight)

        self.current_time_label = QLabel("", self.current_time_widget)
        self.current_time_label.setTextFormat(Qt.RichText)
        self.current_time_label.setStyleSheet(
            "background-color:rgba(0,0,0,120); color: yellow; font-size:16px;"
            "padding:2px;"
        )
        self._last_time_html = None
        vbox_time.addWidget(self.current_time_label)
        layout.addWidget(self.current_time_widget, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)

        # Extra: Edit-Status
        self.edit_status_widget = QWidget(self)
        # War 65 - dort passte "Copymode" nicht hinein, der Text wurde
        # abgeschnitten (daher frueher das verstuemmelte "Edit:Cop"). 120
        # reicht dafuer und bleibt deutlich schmaler als die Zeitanzeige
        # darueber, die rund 195 Punkte breit ist.
        self.edit_status_widget.setMaximumWidth(120)

        vbox_edit = QVBoxLayout(self.edit_status_widget)
        vbox_edit.setContentsMargins(0, 50, 0, 0)
        vbox_edit.setSpacing(0)
        # Rechtsbuendig, damit jede Beschriftung nur so breit wird wie ihr
        # Text - sonst zoege der dunkle Kasten ueber die ganze Breite.
        vbox_edit.setAlignment(Qt.AlignTop | Qt.AlignRight)

        self.edit_status_label = QLabel("", self.edit_status_widget)
        self.acut_status_label = QLabel("", self.edit_status_widget)
        # Unveraendert bei 65: bisher begrenzte der Behaelter diese
        # Beschriftung, und an ihr soll sich nichts aendern.
        self.acut_status_label.setMaximumWidth(65)
        vbox_edit.addWidget(self.edit_status_label)
        vbox_edit.addWidget(self.acut_status_label)
        layout.addWidget(self.edit_status_widget, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)

        # Unten Links: total_length + cut_time
        self.right_time_widget = QWidget(self)
        vbox_right_time = QVBoxLayout(self.right_time_widget)
        vbox_right_time.setContentsMargins(0,0,0,0)
        vbox_right_time.setSpacing(0)
        vbox_right_time.setAlignment(Qt.AlignRight)

        self.total_length_label = QLabel("", self.right_time_widget)
        self.total_length_label.setStyleSheet("color:white; padding-left:5px;")
        vbox_right_time.addWidget(self.total_length_label)

        self.cut_time_label = QLabel("", self.right_time_widget)
        self.cut_time_label.setStyleSheet("color:red; padding-left:5px;")
        vbox_right_time.addWidget(self.cut_time_label)
        self.cut_time_label.hide()

        layout.addWidget(self.right_time_widget, 0, 0, alignment=Qt.AlignBottom | Qt.AlignLeft)

        # 360°-Modus Anzeige
        self._360_label = QLabel("360°", self)
        self._360_label.setStyleSheet(
            "color:white; background-color:rgba(0,100,200,180); "
            "padding:4px; font-weight:bold; font-size:14px;"
        )
        self._360_label.hide()
        layout.addWidget(self._360_label, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        # Der Player. Seit 6.0 gibt es nur noch GES; scheitert er, kann die
        # App kein Video zeigen. Der Fehler wird deshalb durchgereicht - der
        # Start faengt ihn ab und sagt, was zu installieren ist.
        #
        # window_id ist die Rueckfallebene: normalerweise liefert GStreamer
        # die Bilder an video_surface, aber wenn sich die appsink-Kette nicht
        # bauen laesst, zeichnet eine Fenstersenke direkt in video_frame.
        self._backend = GesPlayerBackend(
            window_id=self.video_frame.winId(),
            log_handler=None,
            frame_callback=self.video_surface.bild_setzen,
        )
        # Die Stapelreihenfolge ist entscheidend und war schon einmal falsch:
        # mit raise_() lag die Flaeche ueber ALLEM und verdeckte die Zeiten,
        # "Edit:ENC" und die uebrigen Einblendungen. Richtig ist zweimal
        # lower(): danach liegt der Frame ganz unten, die Flaeche direkt
        # darueber, und alle Beschriftungen bleiben obenauf - egal wie viele
        # davon es gibt und in welcher Reihenfolge sie angelegt wurden.
        self.video_surface.show()
        self.video_surface.lower()
        self.video_frame.lower()

        self.is_playing = False
        self.playlist = []
        self._current_index = 0
        self.multi_durations = []
        self.boundaries = []

        # Ende der Playlist => play_ended
        self._backend.set_end_callback(self.play_ended.emit)

        # Du kannst z. B. die Zeitanzeige in einer Timer-Schleife updaten
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time_label)
        self._time_timer.start(200)  # alle 200ms
        
        
        self._speed_shortcuts = []

        def _sc(seq, cb):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.ApplicationShortcut)
            s.activated.connect(cb)
            s.activatedAmbiguously.connect(cb)  # falls Qt doch mal doppelt matched
            self._speed_shortcuts.append(s)
            
        # Plus (normale Taste und Numpad) + Layout-Variante Shift+='+' → Qt.Key_Equal
        _sc(Qt.Key_Plus,   lambda: self._nudge_speed(+0.10))
        _sc(Qt.Key_Equal,  lambda: self._nudge_speed(+0.10))  # für DE/US Layouts mit Shift+='+' 

        # Minus (normale Taste und Numpad)
        _sc(Qt.Key_Minus,  lambda: self._nudge_speed(-0.10))

        # Reset
        _sc(Qt.Key_1,      lambda: self.set_playback_rate(1.0))
        _sc(Qt.Key_2,      lambda: self.set_playback_rate(2.0))
        _sc(Qt.Key_3,      lambda: self.set_playback_rate(3.0))
        _sc(Qt.Key_4,      lambda: self.set_playback_rate(4.0))
        _sc(Qt.Key_5,      lambda: self.set_playback_rate(5.0))
        _sc(Qt.Key_6,      lambda: self.set_playback_rate(6.0))
        _sc(Qt.Key_7,      lambda: self.set_playback_rate(7.0))
        _sc(Qt.Key_8,      lambda: self.set_playback_rate(8.0))
        _sc(Qt.Key_9,      lambda: self.set_playback_rate(9.0))  

        # -------- Keyboard Shortcuts --------
        # Speed: + / - (mehrere Varianten für unterschiedliche Tastaturen/Numpad)
        
        # 360-Blickwinkel ueber die Tastatur. Schrittweite 5 Grad, in Radiant,
        # weil das Backend in Radiant rechnet.
        _SCHRITT = math.radians(5.0)
        QShortcut(QKeySequence("Ctrl++"), self, activated=lambda: self._nudge_zoom(+_SCHRITT))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._nudge_zoom(-_SCHRITT))
        QShortcut(QKeySequence("Ctrl+0"),  self, activated=self._reset_view)

        # Links druecken heisst nach links schauen, und nach links ist yaw
        # kleiner. Hoch heisst nach oben, und nach oben ist pitch groesser.
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Left),  self, activated=lambda: self._nudge_pan(dx=-_SCHRITT))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Right), self, activated=lambda: self._nudge_pan(dx=+_SCHRITT))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Up),    self, activated=lambda: self._nudge_pan(dy=+_SCHRITT))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Down),  self, activated=lambda: self._nudge_pan(dy=-_SCHRITT))

   # ----------------------------
   # Drag&Drop (Videos)
   # ----------------------------
    def _extract_paths(self, mime):
        paths = []
        if mime and mime.hasUrls():
            for u in mime.urls():
                if u.isLocalFile():
                    paths.append(u.toLocalFile())
        elif mime and mime.hasText():
            for line in mime.text().splitlines():
                line = line.strip()
                if line:
                    paths.append(line)
        return paths

    def _is_video(self, path: str) -> bool:
        return path.lower().endswith((".mp4", ".mov", ".mkv", ".avi"))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Overlay immer auf volle Größe
        self._dnd_overlay.setGeometry(self.rect())

    def dragEnterEvent(self, e):
        ok = any(self._is_video(p) for p in self._extract_paths(e.mimeData()))
        if ok:
            self._dnd_overlay.show()
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._dnd_overlay.hide()
        e.accept()

    def dropEvent(self, e):
        self._dnd_overlay.hide()
        paths = [p for p in self._extract_paths(e.mimeData()) if self._is_video(p)]
        if paths:
            # Emit nach MainWindow; dort Abfrage "New/Append/Cancel"
            try:
                self.videosDropped.emit(paths)
            except Exception:
                pass
            e.acceptProposedAction()
        else:
            e.ignore()
        

    def supports_360(self) -> bool:
        """Ob 360 moeglich ist - braucht die GL-Elemente, siehe view360."""
        return self._backend.supports_360()

    def toggle_360_mode(self, an=None):
        """
        360-Modus umschalten. Ohne Angabe wird umgeschaltet, mit Angabe
        wird genau darauf gesetzt - die Automatik beim Laden braucht das.
        """
        if not self._backend.supports_360():
            grund = getattr(self._backend, "unsupported_360_reason",
                            lambda: "")()
            self._show_speed_label(grund or "360° braucht das GES-Backend")
            return

        ziel = (not self._is_360_mode) if an is None else bool(an)
        if ziel == self._is_360_mode:
            return

        try:
            if not self._backend.set_360(ziel):
                self._show_speed_label("360° liess sich nicht einschalten")
                return
            self._is_360_mode = ziel
            self.video_surface.set_360_aktiv(ziel)
            if ziel:
                self._360_label.show()
                # Beim Einschalten den Blickwinkel NICHT anfassen: beim Laden
                # eines Projekts steht er schon, und ihn hier zu nullen wuerde
                # ihn genau dann wegwerfen.
                self._show_speed_label("360°-Modus: AN")
            else:
                self._360_label.hide()
                self._show_speed_label("360°-Modus: AUS")
        except Exception as e:
            print(f"Fehler beim Umschalten des 360°-Modus: {e}")

    def is_360_mode(self) -> bool:
        """Gibt zurück, ob 360°-Modus aktiv ist"""
        return self._is_360_mode

    # -----------------------------------------
    # ALTE METHODEN (Schnittstellen), die dein restlicher Code aufruft
    # -----------------------------------------
    
    def set_cut_intervals(self, intervals):
        """
        Speichert eine Liste von (start_s, end_s)-Schnittbereichen.
        Beispiel: [(0.0, 12.5), (80.0, 85.2)]
        """
        if not intervals:
            self._cut_intervals = []
        else:
            self._cut_intervals = intervals
    
    def _get_cut_end_if_zero(self) -> float:
        """
        Falls in self._cut_intervals ein Bereich [0..end] existiert,
        gib end zurück. Sonst 0.0.
        Wir suchen das größte 'end', bei dem start quasi 0 ist.
        """
        max_cut_end = 0.0
        for (start_s, end_s) in self._cut_intervals:
            # Prüfen, ob der Schnitt (start_s..end_s) wirklich
            # am absoluten Anfang ansetzt (z.B. <= 0.001)
            if abs(start_s) < 0.001:
                if end_s > max_cut_end:
                    max_cut_end = end_s
        return max_cut_end    
            
            
    def set_time_mode(self, mode: str):
        self._time_mode = mode    
        
    def set_final_time_callback(self, func):
        """func soll sein: func(global_s) -> final_s"""
        self._final_time_callback = func    
        

    def show_first_frame_at_index(self, index: int):
        """An den Anfang von Clip 'index' springen, pausiert => erstes Bild.

        Frueher folgte auf play_index() 80 ms spaeter noch ein seek_local(0).
        Beide sprangen an dieselbe Stelle - den Clipanfang -, der zweite war
        also reine Verdopplung. play_index() ist bei GES laengst kein
        Umschalten mehr, sondern selbst schon ein Sprung dorthin.
        """
        if not self.playlist or index < 0 or index >= len(self.playlist):
            return  # Ungültig => Abbruch

        self.is_playing = False
        try:
            self._backend.play_index(index)
            self._backend.set_paused(True)
        except SystemError as e:
            # Kommt vor, wenn der Player gerade nichts geladen hat.
            print(f"[WARN] show_first_frame: Sprung abgelehnt => {e}")

    def set_playback_rate(self, rate: float):
        print(f"DEBUG: set_playback_rate called with rate={rate}")  # Debug
        self._backend.set_rate(rate)
        print(f"DEBUG: player speed is now: {self._backend.rate()}")  # Debug
        self._show_speed_label(f"Speed: {rate:.2f}x")

    def _show_speed_label(self, txt: str):
        self.speed_label.setText(txt)
        self.speed_label.show()
        QTimer.singleShot(2000, self.speed_label.hide)

    def set_total_length(self, total_s: float):
        # z. B. Summe aller Videos
        txt = self.format_seconds_simple(total_s)
        self.total_length_label.setText(txt)

    def set_old_time(self, old_s: float):
        """
        Falls dein Code hierhin ruft (historische Funktion).
        Man kann z. B. `old_s` = summe aller Video-Längen *vor* dem Cut?
        """
        txt = self.format_seconds_simple(old_s)
        self.total_length_label.setText(txt)

    def set_cut_time(self, cut_s: float):
        if cut_s > 0:
            self.cut_time_label.setText(self.format_seconds_simple(cut_s))
            self.cut_time_label.show()
        else:
            self.cut_time_label.setText("")
            self.cut_time_label.hide()

    def format_seconds_simple(self, secs: float) -> str:
        """z. B. 74.2 => '00:01:14' (ohne ms)"""
        s_rounded = round(secs)
        hh = s_rounded // 3600
        mm = (s_rounded % 3600) // 60
        ss = s_rounded % 60
        return f"<span style='font-size:14px;'>{hh:02d}:{mm:02d}:{ss:02d}</span>"

    def format_seconds_html(self, secs: float) -> str:
        """z. B. 12.345 => '00:00:12.<ms=345>' in HTML-Font-Styles."""
        
        base = int(math.floor(secs))
        fraction = secs - base
        ms = int(round(fraction * 1000))
        if ms == 1000:
            base += 1
            ms = 0
        hh = base // 3600
        mm = (base % 3600) // 60
        ss = base % 60

        return (
            f"<span style='font-size:16px;'>"
            f"{hh:02d}:{mm:02d}:{ss:02d}"
            "</span>"
            f".<span style='font-size:10px;'>{ms:03d}</span>"
        )

    def set_current_time(self, secs: float):
        """
        Externe Updates (z.B. Timeline) liefern i.d.R. globale Zeit.
        Wenn 'final' aktiv ist, wandeln wir vor der Anzeige um,
        damit sich Anzeige und Timer nicht gegenseitig übermalen.
        """
        if self._time_mode == "final" and self._final_time_callback:
            secs = self._final_time_callback(secs)

        text_html = self.format_seconds_html(secs)
        # Nur updaten, wenn sich der Text tatsächlich ändert (verhindert unnötiges Repaint/Flackern)
        if getattr(self, "_last_time_html", None) != text_html:
            self.current_time_label.setText(text_html)
            self._last_time_html = text_html

    def play_pause(self):
        if self.is_playing:
            self._backend.set_paused(True)
            self.is_playing = False
        else:
            self._backend.set_paused(False)
            self.is_playing = True

    def get_current_position_s(self) -> float:
        """
        Gibt die *globale* Zeit (in Sekunden) über alle Clips zurück.
        Ruft intern get_current_global_time() auf.
        """
        return self.get_current_global_time()

    def get_current_index(self) -> int:
        """Ablösung für dein altes self._current_index => Playlist-Index."""
        return self._backend.index()

    def set_time(self, new_s: float):
        """
        Globaler Sprung in der gesamten Playlist:
        Rechnet new_s => clipIndex + local_s und springt dorthin.
        """
        self.seek_global(new_s)

    def frame_step_forward(self):
        self._backend.step_frame(True)

    def frame_step_backward(self):
        self._backend.step_frame(False)

    # -----------------------------------------
    # Player-Auskuenfte fuer MainWindow und die Manager.
    # Alles, was frueher ueber video_editor._player lief, geht hier durch.
    # -----------------------------------------

    def set_paused(self, paused: bool):
        """
        Pausiert bzw. setzt fort und haelt is_playing im Gleichtakt.

        Der Zustand wird zuerst gesetzt, dann der Player angesprochen - so
        stimmt is_playing auch dann, wenn der Player gerade nichts geladen hat
        und der Zugriff fehlschlaegt. Genau so haben es die Aufrufer vorher
        einzeln gemacht.
        """
        self.is_playing = not paused
        try:
            self._backend.set_paused(paused)
        except Exception as e:
            print(f"[WARN] set_paused({paused}) fehlgeschlagen: {e}")

    def is_paused(self) -> bool:
        return self._backend.is_paused()

    def get_current_file(self):
        """Pfad der gerade laufenden Datei, None wenn keine geladen ist."""
        return self._backend.current_file()

    def get_fps(self):
        """Bildrate des aktuellen Videos oder None."""
        return self._backend.fps()

    def get_video_size(self):
        """(Breite, Hoehe) des aktuellen Videos, (0, 0) wenn unbekannt."""
        return self._backend.video_size()

    def preview_width(self) -> int:
        """Breite, in der das Backend die Vorschau rechnet."""
        return int(getattr(self._backend, "PREVIEW_MAX_WIDTH", 1280))

    def supports_preview_cuts(self) -> bool:
        """Ob das Backend die Vorschau geschnitten samt Blenden zeigen kann."""
        return self._backend.supports_cuts()

    def set_preview_cuts(self, cuts):
        """
        Schnitte an das Backend geben: Liste von (start_s, ende_s, blende_s).

        Wirkt nur, wenn der Player das kann. Sonst passiert nichts,
        dort springt der CutManager wie bisher ueber die Schnitte hinweg.
        """
        try:
            return bool(self._backend.set_cuts(cuts))
        except Exception as e:
            print(f"[WARN] set_preview_cuts: {e}")
            return False

    def supports_preview_overlays(self) -> bool:
        """Ob das Backend Overlays in der Vorschau zeigen kann."""
        try:
            return bool(self._backend.supports_overlays())
        except Exception:
            return False

    def set_preview_overlays(self, overlays, export_groesse=None):
        """Overlays an das Backend geben (siehe PlayerBackend.set_overlays).

        Dieselben Rechtecke gehen an die Zeichenflaeche - sie braucht sie zum
        Anwaehlen und Ziehen. Gezeichnet wird das Bild weiterhin von
        GStreamer; Qt malt nur Rahmen und Anfasser darueber.
        """
        try:
            self.video_surface.overlays_setzen(overlays, export_groesse)
        except Exception as e:
            print(f"[WARN] Overlays fuer die Zeichenflaeche: {e}")
        try:
            return bool(self._backend.set_overlays(overlays, export_groesse))
        except Exception as e:
            print(f"[WARN] set_preview_overlays: {e}")
            return False

    def shutdown_player(self):
        """
        Backend beim Beenden sauber herunterfahren.

        Die GES-Pipeline haelt eigene Threads; ohne dieses Abschalten laeuft
        die Anwendung nach dem Schliessen des Fensters weiter.
        """
        try:
            self._time_timer.stop()
        except Exception:
            pass
        try:
            self._backend.shutdown()
        except Exception as e:
            print(f"[WARN] shutdown_player: {e}")

    def stop_and_clear(self):
        """Wiedergabe hart beenden und die Playlist leeren (New Project)."""
        for step in (self._backend.stop, self._backend.clear):
            try:
                step()
            except Exception as e:
                print(f"[WARN] stop_and_clear: {e}")
        self.playlist = []
        self.is_playing = False

    # -----------------------------------------
    # Playlist-Funktionen
    # -----------------------------------------
    def set_multi_durations(self, durations_list):
        """z.B. [60.0, 90.0] => 2 Videos => sum=150 => boundaries=[60,150]."""
        self.multi_durations = durations_list or []
        self.boundaries = []
        accum = 0.0
        for d in self.multi_durations:
            accum += d
            self.boundaries.append(accum)

    def set_playlist(self, video_list, fortschritt=None):
        """
        Laedt die Videoliste ins Backend.

        `fortschritt(nummer, gesamt, pfad)` wird - sofern das Backend das
        vor jeder Datei gerufen. GES analysiert beim Oeffnen die ganze
        Datei, was bei mehreren GB spuerbar dauert; damit laesst sich
        anzeigen, woran gerade gearbeitet wird.
        """
        self._backend.load_playlist(video_list, fortschritt)
        if not video_list:
            self.playlist = []
            self.set_empty_hint_visible(True)
            return

        self.is_playing = False
        self.playlist = video_list
        self.set_empty_hint_visible(False)

    def seek_global(self, wanted_s: float):
        """Sprung auf die globale Zeit ueber alle Clips - EIN Sprung.

        Frueher wurde hier in (Clip-Index, lokale Sekunde) zerlegt und mit
        dem Live-Index des Backends verglichen. Waren die verschieden, ging
        es ueber play_index() zuerst an den CLIP-ANFANG - bei Clip 0 also auf
        0,000 s - und 100 ms spaeter per Timer ans eigentliche Ziel. Das war
        der sichtbare Ruecksprung auf den Anfang beim Steppen ueber eine
        Clipgrenze.

        Der Umweg stammt aus der Playlist-Zeit. GES hat EINE durchgehende
        Zeitachse, und seek_global_raw() trifft die Stelle direkt.
        """
        if not self.boundaries:
            return

        total = self.boundaries[-1]
        if wanted_s < 0:
            wanted_s = 0.0
        elif wanted_s >= total:
            # Ans Ende oder darueber hinaus: kurz VOR das Ende, wie bisher.
            wanted_s = max(0.0, total - 0.001)

        try:
            self._backend.seek_global_raw(wanted_s)
            self._backend.set_paused(True)
            self.is_playing = False
        except SystemError as e:
            print(f"[WARN] seek_global: player refused to seek => {e}")


    # -----------------------------------------
    # Event-Handling
    # -----------------------------------------

    def _update_time_label(self):
        if not self.playlist or self._backend.count() == 0:
            self.current_time_label.hide()
            return
        else:
            self.current_time_label.show()
            
        # 1) globale Sekunde
        global_s = self.get_current_global_time()

        # Die Zeichenflaeche braucht dieselbe Zeit: nur Overlays, die gerade
        # im Bild stehen, sollen sich anwaehlen und ziehen lassen.
        try:
            self.video_surface.zeit_setzen(global_s)
        except Exception:
            pass

        # 2) falls "global" => zeige global_s
        #    falls "final"  => rufe callback auf
        if self._time_mode == "final" and self._final_time_callback:
            show_s = self._final_time_callback(global_s)
        else:
            show_s = global_s

        text_html = self.format_seconds_html(show_s)
        if getattr(self, "_last_time_html", None) != text_html:
            self.current_time_label.setText(text_html)
            self._last_time_html = text_html

    def stop(self):
        """
        Wenn am Anfang ein Schnitt [0..X] existiert, springen wir an X,
        ansonsten an 0s des ersten Videos.
        """
        if not self.playlist:
            return
    
        # (1) Prüfe, ob wir [0..cutX] haben
        cut0_end = self._get_cut_end_if_zero()

        if cut0_end > 0.001:
            # => wir haben einen Schnitt am Anfang => an cut0_end springen
            self.seek_global(cut0_end)

            # Danach Pause + is_playing = False
            self._backend.set_paused(True)
            self.is_playing = False

        else:
            # => kein Schnitt am Anfang => an den Anfang des ersten Videos.
            # Frueher play_index(0) und 50 ms spaeter seek_local(0) - beide
            # sprangen an dieselbe Stelle.
            try:
                self._backend.play_index(0)
                self._backend.set_paused(True)
                self.is_playing = False
            except SystemError as e:
                print(f"[WARN] stop(): player refused to seek => {e}")

    def get_current_global_time(self) -> float:
        """Globale Zeit in Sekunden ueber alle Clips.

        Eine einzige Abfrage im Backend. Frueher wurden index() und
        position() getrennt abgefragt und addiert - das sind zwei
        Messungen, und liefen sie auseinander, sprang das Ergebnis um
        eine ganze Cliplaenge.
        """
        return self._backend.position_global()
        
        
        # -------- Helpers: Speed / Zoom / Pan --------
    def _nudge_speed(self, delta: float):
        """Erhöht/verringert die Abspielgeschwindigkeit und zeigt das Label."""
        print(f"DEBUG: _nudge_speed called with delta={delta}")  # Debug
        cur = self._backend.rate()
        print(f"DEBUG: Current speed = {cur}")  # Debug
        new = max(0.10, min(32.00, cur + delta))  # Klammern 0.10x .. 4.00x
        self.set_playback_rate(new)

    # ---- 360°: Blickwinkel -------------------------------------------------
    # yaw/pitch/fov stehen in Radiant, angezeigt wird in Grad. Die Werte
    # gehoeren zum aktuellen Video und werden im Projekt gespeichert; das
    # Backend rechnet sie im Shader aus (core/view360.py).

    def _nudge_zoom(self, dz: float):
        """Bildwinkel aendern. Positives dz heisst naeher heran."""
        if not self._360_bereit(melden=True):
            return
        # Kleinerer Bildwinkel = staerkere Vergroesserung, deshalb minus.
        self._blick_verschieben(d_fov=-dz)
        _, _, fov = self._backend.view360()
        self._show_speed_label(f"Zoom: {math.degrees(fov):.0f}° Bildwinkel")

    def _nudge_pan(self, dx: float = 0.0, dy: float = 0.0):
        """Schwenken und neigen."""
        if not self._360_bereit(melden=True):
            return
        self._blick_verschieben(d_yaw=dx, d_pitch=dy)
        yaw, pitch, _ = self._backend.view360()
        self._show_speed_label(f"Blick: {math.degrees(yaw):+.0f}° / "
                               f"{math.degrees(pitch):+.0f}°")

    def _reset_view(self):
        """Blickwinkel auf geradeaus und 90° zuruecksetzen."""
        if not self._360_bereit(melden=False):
            return
        self._backend.set_view360(yaw=0.0, pitch=0.0, fov=view360.FOV_VORGABE)
        self._blick_merken()
        self._show_speed_label("View reset")

    def _360_bereit(self, melden: bool = True) -> bool:
        """Kann und soll gerade am Blickwinkel gedreht werden?"""
        if not self._backend.supports_360():
            if melden:
                self._show_speed_label("360° braucht das GES-Backend")
            return False
        if not getattr(self, "_is_360_mode", False):
            if melden:
                self._show_speed_label("Nur im 360°-Modus (Taste V)")
            return False
        return True

    def _blick_verschieben(self, d_yaw=0.0, d_pitch=0.0, d_fov=0.0):
        """Blickwinkel relativ aendern und den neuen Stand merken."""
        yaw, pitch, fov = self._backend.view360()
        self._backend.set_view360(yaw + d_yaw, pitch + d_pitch, fov + d_fov)
        self._blick_merken()

    def _blick_merken(self):
        """Den Blickwinkel des aktuellen Videos nach aussen melden.

        MainWindow haengt sich hier ein, um ihn in der Projektdatei und in der
        Export-Konfiguration mitzufuehren.
        """
        try:
            self.blick360Geaendert.emit(self.get_current_index(),
                                        *self._backend.view360())
        except Exception:
            pass

    def blick360(self):
        """(yaw, pitch, fov) des laufenden Backends."""
        return self._backend.view360()

    def set_blick360(self, yaw=None, pitch=None, fov=None):
        """Blickwinkel des laufenden Videos absolut setzen."""
        if not self._backend.supports_360():
            return False
        return self._backend.set_view360(yaw, pitch, fov)

    def set_blick360_liste(self, ansichten):
        """Alle Blickwinkel auf einmal - beim Laden eines Projekts.

        `ansichten` ist eine Liste von (yaw, pitch, fov) je Video.
        """
        if not self._backend.supports_360():
            return False
        return self._backend.set_view360_liste(ansichten)


    # NEU in der Klasse ergänzen:
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_dnd_overlay") and self._dnd_overlay:
            self._dnd_overlay.setGeometry(self.rect())

    def set_empty_hint_visible(self, visible: bool):
        if visible:
            self._dnd_overlay.setText("Drag & Drop video file(s) here")
            self._dnd_overlay.show()
            self._dnd_overlay.raise_()
        else:
            self._dnd_overlay.hide()
    
    

    # Maus und Mausrad fuer 360 liegen in widgets/video_surface.py, nicht
    # hier. Grund: unter GES liegt die Zeichenflaeche ueber diesem Widget und
    # verschluckt die Ereignisse ohnehin. Sie meldet ihre Zuege ueber die
    # Signale blick360Gezogen und blick360Gezoomt zurueck.

    def _auf_blick_zug(self, dx_punkte, dy_punkte):
        """Mauszug in Winkel umrechnen.

        Der Umrechnungsfaktor haengt am Bildwinkel: ein Punkt auf dem
        Bildschirm entspricht fov/Breite an Winkel. Dadurch bleibt sich das
        Ziehen gleich, egal wie weit hineingezoomt ist - ohne das rast das
        Bild bei starkem Zoom davon.

        Die Vorzeichen: das Bild soll dem Zeiger folgen. Nach rechts ziehen
        heisst, die Welt nach rechts schieben, also nach links schauen.
        """
        if not self._360_bereit(melden=False):
            return
        breite = max(1, self.video_surface.width())
        _, _, fov = self._backend.view360()
        je_punkt = fov / float(breite)
        self._blick_verschieben(d_yaw=-dx_punkte * je_punkt,
                                d_pitch=dy_punkte * je_punkt)

    #: Wieviel Bildwinkel eine Rastung des Mausrads aendert.
    RAD_SCHRITT = math.radians(4.0)

    def _auf_blick_zoom(self, schritte):
        if not self._360_bereit(melden=False):
            return
        # Rad nach vorn (positiv) heisst naeher heran, also kleinerer
        # Bildwinkel.
        self._blick_verschieben(d_fov=-schritte * self.RAD_SCHRITT)
        _, _, fov = self._backend.view360()
        self._show_speed_label(f"Zoom: {math.degrees(fov):.0f}° Bildwinkel")

    