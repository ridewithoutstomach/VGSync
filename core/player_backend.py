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
Wiedergabe-Backend hinter VideoEditorWidget.

Bis Version 5.01 sprach das Widget - und ueber `video_editor._player` auch
MainWindow, StepManager, CutManager und EndManager - direkt mit libmpv. Ein
Backendwechsel haette bedeutet, mpv-Semantik an rund 40 Stellen einzeln
herauszuoperieren; ein Rest der VLC-Anbindung von davor stand sogar noch im
EndManager.

Hier steht deshalb eine schmale Schnittstelle davor. `PlayerBackend` beschreibt,
was ein Backend koennen muss, `MpvPlayerBackend` erfuellt das mit libmpv. Die
Zeitrechnung ueber mehrere Clips (boundaries, globale Zeit) bleibt im Widget,
weil sie von der Wiedergabe unabhaengig ist.

Fehlerverhalten, bewusst zweigeteilt:
  - Lesende Zugriffe (position, fps, video_size, ...) liefern ruhige Vorgaben,
    wenn mpv gerade nichts geladen hat. Die Aufrufer haben das bisher mit
    getattr/try-except selbst abgefangen.
  - Steuernde Zugriffe (seek_local, play_index) reichen Fehler durch. Die
    Aufrufer fangen SystemError ab und setzen dann *bewusst* kein pause.
    Wuerde das Backend schlucken, aendert sich dieses Verhalten.
