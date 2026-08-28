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

# core/gpx_parser.py

#
# managers/encoder_manager.py
#
# Kopiere unten deinen xfade6_2.py-Code GENAU rein, inkl. 
# aller Funktionen. Wir behalten also crossfade, overlays usw. 
# UNVERÄNDERT. Erst nach der Markierung "### Ende xfade6_2.py"
# kommt der neue Code.

#  Aktuelle VErsion: Der Endcut passt nicht!


import os
import sys
import json
import subprocess
import tempfile
import shutil
import contextlib
import urllib.request
import builtins, contextlib, sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit,
    QPushButton, QFileDialog, QApplication,
    QMessageBox
)
class _StringStream:
    def __init__(self, callback):
        # callback ist z. B. self._on_new_text
        self._cb = callback

    def write(self, s):
        if not s:
            return
        # direkt in dein Output-Fenster streamen
        self._cb(s)

    def flush(self):
        pass


# --- NEU: print() nur innerhalb eines Blocks wieder aktivieren ---
class _EnablePrintTemporarily(contextlib.AbstractContextManager):
    def __enter__(self):
        self._old_print = builtins.print
        def _std_print(*args, **kwargs):
            sep   = kwargs.get("sep", " ")
            end   = kwargs.get("end", "\n")
            file  = kwargs.get("file", sys.stdout)
            flush = kwargs.get("flush", False)
            file.write(sep.join(map(str, args)) + end)
            if flush:
                try: file.flush()
                except Exception: pass
        builtins.print = _std_print
        return self
    def __exit__(self, exc_type, exc, tb):
        builtins.print = self._old_print
        return False

from config import MY_GLOBAL_TMP_DIR

##### hier xfade6_2.py rein kopieren!

#!/usr/bin/env python3


#############################################################################
# Aktuelle funktionierende Versiion mit xfade overlay und crf für nvenc!
# Neue Logik der copy cuts integriert!
############################################################################

#

# Aktuell wird nur das erste overlay richtug gesetzt der cut und das zweite overlay wird garnicht erst abgearbeitet
# das Endvideo sollte 1min20s sein und der Kreisel ist am Schild ausgeschnitten
# aktuelle Video-Länge: 2:12s

# Video startet bei dem Parkplatz beim ersten weissen balken
# erstes Overlay am baum
# Kreisel bei Schild geschnitten
# zweites overlay: beim baustellenschild
# Ende: Schild Barrabco

#################

# nutze hierzu die config6.json

import os
import sys
import re
import json
import subprocess
import tempfile
import shutil
from PySide6.QtCore import QSettings

"""
===========================================================
 Universal-Skript für ffmpeg-Encodierung, 
 Crossfades (skip_instructions) und Overlays (overlay_instructions),
 mit deaktivierten B-Frames (closed-GOP), Keyframe-Zähler,
 optionaler GPU-Nutzung und CPU->GPU-Preset-Mapping
===========================================================

JSON-Konfiguration (Beispiel):

{
  "videos": [
    "C:/Pfad/clip1.mp4",
    "C:/Pfad/clip2.mp4"
  ],

  "skip_instructions": [
    [10, 20, 2],
    [55, 65, 3]
  ],
  
  "overlay_instructions": [
    {
      "start": 2,
      "end": 7,
      "fade_in": 1.0,
      "fade_out": 1.0,
      "image": "C:/Logos/logo.png",
      "scale": 0.5,
      "x": 100,
      "y": 50
    },
    {
      "start": 30,
      "end": 35,
      "fade_in": 0,
      "fade_out": 0,
      "image": "C:/Logos/watermark.gif",
      "scale": 1.0,
      "x": "(W-w)/2",    // zentriert in X-Richtung
      "y": "H-h-10"      // 10 px vom unteren Rand
    }
  ],

  "merged_output": "merged.mp4",
  "final_output":  "final_out.mp4",

  "encoder": "libx265",
  "hardware_encode": "nvidia_hevc",
  "crf": 25,
  "fps": 30,
  "width": 1280,
  "preset": "fast"
}


ERLÄUTERUNG DER FELDER
----------------------

1) **"videos"** (Pflicht)  
   Liste der Quellvideos, die wir in Schritt (1) per ffmpeg concat 
   zu einer großen "merged.mp4" (bzw. 'merged_output') machen.

2) **"skip_instructions"** (optional)  
   Array von [start, end, overlap].  
   - start, end => Die Zeitbereiche (in Sekunden) sollen "geskippt" werden.  
   - overlap => Anzahl Sekunden, die wir crossfaden (Crossfade).  
   => Wir schneiden an Keyframes und erstellen pro Skip 
      zwei Overlap-Segmente + xfade => "type":"skip".

3) **"overlay_instructions"** (optional)  
   Array von Objekten:
   {
     "start": <Sekunde>,  // Ab wann Overlay erscheint
     "end":   <Sekunde>,  // Bis wann Overlay sichtbar
     "fade_in":  <Dauer>, // Zeit (in Sek.) ab start => Overlay "erscheint" (enable=..)
     "fade_out": <Dauer>, // Zeit (in Sek.) vor end => Overlay "verschwindet" (enable=..)
     "image":    "C:/..", // Pfad zum PNG/GIF (wenn GIF => loop)
     "scale":    0.5,     // Skalierungsfaktor => 0.5 => halbe Größe
     "x": 100,            // Position X (int oder ffmpeg-Ausdruck, z.B. "(W-w)/2")
     "y": 50              // Position Y 
   }
   => Segmente in [start..end] werden re-encoded, 
      wir legen das Overlay-Bild (PNG/GIF) 
      per ffmpeg overlay=...  
   => "fade_in"/"fade_out" steuert, wann im 
      Segment das Overlay "enable=between(...)" 
      aktiv ist.  
   => x,y = 0 => links/oben, 
      z.B. x="(W-w)/2" => zentriert, 
      y="H-h-10" => unten 10 px Abstand.

4) **"merged_output"** (Pflicht)  
   Zwischen-Datei, in die wir "videos" 
   zusammenkopieren => bframes=0 (closed-gop).

5) **"final_output"** (Pflicht)  
   Ziel-Datei nach allen Crossfades/Overlays, 
   am Ende per "-c copy" zusammengefasst.

6) **"encoder"** (optional, default: "libx265")  
   - "libx264", "libx265" => CPU  
   - wir nutzen bframes=0, closed-gop

7) **"hardware_encode"** (optional, default: "none")  
   - "none" => CPU  
   - "nvidia_h264", "nvidia_hevc" => GPU (NVENC)  
   - "amd_h264", "amd_hevc", "intel_h264", "intel_hevc"  
   => Wir mappen auf h264_nvenc / hevc_nvenc, 
      h264_amf / hevc_amf, etc.  
   => CRF => interpretiert als QP

8) **"crf"** (optional, default: 12)  
   - CPU => "CRF"  
   - GPU => "QP" => globale Konstante QP

9) **"preset"** (optional)  
   CPU: "ultrafast", "superfast", "veryfast", "faster", 
        "fast", "medium", "slow", "slower", "veryslow"  
   GPU (Nvidia): "fast", "hp", "hq", "llhq", usw. 
   => Wir mappen von CPU-Voreinstellungen 
      auf GPU-spezifische Presets

10) **"fps"** (optional, default: 30)  
    => wir resampeln das Video auf diese Rate

11) **"width"** (optional)  
    => Falls angegeben => ffmpeg scale=width:-2 
       => hält Seitenverhältnis. 
    => z.B. 1280 => 1280 x (height?)

BFRAMES=0 / CLOSED-GOP
-----------------------
Wir erzwingen minimal-bf / closed-gop, 
um Non-Monotonic-DTS beim finalen "-c copy" 
zu vermeiden.

KEYFRAME-ZÄHLER
---------------
Das Script zeigt beim Scannen "Indexing Keyframes: N", 
damit man bei größeren Videos eine Fortschrittsanzeige hat.

OVERLAYS & CROSSFADE: KEINE ÜBERSCHNEIDUNG
------------------------------------------
Bitte beachte: "skip_instructions" und 
"overlay_instructions" dürfen sich NICHT 
zeitlich überlappen, weil wir nur einen 
segmentbasierten Re-Encode pro Bereich machen. 
Das Script geht timeline-basiert vor, 
zählt erst den skip-Bereich, 
dann den overlay-Bereich.

FERTIG
------
=> Das Ergebnis liegt in "final_output".

"""

