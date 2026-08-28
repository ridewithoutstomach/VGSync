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
Vorgerenderte Blenden fuer die GES-Vorschau.

Warum ueberhaupt: Eine Blende live zu mischen heisst, an dieser Stelle zwei
Videospuren gleichzeitig laufen zu lassen. Die zweite muss GStreamer mitten im
Abspielen in Betrieb nehmen - Datei oeffnen, an die Stelle springen,
vorpuffern. Bei mehreren GB grossen Quellen stockt das Bild dabei sichtbar,
und zwar genau dort, wo man die Blende beurteilen will. Verschieben laesst
sich das (Vorlauf), beseitigen nicht.

Deshalb wird jede Blende einmal als kleiner Clip gerendert und als fertiges
Stueck in die Timeline gelegt. Dann laeuft dort nur EIN Dekodierer auf einer
wenige MB grossen Datei. Gemessen an 4K-Material: rund 2,8 s Rechenzeit und
4 MB je Blende.

Gerendert wird mit demselben ffmpeg-`xfade`-Filter, den auch der Export
benutzt (crossfade_2 in managers/encoder_manager.py).

ACHTUNG, Unterschied zum heutigen Export: Die Blende liegt hier MITTIG auf der
Schnittkante - bei 2 s je 1 s davor und dahinter, wie in Schnittprogrammen
ueblich. Der Export legt sie derzeit vollstaendig HINTER die Kante; nachgemessen
an final_out_linux_encodermode_hard/xfade beginnt der Unterschied zwischen
harter und weicher Fassung exakt am Schnittbild. Solange das dort nicht
angeglichen ist, zeigt die Vorschau die Blende an einer anderen Stelle als das
gerenderte Ergebnis.

