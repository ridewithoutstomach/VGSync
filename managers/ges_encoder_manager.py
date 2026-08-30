# -*- coding: utf-8 -*-
"""Zweiter Export-Weg: rendern mit GStreamer Editing Services statt ffmpeg.

Diese Datei ist eine ALTERNATIVE zu managers/encoder_manager.py, kein Ersatz.
Beide Wege lesen dieselbe JSON-Konfiguration und schreiben dieselbe Zieldatei,
damit sich die Ergebnisse direkt vergleichen lassen: Laenge, Bildanzahl,
Bildinhalt an gleichen Zeitpunkten, Dauer des Laufs.

    ffmpeg-Weg:  managers.encoder_manager.xfade_main(cfg_path)
    GES-Weg:     managers.ges_encoder_manager.ges_xfade_main(cfg_path)

WER RUFT AUF
------------
managers/encoder_manager.py, EncoderDialog.run_encoding() - das ist der
Export im Encode-Mode. Der Copy-Mode geht einen eigenen Weg ueber ffmpeg
(mainwindow.on_render_clicked) und beruehrt diese Datei nicht.

WARUM ER ANDERS RECHNET
-----------------------
Der ffmpeg-Weg arbeitet in Teilstuecken: erst alle Quellen vorschneiden, dann
in einem Durchlauf komplett neu kodieren (merged.mp4), dann an Keyframes
Teilstuecke herauskopieren, die Blenden einzeln neu kodieren und am Ende alles
mit "-c copy" zusammensetzen. Die Blendenbereiche gehen dabei zweimal durch
einen Encoder.

Der GES-Weg baut dieselbe Schnittfolge als Timeline und kodiert sie in einem
einzigen Durchlauf. Damit entfallen: merged.mp4 als Zwischendatei, das Suchen
und Erzwingen von Keyframes, das Ausrichten der Schnitte auf Keyframes, der
concat-Demuxer samt Laengenmessung - und die Blenden sind erste Generation.

Die Schnittsemantik ist absichtlich identisch:
  * [start, end, -2] -> Anfang wegschneiden
  * [start, end, -1] -> Ende wegschneiden
  * [start, end,  0] -> harte Kante
  * [start, end,  D] -> Blende ueber D Sekunden, MITTIG auf der Kante:
                        D/2 aus dem Material vor der Kante, D/2 aus dem
                        Material hinter der Kante. Die Gesamtlaenge aendert
                        sich dadurch nicht.

Ton wird wie beim ffmpeg-Weg nicht ausgegeben (dort "-an").
"""

import json
import math
import os
import time

from PySide6.QtCore import QSettings

# view360 faengt einen fehlenden GStreamer selbst ab und bleibt importierbar -
# wer den ffmpeg-Weg benutzt, merkt davon nichts.
from core import view360


class GesRenderError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# GStreamer wird bewusst erst beim Aufruf geladen. Wer den ffmpeg-Weg benutzt,
# soll ohne installiertes GStreamer weiterarbeiten koennen.
# ---------------------------------------------------------------------------

Gst = GES = GLib = GstPbutils = GstController = GstVideo = None
NS = 1_000_000_000