"""
KURZ-ERKLÄRUNG: x, y, W, H, w, h BEI OVERLAY

- 'x' und 'y' sind die Pixel-Koordinaten der linken oberen Ecke
  des Overlays im Hauptvideo (Video-Breite= W, Video-Höhe= H).

- 'w', 'h' bezeichnen die Breite/Höhe des Overlays (nach scale=...).

- Typische Positionierungen:

  - Oben links:      x=0,       y=0
  - Unten rechts:    x="W-w",   y="H-h"
  - Zentriert:       x="(W-w)/2",  y="(H-h)/2"
  
- Mit Randabstand z. B. rechts/unten 20px:
  x="W - w - 20",  y="H - h - 20"
  Das bedeutet Weite des Videos minud Weite des Overlays minus 10 pixel!

So kannst du das Overlay per ffmpeg-Ausdruck 'W'/'H'/'w'/'h'
genau platzieren (auch 'main_w'/'main_h'/'overlay_w'/'overlay_h' möglich).
"""
###############################################################################
# 1) QSETTINGS => TEMP
###############################################################################


    
def compute_keep_segments(skip_instructions, total_duration):
    """
    Gibt die Segmente zurück, die **behalten** werden sollen,
    also zwischen -2 (Anfangs-Trim) und -1 (End-Trim)
    Nur Bereiche außerhalb dieser Skips werden behalten.
    """
    trim_ranges = [ (s, e) for s, e, mode in skip_instructions if mode in (-2, -1) and e > s ]
    trim_ranges.sort()

    keep_segments = []
    current = 0.0

    for s, e in trim_ranges:
        if s > current:
            keep_segments.append([current, s])
        current = max(current, e)

    if current < total_duration:
        keep_segments.append([current, total_duration])

    return keep_segments

    
def remap_time(t, timeline_map):
    """
    Mappt eine Zeit aus Original-Zeitleiste auf neue Timeline (nach Pre-Trim)
    Gibt None zurück, wenn die Zeit nicht im behaltenen Bereich liegt
    """
    for i, entry in enumerate(timeline_map):
        src_start = entry["src_start"]
        src_end = entry["src_end"]
        dst_start = entry["dst_start"]
        if src_start <= t < src_end:
            return dst_start + (t - src_start)
        if i == len(timeline_map) - 1 and abs(t - src_end) < 1e-6:
            return dst_start + (src_end - src_start)
    return None


def pre_trim_input_videos(videos, keep_segments, temp_dir):
    """
    Schneidet alle relevanten Keep-Segmente aus allen Videos heraus,
    wobei die Zeitachsen über die gesamte Videoliste laufen.
    Gibt: Liste Trim-Dateien, Mapping-Table mit src_start/src_end/dst_start
    """
    result_files = []
    timeline_map = []
    dst_time = 0.0
    counter = 1

    # Ermittele Gesamtlänge der Videos
    durations = []
    for v in videos:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", v]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        durations.append(float(out.stdout.strip()))

    video_ranges = []  # Liste: (video_index, start_time_in_video, abs_time_start)
    current_abs = 0.0
    for i, dur in enumerate(durations):
        video_ranges.append((i, 0.0, current_abs))
        current_abs += dur

    for seg_start, seg_end in keep_segments:
        for i, (vidx, local_start, abs_start) in enumerate(video_ranges):
            abs_end = abs_start + durations[vidx]
            if seg_end <= abs_start:
                continue
            if seg_start >= abs_end:
                continue

            # Schnittbereich im aktuellen Video (teilweise oder ganz)
            cut_start = max(seg_start, abs_start)
            cut_end = min(seg_end, abs_end)

            ss_local = cut_start - abs_start
            duration = cut_end - cut_start

            if duration <= 0:
                continue

            outname = os.path.join(temp_dir, f"trim_{counter:03d}_{int(cut_start)}_{int(cut_end)}.mp4")
            cmd = [
                "ffmpeg", "-hide_banner", "-y",
                "-ss", f"{ss_local:.3f}",
                "-i", videos[vidx],
                "-t", f"{duration:.3f}",
                "-map", "0:v:0", "-c", "copy",
                outname
            ]
            print("PRE-TRIM:", " ".join(cmd))
            #subprocess.run(cmd, check=True)
            run_command_gui(cmd, log_func=print)  # oder deine GUI-Logfunktion

            result_files.append(outname)
            timeline_map.append({
                "src_start": cut_start,
                "src_end": cut_end,
                "dst_start": dst_time
            })
            dst_time += duration
            counter += 1

    return result_files, timeline_map
    
    
def measure_real_duration(path):
    """
    Liefert die TATSAECHLICHE Inhaltsdauer einer Datei (Frames x Framedauer).

    Warum nicht die Container-Angabe?
    Wird eine Datei mit "-ss" auf eine Position geschnitten, die kein Keyframe
    ist, schleppt sie die Vorlauf-Pakete ab dem letzten Keyframe mit. Container
    und nb_frames zaehlen diese mit, obwohl sie beim Abspielen uebersprungen
    werden. Gemessen an GX010089.MP4, Schnitt bei 2018.884 s:

        tatsaechlich dekodierbar : 2853 Frames = 95.195 s
        format=duration          : 96.096 s   (0.901 s zu viel)
        stream=nb_frames         : 2880       (27 Frames zu viel)

    Der Concat-Demuxer glaubt der Container-Angabe und setzt die naechste Datei
    dadurch fast eine Sekunde zu spaet an. Beim anschliessenden Neukodieren
    wird die Luecke mit einem stehenden Bild gefuellt -> sichtbarer Ruckler an
    der Nahtstelle zwischen zwei Videos.

    Gemessen wird ueber den Zeitstempel des LETZTEN Frames plus eine
    Framedauer. Alle Frames zu zaehlen ("-count_frames") liefert dasselbe
    Ergebnis, dauert bei einer 4K-Datei dieses Umfangs aber ueber anderthalb
    Minuten statt gut drei Sekunden.

    Gibt None zurueck, wenn die Messung nicht moeglich ist; der Aufrufer
    verhaelt sich dann wie bisher.
    """
    try:
        # 1) Bildrate und Container-Dauer aus dem Header - kostet nichts
        head = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate", "-show_entries",
             "format=duration", "-of", "json", path],
            capture_output=True, text=True, check=True)
        info = json.loads(head.stdout)
        st = (info.get("streams") or [{}])[0]
        num, _, den = (st.get("avg_frame_rate") or "0/0").partition("/")
        num, den = float(num or 0), float(den or 0)
        container_dur = float((info.get("format") or {}).get("duration") or 0)
        if num <= 0 or den <= 0 or container_dur <= 0:
            return None
        frame_dur = den / num

        # 2) nur die letzten Sekunden lesen und den letzten Zeitstempel nehmen
        #
        # Das Intervall braucht ein ausdrueckliches ENDE. "START%" allein ist
        # nicht "bis zum Dateiende": nachgemessen liefert es je nach Datei
        # entweder gar nichts oder genau EINEN Frame am Intervallanfang. Im
        # zweiten Fall meldet diese Funktion die Datei um die Fensterbreite zu
        # kurz - bei 60,000 s kamen 55,033 s heraus. Die Concat-Liste bekommt
        # dann zu kleine Dauern, ffmpeg verwirft beim Zusammenfuegen Bilder,
        # und das Ergebnis ist um mehrere Sekunden zu kurz.
        start = max(0.0, container_dur - 5.0)
        fenster = container_dur - start + 1.0
        tail = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-read_intervals", f"{start:.3f}%+{fenster:.3f}",
             "-show_entries", "frame=pts_time", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        last = None
        for line in tail.stdout.splitlines():
            line = line.strip().rstrip(",")
            if line:
                try:
                    last = float(line)
                except ValueError:
                    pass
        if last is None:
            return None
        return last + frame_dur
    except Exception as e:
        print(f"[WARN] measure_real_duration({path}) failed: {e}")
        return None


def measure_real_duration_fast(path):
    """
    Wie measure_real_duration(), aber ueber die PAKETE statt ueber dekodierte
    Frames - deshalb ohne Dekodierung und rund 35x schneller (0,16 s statt
    5,6 s bei einer 4K-Datei).

    Ein mit "-c copy" geschnittener Abschnitt beginnt immer beim Keyframe VOR
    der gewuenschten Position. Die Pakete dieses Vorlaufs bekommen negative
    Zeitstempel und werden im MP4 per Edit-List ausgeblendet - sichtbarer
    Inhalt sind genau die Pakete ab Zeitstempel 0. Deren Anzahl mal Framedauer
    ist die tatsaechliche Inhaltsdauer.

    Gemessen an segment_000.mp4 (Schnitt bei 2018.884 s):
        Pakete gesamt : 2880   (davon 27 Vorlauf)
        sichtbar      : 2853 = 95.195100 s
    - identisch zum Wert aus measure_real_duration().

    Faellt auf measure_real_duration() zurueck, wenn die Pakete keine
    brauchbaren Zeitstempel liefern (z. B. variable Framerate).
    """
    try:
        head = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate", "-of", "json", path],
            capture_output=True, text=True, check=True)
        st = (json.loads(head.stdout).get("streams") or [{}])[0]
        num, _, den = (st.get("avg_frame_rate") or "0/0").partition("/")
        num, den = float(num or 0), float(den or 0)
        if num <= 0 or den <= 0:
            return measure_real_duration(path)
        frame_dur = den / num

        pk = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "packet=pts_time", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        visible = 0
        for line in pk.stdout.splitlines():
            line = line.strip().rstrip(",")
            if not line or line == "N/A":
                continue
            try:
                if float(line) >= -1e-9:
                    visible += 1
            except ValueError:
                pass
        if visible <= 0:
            return measure_real_duration(path)
        return visible * frame_dur
    except Exception as e:
        print(f"[WARN] measure_real_duration_fast({path}) failed: {e}")
        return measure_real_duration(path)


