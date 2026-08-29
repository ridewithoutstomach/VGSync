# -*- coding: utf-8 -*-
"""Bildraten als exakter Bruch - lesen, weiterreichen, anzeigen.

Warum ueberhaupt ein eigener Baustein: eine Bildrate ist ein BRUCH, keine
Kommazahl. Videomaterial aus der NTSC-Welt laeuft mit 30000/1001, also
29,970030 Bilder je Sekunde. Schreibt man dafuer 29.97, ist das Ergebnis nach
vier Minuten schon ein Bild daneben, und genau das war der Fehler, den wir am
29.08.2026 gemessen haben: die Ausgabe lief mit 30 statt 30000/1001, der Export
war 35 ms zu lang und jedes Bild lag eine Position hinter dem Quellmaterial.

Deshalb gilt hier durchgehend:

    ANGEZEIGT wird "29.97"  - das ist die Zahl, die jeder kennt
    GESPEICHERT und GERECHNET wird "30000/1001"

`als_text()` liefert die Form fuer die Einstellungen und die Export-
Konfiguration, `anzeige()` die Form fuer die Oberflaeche.

Beide Encoder-Wege verstehen den Bruch: ffmpeg nimmt "-r 30000/1001" direkt,
GES rechnet ohnehin mit Zaehler und Nenner.
"""

import os
import subprocess

# Die gebraeuchlichen NTSC-Raten mit den Namen, unter denen sie jeder kennt.
_NTSC_NAMEN = {
    (24000, 1001): "23.976",
    (30000, 1001): "29.97",
    (60000, 1001): "59.94",
    (120000, 1001): "119.88",
}

# Ganzzahlige Raten, die immer zur Auswahl stehen.
_GANZE = (24, 25, 30, 50, 60, 120)


def _kuerzen(num, den):
    from math import gcd
    if den <= 0:
        return int(num), 1
    t = gcd(int(num), int(den)) or 1
    return int(num) // t, int(den) // t


def parsen(wert, vorgabe=(30, 1)):
    """Nimmt "30000/1001", "30", 30 oder 29.97 und liefert (zaehler, nenner).

    Eine Kommazahl wird auf die naechstliegende bekannte NTSC-Rate gezogen,
    damit ein altes 29.97 aus den Einstellungen nicht als 2997/100 endet.
    """
    if wert is None or wert == "":
        return vorgabe
    if isinstance(wert, (tuple, list)) and len(wert) == 2:
        return _kuerzen(wert[0], wert[1])
    text = str(wert).strip()
    if "/" in text:
        links, rechts = text.split("/", 1)
        try:
            return _kuerzen(float(links), float(rechts))
        except ValueError:
            return vorgabe
    try:
        zahl = float(text)
    except ValueError:
        return vorgabe
    if zahl <= 0:
        return vorgabe
    if abs(zahl - round(zahl)) < 1e-6:
        return int(round(zahl)), 1
    for (n, d) in _NTSC_NAMEN:
        if abs(zahl - n / d) < 0.02:
            return n, d
    # Alles andere als Tausendstel festhalten, statt es zu verfaelschen.
    return _kuerzen(round(zahl * 1000), 1000)


def als_text(num, den):
    """Form fuer Einstellungen und Export-Konfiguration: "30000/1001"."""
    num, den = _kuerzen(num, den)
    return str(num) if den == 1 else f"{num}/{den}"


def anzeige(num, den):
    """Form fuer die Oberflaeche: "30" oder "29.97"."""
    num, den = _kuerzen(num, den)
    if den == 1:
        return str(num)
    name = _NTSC_NAMEN.get((num, den))
    if name:
        return name
    return f"{num / den:.3f}".rstrip("0").rstrip(".")


def wert(num, den):
    return num / float(den or 1)


def gleich(a, b):
    """Zwei Raten sind gleich, wenn sie sich um weniger als 0,01 fps unterscheiden."""
    return abs(wert(*a) - wert(*b)) < 0.01