"""

# `import mpv` steht bewusst NICHT hier oben, sondern erst in
# MpvPlayerBackend.__init__. Sonst braeuchte auch der GES-Betrieb zwingend eine
# ladbare libmpv, und das Modul liesse sich nicht einmal importieren, bevor
# path_manager.ensure_mpv() den DLL-Pfad gesetzt hat.

# Schluessel in QSettings("KVRouite", "KVRouite"): "player/backend"
BACKEND_MPV = "mpv"
BACKEND_GES = "ges"
DEFAULT_BACKEND = BACKEND_MPV


def create_backend(window_id, log_handler=None, name=None):
    """
    Baut das eingestellte Backend.

    Ohne `name` entscheidet QSettings["player/backend"], Vorgabe ist mpv.
    Laesst sich GES nicht laden - Paket fehlt, keine Video-Senke -, wird das
    gemeldet und auf mpv zurueckgefallen, statt die App nicht starten zu
    lassen. Rueckgabe ist (backend, name, fehlermeldung_oder_None).
    """
    if name is None:
        try:
            from PySide6.QtCore import QSettings
            name = QSettings("KVRouite", "KVRouite").value(
                "player/backend", DEFAULT_BACKEND, type=str)
        except Exception:
            name = DEFAULT_BACKEND

    if name == BACKEND_GES:
        try:
            from core.ges_backend import GesPlayerBackend
            return GesPlayerBackend(window_id, log_handler), BACKEND_GES, None
        except Exception as exc:
            return (MpvPlayerBackend(window_id, log_handler), BACKEND_MPV,
                    f"GES konnte nicht geladen werden, es laeuft mpv:\n{exc}")

    return MpvPlayerBackend(window_id, log_handler), BACKEND_MPV, None


class PlayerBackend:
    """Was ein Wiedergabe-Backend koennen muss."""

    # --- Lebenszyklus -----------------------------------------------------
    def shutdown(self):
        raise NotImplementedError

    # --- Playlist ---------------------------------------------------------
    def load_playlist(self, paths):
        raise NotImplementedError

    def clear(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def play_index(self, index):
        raise NotImplementedError

    def index(self):
        """Aktueller Playlist-Index, -1 wenn keiner aktiv ist."""
        raise NotImplementedError

    def count(self):
        raise NotImplementedError

    def current_file(self):
        raise NotImplementedError

    def set_cuts(self, cuts):
        """
        Schnitte fuer die Vorschau: Liste von (start_s, ende_s, blende_s),
        blende_s = 0 heisst harte Kante.

        Backends, die das koennen, zeigen danach das fertige Video mit Blenden.
        mpv kann es nicht - dort bleibt es wirkungslos, und die Vorschau
        springt weiterhin per CutManager ueber die Schnitte.
        """
        return False

    def supports_cuts(self):
        """True, wenn set_cuts wirklich etwas bewirkt."""
        return False

    # --- Wiedergabe -------------------------------------------------------
    def set_paused(self, paused):
        raise NotImplementedError

    def is_paused(self):
        raise NotImplementedError

    def seek_local(self, seconds):
        """Exakter Sprung innerhalb des aktuellen Clips."""
        raise NotImplementedError

    def position(self):
        """Sekunde innerhalb des aktuellen Clips."""
        raise NotImplementedError

    def step_frame(self, forward=True):
        raise NotImplementedError

    def set_rate(self, rate):
        raise NotImplementedError

    def rate(self):
        raise NotImplementedError

    def set_volume(self, volume):
        raise NotImplementedError

    # --- Medieninfos ------------------------------------------------------
    def fps(self):
        """Bildrate oder None."""
        raise NotImplementedError

    def video_size(self):
        """(Breite, Hoehe); (0, 0) wenn unbekannt."""
        raise NotImplementedError

    # --- Ansicht (optional) ----------------------------------------------
    def supports_view(self):
        """True, wenn Zoom/Pan/360 unterstuetzt werden."""
        return False

    def set_360(self, enabled):
        raise NotImplementedError

    def view(self):
        """(zoom, pan_x, pan_y)."""
        raise NotImplementedError

    def set_view(self, zoom=None, pan_x=None, pan_y=None):
        raise NotImplementedError

    # --- Ereignisse -------------------------------------------------------
    def set_end_callback(self, callback):
        """callback() wird gerufen, wenn die Playlist durchgelaufen ist."""
        raise NotImplementedError


class MpvPlayerBackend(PlayerBackend):
    """PlayerBackend auf Basis von libmpv (python-mpv)."""

    def __init__(self, window_id, log_handler=None):
        import mpv  # erst hier, siehe Hinweis am Dateikopf

        self._end_callback = None
        self._player = mpv.MPV(
            wid=str(int(window_id)),
            log_handler=log_handler,
            hr_seek="yes",
            hr_seek_framedrop="yes",
            loglevel='info',
        )
        self._player["input-vo-keyboard"] = "no"
        # Fenstereinstellungen, damit wir (fast) nie Schwarz flackern
        self._player["force-window"] = "immediate"
        self._player["keep-open"] = "yes"
        self._player.pause = True
        self._player.volume = 50
        self._player.observe_property('playlist-pos', self._on_playlist_pos)

    # --- Lebenszyklus -----------------------------------------------------
    def shutdown(self):
        try:
            self._player.terminate()
        except Exception:
            pass

    # --- Playlist ---------------------------------------------------------
    def load_playlist(self, paths):
        self._player.command("playlist-clear")
        if not paths:
            return
        self._player.command("loadfile", paths[0])
        for path in paths[1:]:
            self._player.command("loadfile", path, "append-play")
        self._player.pause = True

    def clear(self):
        self._player.command("playlist-clear")

    def stop(self):
        self._player.command("stop")

    def play_index(self, index):
        self._player.command("playlist-play-index", str(index))

    def index(self):
        try:
            pos = self._player.playlist_pos
        except Exception:
            return -1
        if pos is None or pos < 0:
            return -1
        return pos

    def count(self):
        try:
            return self._player.playlist_count or 0
        except Exception:
            return 0

    def current_file(self):
        try:
            return self._player.filename
        except Exception:
            return None

    # --- Wiedergabe -------------------------------------------------------
    def set_paused(self, paused):
        self._player.pause = bool(paused)

    def is_paused(self):
        try:
            return bool(self._player.pause)
        except Exception:
            return True

    def seek_local(self, seconds):
        self._player.command("seek", f"{seconds}", "absolute", "exact")

    def position(self):
        try:
            return float(self._player.time_pos or 0.0)
        except Exception:
            return 0.0

    def step_frame(self, forward=True):
        # mpv hat fuer den Rueckwaertsschritt einen EIGENEN Befehl.
        # "frame-step" nimmt kein Argument -> "frame-step", -1 wurde von mpv
        # mit MPV_ERROR_INVALID_PARAMETER (-4) abgelehnt, es passierte nichts.
        self._player.command("frame-step" if forward else "frame-back-step")

    def set_rate(self, rate):
        self._player.speed = rate

    def rate(self):
        try:
            return float(self._player.speed or 1.0)
        except Exception:
            return 1.0

    def set_volume(self, volume):
        self._player.volume = volume

    # --- Medieninfos ------------------------------------------------------
    def fps(self):
        """
        video_params kennt KEIN "fps" - nachgemessen an libmpv enthaelt es
        w/h/aspect/par usw., aber keine Bildrate. Richtig sind "container-fps"
        und ersatzweise "estimated-vf-fps"; video_params bleibt als letzter
        Versuch stehen, damit sich nichts verschlechtert.
        """
        for name in ("container_fps", "estimated_vf_fps"):
            try:
                val = getattr(self._player, name)
                if val and float(val) > 0:
                    return float(val)
            except Exception:
                pass
        try:
            val = self._player.video_params["fps"]
            if val and float(val) > 0:
                return float(val)
        except Exception:
            pass
        return None

    def video_size(self):
        try:
            w = getattr(self._player, "width", 0) or 0
            h = getattr(self._player, "height", 0) or 0
            return int(w), int(h)
        except Exception:
            return 0, 0

    # --- Ansicht ----------------------------------------------------------
    def supports_view(self):
        return True

    def set_360(self, enabled):
        if enabled:
            self._player.video_rotate = 0
            self._player.video_aspect = "16:9"
            self._player.video_unscaled = "yes"
            self._player.panscan = 1.0
            self._player.hr_seek_framedrop = "no"   # Bessere Qualitaet bei 360
            self._player.interpolation = "yes"      # Glattere Bewegung
        else:
            self._player.video_rotate = 0
            self._player.video_aspect = "-1"        # Automatisch
            self._player.video_unscaled = "no"
            self._player.panscan = 0.0
            self._player.hr_seek_framedrop = "yes"
            self._player.interpolation = "no"

    def view(self):
        def _f(name):
            try:
                return float(getattr(self._player, name) or 0.0)
            except Exception:
                return 0.0
        return _f("video_zoom"), _f("video_pan_x"), _f("video_pan_y")

    def set_view(self, zoom=None, pan_x=None, pan_y=None):
        if zoom is not None:
            self._player.video_zoom = zoom
        if pan_x is not None:
            self._player.video_pan_x = pan_x
        if pan_y is not None:
            self._player.video_pan_y = pan_y

    # --- Ereignisse -------------------------------------------------------
    def set_end_callback(self, callback):
        self._end_callback = callback

    def _on_playlist_pos(self, name, value):
        # pos=None bzw. <0 heisst: Playlist ist durchgelaufen.
        if (value is None or value < 0) and self._end_callback:
            self._end_callback()