def run_command_gui(cmd, log_func=print):
    """
    Führt einen externen Befehl aus und streamt stdout + stderr live in die GUI (z. B. QTextEdit).
    """
    log_func(f"[CMD] {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Hier kommt auch das ffmpeg-Encoding rein!
        # ffmpeg liest sonst die Tastatureingabe des Elternprozesses mit. Faellt
        # dabei ein 'c' an, oeffnet es seine Kommandozeile ("Enter command: ...")
        # und schreibt die restlichen Bytes roh zurueck - ein 'q' wuerde den Lauf
        # sogar abbrechen. DEVNULL schaltet das ab.
        stdin=subprocess.DEVNULL,
        bufsize=1,
        # errors="replace" statt strengem UTF-8: ein einzelnes fremdes Byte in
        # der ffmpeg-Ausgabe (gesehen: 0xb2) hat sonst den kompletten
        # Encodier-Lauf mit einem UnicodeDecodeError beendet.
        encoding="utf-8",
        errors="replace",
    )

    for line in process.stdout:
        if line:
            log_func(line.rstrip())

    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)
        
def remap_instructions(skip_instructions, overlay_instructions, timeline_map):
    """
    Remapt skip_instructions und overlay_instructions auf die neue Zeitachse nach Pre-Trim.
    - Nur Skips mit value >= 0.1 (also keine -1/-2) werden berücksichtigt
    - Der dritte Wert wird als xfade_duration übernommen
    """
    new_skips = []
    for s, e, val in skip_instructions:
        if val in (-1, -2):  # Pre-Trim Skips -> wurden bereits geschnitten
            continue
        rs = remap_time(s, timeline_map)
        re = remap_time(e, timeline_map)
        if rs is not None and re is not None and re > rs:
            new_skips.append([rs, re, val])  # val ist hier xfade_dur

    new_overlays = []
    for ov in overlay_instructions:
        rs = remap_time(ov["start"], timeline_map)
        re = remap_time(ov["end"], timeline_map)
        if rs is not None and re is not None and re > rs:
            new_overlays.append({
                "start": rs,
                "end":   re,
                "fade_in": ov.get("fade_in", 1.0),
                "fade_out": ov.get("fade_out", 1.0),
                "image": ov["image"],
                "scale": ov.get("scale", 1.0),
                "x": ov.get("x", 0),
                "y": ov.get("y", 0)
            })

    return new_skips, new_overlays

    
###############################################################################
# 2) GPU-PRESET MAP
###############################################################################

gpu_map_nvidia = {
    "ultrafast": "fast",
    "superfast": "fast",
    "veryfast":  "fast",
    "faster":    "medium",
    "fast":      "hp",
    "medium":    "default",
    "slow":      "hq",
    "slower":    "hq",
    "veryslow":  "llhq"
}
gpu_map_amd = {
    "ultrafast": "speed",
    "superfast": "speed",
    "veryfast":  "speed",
    "faster":    "balanced",
    "fast":      "balanced",
    "medium":    "balanced",
    "slow":      "quality",
    "slower":    "quality",
    "veryslow":  "quality"
}
gpu_map_intel = {
    "ultrafast": "veryfast",
    "superfast": "veryfast",
    "veryfast":  "veryfast",
    "faster":    "fast",
    "fast":      "fast",
    "medium":    "medium",
    "slow":      "slow",
    "slower":    "slower",
    "veryslow":  "slower"
}

# VAAPI kennt kein -preset, sondern -quality als Ganzzahl:
# hoeherer Wert = schneller (siehe "ffmpeg -h encoder=h264_vaapi").
# Wir spiegeln damit dieselbe Skala wie bei den anderen Encodern.
gpu_map_vaapi = {
    "ultrafast": "7",
    "superfast": "7",
    "veryfast":  "6",
    "faster":    "5",
    "fast":      "4",
    "medium":    "4",
    "slow":      "3",
    "slower":    "2",
    "veryslow":  "1"
}

def map_preset_for_gpu(user_preset, hw_encode):
    if not user_preset:
        return None
    up= user_preset.lower()
    hw_lc= (hw_encode or "").lower()
    if hw_lc.startswith("nvidia_"):
        return gpu_map_nvidia.get(up,"default")
    elif hw_lc.startswith("amd_"):
        return gpu_map_amd.get(up,"balanced")
    elif hw_lc.startswith("intel_"):
        return gpu_map_intel.get(up,"medium")
    elif hw_lc.startswith("vaapi_"):
        return gpu_map_vaapi.get(up,"4")
    return user_preset
    

###############################################################################
# 3) DETERMINE ENCODER
###############################################################################

def determine_encoder(cpu_encoder="libx265", hw_encode=None):
    """
    => (encoderName, mode) => e.g. ("libx264","cpu"), ("hevc_nvenc","gpu")
    """
    if not hw_encode or hw_encode.lower()=="none":
        return cpu_encoder,"cpu"
    hw_map={
        "nvidia_h264":"h264_nvenc",
        "nvidia_hevc":"hevc_nvenc",
        "amd_h264":"h264_amf",
        "amd_hevc":"hevc_amf",
        "intel_h264":"h264_qsv",
        "intel_hevc":"hevc_qsv",
        "vaapi_h264":"h264_vaapi",
        "vaapi_hevc":"hevc_vaapi"
    }
    val= hw_map.get(hw_encode.lower(),"")
    if not val:
        print(f"[WARN] unknown hw_encode={hw_encode}, fallback CPU {cpu_encoder}")
        return cpu_encoder,"cpu"
    return val,"gpu"

###############################################################################
# 4) BFRAMES=0 => CLOSED-GOP
###############################################################################

def get_cpu_closedgop_params(enc_name="libx265"):
    if enc_name=="libx264":
        return ["-x264-params","bframes=0:scenecut=0","-g","5","-keyint_min","5"]
    else:
        return ["-x265-params","bframes=0:no-open-gop=1:scenecut=0","-g","5","-keyint_min","5"]

def get_gpu_closedgop_params(hw_encode):
    return ["-bf","0","-g","5"]

###############################################################################
# 5) CPU CRF vs GPU pseudo-CRF
###############################################################################

def clamp_crf(crf_val):
    if crf_val<0: crf_val=0
    if crf_val>51: crf_val=51
    return crf_val

###############################################################################
# 5b) VAAPI-Hilfen (Linux: Intel-iGPU und AMD)
###############################################################################

_cached_vaapi_device = "unset"

def is_vaapi(hw_encode):
    return (hw_encode or "").lower().startswith("vaapi_")

def find_vaapi_device():
    """
    Sucht den ersten VAAPI-Renderknoten (/dev/dri/renderD128, ...).
    Gibt den Pfad zurueck oder None. Ergebnis wird gecacht.
    """
    global _cached_vaapi_device
    if _cached_vaapi_device != "unset":
        return _cached_vaapi_device
    dev = None
    try:
        import glob as _glob
        nodes = sorted(_glob.glob("/dev/dri/renderD*"))
        if nodes:
            dev = nodes[0]
    except Exception as e:
        print("[WARN] find_vaapi_device failed:", e)
    _cached_vaapi_device = dev
    return dev

def vaapi_input_args(hw_encode):
    """
    Globale Argumente, die VOR dem Input stehen muessen.
    Nur fuer VAAPI belegt, sonst leer -> andere Encoder bleiben unveraendert.
    """
    if not is_vaapi(hw_encode):
        return []
    dev = find_vaapi_device()
    if not dev:
        print("[WARN] VAAPI selected but no /dev/dri/renderD* found")
        return []
    return ["-vaapi_device", dev]

# VAAPI-Encoder nehmen keine Software-Frames entgegen: die Filterkette
# muss auf format=nv12,hwupload enden.
VAAPI_FILTER_SUFFIX = "format=nv12,hwupload"