def auswahl(quelle, zusaetzlich=None):
    """Die Raten, die zur Auswahl stehen, wenn die Quelle mit `quelle` laeuft.

    Regel wie in Schnittprogrammen ueblich: die ganzzahligen Raten stehen immer
    bereit, die NTSC-Raten nur, wenn das Material selbst aus dieser Welt kommt.
    Bei 25-fps-Material werden also weder 29,97 noch 59,94 angeboten - die
    waeren dort nur eine Umrechnung ohne Nutzen.

    Die Rate der Quelle steht immer dabei, ebenso ein bereits eingestellter
    Wert, damit eine vorhandene Einstellung nicht stillschweigend verschwindet.
    """
    kandidaten = [(n, 1) for n in _GANZE]
    if quelle and int(quelle[1]) == 1001:
        kandidaten += list(_NTSC_NAMEN.keys())
    if quelle:
        kandidaten.append(_kuerzen(*quelle))
    if zusaetzlich:
        kandidaten.append(_kuerzen(*zusaetzlich))

    gesehen = []
    for k in kandidaten:
        if not any(gleich(k, g) for g in gesehen):
            gesehen.append(k)
    gesehen.sort(key=lambda k: wert(*k))
    return gesehen


def _lesen_gstreamer(pfad):
    """Bildrate ueber GStreamer, ohne ffprobe.

    Damit die Anwendung nicht an ffprobe haengt: sobald GStreamer da ist (und
    das ist es, wenn das GES-Backend benutzt wird), kommt die Rate von dort.
    Der Discoverer liest nur die Kopfdaten des Containers und liefert
    denselben Bruch, den auch ffprobe als r_frame_rate meldet.
    """
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstPbutils", "1.0")
        from gi.repository import Gst, GstPbutils, GLib
        if not Gst.is_initialized():
            Gst.init(None)
        sucher = GstPbutils.Discoverer.new(10 * Gst.SECOND)
        info = sucher.discover_uri(
            GLib.filename_to_uri(os.path.abspath(pfad), None))
        for strom in info.get_video_streams():
            num = strom.get_framerate_num()
            den = strom.get_framerate_denom()
            if num and den:
                return _kuerzen(num, den)
    except Exception:
        return None
    return None


def lesen(pfad, ffprobe="ffprobe"):
    """Bildrate einer Videodatei als (zaehler, nenner), oder None.

    Zuerst ueber GStreamer, dann ueber ffprobe. Beide liefern denselben Bruch
    aus dem Container ("30000/1001"), nicht die gerundete Kommazahl. Die
    Reihenfolge ist Absicht: langfristig soll die Anwendung ohne ffmpeg
    auskommen, und diese Stelle darf dem nicht im Weg stehen.
    """
    if not pfad or not os.path.isfile(pfad):
        return None
    ueber_gst = _lesen_gstreamer(pfad)
    if ueber_gst:
        return ueber_gst
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=r_frame_rate",
           "-of", "default=noprint_wrappers=1:nokey=1", pfad]
    try:
        roh = subprocess.run(
            cmd, capture_output=True, text=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except Exception:
        return None
    if not roh or roh == "0/0":
        return None
    if "/" in roh:
        n, d = roh.split("/", 1)
        try:
            n, d = int(n), int(d)
        except ValueError:
            return None
        if d == 0:
            return None
        return _kuerzen(n, d)
    try:
        return parsen(roh)
    except Exception:
        return None


def liste_lesen(pfade, ffprobe="ffprobe"):
    """Bildraten mehrerer Dateien: (raten_je_datei, alle_gleich)."""
    raten = [lesen(p, ffprobe) for p in pfade]
    bekannt = [r for r in raten if r]
    alle_gleich = all(gleich(r, bekannt[0]) for r in bekannt) if bekannt else True
    return raten, alle_gleich
