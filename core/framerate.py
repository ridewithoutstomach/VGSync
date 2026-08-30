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

Gelesen wird ueber GStreamer, ergaenzt um die Laenge direkt aus dem
MP4/MOV-Container. ffmpeg kommt hier nicht mehr vor - es wird in KVRouite nur
noch fuer den Copy-Mode gebraucht.
"""

import json
import os

# Die gebraeuchlichen NTSC-Raten mit den Namen, unter denen sie jeder kennt.
_NTSC_NAMEN = {
    (24000, 1001): "23.976",
    (30000, 1001): "29.97",
    (60000, 1001): "59.94",
    (120000, 1001): "119.88",
}

# Ganzzahlige Raten, die immer zur Auswahl stehen.
_GANZE = (24, 25, 30, 50, 60, 120)

# Gemerkte Eckdaten je Datei, damit dieselbe Datei nicht bei jedem
# Neuaufbau der Zeitleiste erneut geoeffnet wird.
_CACHE = {}


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


def _drehung_aus_tag(text):
    """GStreamers "image-orientation" in die Zaehlweise von ffprobe.

    ffprobe meldet die Drehung als vorzeichenbehaftete Zahl in der
    "rotation"-Zusatzangabe des Datenstroms; GStreamer nennt dasselbe
    "rotate-180". Bei kopfueber aufgenommenem GoPro-Material stehen dort
    "rotate-180" und -180 - an derselben Datei geprueft.

    Nur 0 und 180 werden zugeordnet. Bei 90 und 270 gehen die Zaehlweisen
    auseinander (Drehrichtung), und weil in dieser Anwendung ohnehin nur 0 und
    180 behandelt werden, wird alles andere als "unbekannt" gemeldet - dann
    wird alles andere als "unbekannt" gemeldet - GES wertet die
    Kennzeichnung dann selbst aus.
    """
    return {"rotate-0": 0, "rotate-180": -180}.get(text)


def _schluessel(pfad):
    st = os.stat(pfad)
    return (os.path.abspath(pfad), st.st_size, int(st.st_mtime))


def _eckdaten_gstreamer(pfad):
    """Bildrate, Laenge und Bildgroesse in einem Zug, ohne ffprobe.

    Der Discoverer liest nur die Kopfdaten des Containers. Gemessen an einer
    11,9-GB-Datei: 0,036 s, gegen 0,772 s fuer einen ffprobe-Start.
    """
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstPbutils", "1.0")
        from gi.repository import Gst, GstPbutils, GLib
        if not Gst.is_initialized():
            Gst.init(None)
        sucher = GstPbutils.Discoverer.new(30 * Gst.SECOND)
        info = sucher.discover_uri(
            GLib.filename_to_uri(os.path.abspath(pfad), None))
        daten = {"fps": None, "dauer": 0.0, "breite": 0, "hoehe": 0,
                 "drehung": None, "quelle": "gstreamer"}
        # Merkt, ob ueberhaupt eine Drehungs-Kennzeichnung vorhanden war.
        # Fehlt sie ganz, ist das Video nicht gedreht - dann muss nicht extra
        # nichts weiter geprueft werden. Nur ein vorhandenes, aber nicht
        # zuordenbares Tag (90 oder 270 Grad) bleibt "unbekannt".
        gesehen = {"tag": False}
        gesamt = info.get_duration()
        if gesamt and gesamt > 0:
            daten["dauer"] = gesamt / 1_000_000_000.0
        for strom in info.get_video_streams():
            num, den = strom.get_framerate_num(), strom.get_framerate_denom()
            if num and den and not daten["fps"]:
                daten["fps"] = _kuerzen(num, den)
            daten["breite"] = daten["breite"] or strom.get_width()
            daten["hoehe"] = daten["hoehe"] or strom.get_height()
            if daten["drehung"] is None and not gesehen["tag"]:
                tags = strom.get_tags()
                ok, text = (tags.get_string("image-orientation")
                            if tags is not None else (False, None))
                if ok:
                    gesehen["tag"] = True
                    daten["drehung"] = _drehung_aus_tag(text)
        if not gesehen["tag"]:
            daten["drehung"] = 0
        return daten if (daten["fps"] or daten["dauer"]) else None
    except Exception:
        return None


def eckdaten(pfad, ffprobe=None):
    """Bildrate, Laenge und Bildgroesse einer Videodatei.

    Gelesen ueber GStreamer, die Laenge zusaetzlich direkt aus dem Container.
    Das Ergebnis wird gemerkt, solange Groesse und Aenderungszeit gleich bleiben - die
    Zeitleiste wird nach jeder Aenderung der Wiedergabeliste neu gerechnet,
    und ohne das Merken laeuft die Abfrage bei jeder Datei erneut.

    Liefert None, wenn sich gar nichts lesen laesst.
    """
    if not pfad or not os.path.isfile(pfad):
        return None
    try:
        k = _schluessel(pfad)
    except OSError:
        return None
    if k in _CACHE:
        return _CACHE[k]
    daten = _eckdaten_gstreamer(pfad)

    # Die Laenge kommt bevorzugt direkt aus dem Container. Grund: GStreamers
    # Discoverer meldet die Gesamtlaenge aus der "mvhd"-Box, und deren
    # Zeitbasis ist oft nur 1000 - bei 1min_Nr2.mp4 kamen so 60.834 statt
    # 60.833333 heraus, 0,667 ms zu viel. Die "mdhd"-Box der Videospur haelt
    # den Wert exakt; gemessen ueber vier Dateien: 0,0003 ms Abweichung
    # gegenueber ffprobe, bei 0,001 s Laufzeit.
    try:
        from core.mp4_keyframes import video_duration_from_container
        genau = video_duration_from_container(pfad)
    except Exception:
        genau = None
    if genau and genau > 0:
        if daten is None:
            daten = {"fps": None, "dauer": genau, "breite": 0, "hoehe": 0,
                     "quelle": "container"}
        else:
            daten = dict(daten)
            daten["dauer"] = genau
            daten["quelle"] = daten["quelle"] + "+container"

    if daten:
        _CACHE[k] = daten
    return daten


def drehung(pfad, ffprobe=None):
    """Drehung der Videospur in Grad, in der Zaehlweise von ffprobe.

    0, wenn keine hinterlegt ist oder sich die Angabe nicht eindeutig zuordnen
    laesst (90 oder 270 Grad) - diese Anwendung behandelt nur 0 und 180, alles
    andere ueberlaesst sie GES.
    """
    daten = eckdaten(pfad, ffprobe)
    if not daten:
        return 0
    if daten.get("drehung") is not None:
        return daten["drehung"]
    # Nicht zuordenbar (90 oder 270 Grad). Diese Anwendung behandelt ohnehin
    # nur 0 und 180; alles andere ueberlaesst sie GES, das die Kennzeichnung
    # selbst auswertet.
    daten["drehung"] = 0
    return 0


def dauer(pfad, ffprobe=None):
    """Laenge einer Videodatei in Sekunden, 0.0 wenn nicht lesbar."""
    daten = eckdaten(pfad, ffprobe)
    return float(daten["dauer"]) if daten else 0.0


def lesen(pfad, ffprobe=None):
    """Bildrate einer Videodatei als (zaehler, nenner), oder None.

    Geliefert wird der Bruch aus dem Container ("30000/1001"), nicht die
    gerundete Kommazahl.
    """
    daten = eckdaten(pfad, ffprobe)
    return daten["fps"] if daten else None


def liste_lesen(pfade, ffprobe=None):
    """Bildraten mehrerer Dateien: (raten_je_datei, alle_gleich)."""
    raten = [lesen(p, ffprobe) for p in pfade]
    bekannt = [r for r in raten if r]
    alle_gleich = all(gleich(r, bekannt[0]) for r in bekannt) if bekannt else True
    return raten, alle_gleich