def vaapi_vf(hw_encode, filter_str):
    """
    Haengt den hwupload-Schritt an einen -vf Ausdruck an (oder erzeugt ihn).
    Fuer Nicht-VAAPI wird filter_str unveraendert zurueckgegeben.
    """
    if not is_vaapi(hw_encode):
        return filter_str
    if filter_str:
        return f"{filter_str},{VAAPI_FILTER_SUFFIX}"
    return VAAPI_FILTER_SUFFIX

def vaapi_pixfmt_args(hw_encode):
    """
    "-pix_fmt yuv420p" ist mit VAAPI-Hardwareframes unvereinbar.
    Liefert die bisherigen Argumente fuer alle anderen Encoder.
    """
    if is_vaapi(hw_encode):
        return []
    return ["-pix_fmt", "yuv420p"]

###############################################################################
# 5c) GPU-Encode-Parameter je Encoder-Familie
###############################################################################

def get_gpu_encode_params(hw_encode, crf, preset, bitrate_mbps, rc_flag="-rc"):
    """
    Uebersetzt die generischen Einstellungen (CRF, Preset, Bitrate) in die
    Optionen, die der jeweilige Hardware-Encoder tatsaechlich kennt.

    NVENC  : -rc vbr_hq -cq N   -preset <hp/hq/...>   (unveraendert wie bisher)
    QSV    : -global_quality N  -preset <veryfast/...>
    AMF    : -rc cqp -qp_i/-qp_p/-qp_b N   -quality <speed/balanced/quality>
    VAAPI  : -rc_mode CQP -qp N -quality <1..7>

    Die CRF-Zahl wird bei allen als Qualitaetswert durchgereicht, damit
    dieselbe Einstellung ueberall dieselbe Bildqualitaet meint.

    rc_flag existiert nur, um die bisherige Schreibweise der Aufrufstellen
    exakt beizubehalten ("-rc:v" in encode_closedgop, "-rc" in den anderen).
    """
    hw = (hw_encode or "").lower()
    qv = clamp_crf(crf)
    real_preset = map_preset_for_gpu(preset, hw_encode)
    p_extra = get_gpu_closedgop_params(hw_encode)

    br_args = []
    if bitrate_mbps:
        br = f"{bitrate_mbps}M"
        br_args = ["-b:v", br, "-maxrate", br, "-bufsize", f"{bitrate_mbps * 2}M"]

    if hw.startswith("nvidia_"):
        args = [rc_flag, "vbr_hq", "-cq", str(qv)]
        if real_preset:
            args += ["-preset", real_preset]
        args += p_extra + br_args
        print(f"[DEBUG] GPU(NVENC) => vbr_hq + -cq={qv}")
        return args

    if hw.startswith("intel_"):
        # QSV kennt weder -rc noch -cq; Qualitaet laeuft ueber -global_quality
        args = ["-global_quality", str(qv)]
        if real_preset:
            args += ["-preset", real_preset]
        args += p_extra
        print(f"[DEBUG] GPU(QSV) => -global_quality={qv}")
        return args

    if hw.startswith("amd_"):
        # AMF kennt weder vbr_hq noch -cq; konstante Qualitaet = cqp
        args = ["-rc", "cqp",
                "-qp_i", str(qv), "-qp_p", str(qv), "-qp_b", str(qv)]
        if real_preset:
            args += ["-quality", real_preset]
        args += p_extra
        print(f"[DEBUG] GPU(AMF) => cqp + -qp={qv}")
        return args

    if hw.startswith("vaapi_"):
        # VAAPI kennt weder -rc/-cq noch -preset.
        # Achtung: -quality gibt es nur bei h264_vaapi, NICHT bei hevc_vaapi
        # (geprueft mit "ffmpeg -h encoder=hevc_vaapi"). Ein -quality wuerde
        # dort zum Abbruch fuehren, deshalb nur fuer H.264 setzen.
        args = ["-rc_mode", "CQP", "-qp", str(qv)]
        if real_preset and hw == "vaapi_h264":
            args += ["-quality", str(real_preset)]
        args += p_extra
        print(f"[DEBUG] GPU(VAAPI) => CQP + -qp={qv}")
        return args

    # Unbekannte GPU-Kennung: wie bisher NVENC-Schreibweise verwenden
    args = [rc_flag, "vbr_hq", "-cq", str(qv)]
    if real_preset:
        args += ["-preset", real_preset]
    args += p_extra + br_args
    print(f"[DEBUG] GPU(?) => vbr_hq + -cq={qv}")
    return args

###############################################################################
# 6) SCALE-FILTER
###############################################################################

def build_scale_filter(width):
    if width is None:
        return None
    return f"scale={width}:-2"

###############################################################################
# 7) ENCODE_CLOSEDGOP => CPU CRF / GPU VBR_HQ + -cq
###############################################################################

def encode_closedgop(
    concat_file,
    outname,
    encoder="libx265",
    hw_encode=None,
    fps=None,
    crf=None,       # read from config; no default 12
    width=None,
    preset=None,
    bitrate_mbps=None,
    force_kf=None
):
    enc_name, mode = determine_encoder(encoder, hw_encode)
    real_preset = preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset, hw_encode)

    filter_str= build_scale_filter(width)

    cmd=[
        "ffmpeg","-hide_banner","-y"
    ] + vaapi_input_args(hw_encode) + [
        "-f","concat","-safe","0",
        "-i", concat_file,
        "-an"
    ]

    # if user didn't specify => fallback?
    if crf is None:
        crf=23  # or 25 ?

    if mode=="cpu":
        # => real CRF
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        if bitrate_mbps:
            br = f"{bitrate_mbps}M"
            cmd += ["-b:v", br, "-maxrate", br, "-bufsize", f"{bitrate_mbps * 2}M"]
        print(f"[DEBUG] CPU => CRF={crf}")
        
        

    else:
        # => GPU => Parameter je Encoder-Familie (NVENC unveraendert wie bisher)
        cmd+= ["-c:v", enc_name]
        cmd+= get_gpu_encode_params(hw_encode, crf, preset, bitrate_mbps,
                                    rc_flag="-rc:v")

    if fps:
        cmd+= ["-r", str(fps)]
    filter_str= vaapi_vf(hw_encode, filter_str)
    if filter_str:
        cmd+= ["-vf", filter_str]

    cmd+= [outname]
    # An jeder Schnittkante einen Keyframe erzwingen.
    #
    # Die Teilstuecke werden spaeter mit "-c copy" aus merged.mp4 geholt und
    # koennen deshalb nur an Keyframes beginnen. Ohne diese Zeile liegt die
    # naechste Kante bis zu eine GOP daneben (bei -g 5 rund 0,17 s), und der
    # Fehler summiert sich ueber alle Schnitte - gemessen -0,167 s pro
    # Schnitt, bei harter Kante wie bei Blende gleichermassen. Mit einem
    # Keyframe genau auf der Kante ist der Schnitt bildgenau. Kostet nichts:
    # merged.mp4 wird hier ohnehin komplett neu encodiert.
    if force_kf:
        times = ",".join(f"{float(t):.6f}" for t in force_kf)
        cmd = cmd[:-1] + ["-force_key_frames", times] + [cmd[-1]]

    print("ENCODE_CLOSEDGOP:", " ".join(cmd))
    #subprocess.run(cmd, check=True)
    run_command_gui(cmd, log_func=print)  # oder deine GUI-Logfunktion
    

###############################################################################
# 8) KEYFRAMES => live counter
###############################################################################

import re

def get_keyframes(src):
    """
    Liefert die Keyframe-Zeitpunkte von src.

    Zuerst ueber die PAKETE (Flag "K"), das kommt ohne Dekodierung aus.
    Gemessen an einer 60-s-Datei (1080p hevc, -g 5): 0,08 s statt 8,3 s
    ueber "-skip_frame nokey -show_frames" - hochgerechnet auf ein Projekt
    von 1989 s sind das rund 3 s statt gut viereinhalb Minuten. Die Liste ist
    dabei nicht nur aehnlich, sondern identisch (360 von 360 Werten gleich).

    Aufgerufen wird die Funktion nur mit merged.mp4, also einer Datei, die
    wir selbst mit "-bf 0" erzeugt haben. Trotzdem wird sortiert, damit die
    Reihenfolge auch bei B-Frames stimmt (Pakete kommen in Dekodier-, nicht
    in Anzeigereihenfolge).

    Liefert der Paket-Weg nichts, greift der alte Weg ueber die dekodierten
    Frames.
    """
    times = _get_keyframes_from_packets(src)
    if times:
        print(f"Total Keyframes found: {len(times)}\n")
        return times
    print("[WARN] No keyframes found in packets - falling back to frame scan.")
    return _get_keyframes_by_decoding(src)