def _lade_gst():
    global Gst, GES, GLib, GstPbutils, GstController, GstVideo
    if Gst is not None:
        return
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GES", "1.0")
    gi.require_version("GstPbutils", "1.0")
    gi.require_version("GstController", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import (Gst as _Gst, GES as _GES, GLib as _GLib,
                               GstPbutils as _Pb, GstController as _Ctrl,
                               GstVideo as _Video)
    Gst, GES, GLib = _Gst, _GES, _GLib
    GstPbutils, GstController, GstVideo = _Pb, _Ctrl, _Video
    if not Gst.is_initialized():
        Gst.init(None)
    GES.init()


# ---------------------------------------------------------------------------
# Encoder-Zuordnung: ffmpeg-Name -> GStreamer-Element
# ---------------------------------------------------------------------------
# Die Namen links sind die, die in der JSON stehen ("encoder" bzw.
# "hardware_encode"). Rechts das GStreamer-Element und die Caps, die im
# Encoding-Profil verlangt werden.

_H264 = "video/x-h264"
_H265 = "video/x-h265"

_CPU_ENCODER = {
    "libx264": ("x264enc", _H264),
    "libx265": ("x265enc", _H265),
}

_HW_ENCODER = {
    "nvidia_h264": ("nvh264enc", _H264),
    "nvidia_hevc": ("nvh265enc", _H265),
    "amd_h264":    ("amfh264enc", _H264),
    "amd_hevc":    ("amfh265enc", _H265),
    "intel_h264":  ("qsvh264enc", _H264),
    "intel_hevc":  ("qsvh265enc", _H265),
    "vaapi_h264":  ("vah264enc", _H264),
    "vaapi_hevc":  ("vah265enc", _H265),
}

# x264/x265 kennen dieselben Namen wie auf der ffmpeg-Kommandozeile.
_SPEED_PRESET = ("ultrafast", "superfast", "veryfast", "faster", "fast",
                 "medium", "slow", "slower", "veryslow", "placebo")


def _element_da(name):
    try:
        return Gst.ElementFactory.make(name, None) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Zeitachse
# ---------------------------------------------------------------------------

def _keep_segmente(skip_list, gesamt):
    """Bereiche, die BLEIBEN, nachdem Anfangs- und End-Trim entfernt sind.

    Gleiche Regel wie compute_keep_segments() im ffmpeg-Weg: nur die Eintraege
    mit -2 (Anfang) und -1 (Ende) schneiden Material weg; alle anderen Schnitte
    werden spaeter innerhalb der Timeline behandelt.
    """
    trims = sorted((s, e) for s, e, modus in skip_list
                   if modus in (-2, -1) and e > s)
    keeps = []
    lauf = 0.0
    for s, e in trims:
        if s > lauf:
            keeps.append([lauf, s])
        lauf = max(lauf, e)
    if lauf < gesamt:
        keeps.append([lauf, gesamt])
    return keeps


class _Quellen:
    """Die Videoliste als eine durchgehende Rohzeitachse.

    Genau dieselbe Sicht, die auch die Vorschau und der ffmpeg-Weg benutzen:
    die Dateien liegen hintereinander, Zeiten in der Konfiguration beziehen
    sich auf diese gedachte Gesamtdatei.
    """

    def __init__(self, videos):
        self.assets = []
        self.grenzen = []      # (start_ns, ende_ns) je Datei
        lauf = 0
        for pfad in videos:
            uri = GLib.filename_to_uri(os.path.abspath(pfad), None)
            asset = GES.UriClipAsset.request_sync(uri)
            dauer = asset.get_duration()
            if not dauer or dauer <= 0:
                raise GesRenderError(f"Laenge nicht lesbar: {pfad}")
            self.assets.append(asset)
            self.grenzen.append((lauf, lauf + dauer))
            lauf += dauer
        self.gesamt_ns = lauf

    def masse(self):
        """Breite, Hoehe und Bildrate der ersten Datei."""
        info = self.assets[0].get_info()
        stroeme = info.get_video_streams()
        if not stroeme:
            raise GesRenderError("Die erste Datei enthaelt keine Videospur")
        s = stroeme[0]
        num = s.get_framerate_num() or 30
        den = s.get_framerate_denom() or 1
        return s.get_width(), s.get_height(), num, den

    def index_bei(self, roh_ns):
        """Platz in der Videoliste, zu dem diese Rohzeit gehoert.

        Eindeutig auch dann, wenn dieselbe Datei mehrfach in der Playlist
        steht - anders als die URI des Assets.
        """
        for index, (a, b) in enumerate(self.grenzen):
            if a <= roh_ns < b:
                return index
        return len(self.grenzen) - 1 if self.grenzen else -1

    def stuecke(self, von_ns, bis_ns):
        """Zerlegt einen Rohbereich in (asset, inpoint, dauer, rohstart)."""
        ergebnis = []
        for asset, (a, b) in zip(self.assets, self.grenzen):
            start = max(von_ns, a)
            ende = min(bis_ns, b)
            if ende - start <= 0:
                continue
            ergebnis.append((asset, start - a, ende - start, start))
        return ergebnis


# Die Mitglieder von GstVideo.VideoOrientationMethod heissen "IDENTITY", "180",
# "90L", "90R" - also teils keine gueltigen Python-Namen. Sie MUESSEN ueber
# getattr geholt werden. Ein geschriebenes "._180" wirft AttributeError; wird
# der geschluckt und dann IDENTITY zurueckgegeben, steht kopfueber
# aufgenommenes Material im fertigen Video auf dem Kopf. Genau so passiert am
# 29.08.2026 mit GoPro-Material (image-orientation=rotate-180).
_DREHUNG = {"rotate-0": "IDENTITY", "rotate-180": "180"}


def _orientierung(asset):
    """Drehung der Quelle, oder None wenn GES selbst entscheiden soll.

    GES stellt jeden Clip auf AUTO: das Drehelement liest die Kennzeichnung aus
    dem Datenstrom. Kommt sie nicht rechtzeitig an, bleibt der Clip ungedreht -
    deshalb wird sie vorgegeben, WENN sie sich sicher bestimmen laesst.

    Nur 0 und 180 Grad. Bei 90 und 270 vertauschen sich Breite und Hoehe, das
    braucht mehr als eine andere Zahl; dort bleibt es bei AUTO, indem None
    zurueckgegeben wird. Auch wenn gar keine Kennzeichnung da ist: lieber GES
    entscheiden lassen als etwas Falsches festschreiben.
    """
    try:
        for strom in asset.get_info().get_video_streams():
            tags = strom.get_tags()
            if tags is None:
                continue
            ok, wert = tags.get_string("image-orientation")
            if not ok:
                continue
            name = _DREHUNG.get(wert)
            if name is None:
                return None
            return getattr(GstVideo.VideoOrientationMethod, name)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def _alpha_rampe(element, von_ns, bis_ns, inpoint_ns, start_wert, ziel_wert):
    """Blendet die Deckkraft eines Clips linear auf.

    Die Stuetzstellen einer Steuerquelle werden in MEDIENZEIT ausgewertet, also
    ab dem inpoint des Clips - nicht ab seinem Platz auf der Timeline. Wird das
    verwechselt, liegen die Punkte ausserhalb des Clips und man sieht gar keine
    Blende.
    """
    quelle = GstController.InterpolationControlSource()
    quelle.props.mode = GstController.InterpolationMode.LINEAR
    element.set_control_source(quelle, "alpha", "direct")
    quelle.set(inpoint_ns + von_ns, start_wert)
    quelle.set(inpoint_ns + bis_ns, ziel_wert)


def _raster(sekunden, fps_n, fps_d):
    """Sekunden auf das Bildraster der ZIELrate legen, Ergebnis in Nanosekunden.

    Ohne das landen Clipgrenzen zwischen zwei Bildern, und der Encoder muss
    auf- oder abrunden. Beim ersten Lauf kamen so 1827 statt 1825 Bilder
    heraus - zwei zu viel, und damit waere die GPX-Kopplung verschoben. Alle
    Zeiten der Timeline gehen deshalb durch diese Funktion.
    """
    bilder = int(round(sekunden * fps_n / float(fps_d)))
    return bilder * fps_d * NS // fps_n


def _blicke_liste(quellen, view360_cfg):
    """
    Blickwinkel je Playlist-Eintrag, in der Reihenfolge der Videoliste.

    Leere Liste heisst: 360 ist aus, es wird nichts projiziert.

    NICHT ueber die URI des Assets zuordnen: steht dieselbe Datei zweimal in
    der Playlist, liefert GES beidemal DASSELBE Asset, und der zweite
    Blickwinkel wuerde den ersten verdraengen. Eindeutig ist der Platz auf der
    Rohzeitachse - siehe _blick_fuer().
    """
    if not view360_cfg or not view360_cfg.get("enabled"):
        return []
    ansichten = view360_cfg.get("views") or []
    return [view360.Blickwinkel.aus_dict(
                ansichten[i] if i < len(ansichten) else None)
            for i in range(len(quellen.assets))]


def _timeline_bauen(quellen, skip_list, overlay_list, breite, hoehe, fps_n, fps_d,
                    log, blicke=None):
    timeline = GES.Timeline.new_audio_video()
    blicke = blicke or []
    aspect = view360.ziel_aspect(breite, hoehe)

    def blick_fuer(rohstart):
        """Blickwinkel des Videos, aus dem dieses Stueck stammt."""
        if not blicke:
            return None
        index = quellen.index_bei(rohstart)
        return blicke[index] if 0 <= index < len(blicke) else None

    def ns(sekunden):
        return _raster(sekunden, fps_n, fps_d)

    # Zielformat einmal zentral: der Compositor rechnet dann in dieser Groesse
    # und encodebin bekommt bereits fertige Bilder. Das ersetzt ffmpegs
    # "scale=BREITE:-2" und "-r FPS".
    for track in timeline.get_tracks():
        if track.get_property("track-type") == GES.TrackType.VIDEO:
            track.set_restriction_caps(Gst.Caps.from_string(
                f"video/x-raw,width={breite},height={hoehe},"
                f"framerate={fps_n}/{fps_d}"))

    # Layer 0 liegt in GES OBEN. Das Grundmaterial kommt deshalb nach unten,
    # die einblendende Seite einer Ueberblendung nach oben.
    # Overlays bekommen eine eigene Ebene, sonst koennen sie zeitlich mit einer
    # Blendenhaelfte kollidieren - zwei Clips duerfen auf derselben Ebene nicht
    # ueberlappen.
    ovl_ebene = timeline.append_layer()  # Prioritaet 0 - ganz oben
    oben = timeline.append_layer()       # Prioritaet 1 - Blendenhaelften
    unten = timeline.append_layer()      # Prioritaet 2 - Grundmaterial
    for ebene in (ovl_ebene, oben, unten):
        ebene.set_auto_transition(False)

    def clip_setzen(layer, asset, start, inpoint, dauer, rohstart=0):
        clip = layer.add_asset(asset, start, inpoint, dauer, GES.TrackType.UNKNOWN)
        if clip is None:
            raise GesRenderError("Clip konnte nicht eingefuegt werden")
        richtung = _orientierung(asset)
        if richtung is not None:
            for element in clip.find_track_elements(None, GES.TrackType.VIDEO,
                                                    GES.VideoSource):
                element.set_child_property("video-direction", richtung)
        # 360: derselbe Shader wie in der Vorschau (core/view360.py). Jedes
        # Stueck geht hier durch, auch die Haelften einer Blende - beide werden
        # einzeln projiziert und danach ueber die alpha-Rampe gemischt, was
        # richtig ist: gemischt wird im fertigen Bild, nicht auf der Kugel.
        blick = blick_fuer(rohstart)
        if blick is not None:
            if view360.effekt_anhaengen(clip, blick, aspect) is None:
                raise GesRenderError(
                    "360-Effekt liess sich nicht anhaengen: "
                    + (view360.fehlgrund() or "unbekannter Grund"))
            view360.rahmen_setzen(clip, breite, hoehe)
        return clip

    keeps = _keep_segmente(skip_list, quellen.gesamt_ns / NS)

    # Schnitte, die INNERHALB des behaltenen Materials liegen: sie erzeugen
    # keine neue Datei, sondern eine Kante in der Timeline.
    kanten = []
    for s, e, v in skip_list:
        if v in (-2, -1):
            continue
        kanten.append((float(s), float(e), max(0.0, float(v))))
    kanten.sort()

    # Rohbereiche, die tatsaechlich im Ergebnis landen, samt ihrer Kante.
    # Aufbau je Stueck: (roh_von, roh_bis, blende_davor, blende_danach)
    stuecke = []
    for k_von, k_bis in keeps:
        grenzen = [k_von]
        for s, e, _v in kanten:
            if k_von <= s and e <= k_bis:
                grenzen += [s, e]
        grenzen.append(k_bis)
        for i in range(0, len(grenzen) - 1, 2):
            von, bis = grenzen[i], grenzen[i + 1]
            if bis - von <= 0:
                continue
            blende_davor = 0.0
            blende_danach = 0.0
            for s, e, v in kanten:
                if v <= 0:
                    continue
                if abs(e - von) < 1e-6:
                    blende_davor = v
                if abs(s - bis) < 1e-6:
                    blende_danach = v
            stuecke.append([von, bis, blende_davor, blende_danach])

    # ---- auf die Timeline legen -------------------------------------------
    zeit_ns = 0
    blenden = 0
    abbildung = []   # (roh_von, roh_bis, ausgabe_start_ns) je Teilstueck
    for index, (von, bis, bl_davor, bl_danach) in enumerate(stuecke):
        halb_davor = bl_davor / 2.0
        halb_danach = bl_danach / 2.0

        # Ein Stueck muss lang genug fuer seine beiden halben Blenden sein.
        if halb_davor + halb_danach >= (bis - von):
            halb_davor = halb_danach = 0.0
            bl_davor = bl_danach = 0.0

        # Das Stueck reicht eine halbe Blende ueber seine hintere Kante hinaus
        # und beginnt eine halbe Blende vor seiner vorderen Kante - genau das
        # Material, das ohne Blende weggeschnitten worden waere.
        roh_von = von - halb_davor
        roh_bis = bis + halb_danach

        # GES zaehlt die Endkante mit: eine Timeline ueber 60 Bilder liefert 61
        # Bilder, das letzte liegt genau auf der Grenze. ffmpeg laesst es weg
        # ("-t" ist ausschliesslich). Gemessen an einem Einzelclip: 61 statt 60,
        # und das 61. Bild ist echtes Material, keine Wiederholung. Damit beide
        # Wege dieselbe Bildanzahl liefern, endet das letzte Stueck ein Bild
        # frueher.
        if index == len(stuecke) - 1:
            ein_bild = fps_d / float(fps_n)
            if roh_bis - roh_von > ein_bild:
                roh_bis -= ein_bild

        # Anfang dieses Stuecks auf der Rohzeitachse und in der Ausgabe. Beides
        # wird gebraucht, um die Overlays umzurechnen: deren Zeiten stehen in
        # der Konfiguration in ROHZEIT, auf der Timeline zaehlt aber die
        # Ausgabezeit. Ohne die Umrechnung landet ein Overlay bei Rohsekunde
        # 2108 auch auf Timeline-Sekunde 2108 - die Ausgabe wird dadurch
        # zigfach zu lang und hinten schwarz.
        roh_anfang = roh_von
        out_anfang = zeit_ns

        # Die einblendende Haelfte liegt oben und ueberlappt den Vorgaenger.
        if bl_davor > 0 and index > 0:
            blende_ns = ns(bl_davor)
            start_ns = zeit_ns - blende_ns
            out_anfang = start_ns
            for asset, inpoint, dauer, rohstart in quellen.stuecke(
                    ns(roh_von), ns(roh_von + bl_davor)):
                clip = clip_setzen(oben, asset,
                                   start_ns + (rohstart - ns(roh_von)),
                                   inpoint, dauer, rohstart)
                for element in clip.find_track_elements(None, GES.TrackType.VIDEO,
                                                        GES.VideoSource):
                    _alpha_rampe(element, 0, blende_ns, inpoint, 0.0, 1.0)
            blenden += 1
            roh_von = roh_von + bl_davor

        # Der Rest des Stuecks liegt unten und schliesst luecklos an.
        for asset, inpoint, dauer, rohstart in quellen.stuecke(
                ns(roh_von), ns(roh_bis)):
            clip_setzen(unten, asset, zeit_ns + (rohstart - ns(roh_von)),
                        inpoint, dauer, rohstart)

        abbildung.append((roh_anfang, roh_bis, out_anfang))
        zeit_ns += ns(roh_bis) - ns(roh_von)

    _overlays_setzen(ovl_ebene, overlay_list, breite, hoehe, abbildung,
                     fps_n, fps_d, log)

    timeline.commit_sync()
    gesamt = timeline.get_duration()
    log(f"[GES] Timeline: {len(stuecke)} Stueck(e), {blenden} Blende(n), "
        f"{gesamt / NS:.6f}s bei {breite}x{hoehe} @ {fps_n}/{fps_d}")
    return timeline, gesamt


def _zahl(wert, gross, klein):
    """Wertet eine Overlay-Koordinate aus.

    Zahlen werden direkt uebernommen. Ausdruecke wie "(W-w)/2" oder "H-h-10"
    kommen aus der ffmpeg-Welt und werden mit denselben Namen ausgewertet.
    """
    if isinstance(wert, (int, float)):
        return int(round(wert))
    text = str(wert).strip()
    if not text:
        return 0
    umgebung = {"W": gross[0], "H": gross[1], "w": klein[0], "h": klein[1],
                "main_w": gross[0], "main_h": gross[1],
                "overlay_w": klein[0], "overlay_h": klein[1]}
    try:
        return int(round(eval(text, {"__builtins__": {}}, umgebung)))
    except Exception:
        return 0


def _auf_ausgabe(rohzeit, abbildung):
    """Rohzeit -> Zeit in der fertigen Ausgabe (Nanosekunden), oder None.

    None heisst: dieser Zeitpunkt wurde weggeschnitten und kommt im Ergebnis
    gar nicht vor.
    """
    for roh_von, roh_bis, out_ns in abbildung:
        if roh_von <= rohzeit <= roh_bis:
            return out_ns + int(round((rohzeit - roh_von) * NS))
    return None


def _overlays_setzen(layer, overlay_list, breite, hoehe, abbildung,
                     fps_n, fps_d, log):
    for ovl in overlay_list or []:
        bild = ovl.get("image") or ""
        if not bild or not os.path.isfile(bild):
            log(f"[GES] Overlay uebersprungen, Datei fehlt: {bild}")
            continue
        roh_start = float(ovl.get("start", 0.0))
        roh_ende = float(ovl.get("end", 0.0))
        if roh_ende <= roh_start:
            continue

        # Die Zeiten in der Konfiguration sind ROHZEITEN, die Timeline zaehlt
        # Ausgabezeit. Faellt ein Overlay ganz in einen Schnitt, entfaellt es;
        # ragt es hinein, wird es auf den sichtbaren Teil gestutzt.
        start_ns = _auf_ausgabe(roh_start, abbildung)
        ende_ns = _auf_ausgabe(roh_ende, abbildung)
        if start_ns is None and ende_ns is None:
            log(f"[GES] Overlay {os.path.basename(bild)} liegt komplett in einem "
                f"Schnitt ({roh_start:.2f}s - {roh_ende:.2f}s) und entfaellt")
            continue
        if start_ns is None:
            for roh_von, _rb, out_ns in abbildung:
                if roh_start <= roh_von:
                    start_ns = out_ns
                    break
        if ende_ns is None:
            for roh_von, roh_bis, out_ns in abbildung:
                if roh_von <= roh_ende:
                    ende_ns = out_ns + int(round((roh_bis - roh_von) * NS))
        if start_ns is None or ende_ns is None or ende_ns <= start_ns:
            log(f"[GES] Overlay {os.path.basename(bild)} liess sich nicht "
                f"einordnen und entfaellt")
            continue
        start, ende = start_ns / NS, ende_ns / NS

        try:
            uri = GLib.filename_to_uri(os.path.abspath(bild), None)
            asset = GES.UriClipAsset.request_sync(uri)
        except Exception as exc:
            log(f"[GES] Overlay nicht ladbar ({bild}): {exc}")
            continue

        dauer_ns = ende_ns - start_ns
        clip = layer.add_asset(asset, start_ns, 0, dauer_ns,
                               GES.TrackType.VIDEO)
        if clip is None:
            log(f"[GES] Overlay konnte nicht eingefuegt werden: {bild}")
            continue

        # Groesse des Bildes ermitteln, damit Ausdruecke wie "(W-w)/2" stimmen.
        try:
            strom = asset.get_info().get_video_streams()[0]
            bw, bh = strom.get_width(), strom.get_height()
        except Exception:
            bw = bh = 0
        faktor = float(ovl.get("scale", 1.0) or 1.0)
        zw = max(1, int(round(bw * faktor))) if bw else 0
        zh = max(1, int(round(bh * faktor))) if bh else 0

        ein = float(ovl.get("fade_in", 0) or 0)
        aus = float(ovl.get("fade_out", 0) or 0)

        for element in clip.find_track_elements(None, GES.TrackType.VIDEO,
                                                GES.VideoSource):
            if zw and zh:
                element.set_child_property("width", zw)
                element.set_child_property("height", zh)
            element.set_child_property("posx", _zahl(ovl.get("x", 0),
                                                     (breite, hoehe), (zw, zh)))
            element.set_child_property("posy", _zahl(ovl.get("y", 0),
                                                     (breite, hoehe), (zw, zh)))
            if ein > 0 or aus > 0:
                quelle = GstController.InterpolationControlSource()
                quelle.props.mode = GstController.InterpolationMode.LINEAR
                element.set_control_source(quelle, "alpha", "direct")
                quelle.set(0, 0.0 if ein > 0 else 1.0)
                if ein > 0:
                    quelle.set(int(round(ein * NS)), 1.0)
                if aus > 0:
                    quelle.set(max(0, dauer_ns - int(round(aus * NS))), 1.0)
                    quelle.set(dauer_ns, 0.0)
                else:
                    quelle.set(dauer_ns, 1.0)
        log(f"[GES] Overlay {os.path.basename(bild)}: roh "
            f"{roh_start:.2f}s - {roh_ende:.2f}s  ->  Ausgabe "
            f"{start:.2f}s - {ende:.2f}s")


# ---------------------------------------------------------------------------
# Encoding-Profil
# ---------------------------------------------------------------------------

def _profil(encoder, hw_encode, crf, preset, bitrate_mbps, log):
    hw = (hw_encode or "none").lower()
    if hw and hw != "none":
        eintrag = _HW_ENCODER.get(hw)
        if eintrag is None:
            log(f"[GES] unbekanntes hardware_encode={hw_encode}, nutze CPU")
        elif not _element_da(eintrag[0]):
            log(f"[GES] {eintrag[0]} nicht verfuegbar, nutze CPU")
        else:
            element, caps = eintrag
            return _profil_bauen(element, caps,
                                 _gpu_eigenschaften(element, crf, preset,
                                                    bitrate_mbps),
                                 log)

    element, caps = _CPU_ENCODER.get((encoder or "libx265").lower(),
                                     ("x265enc", _H265))
    if not _element_da(element):
        raise GesRenderError(
            f"Encoder {element} fehlt. Unter Linux: "
            f"sudo apt install gstreamer1.0-plugins-ugly")
    return _profil_bauen(element, caps,
                         _cpu_eigenschaften(element, crf, preset), log)


# Ein Deckel, der praktisch nie greift. x264enc benutzt seine
# "bitrate"-Eigenschaft auch im Qualitaetsmodus als harte Obergrenze, und die
# Vorgabe von 2048 kbit/s schneidet jede bessere Einstellung ab. Der
# ffmpeg-Weg setzt fuer die CPU gar keine Obergrenze (die Bitrate aus den
# Einstellungen gilt dort nur fuer die GPU), deshalb wird sie hier aus dem Weg
# geraeumt statt uebernommen.
_X264_KEIN_DECKEL = 200000      # kbit/s


def _cpu_eigenschaften(element, crf, preset):
    """CRF und Preset wie auf der ffmpeg-Kommandozeile.

    Die beiden Encoder wollen das auf verschiedenen Wegen hoeren - gemessen an
    4 s echtem Material in 1280x720:

        x265enc:  "option-string=crf=N" wirkt (crf 18 gegen 35 ergab
                  11,54 gegen 0,59 Mb/s).

        x264enc:  "option-string" wird von den Rate-Einstellungen wieder
                  ueberschrieben und bleibt wirkungslos (crf 23 ergab
                  1,64 Mb/s, also die Vorgabe). Richtig ist "pass=qual" mit
                  "quantizer", UND die Bitratengrenze muss aus dem Weg -
                  sonst deckelt sie bei 2048 kbit/s:

                      crf   x264enc     ffmpeg libx264
                       15   36,63 Mb/s    32,70 Mb/s
                       23   13,91 Mb/s    11,32 Mb/s
                       30    4,23 Mb/s     3,44 Mb/s

    Ohne diese Unterscheidung liefen alle CPU-Exporte mit Container x264 in
    2048 kbit/s statt in der eingestellten Qualitaet.
    """
    werte = {}
    if element == "x264enc":
        if crf is not None:
            werte["pass"] = 5                    # Constant Quality = CRF
            werte["quantizer"] = int(crf)
            werte["bitrate"] = _X264_KEIN_DECKEL
    elif crf is not None:
        werte["option-string"] = f"crf={int(crf)}"
    if preset and str(preset).lower() in _SPEED_PRESET:
        werte["speed-preset"] = str(preset).lower()
    return werte


def _gpu_eigenschaften(element, crf, preset, bitrate_mbps):
    """Dieselbe Rate-Steuerung wie im ffmpeg-Weg.

    ffmpeg fuer NVENC (get_gpu_encode_params):
        -rc vbr_hq  -cq N  -b:v XM  -maxrate XM  -bufsize 2XM
    Also ein Qualitaetsziel UND ein Bitratendeckel. Hier entsprechend:
        rc-mode=Variable Bit Rate, const-quality=N ("const-quality" ist
        NVENCs targetQuality, genau ffmpegs -cq), bitrate/max-bitrate=X,
        vbv-buffer-size=2X.

    NICHT "Constant Quantization" mit qp-const nehmen: dabei ignoriert NVENC
    jede Bitratengrenze. Am 29.08.2026 so gemessen - aus 1,15 GB bei 35 Mb/s
    wurden 3,3 GB bei 107 Mb/s, bei gleicher Einstellung.

    Die Presetnamen der Hersteller-Encoder unterscheiden sich von denen der
    CPU-Encoder, deshalb wird das Preset hier nicht durchgereicht.
    """
    werte = {}
    kbit = int(bitrate_mbps) * 1000 if bitrate_mbps else 0
    qualitaet = None if crf is None else float(max(0, min(51, int(crf))))

    if element.startswith("nvh26"):
        if qualitaet is not None:
            werte["rc-mode"] = 3            # Variable Bit Rate = vbr_hq
            werte["const-quality"] = qualitaet
        if kbit:
            werte["bitrate"] = kbit
            werte["max-bitrate"] = kbit
            werte["vbv-buffer-size"] = kbit * 2
        return werte

    # Intel, AMD und VA-API sind hier nicht geprueft - es steht keine passende
    # Hardware zur Verfuegung. Deshalb nur der Bitratendeckel, den alle
    # kennen; die Feinsteuerung bleibt beim Element. Wer solche Hardware hat,
    # sollte das Ergebnis gegen den ffmpeg-Weg messen.
    if kbit:
        werte["bitrate"] = kbit
        werte["max-bitrate"] = kbit
    return werte


def _profil_bauen(element, video_caps, eigenschaften, log):
    behaelter = GstPbutils.EncodingContainerProfile.new(
        "KVRouite", "MP4 ohne Ton",
        Gst.Caps.from_string("video/quicktime,variant=iso"), None)
    video = GstPbutils.EncodingVideoProfile.new(
        Gst.Caps.from_string(video_caps), None, None, 0)
    video.set_preset_name(element)

    if eigenschaften:
        # Die Werte laufen erst durch ein Probe-Element. Grund: "speed-preset"
        # ist eine Aufzaehlung, und ein Text wird dafuer abgelehnt
        # ("unable to set property 'speed-preset' ... from value of type
        # 'gchararray'"). Setzt man ihn am Element, uebernimmt PyGObject die
        # Umwandlung, und der zurueckgelesene Wert hat den richtigen Typ.
        # Ausserdem faellt so gleich auf, wenn eine Eigenschaft gar nicht
        # existiert - dann steht es im Log statt spaeter still danebenzugehen.
        probe = Gst.ElementFactory.make(element, None)
        struktur = Gst.Structure.new_empty("element-properties")
        for name, wert in eigenschaften.items():
            try:
                probe.set_property(name, wert)
                struktur.set_value(name, probe.get_property(name))
            except Exception as exc:
                log(f"[GES] {element}: {name}={wert} nicht gesetzt ({exc})")
        video.set_element_properties(struktur)
        log(f"[GES] Encoder: {element} ({struktur.to_string()})")
    else:
        log(f"[GES] Encoder: {element}")

    behaelter.add_profile(video)
    return behaelter


# ---------------------------------------------------------------------------
# Rendern
# ---------------------------------------------------------------------------

def _rendern(timeline, profil, ziel, gesamt_ns, log):
    pipeline = GES.Pipeline()
    pipeline.set_timeline(timeline)
    uri = GLib.filename_to_uri(os.path.abspath(ziel), None)
    if not pipeline.set_render_settings(uri, profil):
        raise GesRenderError("Render-Einstellungen wurden abgelehnt")
    if not pipeline.set_mode(GES.PipelineFlags.RENDER):
        raise GesRenderError("Render-Modus liess sich nicht setzen")

    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        raise GesRenderError("Pipeline startete nicht")

    bus = pipeline.get_bus()
    begonnen = time.time()
    zuletzt = -1
    fehler = None
    try:
        while True:
            msg = bus.timed_pop_filtered(
                200 * Gst.MSECOND,
                Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg is not None:
                if msg.type == Gst.MessageType.ERROR:
                    err, dbg = msg.parse_error()
                    fehler = f"{err.message} ({dbg})"
                break

            ok, pos = pipeline.query_position(Gst.Format.TIME)
            if ok and gesamt_ns > 0:
                prozent = min(100, int(pos * 100 / gesamt_ns))
                if prozent != zuletzt:
                    zuletzt = prozent
                    vergangen = time.time() - begonnen
                    rest = (vergangen * (100 - prozent) / prozent) if prozent else 0
                    log(f"[GES] {prozent:3d}%  {pos / NS:8.2f}s / "
                        f"{gesamt_ns / NS:.2f}s   noch ca. {rest:5.0f}s")
    finally:
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(5 * Gst.SECOND)

    if fehler:
        raise GesRenderError(fehler)
    log(f"[GES] Fertig in {time.time() - begonnen:.1f}s")


# ---------------------------------------------------------------------------
# Einstieg - gleiche Signatur wie xfade_main()
# ---------------------------------------------------------------------------

def ges_xfade_main(cfg_path):
    _lade_gst()

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    videos = cfg["videos"]
    skip_list = cfg.get("skip_instructions", [])
    overlay_list = cfg.get("overlay_instructions", [])
    final_out = cfg["final_output"]
    encoder = cfg.get("encoder", "libx265")
    hw_encode = cfg.get("hardware_encode", "none")
    crf = cfg.get("crf", 23)
    fps = cfg.get("fps", 30)
    breite = cfg.get("width", None)
    preset = cfg.get("preset", None)
    view360_cfg = cfg.get("view360") or {}
    bitrate_mbps = QSettings("KVRouite", "KVRouite").value(
        "encoder/bitrate_mbps", 20, type=int)

    log = print
    log("[GES] Render-Engine: GStreamer Editing Services (zweiter Weg)")
    log(f"[GES] Ziel: {final_out}")

    quellen = _Quellen(videos)
    q_breite, q_hoehe, q_num, q_den = quellen.masse()
    log(f"[GES] Quelle: {len(videos)} Datei(en), "
        f"{quellen.gesamt_ns / NS:.6f}s, {q_breite}x{q_hoehe} @ "
        f"{q_num}/{q_den}")

    # Zielgroesse wie ffmpegs "scale=BREITE:-2": Seitenverhaeltnis halten,
    # Hoehe auf eine gerade Zahl bringen.
    #
    # Bei 360 gilt das NICHT: das 2:1-Format der Quelle ist dort die Kugel und
    # kein Bildformat. Herauskommen soll ein normales 16:9-Video mit dem
    # eingestellten Blickwinkel - ohne diese Ausnahme rendert der Export
    # weiter das verzerrte Equirect-Bild.
    ist_360 = bool(view360_cfg and view360_cfg.get("enabled"))
    if breite:
        breite = int(breite)
        if ist_360:
            hoehe = view360.ziel_hoehe(breite)
        else:
            hoehe = int(round(q_hoehe * breite / float(q_breite)))
            if hoehe % 2:
                hoehe += 1
    elif ist_360:
        breite, hoehe = q_breite, view360.ziel_hoehe(q_breite)
    else:
        breite, hoehe = q_breite, q_hoehe

    # Die Rate kommt als BRUCH herein ("30000/1001") und wird auch so
    # weiterverwendet. Ein gerundetes 29.97 waere nach vier Minuten schon ein
    # Bild daneben. Fehlt die Angabe, laeuft die Ausgabe mit der Rate der
    # Quelle - dann ist jedes Ausgabebild genau ein Quellbild.
    if fps:
        from core.framerate import parsen
        fps_n, fps_d = parsen(fps, (q_num, q_den))
    else:
        fps_n, fps_d = q_num, q_den

    for eintrag in skip_list:
        s, e, v = float(eintrag[0]), float(eintrag[1]), float(eintrag[2])
        if v == -2:
            was = "trimmed away (video start)"
        elif v == -1:
            was = "trimmed away (video end)"
        elif v <= 0:
            was = "hard cut (no crossfade)"
        else:
            was = f"crossfade {v:.1f}s (centred on the cut)"
        log(f"[GES] Cut {s:.2f}s - {e:.2f}s: {was}")

    blicke = _blicke_liste(quellen, view360_cfg)
    if blicke:
        grund = view360.fehlgrund()
        if grund:
            raise GesRenderError(f"360 ist eingeschaltet, geht aber nicht: {grund}")
        log(f"[GES] 360: {len(blicke)} Quelle(n) werden projiziert, "
            f"Ausgabe {breite}x{hoehe}")

    timeline, gesamt_ns = _timeline_bauen(quellen, skip_list, overlay_list,
                                          breite, hoehe, fps_n, fps_d, log,
                                          blicke)
    profil = _profil(encoder, hw_encode, crf, preset, bitrate_mbps, log)

    ordner = os.path.dirname(os.path.abspath(final_out))
    if ordner and not os.path.isdir(ordner):
        os.makedirs(ordner, exist_ok=True)

    _rendern(timeline, profil, final_out, gesamt_ns, log)

    log(f"\n== DONE == Final video: {final_out}")
    return final_out
