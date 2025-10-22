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
import mpv
import math

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QFrame, QLabel, QVBoxLayout
)
from PySide6.QtCore import Qt, QTimer, Signal

from PySide6.QtGui import QShortcut, QKeySequence

class VideoEditorWidget(QWidget):
     #Signal MUSS als Klassenattribut definiert werden
    videosDropped = Signal(list)  # list[str]
    
    """
    Ein mpv-basierter Video-Player, der die alten Methoden (show_first_frame_at_index,
    set_playback_rate, etc.) bereitstellt, damit dein restlicher Code weiter funktioniert.
    Er kann mehrere Videos in die mpv-Playlist laden und nacheinander abspielen.
    
    Zusätzlich mit 360°-Video-Unterstützung, die mit Taste 'V' umgeschaltet werden kann.
    """

    play_ended = Signal()  # z.B. wenn das letzte Video fertig ist

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
        vbox_time.addWidget(self.current_time_label)
        layout.addWidget(self.current_time_widget, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)

        # Extra: Edit-Status
        self.edit_status_widget = QWidget(self)
        self.edit_status_widget.setMaximumWidth(65)

        vbox_edit = QVBoxLayout(self.edit_status_widget)
        vbox_edit.setContentsMargins(0, 50, 0, 0)
        vbox_edit.setSpacing(0)

        self.edit_status_label = QLabel("", self.edit_status_widget)
        self.acut_status_label = QLabel("", self.edit_status_widget)
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

        # MPV Setup
        self._player = mpv.MPV(
            wid=str(int(self.video_frame.winId())),
            log_handler=self._mpv_log_handler,
            hr_seek="yes",
            hr_seek_framedrop="yes",
            loglevel='info',
        )
        self._player["input-vo-keyboard"] = "no"
        # Fenstereinstellungen, damit wir (fast) nie Schwarz flackern
        self._player["force-window"] = "immediate"
        self._player["keep-open"] = "yes"

        # Start = paused
        self._player.pause = True
        self._player.volume = 50

        self.is_playing = False
        self.playlist = []
        self._current_index = 0
        self.multi_durations = []
        self.boundaries = []

        # Falls du end-file auswerten willst:
        self._player.observe_property('playlist-pos', self._on_playlist_pos_changed)

        # Du kannst z. B. die Zeitanzeige in einer Timer-Schleife updaten
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time_label)
        self._time_timer.start(200)  # alle 200ms
        
        # -------- Keyboard Shortcuts --------
        """
        # Speed: + / -  (auch Numpad; mehrere Sequenzen, damit alle Layouts greifen)
        #s = QShortcut(QKeySequence("+"),          self, activated=lambda: self._nudge_speed(+0.10)); s.setContext(Qt.ApplicationShortcut)
        #s = QShortcut(QKeySequence("-"),          self, activated=lambda: self._nudge_speed(-0.10)); s.setContext(Qt.ApplicationShortcut)
        s = QShortcut(QKeySequence(Qt.Key_Plus),  self, activated=lambda: self._nudge_speed(+0.10)); s.setContext(Qt.ApplicationShortcut)
        s = QShortcut(QKeySequence(Qt.Key_Minus), self, activated=lambda: self._nudge_speed(-0.10)); s.setContext(Qt.ApplicationShortcut)
        s = QShortcut(QKeySequence(Qt.Key_Equal), self, activated=lambda: self._nudge_speed(+0.10)); s.setContext(Qt.ApplicationShortcut)  # Shift+='+' Layouts
        # Speed reset: 1
        s = QShortcut(QKeySequence("1"),          self, activated=lambda: self.set_playback_rate(1.0)); s.setContext(Qt.ApplicationShortcut)
        """
        # -------- Keyboard Shortcuts (keine Ambiguität) --------
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
        
        # Viewport Zoom/Pan dürfen beim bisherigen Kontext bleiben:
        QShortcut(QKeySequence("Ctrl++"), self, activated=lambda: self._nudge_zoom(+0.10))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._nudge_zoom(-0.10))
        QShortcut(QKeySequence("Ctrl+0"),  self, activated=self._reset_view)

        #QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Left),  self, activated=lambda: self._nudge_pan(dx=-0.05))
        #QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Right), self, activated=lambda: self._nudge_pan(dx=+0.05))
        #QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Up),    self, activated=lambda: self._nudge_pan(dy=-0.05))
        #QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Down),  self, activated=lambda: self._nudge_pan(dy=+0.05))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Left),  self, activated=lambda: self._nudge_pan(dx=+0.05))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Right), self, activated=lambda: self._nudge_pan(dx=-0.05))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Up),    self, activated=lambda: self._nudge_pan(dy=+0.05))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Down),  self, activated=lambda: self._nudge_pan(dy=-0.05))

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
        

    def toggle_360_mode(self):
        """Schaltet den 360°-Video-Modus um"""
        self._is_360_mode = not self._is_360_mode
        
        try:
            if self._is_360_mode:
                # 360°-Video Einstellungen aktivieren
                self._player.video_rotate = 0
                self._player.video_aspect = "16:9"
                self._player.video_unscaled = "yes"
                self._player.panscan = 1.0
                
                # 360°-spezifische Einstellungen
                self._player.hr_seek_framedrop = "no"  # Bessere Qualität bei 360°
                self._player.interpolation = "yes"     # Glattere Bewegung
                
                self._360_label.show()
                print("360°-Modus aktiviert")
            else:
                # Zurück zu normalen Einstellungen
                self._player.video_rotate = 0
                self._player.video_aspect = "-1"  # Automatisch
                self._player.video_unscaled = "no"
                self._player.panscan = 0.0
                
                # Zurück zu normalen Performance-Einstellungen
                self._player.hr_seek_framedrop = "yes"
                self._player.interpolation = "no"
                
                self._360_label.hide()
                self._reset_view()
                self._show_speed_label("360°-Modus: AUS")
                print("360°-Modus deaktiviert")
                
                
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
        """
        Gehe zum playlist-Index 'index', pausiere + seek an den Anfang => 1. Frame
        """
        if not self.playlist or index < 0 or index >= len(self.playlist):
            return  # Ungültig => Abbruch

        self.is_playing = False
    
        # => mpv springt zu Clip 'index'
        self._player.command("playlist-play-index", str(index))
    
        def do_seek():
            # 1) Prüfen, ob mpv noch ein Video hat + Position >=0
            if self._player.playlist_count == 0:
                return
            if self._player.playlist_pos is None or self._player.playlist_pos < 0:
                return

            # 2) Seek an 0s
            try:
                self._player.command("seek", "0", "absolute", "exact")
                self._player.pause = True
                self.is_playing = False
            except SystemError as e:
                # -12 bedeutet oft, dass mpv in Idle ist oder "keine Datei mehr hat"
                print(f"[WARN] show_first_frame: mpv refused to seek => {e}")

        QTimer.singleShot(80, do_seek)

    def set_playback_rate(self, rate: float):
        print(f"DEBUG: set_playback_rate called with rate={rate}")  # Debug
        self._player.speed = rate
        print(f"DEBUG: mpv speed is now: {self._player.speed}")  # Debug
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
        Wird evtl. aufgerufen, wenn Timeline den Schieberegler setzt und wir
        nur das UI-Label anpassen wollen. (Oder optional -> self._player.seek())
        """
        # => wir machen hier NUR Label:
        text_html = self.format_seconds_html(secs)
        self.current_time_label.setTextFormat(Qt.RichText)
        self.current_time_label.setText(text_html)

    def play_pause(self):
        if self.is_playing:
            self._player.pause = True
            self.is_playing = False
        else:
            self._player.pause = False
            self.is_playing = True

    def get_current_position_s(self) -> float:
        """
        Gibt die *globale* Zeit (in Sekunden) über alle Clips zurück.
        Ruft intern get_current_global_time() auf.
        """
        return self.get_current_global_time()

    def get_current_index(self) -> int:
        """Ablösung für dein altes self._current_index => mpv.playlist_pos."""
        pos = self._player.playlist_pos
        if pos is None or pos < 0:
            return -1
        return pos

    def set_time(self, new_s: float):
        """
        Globaler Sprung in der gesamten Playlist:
        Rechnet new_s => clipIndex + local_s und ruft 'playlist-play-index' + 'seek' auf.
        """
        self._jump_to_global_time(new_s)

    def frame_step_forward(self):
        self._player.command("frame-step")

    def frame_step_backward(self):
        self._player.command("frame-step", -1)

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

    def set_playlist(self, video_list):
        """Erzeugt mpv-Playlist per 'append-play'."""
        self._player.command("playlist-clear")
        if not video_list:
            self.playlist = []
            self.set_empty_hint_visible(True)
            return
        # Erstes normal load
        self._player.command("loadfile", video_list[0])
        # Rest => append
        for path in video_list[1:]:
            self._player.command("loadfile", path, "append-play")

        # Start paused
        self._player.pause = True
        self.is_playing = False

        self.playlist = video_list
        self.set_empty_hint_visible(False)

    def _jump_to_global_time(self, wanted_s: float):
        """
        'wanted_s' ist die globale Zeit über alle Clips.
        Wir ermitteln clipIndex + local_s.
        """
        if not self.boundaries:
            return

        total = self.boundaries[-1]
        if wanted_s < 0:
            wanted_s = 0.0
        elif wanted_s >= total:
            # Wenn wir ans Ende oder darüber hinaus wollen, gehen wir zum Ende des letzten Videos
            wanted_s = total
            clip_idx = len(self.boundaries) - 1
            offset_prev = self.boundaries[clip_idx-1] if clip_idx > 0 else 0.0
            local_s = self.multi_durations[clip_idx] - 0.001  # Kurz vor das Ende setzen
        else:
            # Normaler Fall: finde den Clip-Index
            clip_idx = 0
            offset_prev = 0.0
            for i, bound_val in enumerate(self.boundaries):
                if wanted_s < bound_val:
                    clip_idx = i
                    break
                offset_prev = bound_val
            local_s = wanted_s - offset_prev
    
        # Aktueller mpv-Playlist-Index:
        current_idx = self._player.playlist_pos

        if current_idx == clip_idx:
            # Gleicher Clip => direkt seek
            try:
                self._player.command("seek", f"{local_s}", "absolute", "exact")
                self._player.pause = True
                self.is_playing = False
            except SystemError as e:
                print(f"[WARN] _jump_to_global_time: mpv refused to seek => {e}")
        else:
            # Clip-Wechsel => playlist-play-index + Delay
            self._player.command("playlist-play-index", str(clip_idx))
    
            def do_seek():
                if self._player.playlist_count == 0:
                    return
                if self._player.playlist_pos is None or self._player.playlist_pos < 0:
                    return
                try:
                    self._player.command("seek", f"{local_s}", "absolute", "exact")
                    self._player.pause = True
                    self.is_playing = False
                except SystemError as e:
                    print(f"[WARN] _jump_to_global_time: mpv refused to seek => {e}")
    
            QTimer.singleShot(100, do_seek)
            
    # -----------------------------------------
    # mpv Event-Handling
    # -----------------------------------------

    def _on_playlist_pos_changed(self, name, value):
        """
        mpv ruft diese Callback auf, sobald 'playlist-pos' wechselt.
        Falls wir am Ende sind, pos=None. Dann => play_ended-Signal?
        """
        if value is None or value < 0:
            # => wir sind evtl. am Ende der Playlist
            self.play_ended.emit()

    # optionales Log
    def _mpv_log_handler(self, level, component, message):
        print(f"[MPV] {level} {component}: {message}", end="")
    
    def _update_time_label(self):
        if not self.playlist or self._player.playlist_count == 0:
            self.current_time_label.hide()
            return
        else:
            self.current_time_label.show()
            
        # 1) globale Sekunde
        global_s = self.get_current_global_time()

        # 2) falls "global" => zeige global_s
        #    falls "final"  => rufe callback auf
        if self._time_mode == "final" and self._final_time_callback:
            show_s = self._final_time_callback(global_s)
        else:
            show_s = global_s

        text_html = self.format_seconds_html(show_s)
        self.current_time_label.setText(text_html)

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
            self._jump_to_global_time(cut0_end)
        
            # Danach Pause + is_playing = False
            self._player.pause = True
            self.is_playing = False

        else:
            # => kein Schnitt am Anfang => normaler Sprung an Clip=0, 0s
            self._player.command("playlist-play-index", "0")

            def do_seek_zero():
                if self._player.playlist_count == 0:
                    return
                if self._player.playlist_pos is None or self._player.playlist_pos < 0:
                    return
            
                try:
                    self._player.command("seek", "0", "absolute", "exact")
                    self._player.pause = True
                    self.is_playing = False
                except SystemError as e:
                    print(f"[WARN] stop(): mpv refused to seek => {e}")
        
            QTimer.singleShot(50, do_seek_zero)

    def get_current_global_time(self) -> float:
        """
        Gibt die 'globale' Zeit (in Sekunden) über alle Clips zurück.
        Beispiel: wenn wir im 2. Clip sind, der erste Clip war 60s lang 
        und im 2. Clip sind wir gerade bei Sekunde 10 => Rückgabe = 70.
        """
        clipIndex = self._player.playlist_pos  # python-mpv property
        local_s   = self._player.time_pos or 0.0
        if clipIndex is None or clipIndex < 0:
            return 0.0

        # offset_prev = boundaries[clipIndex - 1] (0.0 wenn clipIndex==0)
        if clipIndex == 0:
            offset_prev = 0.0
        else:
            offset_prev = self.boundaries[clipIndex - 1]
    
        return offset_prev + local_s
        
        
        # -------- Helpers: Speed / Zoom / Pan --------
    def _nudge_speed(self, delta: float):
        """Erhöht/verringert die Abspielgeschwindigkeit und zeigt das Label."""
        print(f"DEBUG: _nudge_speed called with delta={delta}")  # Debug
        try:
            cur = float(self._player.speed or 1.0)
            print(f"DEBUG: Current speed = {cur}")  # Debug
        except Exception as e:
            print(f"DEBUG: Error getting current speed: {e}")  # Debug
            cur = 1.0
        new = max(0.10, min(32.00, cur + delta))  # Klammern 0.10x .. 4.00x
        self.set_playback_rate(new)

    def _nudge_zoom(self, dz: float):
        # Nur im 360°-Modus erlauben
        if not getattr(self, "_is_360_mode", False):
            self._show_speed_label("Zoom nur im 360°-Modus (Taste V)")
            return
        """Zoom der Videodarstellung (mpv video-zoom)."""
        try:
            cur = float(self._player.video_zoom or 0.0)
        except Exception:
            cur = 0.0
        new = max(-0.90, min(5.00, cur + dz))     # -0.9 .. 5.0 sind praxistauglich
        self._player.video_zoom = new
        # Beim Zoomen Pan beibehalten (mpv macht das), optional Overlay:
        self._show_speed_label(f"Zoom: {new:+.2f}")

    def _nudge_pan(self, dx: float = 0.0, dy: float = 0.0):
        if not getattr(self, "_is_360_mode", False):
            self._show_speed_label("Pan/Tilt nur im 360°-Modus (Taste V)")
            return
        """Viewport verschieben (mpv video-pan-x/y). Sinnvoll bei Zoom > 0."""
        try:
            px = float(self._player.video_pan_x or 0.0)
            py = float(self._player.video_pan_y or 0.0)
        except Exception:
            px, py = 0.0, 0.0
        px = max(-1.0, min(1.0, px + dx))
        py = max(-1.0, min(1.0, py + dy))
        self._player.video_pan_x = px
        self._player.video_pan_y = py
        # kleines Overlay, damit man Feedback hat:
        self._show_speed_label(f"Pan: x={px:+.2f}, y={py:+.2f}")

    def _reset_view(self):
        """Zoom/Pan auf Standard zurücksetzen."""
        self._player.video_zoom = 0.0
        self._player.video_pan_x = 0.0
        self._player.video_pan_y = 0.0
        self._show_speed_label("View reset")
        
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
    
    

        # ---- Mouse-based pan (for 360° view) ----
    def mousePressEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._is_360_mode:
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_last_mouse_pos") and self._is_360_mode:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()

            # adjust sensitivity here
            dx = delta.x() / 1000.0
            dy = delta.y() / 1000.0

            self._nudge_pan(dx, dy)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_last_mouse_pos"):
            del self._last_mouse_pos
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    