def _get_keyframes_from_packets(src):
    print(f"\nIndexing Keyframes in {src} ...")
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", src],
            capture_output=True, encoding="utf-8", errors="replace", check=True)
    except Exception as e:
        print(f"[WARN] Keyframe scan via packets failed: {e}")
        return []
    times = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        try:
            times.append(float(parts[0]))
        except ValueError:
            pass
    times.sort()
    return times


def _get_keyframes_by_decoding(src):
    pattern= re.compile(r'"best_effort_timestamp_time"\s*:\s*"')
    cmd=[
        "ffprobe","-hide_banner",
        "-select_streams","v:0",
        "-skip_frame","nokey",
        "-show_frames",
        "-show_entries","frame=best_effort_timestamp_time",
        "-print_format","json",
        "-i", src
    ]
    p= subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        encoding="utf-8",errors="replace")
    lines=[]
    count=0
    spinner = ['|', '/', '-', '\\']
    while True:
        line= p.stdout.readline()
        if not line: break
        lines.append(line)
        if pattern.search(line):
            count+=1
            m = re.search(r'"best_effort_timestamp_time"\s*:\s*"([^"]+)"', line)
            t_str = m.group(1) if m else "?"
            
            if count % 50 == 0:
                print(f"\rKeyframes found: {count} => Time: {t_str}", end='', flush=True)
            
    p.wait()
    print()
    data= json.loads("".join(lines))
    frames_data= data.get("frames",[])
    times=[]
    for fr in frames_data:
        t= float(fr.get("best_effort_timestamp_time","0"))
        times.append(t)
    times.sort()
    print(f"Total Keyframes found: {len(times)}\n")
    
    #for i, t in enumerate(times, start=1):
    #    print(f" - Keyframe {i} bei {t:.3f}s")
    return times        
# Toleranz fuer die Keyframe-Suche: 1 ms. Zwei Bilder liegen mindestens 16 ms
# auseinander, ein Keyframe kann also nie versehentlich der falsche sein.
# Noetig, weil die Schnittzeiten durch die Umrechnung auf die Zeitachse nach
# dem Vorschnitt minimal danebenliegen koennen: 18.1 - 3.1 ergibt in Python
# 15.000000000000002, der erzwungene Keyframe steht aber bei 15.000000 - ohne
# Toleranz wird er uebersehen und der Schnitt springt eine GOP zu weit.
KF_EPS = 0.001

def get_kf_le(kf_list,t):
    if not kf_list:
        return 0.0
    best=kf_list[0]
    for k in kf_list:
        if k<=t+KF_EPS:
            best=k
        else:
            break
    return best

def get_kf_ge(kf_list,t):
    if not kf_list:
        return t
    for k in kf_list:
        if k>=t-KF_EPS:
            return k
    return kf_list[-1]

###############################################################################
# 9) COPY_CUT / CROSSFADE
###############################################################################

def copy_cut(src,start,end,outfile):
    dur= end-start
    if dur<=0:
        raise ValueError("invalid cut dur => start={start},end={end}")
    cmd=[
        "ffmpeg","-hide_banner","-y",
        # 6 Nachkommastellen, NICHT 3: start ist ein Keyframe-Zeitpunkt aus
        # get_kf_le(). Auf 3 Stellen gerundet liegt er knapp VOR dem Keyframe
        # (5.833 statt 5.833333), und ffmpeg beginnt beim Keyframe davor - eine
        # ganze GOP (5 Frames) Vorlauf, die spaeter im Concat auf 0.3 ms
        # zusammengedraengt wird und als Ruckler sichtbar ist.
        # Gemessen an merged.mp4: -ss 5.833 -> 45 Frames, erstes Paket
        # -0.166667; -ss 5.833333 -> 40 Frames, erstes Paket 0.000000.
        "-ss",f"{start:.6f}",
        "-i",src,
        # -t bleibt bei 3 Stellen: dur ist der Abstand zweier Keyframes, und
        # das Abrunden haelt genau den Frame draussen, mit dem das naechste
        # Teilstueck beginnt. Mehr Stellen wuerden ihn doppelt liefern.
        "-t",f"{dur:.3f}",
        "-map","0:v:0",
        "-c","copy",
        outfile
    ]
    print("COPY_CUT:", " ".join(cmd))
    #subprocess.run(cmd,check=True)
    run_command_gui(cmd, log_func=print)
    
def crossfade_2(
    inA,inB,outname,
    encoder="libx265",
    hw_encode=None,
    crf=23,
    fps=None,width=None,preset=None,
    overlap=2,
    bitrate_mbps=None,
    ss_a=None, ss_b=None, seg_dur=None, seg_dur_b=None
):
    """
    Blendet inA nach inB. Die Blende beginnt am Anfang von inA (offset=0),
    beide Eingaenge muessen also genau `overlap` lang sein.

    Mit ss_a/ss_b/seg_dur wird der Ausschnitt direkt beim Lesen bestimmt,
    statt vorher Teilstuecke herauszukopieren. Das ist bildgenau: `-ss` vor
    `-i` dekodiert ab dem vorherigen Keyframe und verwirft, was davor liegt.
    Noetig fuer die mittige Blende - deren Segmente beginnen mitten im
    Material, und ein "-c copy"-Schnitt kann dort nicht ansetzen.
    """
    enc_name, mode= determine_encoder(encoder,hw_encode)
    real_preset= preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset,hw_encode)

    filter_complex=[]
    if width:
        filter_complex.append(f"[0:v]scale={width}:-2,format=yuv420p[v0]")
        filter_complex.append(f"[1:v]scale={width}:-2,format=yuv420p[v1]")
    else:
        filter_complex.append("[0:v]format=yuv420p[v0]")
        filter_complex.append("[1:v]format=yuv420p[v1]")
    xfade_chain= f"xfade=transition=fade:duration={overlap}:offset=0"
    if is_vaapi(hw_encode):
        xfade_chain= f"{xfade_chain},{VAAPI_FILTER_SUFFIX}"
    filter_complex.append(f"[v0][v1]{xfade_chain}[vout]")
    flt=";".join(filter_complex)

    def _eingang(pfad, ss, dauer):
        vor = []
        if ss is not None:
            vor += ["-ss", f"{float(ss):.6f}"]
        if dauer is not None:
            vor += ["-t", f"{float(dauer):.6f}"]
        return vor + ["-i", pfad]

    # B darf laenger sein als die Blende: nach dem Uebergang laeuft es dann
    # noch bis zum naechsten Keyframe weiter, damit das folgende
    # "-c copy"-Stueck sauber dort ansetzen kann.
    cmd=[
        "ffmpeg","-hide_banner","-y"
    ] + vaapi_input_args(hw_encode) + _eingang(inA, ss_a, seg_dur)       + _eingang(inB, ss_b, seg_dur_b if seg_dur_b is not None else seg_dur) + [
        "-filter_complex",flt,
        "-map","[vout]"
    ]

    if mode=="cpu":
        # CPU => -crf
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        if bitrate_mbps:
            br = f"{bitrate_mbps}M"
            cmd += ["-b:v", br, "-maxrate", br, "-bufsize", f"{bitrate_mbps * 2}M"]
        print(f"[DEBUG] CROSSFADE => CPU => CRF={crf}")
    else:
        # GPU => Parameter je Encoder-Familie (NVENC unveraendert wie bisher)
        cmd+= ["-c:v", enc_name]
        cmd+= get_gpu_encode_params(hw_encode, crf, preset, bitrate_mbps)

    if fps:
        cmd+=["-r",str(fps)]
    cmd+= vaapi_pixfmt_args(hw_encode) + ["-an", outname]
    print("CROSSFADE_2:", " ".join(cmd))
    #subprocess.run(cmd,check=True)
    run_command_gui(cmd, log_func=print)
###############################################################################
# 10) FINAL CONCAT
###############################################################################

