#!/usr/bin/env python3
"""Prueft, ob ein Export zeitlich auf dem Quellmaterial liegt.

    python3 check_alignment.py --projekt mein.KVRouiteproj --video export.mp4

Die Frage, die das Werkzeug beantwortet, ist nicht "unterscheiden sich zwei
Exporte", sondern "welcher trifft das Original". Als Referenz dient das
Quellmaterial selbst, nicht der jeweils andere Export.

SO WIRD GERECHNET
-----------------
Aus der Projektdatei stehen fest: die Videoliste, die Laengen und die Schnitte.
Damit ist zu jedem Zeitpunkt der Ausgabe eindeutig bestimmt, welches Bild
welcher Quelldatei dort stehen MUSS - die Schnitte entfernen Material, alles
andere rutscht auf. Eine mittig auf der Kante liegende Blende aendert daran
nichts, weil sie die Laenge nicht veraendert.

Das Werkzeug holt ein Bild aus der Ausgabe, holt aus der Quelle die Bilder
ringsum und sucht das passende. Verglichen werden dabei die ECHTEN
Zeitstempel beider Dateien (ffmpeg mit -copyts und showinfo), nicht die
angeforderten Suchzeiten - sonst misst man das Rundungsverhalten von "-ss"
statt des Exports. Genau das ist mir am 29.08.2026 passiert und hat einen
Versatz von +1 vorgetaeuscht, den es nicht gab.

Versatz  0 = der Export trifft das Quellmaterial.
Versatz -1 = der Export zeigt dort ein Bild zu frueh.

WICHTIG BEI AELTEREN EXPORTEN
-----------------------------
Gerechnet wird mit der MITTIGEN Blende. Exporte von vor dieser Umstellung
legten die Blende komplett hinter die Kante; ein Versatz dort zeigt das alte
Modell an und nicht zwingend einen Fehler.

Braucht ffmpeg und ffprobe im PATH. Veraendert nichts.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BREITE, HOEHE = 320, 180


def _ffprobe_dauer(pfad):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", pfad]
    return float(subprocess.run(cmd, capture_output=True, text=True,
                                check=True).stdout.strip())


def _ffprobe_video(pfad):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=r_frame_rate,width,height", "-show_entries",
           "format=duration", "-of", "json", pfad]
    d = json.loads(subprocess.run(cmd, capture_output=True, text=True,
                                  check=True).stdout)
    st = (d.get("streams") or [{}])[0]
    num, den = (st.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    return {"fps": float(num) / float(den or 1),
            "breite": int(st.get("width", 0) or 0),
            "hoehe": int(st.get("height", 0) or 0),
            "dauer": float((d.get("format") or {}).get("duration", 0) or 0)}


def _bilder(pfad, start, anzahl, ordner, name):
    """Bilder ab `start` als Liste von (zeitstempel, graustufen-rohdaten).

    -copyts haelt die Original-Zeitstempel fest; ohne das setzt ffmpeg sie
    beim Suchen auf 0 zurueck, und der Vergleich misst nichts mehr.
    showinfo schreibt zu jedem Bild seinen Zeitstempel nach stderr, in
    derselben Reihenfolge, in der die Rohdaten geschrieben werden.
    """
    ziel = os.path.join(ordner, name)
    cmd = ["ffmpeg", "-hide_banner", "-y", "-copyts",
           "-ss", f"{max(0.0, start):.6f}", "-i", pfad,
           "-frames:v", str(anzahl),
           "-vf", f"scale={BREITE}:{HOEHE},format=gray,showinfo",
           "-f", "rawvideo", "-pix_fmt", "gray", ziel]
    r = subprocess.run(cmd, capture_output=True, text=True)
    zeiten = [float(x) for x in re.findall(r"pts_time:\s*([0-9.]+)", r.stderr)]
    with open(ziel, "rb") as f:
        roh = f.read()
    n = BREITE * HOEHE
    bilder = [roh[i * n:(i + 1) * n] for i in range(len(roh) // n)]
    return list(zip(zeiten, bilder))


def _sad(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _keeps(dauern, cuts):
    """Behaltene Rohbereiche, in der Reihenfolge der Ausgabe."""
    gesamt = sum(dauern)
    schnitte = sorted((float(s), float(e)) for s, e in cuts
                      if float(e) > float(s))
    keeps = []
    lauf = 0.0
    for s, e in schnitte:
        if s > lauf:
            keeps.append((lauf, min(s, gesamt)))
        lauf = max(lauf, e)
    if lauf < gesamt:
        keeps.append((lauf, gesamt))
    return [(a, b) for a, b in keeps if b - a > 0.001]


def _quelle_fuer(rohzeit, videos, dauern):
    lauf = 0.0
    for pfad, d in zip(videos, dauern):
        if rohzeit < lauf + d - 1e-6:
            return pfad, rohzeit - lauf
        lauf += d
    return videos[-1], dauern[-1] - 0.001


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projekt", required=True, help="*.KVRouiteproj")
    ap.add_argument("--video", required=True, help="der zu pruefende Export")
    ap.add_argument("--rand", type=float, default=3.0,
                    help="Abstand zu jeder Schnittkante in Sekunden (Vorgabe 3)")
    ap.add_argument("--pro-stueck", type=int, default=2,
                    help="Messpunkte je Teilstueck (Vorgabe 2)")
    ap.add_argument("--suchweite", type=int, default=4,
                    help="wie viele Bilder in jede Richtung gesucht wird")
    args = ap.parse_args()

    for p in (args.projekt, args.video):
        if not os.path.isfile(p):
            print(f"Nicht gefunden: {p}")
            return 2

    with open(args.projekt, "r", encoding="utf-8") as f:
        proj = json.load(f)
    videos = proj.get("playlist") or []
    dauern = proj.get("video_durations") or []
    cuts = proj.get("cut_intervals") or []
    if not videos:
        print("Die Projektdatei enthaelt keine Videoliste.")
        return 2
    if len(dauern) != len(videos):
        dauern = [_ffprobe_dauer(v) for v in videos]

    fehlend = [v for v in videos if not os.path.isfile(v)]
    if fehlend:
        print("Quelldateien nicht gefunden:")
        for v in fehlend:
            print("  " + v)
        return 2

    info = _ffprobe_video(args.video)
    fps = info["fps"] or 30.0
    keeps = _keeps(dauern, cuts)
    soll = sum(b - a for a, b in keeps)

    print(f"Projekt   : {os.path.basename(args.projekt)}")
    print(f"Quellen   : {len(videos)} Datei(en), {sum(dauern):.6f}s roh")
    print(f"Schnitte  : {len(cuts)}  ->  {len(keeps)} Teilstueck(e)")
    print(f"Export    : {os.path.basename(args.video)}  "
          f"{info['breite']}x{info['hoehe']} @ {fps:g} fps, "
          f"{info['dauer']:.6f}s")
    print(f"Soll-Laenge nach den Schnitten: {soll:.6f}s "
          f"({info['dauer'] - soll:+.6f}s im Export)")
    print()

    punkte = []
    ausgabe_pos = 0.0
    for i, (a, b) in enumerate(keeps):
        laenge = b - a
        nutzbar = laenge - 2 * args.rand
        if nutzbar <= 0.5:
            ausgabe_pos += laenge
            continue
        for k in range(args.pro_stueck):
            anteil = (k + 1) / (args.pro_stueck + 1)
            t_out = ausgabe_pos + args.rand + nutzbar * anteil
            if t_out > info["dauer"] - 0.5:
                continue
            punkte.append((i + 1, t_out, a + (t_out - ausgabe_pos)))
        ausgabe_pos += laenge

    if not punkte:
        print("Keine brauchbaren Messpunkte - die Teilstuecke sind zu kurz.\n"
              "Mit --rand einen kleineren Abstand versuchen.")
        return 1

    quell_raten = {v: _ffprobe_video(v)["fps"] for v in videos}
    if any(abs(r - fps) > 0.01 for r in quell_raten.values()):
        print("Hinweis: Quelle und Ausgabe haben verschiedene Bildraten "
              f"({', '.join(f'{r:.3f}' for r in quell_raten.values())} gegen "
              f"{fps:.3f}).")
        print("  Es gibt dann keine 1:1-Zuordnung der Bilder. Gemessen wird")
        print("  der Abstand in Millisekunden; alles unter einer halben")
        print("  Quellbilddauer gilt als 0.")
        print()

    def _quell_fps(pfad):
        return quell_raten.get(pfad, fps) or fps

    print(f"{'Stueck':>6} {'Ausgabe':>10} {'Quelle soll':>12} "
          f"{'Quelle ist':>11}  {'Datei':<20} {'Versatz':>8} {'ms':>8} "
          f"{'Guete':>6}")
    ordner = tempfile.mkdtemp(prefix="kvr_align_")
    ergebnisse = []
    try:
        for nr, t_out, t_raw in punkte:
            quelle, t_src = _quelle_fuer(t_raw, videos, dauern)
            ziel = _bilder(args.video, t_out, 1, ordner, "out.gray")
            if not ziel:
                continue
            # Zeitstempel des tatsaechlich geholten Ausgabebildes. Die Sollzeit
            # in der Quelle verschiebt sich um genau dieselbe Differenz.
            ist_out, bild = ziel[0]
            soll_src = t_src + (ist_out - t_out)

            w = args.suchweite
            kandidaten = _bilder(quelle, soll_src - (w + 0.5) / fps,
                                 2 * w + 2, ordner, "src.gray")
            if len(kandidaten) < 2:
                continue
            bewertet = sorted((_sad(bild, k), zeit) for zeit, k in kandidaten)
            beste, ist_src = bewertet[0]
            zweit = bewertet[1][0] if len(bewertet) > 1 else beste
            guete = (zweit - beste) / max(beste, 0.001)
            # In QUELLbildern rechnen, nicht in Ausgabebildern. Laufen die
            # Raten auseinander (29,97 gegen 30), gibt es keine 1:1-Zuordnung;
            # das naechstgelegene Quellbild liegt dann bis zu einer halben
            # Quellbilddauer daneben. In Ausgabebildern gerechnet sieht das
            # faelschlich nach einem ganzen Bild Versatz aus.
            src_fps = _quell_fps(quelle)
            abweichung = ist_src - soll_src
            versatz = int(round(abweichung * src_fps))
            if abs(abweichung * src_fps) < 0.5:
                versatz = 0
            ergebnisse.append((nr, versatz))
            marke = "" if versatz == 0 else "  <<<"
            print(f"{nr:>6} {ist_out:>10.3f} {soll_src:>12.3f} "
                  f"{ist_src:>11.3f}  {os.path.basename(quelle)[:20]:<20} "
                  f"{versatz:>+8d} {abweichung * 1000:>+8.1f} {guete:>6.2f}{marke}")
    finally:
        shutil.rmtree(ordner, ignore_errors=True)

    print()
    if not ergebnisse:
        print("Es liessen sich keine Bilder vergleichen.")
        return 1

    versaetze = [v for _nr, v in ergebnisse]
    if set(versaetze) == {0}:
        print("Ergebnis: alle Messpunkte liegen exakt auf dem Quellmaterial.")
        return 0

    print("Ergebnis: der Export weicht vom Quellmaterial ab.")
    print("  Versaetze: "
          f"{', '.join(f'{v:+d}' for v in sorted(set(versaetze)))} Bild(er)")
    je_stueck = {}
    for nr, v in ergebnisse:
        je_stueck.setdefault(nr, []).append(v)
    print("  Verlauf ueber die Teilstuecke:")
    for nr in sorted(je_stueck):
        print(f"    Stueck {nr}: {', '.join(f'{v:+d}' for v in je_stueck[nr])}")

    nummern = sorted(je_stueck)
    if len(nummern) > 1:
        erste = je_stueck[nummern[0]][0]
        letzte = je_stueck[nummern[-1]][-1]
        schritte = len(nummern) - 1
        if schritte and abs(letzte - erste) >= schritte:
            print("\n  Der Versatz waechst mit jedem Teilstueck: jeder Schnitt\n"
                  "  fuegt ihn erneut hinzu, er summiert sich.")
        elif erste == letzte != 0:
            print("\n  Der Versatz ist ueberall gleich gross: er entsteht einmal\n"
                  "  und nicht pro Schnitt.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
