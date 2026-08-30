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


# core/hardware_detect.py
import time


# ---------------------------------------------------------------------------
# Encoder-Test ueber GStreamer
# ---------------------------------------------------------------------------
# Die Kennungen links sind die, die das ganze Programm benutzt ("nvidia_hevc"
# und so weiter). Rechts steht das GStreamer-Element. Die Tabelle liegt hier,
# damit es sie nur einmal gibt: managers/ges_encoder_manager.py holt sie sich
# von hier, statt eine eigene Kopie zu fuehren.

GST_HW_ENCODER = {
    "nvidia_h264": ("nvh264enc", "video/x-h264"),
    "nvidia_hevc": ("nvh265enc", "video/x-h265"),
    "amd_h264":    ("amfh264enc", "video/x-h264"),
    "amd_hevc":    ("amfh265enc", "video/x-h265"),
    "intel_h264":  ("qsvh264enc", "video/x-h264"),
    "intel_hevc":  ("qsvh265enc", "video/x-h265"),
    "vaapi_h264":  ("vah264enc", "video/x-h264"),
    "vaapi_hevc":  ("vah265enc", "video/x-h265"),
}


def gstreamer_verfuegbar():
    """True, wenn GStreamer benutzbar ist."""
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        if not Gst.is_initialized():
            Gst.init(None)
        return True
    except Exception:
        return False


def can_encode_with_gst(element, bilder=12, zeitgrenze=8.0):
    """Baut den Encoder wirklich auf und schickt Bilder hindurch.

    Getestet wird wirklich, nicht nur geraten: es laeuft eine kleine
    Pipeline

        videotestsrc -> videoconvert -> <encoder> -> fakesink

    bis ans Ende durch. Ein Element laesst sich naemlich oft anlegen, ohne dass
    die Hardware wirklich da ist - erst beim Starten faellt das auf. Deshalb
    wird bis EOS gewartet und nicht nur gebaut.

    Liefert (True, "") oder (False, grund). Der Grund landet im Log; wenn ein
    Anwender meldet, seine Karte werde nicht erkannt, steht dort, woran es lag.
    """
    if not gstreamer_verfuegbar():
        return False, "GStreamer nicht verfuegbar"
    import gi
    from gi.repository import Gst

    beschreibung = (
        f"videotestsrc num-buffers={int(bilder)} ! "
        "video/x-raw,width=320,height=240,framerate=25/1 ! "
        f"videoconvert ! {element} ! fakesink sync=false")
    try:
        pipeline = Gst.parse_launch(beschreibung)
    except Exception as exc:
        return False, f"Pipeline nicht baubar: {exc}"

    ergebnis, grund = False, "keine Rueckmeldung"
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            return False, "Pipeline startete nicht"
        bus = pipeline.get_bus()
        ende = time.time() + zeitgrenze
        while time.time() < ende:
            msg = bus.timed_pop_filtered(
                200 * Gst.MSECOND,
                Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg is None:
                continue
            if msg.type == Gst.MessageType.EOS:
                ergebnis, grund = True, ""
            else:
                err, _dbg = msg.parse_error()
                grund = err.message
            break
        else:
            grund = "Zeitgrenze ueberschritten"
    finally:
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(2 * Gst.SECOND)
    return ergebnis, grund


def detect_hw_encoders_gst():
    """Alle Kennungen, deren Encoder sich wirklich betreiben laesst.

    "CPU" ist immer dabei. Zurueck kommt (menge, protokoll): das Protokoll
    haelt zu jedem Kandidaten fest, ob er lief und warum nicht.
    """
    gefunden = {"CPU"}
    protokoll = []
    if not gstreamer_verfuegbar():
        return gefunden, [("GStreamer", False, "nicht verfuegbar")]
    for kennung, (element, _caps) in GST_HW_ENCODER.items():
        ok, grund = can_encode_with_gst(element)
        if ok:
            gefunden.add(kennung)
        protokoll.append((f"{kennung} ({element})", ok, grund))
    return gefunden, protokoll


def list_hw_encoders_gst():
    """Die Kennungen, deren Encoder-Element vorhanden ist - ohne Testlauf.

    Sagt nur, was theoretisch da ist; der Beweis bleibt der Knopf
    "Detect HW", der wirklich kodiert. GStreamer legt die Hersteller-Elemente
    erst an, wenn beim Start eine passende Karte gefunden wurde - auf einem
    Rechner mit nur NVIDIA meldet es zwei Kennungen, waehrend die frueher
    benutzte ffmpeg-Liste sechs auffuehrte, unabhaengig von der Hardware.
    """
    gefunden = {"CPU"}
    if not gstreamer_verfuegbar():
        return gefunden
    from gi.repository import Gst
    for kennung, (element, _caps) in GST_HW_ENCODER.items():
        try:
            if Gst.ElementFactory.make(element, None) is not None:
                gefunden.add(kennung)
        except Exception:
            pass
    return gefunden
