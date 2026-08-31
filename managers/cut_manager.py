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

# managers/cut_manager.py
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QObject, Signal

class VideoCutManager(QObject):
    cutsChanged = Signal(float)

    def __init__(self, video_editor, timeline, parent=None):
        super().__init__(parent)
        self.video_editor = video_editor
        self.timeline = timeline
        self.markB_time_s = -1.0
        self.markE_time_s = -1.0
        self._cut_intervals = []
        # Schnitte, die OHNE Blende ausgefuehrt werden sollen (harte Kante).
        # Gespeichert als gerundete (start, end)-Schluessel, damit
        # _cut_intervals selbst unveraendert bleibt.
        self._hard_cuts = set()
        self.video_durations = []
        
        
    def set_video_durations(self, durations_list):
        self.video_durations = durations_list

    def on_markB_clicked(self):
        current_global_s = self._get_current_global_time()
        if self.markE_time_s >= 0 and current_global_s >= self.markE_time_s:
            QMessageBox.warning(
                None,
                "Invalid MarkB",
                f"You cannot set MarkB ({current_global_s:.2f}s) behind MarkE ({self.markE_time_s:.2f}s)!"
            )
            return  # Abbrechen, gar nicht setzen
            
        self.markB_time_s = current_global_s
        self.timeline.set_markB_time(current_global_s)

    def on_markE_clicked(self):
        current_global_s = self._get_current_global_time()
        if self.markB_time_s >= 0 and current_global_s <= self.markB_time_s:
            QMessageBox.warning(
                None,
                "Invalid MarkE",
                f"You cannot set MarkE ({current_global_s:.2f}s) in front of MarkB ({self.markB_time_s:.2f}s)!"
            )
            return
        video_total = sum(self.video_durations)
        if video_total - current_global_s < 1 : # das letzte Bild laesst sich nicht anwaehlen, deshalb klemmen wir von Hand
            current_global_s = video_total
        self.markE_time_s = current_global_s
        self.timeline.set_markE_time(current_global_s)

    def on_cut_clicked(self):
        if self.markB_time_s < 0 or self.markE_time_s < 0:
            return
        start_s = min(self.markB_time_s, self.markE_time_s)
        end_s   = max(self.markB_time_s, self.markE_time_s)
        video_total = sum(self.video_durations)
        start_s = max(0.0, start_s)
        end_s   = min(end_s, video_total)
        if (end_s - start_s) < 0.01:
            print("[DEBUG] Cut-Bereich zu klein, Abbruch. Start:", start_s, "Ende:", end_s)
            return
        # Ein neuer End-Schnitt ERSETZT einen vorhandenen End-Schnitt,
        # er kommt nicht zusaetzlich dazu. Sonst waere der ueberlappende
        # Bereich doppelt gezaehlt und ein spaeteres Ende nicht einstellbar.
        if self.is_end_cut(end_s):
            self.remove_end_cut_intervals()

        print(f"[DEBUG] CUT hinzugefügt: ({start_s:.3f}, {end_s:.3f})")
        self.prune_hard_cuts()
        self._cut_intervals.append((start_s, end_s))
        self.timeline.add_cut_interval(start_s, end_s)
        self.markB_time_s = -1
        self.markE_time_s = -1
        self.timeline.set_markB_time(-1)
        self.timeline.set_markE_time(-1)
        self._emit_cuts_changed()
        self.video_editor.set_cut_intervals(self._cut_intervals)
    
    def on_markClear_clicked(self):
        if self.markB_time_s >= 0 or self.markE_time_s >= 0:
            self.markB_time_s = -1.0
            self.markE_time_s = -1.0
            self.timeline.set_markB_time(-1)
            self.timeline.set_markE_time(-1)

    def get_merged_cut_intervals(self):
        """
        Gibt die Schnitte zurueck, wobei ueberlappende bzw. aneinander
        stossende Bereiche zu einem zusammengefasst werden.

        Ohne dieses Zusammenfassen wuerde ein doppelt geschnittener Bereich
        auch doppelt gezaehlt - die Restlaenge waere dann zu klein oder sogar
        negativ. Dieselbe Logik nutzt _compute_keep_intervals() im MainWindow.
        """
        if not self._cut_intervals:
            return []

        sorted_cuts = sorted(self._cut_intervals, key=lambda x: x[0])
        merged = []
        cur_start, cur_end = sorted_cuts[0]
        for (st, en) in sorted_cuts[1:]:
            if st <= cur_end:
                if en > cur_end:
                    cur_end = en
            else:
                merged.append((cur_start, cur_end))
                cur_start, cur_end = st, en
        merged.append((cur_start, cur_end))
        return merged

    def get_total_cuts(self) -> float:
        total_cut = 0.0
        for (start_s, end_s) in self.get_merged_cut_intervals():
            total_cut += (end_s - start_s)
        print(f"[DEBUG] get_total_cuts => {total_cut:.3f}")
        return total_cut

    def get_cut_intervals(self):
        return self._cut_intervals

    # ------------------------------------------------------------------
    # Harte Schnitte (kein Crossfade)
    # ------------------------------------------------------------------
    @staticmethod
    def _cut_key(start_s, end_s):
        return (round(float(start_s), 3), round(float(end_s), 3))

    def is_hard_cut(self, start_s, end_s) -> bool:
        return self._cut_key(start_s, end_s) in self._hard_cuts

    def set_hard_cut(self, start_s, end_s, hard: bool = True):
        key = self._cut_key(start_s, end_s)
        if hard:
            self._hard_cuts.add(key)
        else:
            self._hard_cuts.discard(key)
        self._sync_timeline_hard_cuts()

    def toggle_hard_cut(self, start_s, end_s) -> bool:
        """Schaltet um und liefert den neuen Zustand (True = harte Kante)."""
        new_state = not self.is_hard_cut(start_s, end_s)
        self.set_hard_cut(start_s, end_s, new_state)
        return new_state

    def get_hard_cuts(self) -> list:
        """Fuer die Projektdatei: Liste [[start, end], ...]."""
        self.prune_hard_cuts()
        return [[a, b] for (a, b) in sorted(self._hard_cuts)]

    def set_hard_cuts(self, pairs):
        self._hard_cuts = set()
        for item in (pairs or []):
            try:
                self._hard_cuts.add(self._cut_key(item[0], item[1]))
            except (TypeError, IndexError, ValueError):
                continue
        self.prune_hard_cuts()
        self._sync_timeline_hard_cuts()

    def prune_hard_cuts(self):
        """Markierungen wegwerfen, zu denen es keinen Schnitt mehr gibt.

        Sonst wuerde ein spaeter an genau derselben Stelle gesetzter Schnitt
        die alte Markierung erben.
        """
        alive = {self._cut_key(a, b) for (a, b) in self._cut_intervals}
        self._hard_cuts &= alive
        self._sync_timeline_hard_cuts()

    def _sync_timeline_hard_cuts(self):
        try:
            self.timeline.set_hard_cut_keys(self._hard_cuts)
        except AttributeError:
            pass

    def is_end_cut(self, end_s: float, eps: float = 0.1) -> bool:
        """True, wenn end_s bis ans Ende des Gesamtvideos reicht."""
        video_total = sum(self.video_durations)
        return abs(end_s - video_total) < eps

    def remove_end_cut_intervals(self, eps: float = 0.1) -> list:
        """
        Entfernt vorhandene End-Schnitte (Schnitte, die bis ans Videoende
        reichen) und aktualisiert die Timeline.

        Gegenstueck zu on_set_begin_clicked() im MainWindow, das denselben
        Austausch fuer den Anfangsschnitt macht. Ohne das wuerde ein zweiter
        End-Schnitt zusaetzlich angelegt statt den ersten zu ersetzen - und
        ein spaeteres Videoende liesse sich gar nicht mehr einstellen.

        Gibt die entfernten Intervalle zurueck.
        """
        removed = [iv for iv in self._cut_intervals if self.is_end_cut(iv[1], eps)]
        if not removed:
            return []

        for iv in removed:
            self._cut_intervals.remove(iv)
        print(f"[DEBUG] vorhandene End-Cuts ersetzt: {removed}")

        self.prune_hard_cuts()
        self.timeline.clear_all_cuts()
        for (a, b) in self._cut_intervals:
            self.timeline.add_cut_interval(a, b)
        self._sync_timeline_hard_cuts()
        return removed

    def _has_active_file(self) -> bool:
        """Prüft, ob der Player noch eine gültige Datei (playlist/current_index) geladen hat."""
        # 1) Hat der VideoEditor eine Playlist?
        if not self.video_editor.playlist:
            return False

        # 2) current_index darf nicht außerhalb liegen
        idx = self.video_editor.get_current_index()
        if idx < 0 or idx >= len(self.video_editor.playlist):
            return False

        # 3) Es muss auch wirklich eine Datei geladen sein
        fname = self.video_editor.get_current_file()
        if not fname:
            return False

        return True
    
    

    def _get_current_global_time(self) -> float:
        return self.video_editor.get_current_position_s()
    
    def _emit_cuts_changed(self):
        total_cut = self.get_total_cuts()
        self.cutsChanged.emit(total_cut)
    
    def is_in_cut_segment(self, time_s: float) -> bool:
        """
        Returns True, wenn 'time_s' innerhalb eines vorhandenen 
        Schnittbereichs (start_s <= time_s < end_s) liegt.
        """
        for (start_s, end_s) in self._cut_intervals:
            if start_s <= time_s < end_s:
                return True
        return False