def final_concat_copy(parts,outfile):
    """
    Fuegt die fertigen Teilstuecke zusammen.

    Jede Datei bekommt ihre gemessene Inhaltsdauer mit. Ohne diese Angabe
    nimmt der Concat-Demuxer die Container-Dauer, und die stimmt bei einem
    "-c copy" geschnittenen Teilstueck nicht zwingend auf den Frame genau -
    das naechste Teilstueck sitzt dann zu spaet (stehendes Bild) oder zu
    frueh (zusammengedraengte Frames).

    Seit copy_cut() exakt auf dem Keyframe ansetzt, sind die Container-Dauern
    in allen nachgemessenen Faellen bereits richtig; die Angabe hier aendert
    dann nichts (nachgemessen: Ausgabe mit und ohne Dauerangabe frameweise
    gleich). Sie bleibt als Absicherung stehen, weil sie im Copy-Mode
    nachweislich einen 934-ms-Ruckler behebt und hier nichts kostet
    (~0,16 s je Teilstueck).

    Es aendert sich ausschliesslich der Zeitstempel; kein Paket wird
    hinzugefuegt oder verworfen. Siehe measure_real_duration_fast().
    """
    tmp_list= os.path.splitext(outfile)[0]+"_concat.txt"
    total_parts = len(parts)
    print(f"\n[INFO] Checking length of {total_parts} part(s) ...")
    with open(tmp_list,"w",encoding="utf-8") as f:
        for i, p in enumerate(parts, 1):
            abspath= os.path.abspath(p)
            name = os.path.basename(abspath)
            f.write(f"file '{abspath}'\n")
            real_dur = measure_real_duration_fast(abspath)
            if real_dur:
                f.write(f"duration {real_dur:.6f}\n")
                print(f"[{i}/{total_parts}] {name}: {real_dur:.3f}s")
            else:
                print(f"[{i}/{total_parts}] {name}: length not measurable, "
                      f"using container value")
    print("[INFO] Length check done, joining ...\n")

    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-f","concat","-safe","0",
        "-i", tmp_list,
        "-map","0:v:0",
        "-c","copy",
        outfile
    ]
    print("FINAL CONCAT COPY:", " ".join(cmd))
    #subprocess.run(cmd,check=True)
    run_command_gui(cmd, log_func=print)
    os.remove(tmp_list)

###############################################################################
# 11) ALPHA FADE OVERLAY
###############################################################################

def _build_overlay_input_args(img):
    ext= os.path.splitext(img.lower())[1]
    if ext in (".png",".jpg",".jpeg",".bmp"):
        return ["-loop","1","-f","image2","-i", img]
    elif ext==".gif":
        return ["-stream_loop","-1","-i", img]
    else:
        return ["-i", img]

def overlay_segment_encode(
    in_segment,out_segment,
    overlay_image,
    fade_in=1.0,fade_out=1.0,
    seg_duration=None,scale=1.0,x=0,y=0,
    encoder="libx265",hw_encode=None,crf=23,
    fps=None,preset=None,width=None,
    bitrate_mbps=None
):
    # => real alpha fade => RGBA => fade in/out => scale => overlay
    # => same idea as we had:
    #   fade_in => 0..fade_in => alpha=0..1
    #   fade_out => (dur-fade_out)..dur => alpha=1..0
    if seg_duration is None:
        cmd_dur=[
            "ffprobe","-v","error",
            "-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",
            in_segment
        ]
        rr=subprocess.run(cmd_dur,capture_output=True,text=True,check=True)
        seg_duration= float(rr.stdout.strip())

    fade_out_start= seg_duration - fade_out
    if fade_out_start<0:
        fade_out_start=0

    filter_complex=[]
    chain=[]
    chain.append("format=rgba")
    if fade_in>0:
        chain.append(f"fade=t=in:st=0:d={fade_in:.3f}:alpha=1")
    if fade_out>0:
        chain.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}:alpha=1")
    chain.append(f"scale=iw*{scale}:ih*{scale}:force_original_aspect_ratio=decrease")

    chain_str=",".join(chain)
    filter_complex.append(f"[1:v]{chain_str}[ov1]")

    base_in="[vbase]"
    if width:
        filter_complex.append(f"[0:v]scale={width}:-2,format=yuv420p[vbase]")
    else:
        filter_complex.append("[0:v]format=yuv420p[vbase]")
    x_str= str(x)
    y_str= str(y)
    overlay_chain= f"overlay=x={x_str}:y={y_str}:format=auto"
    if is_vaapi(hw_encode):
        overlay_chain= f"{overlay_chain},{VAAPI_FILTER_SUFFIX}"
    overlay_str= f"{base_in}[ov1]{overlay_chain}[vout]"
    filter_complex.append(overlay_str)

    fc_str= ";".join(filter_complex)

    overlay_input_args= _build_overlay_input_args(overlay_image)
    cmd=[
        "ffmpeg","-hide_banner","-y"
    ]+ vaapi_input_args(hw_encode) + [
        "-i", in_segment
    ]+ overlay_input_args + [
        "-filter_complex", fc_str,
        "-map","[vout]",
        "-t", f"{seg_duration:.3f}"
    ]

    enc_name, mode= determine_encoder(encoder, hw_encode)
    real_preset= preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset,hw_encode)

    if mode=="cpu":
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        if bitrate_mbps:
            br = f"{bitrate_mbps}M"
            cmd += ["-b:v", br, "-maxrate", br, "-bufsize", f"{bitrate_mbps * 2}M"]
        print(f"[DEBUG] overlay => CPU => CRF={crf}")
    else:
        # GPU => Parameter je Encoder-Familie (NVENC unveraendert wie bisher)
        cmd+= ["-c:v", enc_name]
        cmd+= get_gpu_encode_params(hw_encode, crf, preset, bitrate_mbps)

    if fps:
        cmd+=["-r",str(fps)]
    cmd+= vaapi_pixfmt_args(hw_encode) + ["-an", out_segment]

    print("OVERLAY_SEGMENT_ENCODE:", " ".join(cmd))
    #subprocess.run(cmd,check=True)
    run_command_gui(cmd, log_func=print)