Die Dateien liegen im Instanz-Temp-Ordner (config.TMP_FADE_DIR) und
verschwinden mit ihm. Der Name enthaelt einen Hash ueber alles, was das
Ergebnis bestimmt - aendert sich nichts, wird nicht neu gerendert.
"""

import hashlib
import os
import subprocess

from PySide6.QtCore import QObject, QProcess, Signal

import config

# Aendert sich die Art, wie gerendert wird, muss der Zwischenspeicher
# ungueltig werden. Deshalb geht diese Marke in den Namen ein.
_RENDER_VERSION = "2"

_rotation_cache = {}


def source_rotation(path, ffprobe="ffprobe"):
    """
    Drehung aus dem Container, in Grad. 0, wenn keine hinterlegt ist.

    Wichtig fuer die Vorschau: GoPro-Aufnahmen einer kopfueber montierten
    Kamera tragen -180. GES dreht jeden Clip einzeln anhand dieser Angabe.
    Haette der gerenderte Schnipsel sie nicht, laege er als einziger Clip
    anders herum in der Timeline.
    """
    try:
        st = os.stat(path)
        schluessel = (path, st.st_size, int(st.st_mtime))
    except OSError:
        return 0
    if schluessel in _rotation_cache:
        return _rotation_cache[schluessel]

    wert = 0
    try:
        aus = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream_side_data=rotation",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        zeile = (aus.stdout or "").strip().splitlines()
        if zeile:
            wert = int(round(float(zeile[0])))
    except Exception:
        wert = 0
    _rotation_cache[schluessel] = wert
    return wert


class FadeJob:
    """Eine zu rendernde Blende."""

    def __init__(self, src_a, in_a, src_b, in_b, duration, width, fps):
        self.src_a = src_a          # Datei mit dem abgehenden Bild
        self.in_a = float(in_a)     # Sekunde darin
        self.src_b = src_b          # Datei mit dem ankommenden Bild
        self.in_b = float(in_b)
        self.duration = float(duration)
        self.width = int(width)
        self.fps = fps              # (zaehler, nenner)

    def key(self):
        """Erkennungsmerkmal. Aendert sich eine Quelldatei, aendert sich der Hash."""
        teile = []
        for p in (self.src_a, self.src_b):
            try:
                st = os.stat(p)
                teile.append(f"{p}|{st.st_size}|{int(st.st_mtime)}")
            except OSError:
                teile.append(f"{p}|?")
        teile.append(f"{self.in_a:.6f}|{self.in_b:.6f}|{self.duration:.6f}"
                     f"|{self.width}|{self.fps[0]}/{self.fps[1]}|v{_RENDER_VERSION}")
        h = hashlib.sha1("||".join(teile).encode("utf-8")).hexdigest()[:16]
        return h

    def path(self):
        return os.path.join(config.TMP_FADE_DIR, f"fade_{self.key()}.mp4")


class FadeRenderer(QObject):
    """
    Rendert Blenden nacheinander im Hintergrund.

    Nacheinander und nicht parallel: die Quellen liegen oft auf derselben
    Platte, und zwei ffmpeg-Laeufe wuerden sich beim Lesen gegenseitig
    ausbremsen statt zu beschleunigen.
    """

    #: (fertig, gesamt) - fuer eine Fortschrittsanzeige
    progress = Signal(int, int)
    #: alle angeforderten Blenden liegen vor
    finished = Signal()

    def __init__(self, ffmpeg="ffmpeg", ffprobe="ffprobe", parent=None):
        super().__init__(parent)
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._queue = []
        self._proc = None
        self._current = None
        self._done = 0
        self._total = 0

    # ------------------------------------------------------------------
    def ready_path(self, job):
        """Pfad der fertigen Datei, oder None wenn sie noch nicht existiert."""
        p = job.path()
        try:
            if os.path.getsize(p) > 0:
                return p
        except OSError:
            pass
        return None

    def request(self, jobs):
        """
        Blenden anfordern. Bereits vorhandene werden uebersprungen.

        Rueckgabe: Anzahl der Blenden, die noch gerendert werden muessen.
        """
        self.cancel()
        offen = [j for j in jobs if self.ready_path(j) is None]
        self._queue = offen
        self._done = 0
        self._total = len(offen)
        if not offen:
            self.finished.emit()
            return 0
        self.progress.emit(0, self._total)
        self._next()
        return self._total

    def cancel(self):
        """Laufende und wartende Auftraege verwerfen."""
        self._queue = []
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.waitForFinished(2000)
            except Exception:
                pass
            self._proc = None
        # Halb geschriebene Datei nicht liegen lassen - sie wuerde beim
        # naechsten Mal als "fertig" gelten.
        if self._current is not None:
            self._verwerfen(self._current)
            self._current = None

    def _verwerfen(self, job):
        try:
            p = job.path()
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def _next(self):
        if not self._queue:
            self._current = None
            self._proc = None
            self.finished.emit()
            return

        job = self._queue.pop(0)
        self._current = job
        num, den = job.fps
        d = job.duration
        # Derselbe Filter wie im Export (crossfade_2): beide Seiten auf die
        # Vorschaubreite skalieren, dann xfade mit offset 0 - die Segmente
        # sind genau so lang wie die Blende.
        flt = (f"[0:v]scale={job.width}:-2,fps={num}/{den},format=yuv420p[a];"
               f"[1:v]scale={job.width}:-2,fps={num}/{den},format=yuv420p[b];"
               f"[a][b]xfade=transition=fade:duration={d}:offset=0[v]")

        # Drehung wie in der Quelle beibehalten, damit der Schnipsel in der
        # GES-Timeline genauso behandelt wird wie das uebrige Material.
        # Voraussetzung: beide Seiten kommen aus gleich gedrehten Dateien.
        # Sonst wird die Drehung wie bisher ins Bild gerechnet.
        rot_a = source_rotation(job.src_a, self._ffprobe)
        rot_b = source_rotation(job.src_b, self._ffprobe)
        roh = ["-noautorotate"] if (rot_a == rot_b and rot_a != 0) else []
        # ffprobe meldet die Drehung mit umgekehrtem Vorzeichen zum Tag.
        nach = (["-metadata:s:v:0", f"rotate={-rot_a}"]
                if (rot_a == rot_b and rot_a != 0) else [])

        args = (["-y", "-hide_banner", "-loglevel", "error"]
                + roh + ["-ss", f"{job.in_a:.6f}", "-t", f"{d:.6f}", "-i", job.src_a]
                + roh + ["-ss", f"{job.in_b:.6f}", "-t", f"{d:.6f}", "-i", job.src_b]
                + ["-filter_complex", flt, "-map", "[v]",
                   "-c:v", "libx264", "-crf", "23", "-preset", "veryfast", "-an"]
                + nach + [job.path()])

        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._proc.start(self._ffmpeg, args)

    def _on_error(self, err):
        print(f"[FADE] ffmpeg konnte nicht starten: {err}")
        if self._current is not None:
            self._verwerfen(self._current)
        self._weiter()

    def _on_finished(self, code, _status):
        job = self._current
        if code != 0 and job is not None:
            print(f"[FADE] Rendern fehlgeschlagen (Code {code})")
            self._verwerfen(job)
        self._weiter()

    def _weiter(self):
        self._current = None
        self._proc = None
        self._done += 1
        self.progress.emit(min(self._done, self._total), self._total)
        self._next()
