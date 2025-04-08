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

from PySide6.QtCore import QObject, Signal

class OverlayManager(QObject):
    """
    Verwaltet Overlays, z.B.:
      {
        "start": 30,
        "end": 50,
        "fade_in": 2,
        "fade_out": 0,
        "image": "C:/Logos/watermark.gif",
        "scale": 1.0,
        "x": "(W-w)/2",
        "y": "H-h-10"
      }
    """

    overlaysChanged = Signal()

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline  # VideoTimelineWidget
        self._overlays = []

    def add_overlay(self, ovl_dict):
        start_s = ovl_dict.get("start", 0.0)
        end_s   = ovl_dict.get("end", 0.0)
        if end_s <= start_s:
            print("[WARN] Overlay end <= start ⇒ ignoriert")
            return
        self._overlays.append(ovl_dict)
        # => Timeline anweisen, blaues Overlay anzuzeigen:
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