###############################################################################
# 12) Build skip/overlay events
###############################################################################
def build_segments_with_skip_and_overlay(
    merged_file, kf_list, total_duration,
    skip_instructions, overlay_instructions,
    encoder="libx265", hw_encode=None, crf=23, fps=None, width=None, preset=None,
    temp_dir=None, bitrate_mbps=None
):
    """
    Erzeugt Segmente (normal/skip/overlay) streng aufsteigend entlang der Timeline,
    damit es keine Überschneidungen oder rückwärtslaufende Schnitte gibt.
    """

    # 1) Events aus JSON sammeln
    events = []
    for triple in skip_instructions:
        s, e, o = triple
        ev = {"type": "skip", "start": float(s), "end": float(e), "overlap": float(o)}
        events.append(ev)

    for ov in overlay_instructions:
        ev = {
            "type":     "overlay",
            "start":    float(ov["start"]),
            "end":      float(ov["end"]),
            "fade_in":  float(ov.get("fade_in", 1.0)),
            "fade_out": float(ov.get("fade_out", 1.0)),
            "image":    ov["image"],
            "scale":    float(ov.get("scale", 1.0)),
            "x":        ov.get("x", 0),
            "y":        ov.get("y", 0)
        }
        events.append(ev)

    # Sortieren nach Startzeit
    events.sort(key=lambda x: x["start"])

    
    segments = []
    out_count = 1
    current_pos = 0.0

    # Debug-Liste
    debug_logs = []

    # ============= Schleife durch alle Events =============
    for ev in events:
        t1 = ev["start"]
        t2 = ev["end"]
        if t2 <= t1:
            # Ungültig, überspringen
            continue

        # 1) Normal-Part: [current_pos..t1]
        if t1 > current_pos:
            seg_start = get_kf_le(kf_list, current_pos)
            if ev["type"] == "skip":
                # Ein "-c copy"-Stueck darf mitten in der GOP ENDEN, nur der
                # Anfang braucht einen Keyframe. Deshalb sitzt die Kante hier
                # exakt, auch wenn oben kein Keyframe erzwungen werden konnte.
                #
                # Bei einer Blende endet das Normalstueck eine HALBE
                # Blendenlaenge vor der Kante: die Blende liegt mittig darauf,
                # reicht also ebensoweit ins behaltene Material hinein.
                ov = float(ev["overlap"])
                seg_end = t1 if ov <= 0 else max(current_pos, t1 - ov / 2.0)
            else:
                seg_end   = get_kf_le(kf_list, t1)
            if seg_end > seg_start:
                part_out = os.path.join(
                    temp_dir, f"part_{out_count:02d}_{int(seg_start)}_{int(seg_end)}.mp4"
                )
                copy_cut(merged_file, seg_start, seg_end, part_out)
                segments.append(part_out)
                debug_logs.append(
                    f"[NORMAL] JSON-Range: {current_pos:.2f}..{t1:.2f} "
                    f"=> Keyframes: {seg_start:.2f}..{seg_end:.2f}"
                )
                out_count += 1
            normal_end = seg_end
        else:
            # Falls t1 <= current_pos, sind wir schon "drüber"
            normal_end = current_pos

        # 2) Schauen, ob wir SKIP oder OVERLAY haben
        if ev["type"] == "skip":
            overlap = ev["overlap"]

            # Harter Schnitt: overlap = 0 bedeutet "keine Blende".
            # Ohne diesen Zweig laeuft copy_cut() in eine Exception, denn
            # A_end = get_kf_le(t1 + 0) ist derselbe Keyframe wie A_start,
            # das A-Segment haette also Dauer 0.
            #
            # current_pos wird bewusst auf den Keyframe NACH t2 gesetzt und
            # nicht auf t2 selbst: das naechste Normalstueck startet mit
            # get_kf_le(current_pos) und wuerde sonst rueckwaerts in den
            # weggeschnittenen Bereich runden (bis zu eine GOP, bei -g 5 also
            # rund 0,17 s). Liegt current_pos schon auf einem Keyframe, ist
            # das spaetere get_kf_le() wirkungslos und die Schnittkante bleibt
            # genau dort, wo der Benutzer sie gesetzt hat.
            if overlap <= 0:
                current_pos = max(
                    current_pos,
                    get_kf_ge(kf_list, min(t2, total_duration))
                )
                debug_logs.append(
                    f"[SKIP] JSON-Bereich: {t1:.2f}..{t2:.2f}, harter Schnitt "
                    f"=> kein Crossfade, weiter ab {current_pos:.2f}"
                )
                continue
            #if t2 > total_duration:
            #    t2 = total_duration
            #if t1 >= total_duration:
            #    debug_logs.append(f"[SKIP] JSON-Bereich {t1:.2f}..{t2:.2f} liegt komplett hinter Video-Ende => skip!")
            #    continue
                
            # Wir "skippen" [t1..t2] und blenden MITTIG ueber die Kante:
            #   Segment A = [t1 - overlap/2 .. t1 + overlap/2]
            #   Segment B = [t2 - overlap/2 .. t2 + overlap/2]
            # Je zur Haelfte behaltenes Material, je zur Haelfte Ueberhang aus
            # dem weggeschnittenen Bereich - so machen es Schnittprogramme.
            # Die Gesamtlaenge bleibt gleich: das Normalstueck endet eine halbe
            # Laenge frueher, das naechste beginnt eine halbe Laenge spaeter.
            #
            # A und B werden NICHT mehr vorher herauskopiert. Sie beginnen
            # mitten im Material, und "-c copy" kann nur an einem Keyframe
            # ansetzen - das Ergebnis waere um bis zu eine GOP verschoben.
            # Stattdessen liest ffmpeg beide Ausschnitte direkt aus der
            # zusammengefuegten Datei; beim Neukodieren ist "-ss" bildgenau.
            half = overlap / 2.0
            A_start = max(0.0, t1 - half)
            B_start = max(0.0, t2 - half)
            if B_start + overlap > total_duration:
                # Am Materialende ist kein voller Ueberhang mehr da.
                overlap = max(0.0, total_duration - B_start)
                half = overlap / 2.0
            if overlap <= 0:
                debug_logs.append(
                    f"[SKIP] JSON-Bereich {t1:.2f}..{t2:.2f}: kein Platz fuer eine "
                    f"Blende am Materialende => harte Kante."
                )
                current_pos = max(current_pos, min(t2, total_duration))
                continue

            # Die Blende endet bei t2 + overlap/2, also mitten in einer GOP.
            # Das naechste Stueck wird aber mit "-c copy" geschnitten und muss
            # an einem Keyframe beginnen. Deshalb laeuft dieses Segment nach
            # der Blende noch bis zum naechsten Keyframe weiter - dort setzt
            # das Normalstueck dann exakt an, ohne Luecke und ohne Dopplung.
            blende_ende = min(t2 + half, total_duration)
            naechster_kf = min(get_kf_ge(kf_list, blende_ende), total_duration)
            nachlauf = max(0.0, naechster_kf - blende_ende)

            xf_out = os.path.join(temp_dir, f"skipX_{out_count:02d}_{int(t1)}_{int(t2)}.mp4")
            crossfade_2(
                inA=merged_file, inB=merged_file, outname=xf_out,
                encoder=encoder, hw_encode=hw_encode, crf=crf,
                fps=fps, width=width, preset=preset,
                overlap=overlap,
                bitrate_mbps=bitrate_mbps,
                ss_a=A_start, ss_b=B_start,
                seg_dur=overlap, seg_dur_b=overlap + nachlauf
            )
            segments.append(xf_out)

            debug_logs.append(
                f"[SKIP] JSON-Bereich: {t1:.2f}..{t2:.2f}, overlap={overlap:.1f} "
                f"=> A=({A_start:.2f}..{A_start+overlap:.2f}), "
                f"B=({B_start:.2f}..{B_start+overlap:.2f}), Blende mittig auf der Kante"
            )
            out_count += 1

            # Weiter geht es am Keyframe hinter der Blende - genau dort endet
            # das eben erzeugte Segment.
            current_pos = max(current_pos, naechster_kf)

        elif ev["type"] == "overlay":
            fade_in  = ev["fade_in"]
            fade_out = ev["fade_out"]
            ov_img   = ev["image"]
            sc       = ev["scale"]
            xx       = ev["x"]
            yy       = ev["y"]

            # Re-encode [t1..t2] => auf Keyframes gerundet
            ov_start = get_kf_le(kf_list, t1)
            ov_end   = get_kf_le(kf_list, t2)
            if ov_end < ov_start:
                ov_end = ov_start

            in_cut = os.path.join(temp_dir, f"ov_in_{out_count:02d}_{int(t1)}.mp4")
            copy_cut(merged_file, ov_start, ov_end, in_cut)

            out_cut = os.path.join(temp_dir, f"ov_out_{out_count:02d}_{int(t1)}_{int(t2)}.mp4")
            seg_dur = ov_end - ov_start
            overlay_segment_encode(
                in_segment=in_cut, out_segment=out_cut,
                overlay_image=ov_img, fade_in=fade_in, fade_out=fade_out,
                seg_duration=seg_dur, scale=sc, x=xx, y=yy,
                encoder=encoder, hw_encode=hw_encode, crf=crf,
                fps=fps, preset=preset, width=None,
                bitrate_mbps=bitrate_mbps
            )
            segments.append(out_cut)

            debug_logs.append(
                f"[OVERLAY] JSON-Range: {t1:.2f}..{t2:.2f} => "
                f"Keyframes: {ov_start:.2f}..{ov_end:.2f}"
            )
            out_count += 1

            # current_pos anheben
            current_pos = max(current_pos, t2)

    # 3) Letztes Segment (falls was übrig)
    if current_pos < total_duration:
        seg_start = get_kf_le(kf_list, current_pos)
        # Beim "-c copy" muss nur der ANFANG auf einem Keyframe liegen, das Ende
        # nicht. Ein get_kf_le() hier wuerde auf den letzten Keyframe abrunden
        # und dadurch bis zu 5 Frames (bei -g 5) am Dateiende verwerfen.
        seg_end   = total_duration
        if seg_end > seg_start:
            final_out = os.path.join(
                temp_dir, f"final_{out_count:02d}_{int(seg_start)}_{int(seg_end)}.mp4"
            )
            copy_cut(merged_file, seg_start, seg_end, final_out)
            segments.append(final_out)
            debug_logs.append(
                f"[END] JSON-Range: {current_pos:.2f}..{total_duration:.2f} => "
                f"{seg_start:.2f}..{seg_end:.2f}"
            )

    # ============= Debug-Ausgabe =============
    print("\n============== DEBUG CUT-LIST ==============")
    for line in debug_logs:
        print(line)
    print("=================================================\n")

    return segments
    
    


###############################################################################
# MAIN
###############################################################################
def xfade_main(cfg_path):
    
    #if len(sys.argv) < 2:
    #    print("Usage: python script.py config.json")
    #    sys.exit(1)

    #with open(sys.argv[1], "r", encoding="utf-8") as f:
    #    cfg = json.load(f)
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        
    videos = cfg["videos"]
    skip_list = cfg.get("skip_instructions", [])
    overlay_list = cfg.get("overlay_instructions", [])
    merged_out = cfg["merged_output"]
    final_out = cfg["final_output"]
    hw_encode = cfg.get("hardware_encode", "none")
    encoder = cfg.get("encoder", "libx265")
    crf = cfg.get("crf", 23)
    settings = QSettings("KVRouite", "KVRouite")
    bitrate_mbps = settings.value("encoder/bitrate_mbps", 20, type=int)
    fps = cfg.get("fps", 30)
    width = cfg.get("width", None)
    preset = cfg.get("preset", None)

    temp_dir = MY_GLOBAL_TMP_DIR
    os.makedirs(temp_dir, exist_ok=True)
    print("[INFO] TempDir:", temp_dir)

    
    
   
    
    total_duration = 0.0
    for v in videos:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", v]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        total_duration += float(out.stdout.strip())

    # Was mit jedem Schnitt passiert. Steht einmal oben im Encoder-Fenster
    # und am Ende noch einmal unter "DONE" - dort bleibt es stehen, waehrend
    # der obere Teil beim Rendern durchlaeuft.
    def _cut_summary():
        lines = []
        for (c_s, c_e, c_v) in skip_list:
            if c_v == -2:
                what = "trimmed away (video start)"
            elif c_v == -1:
                what = "trimmed away (video end)"
            elif float(c_v) <= 0:
                what = "hard cut (no crossfade)"
            else:
                what = f"crossfade {float(c_v):.1f}s"
            lines.append(f"Cut {float(c_s):.2f}s - {float(c_e):.2f}s: {what}")
        return lines

    for line in _cut_summary():
        print("[INFO] " + line)

    keep_segments = compute_keep_segments(skip_list, total_duration)
    print("[INFO] Keep segments:", keep_segments)

    trimmed_parts, timeline_map = pre_trim_input_videos(videos, keep_segments, temp_dir)
    print("[INFO] Timeline map:", timeline_map)

    # Jede Datei bekommt ihre gemessene Inhaltsdauer mit. Ohne diese Angabe
    # verlaesst sich der Concat-Demuxer auf die Container-Dauer, die bei
    # geseekten Trim-Dateien zu gross ist -> stehendes Bild an der Nahtstelle.
    # Siehe measure_real_duration().
    concat_txt = os.path.join(temp_dir, "concat_input.txt")
    total_parts = len(trimmed_parts)
    print(f"\n[INFO] Checking length of {total_parts} part(s) - "
          f"a few seconds per file ...")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for i, path in enumerate(trimmed_parts, 1):
            abs_path = os.path.abspath(path)
            name = os.path.basename(abs_path)
            # Ausgabe VOR der Messung: xfade_main laeuft im GUI-Thread, und das
            # Fenster wird nur beim Schreiben neu gezeichnet. Ohne diese Zeile
            # steht die Oberflaeche waehrend der Messung scheinbar still.
            print(f"[{i}/{total_parts}] measuring {name} ...")
            f.write(f"file '{abs_path}'\n")
            real_dur = measure_real_duration(abs_path)
            if real_dur:
                f.write(f"duration {real_dur:.6f}\n")
                print(f"[{i}/{total_parts}] {name}: {real_dur:.3f}s")
            else:
                print(f"[{i}/{total_parts}] {name}: length not measurable, "
                      f"using container value")
    print("[INFO] Length check done, merging ...\n")

    merged_path = os.path.join(temp_dir, merged_out)

    # Die Schnitte auf die Zeitachse NACH dem Vorschnitt umrechnen. Das
    # Ergebnis wird zweimal gebraucht: hier fuer die erzwungenen Keyframes
    # und weiter unten fuer die Segmente.
    remapped_skips, remapped_overlays = remap_instructions(
        skip_list, overlay_list, timeline_map)
    cut_edges = sorted({t for (c_s, c_e, _v) in remapped_skips
                        for t in (c_s, c_e)})

    encode_closedgop(
        force_kf=cut_edges,
        concat_file=concat_txt,
        outname=merged_path,
        encoder=encoder,
        hw_encode=hw_encode,
        fps=fps,
        crf=crf,
        width=width,
        preset=preset,
        bitrate_mbps=bitrate_mbps
    )
    print("[INFO] Cleaning up TRIM files to free space...")
    for path in trimmed_parts:
        try:
            os.remove(path)
        except Exception as e:
            print(f"[WARN] Could not delete {path}: {e}")
    

    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", merged_path]
    rr = subprocess.run(cmd_dur, capture_output=True, text=True, check=True)
    new_duration = float(rr.stdout.strip())
    print("[INFO] Merged duration:", new_duration)

    kf = get_keyframes(merged_path)

    parts = build_segments_with_skip_and_overlay(
        merged_file=merged_path,
        kf_list=kf,
        total_duration=new_duration,
        skip_instructions=remapped_skips,
        overlay_instructions=remapped_overlays,
        encoder=encoder,
        hw_encode=hw_encode,
        crf=crf,
        fps=fps,
        width=width,
        preset=preset,
        temp_dir=temp_dir,
        bitrate_mbps=bitrate_mbps     
    )

    final_concat_copy(parts, final_out)
    print("\n== DONE == Final video:", final_out)
    for line in _cut_summary():
        print("   " + line)

if __name__ == "__main__":
    main()



### Ende xfade6_2.py


#-----------------------------------------------------------------
# Neuer Code: 
#  - Wir definieren xfade_main(cfg_json) als Ersatz für main().
#  - Wir leiten print() ins QPlainTextEdit (EncoderDialog).
#  - Vorher machen wir ein Dateiauswahl-Fenster, damit der User 
#    den final_output festlegen kann, wenn du das möchtest.
#-----------------------------------------------------------------

class EncoderDialog(QDialog):
    _counter_url = "http://www.KVRouite.com/project/counter.php"
    """
    Dieses QFenster zeigt den gesamten ffmpeg-Output,
    den dein xfade6_2.py generiert (also Keyframe-Indexing, etc.),
    live an. 
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("XFade Encoding - This may take a while")
        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)

        self.setLayout(layout)
        self.resize(800, 600)
        
    def _increment_counter_on_server(self, mode: str):
        """
        Erhöht den Zähler auf dem Server (mode='video' oder 'gpx')
        """
        if mode not in ("video", "gpx"):
            print("[WARN] Ungültiger mode für Counter:", mode)
            return None

        action = "increment_video" if mode == "video" else "increment_gpx"
        url = f"{self._counter_url}?action={action}"
        
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except Exception as e:
            print(f"[ERROR] Counter-Update fehlgeschlagen: {str(e)}")
            return None    


    def run_encoding(self, json_path: str):
        """
        1) Wir lesen json_path => c 
        2) Zeigen ein QFileDialog, damit User final_out wählt (optional).
        3) Überschreiben c["final_output"].
        4) Leiten print(...) in self._on_new_text
        5) Rufen xfade_main(cfg_path) oder xfade_main_direct(c) auf
        """
        # 1) JSON lesen
        with open(json_path, "r", encoding="utf-8") as f:
            c = json.load(f)

        # 2) Dateiauswahl => final_out
        default_out = c.get("final_output", "final.mp4")
        chosen_out, _ = QFileDialog.getSaveFileName(
            self,
            "Select final output",
            default_out,
            "Video Files (*.mp4)"
        )
        if not chosen_out:
            self._on_new_text("[CANCELED] No output file selected.\n")
            return
        
        if not chosen_out.lower().endswith('.mp4'):
            chosen_out += '.mp4'
            QMessageBox.information(
                self,
                "File Extension Added!",
                f"Added '.mp4' extension to:\n{os.path.basename(chosen_out)}"
            )
        
        # => final_out überschreiben
        c["final_output"] = chosen_out

        # 3) c in eine temp-Datei schreiben, damit wir "xfade_main(...)" 
        #    ohne sys.argv aufrufen können:
        temp_cfg = os.path.join(tempfile.gettempdir(), "xfade_temp.json")
        with open(temp_cfg, "w", encoding="utf-8") as f2:
            json.dump(c, f2, indent=2)

        # 4) print-Umleitung => self._on_new_text
        stream = _StringStream(self._on_new_text)
        
        with _EnablePrintTemporarily(), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                # 5) xfade_main(temp_cfg) => ruft dein "main()" auf, 
                #    nur ohne sys.argv.
                xfade_main(temp_cfg)
                result = self._increment_counter_on_server("video")
                
                    
                QMessageBox.information(
                     self,
                    "Done",
                    "Video exported successfully!"
                )
                
                for file in os.listdir(MY_GLOBAL_TMP_DIR):
                    full_path = os.path.join(MY_GLOBAL_TMP_DIR, file)
                    if file.endswith(".mp4"):
                        try:
                            os.remove(full_path)
                            print(f"[INFO] Deleted temp file: {full_path}")
                        except Exception as e:
                            print(f"[WARN] Could not delete temp file {full_path}: {e}")

                
                try:
                    shutil.rmtree(MY_GLOBAL_TMP_DIR)
                    #print("[INFO] TEMP-Ordner gelöscht:", MY_GLOBAL_TMP_DIR)
                    os.makedirs(MY_GLOBAL_TMP_DIR, exist_ok=True)
                except Exception as e:
                    #print("[WARN] TEMP konnte nicht gelöscht werden:", e)
                    os.makedirs(MY_GLOBAL_TMP_DIR, exist_ok=True)

            except Exception as e:
                print(f"[ERROR] {e}")
        

    def _on_new_text(self, text: str):
        """Callback pro print-Ausgabe => wir hängen ans Textfeld an."""
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(text)
        self.text_edit.moveCursor(QTextCursor.End)
        QApplication.processEvents()
