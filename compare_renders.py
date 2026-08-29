#!/usr/bin/env python3
"""Vergleicht zwei Exporte derselben Zeitachse - ffmpeg-Weg gegen GES-Weg.

    python3 compare_renders.py ffmpeg.mp4 ges.mp4
    python3 compare_renders.py ffmpeg.mp4 ges.mp4 --punkte 29 30 31

Geprueft wird, was fuer KVRouite zaehlt:

  * Laenge und Bildanzahl - weicht eines davon ab, verschiebt sich die
    GPX-Kopplung, und der Vergleich ist damit schon entschieden
  * Aufloesung, Bildrate, Codec
  * das Bild selbst an frei waehlbaren Zeitpunkten: mittlere Abweichung und
    groesster Einzelfehler in Helligkeitsstufen (0..255)

Braucht ffmpeg und ffprobe im PATH. Veraendert nichts, schreibt nur nach
stdout; die Einzelbilder landen in einem temporaeren Ordner und werden
wieder geloescht.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def _probe(pfad):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries",
           "stream=nb_read_frames,width,height,r_frame_rate,codec_name",
           "-show_entries", "format=duration,size",
           "-of", "json", pfad]
    roh = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    d = json.loads(roh)
    strom = (d.get("streams") or [{}])[0]
    fmt = d.get("format") or {}
    return {
        "bilder": int(strom.get("nb_read_frames", 0) or 0),
        "breite": int(strom.get("width", 0) or 0),
        "hoehe": int(strom.get("height", 0) or 0),
        "rate": strom.get("r_frame_rate", "?"),
        "codec": strom.get("codec_name", "?"),
        "dauer": float(fmt.get("duration", 0) or 0),
        "groesse": int(fmt.get("size", 0) or 0),
    }


def _graubild(pfad, zeit, ordner, name, breite=160):
    """Ein Bild an Position `zeit` als rohes Graustufenbild."""
    ziel = os.path.join(ordner, name)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{zeit:.6f}", "-i", pfad,
           "-frames:v", "1", "-vf", f"scale={breite}:-2,format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", ziel]
    subprocess.run(cmd, check=True)
    with open(ziel, "rb") as f:
        return f.read()


def _abweichung(a, b):
    if not a or not b or len(a) != len(b):
        return None
    summe = 0
    groesster = 0
    for x, y in zip(a, b):
        d = abs(x - y)
        summe += d
        if d > groesster:
            groesster = d
    return summe / len(a), groesster


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei_a", help="Ergebnis des ffmpeg-Weges")
    ap.add_argument("datei_b", help="Ergebnis des GES-Weges")
    ap.add_argument("--punkte", nargs="*", type=float, default=None,
                    help="Zeitpunkte in Sekunden (Vorgabe: 9 gleichmaessig verteilt)")
    args = ap.parse_args()

    for pfad in (args.datei_a, args.datei_b):
        if not os.path.isfile(pfad):
            print(f"Nicht gefunden: {pfad}")
            return 1

    a = _probe(args.datei_a)
    b = _probe(args.datei_b)

    # Nach Dateinamen beschriften, nicht nach Reihenfolge: sonst liest man
    # die Spalten falsch herum, wenn die Dateien andersherum uebergeben werden.
    na = os.path.basename(args.datei_a)[:18]
    nb = os.path.basename(args.datei_b)[:18]
    print(f"{'':22} {na:>18} {nb:>18}   Urteil")
    print("-" * 74)

    def zeile(name, wa, wb, gleich=None, form=str):
        if gleich is None:
            gleich = (wa == wb)
        print(f"{name:22} {form(wa):>18} {form(wb):>18}   "
              f"{'gleich' if gleich else 'ABWEICHUNG'}")
        return gleich

    ok = True
    ok &= zeile("Bilder", a["bilder"], b["bilder"])
    ok &= zeile("Dauer (s)", a["dauer"], b["dauer"],
                gleich=abs(a["dauer"] - b["dauer"]) < 0.001,
                form=lambda v: f"{v:.6f}")
    ok &= zeile("Aufloesung", f"{a['breite']}x{a['hoehe']}",
                f"{b['breite']}x{b['hoehe']}")
    ok &= zeile("Bildrate", a["rate"], b["rate"])
    zeile("Codec", a["codec"], b["codec"])
    zeile("Dateigroesse (MB)", a["groesse"] / 1048576, b["groesse"] / 1048576,
          gleich=True, form=lambda v: f"{v:.1f}")

    if a["bilder"] != b["bilder"]:
        print("\nDie Bildanzahl unterscheidet sich. Ein Bildvergleich waere ab der\n"
              "ersten Abweichung sinnlos, weil die Zeitachsen auseinanderlaufen.")
        return 1

    punkte = args.punkte
    if not punkte:
        dauer = min(a["dauer"], b["dauer"])
        punkte = [dauer * i / 10.0 for i in range(1, 10)]

    ordner = tempfile.mkdtemp(prefix="kvr_cmp_")
    try:
        print(f"\nBildvergleich an {len(punkte)} Stelle(n), "
              f"Helligkeitsstufen von 255:")
        print(f"  {'Zeit':>10}  {'mittlere Abw.':>14}  {'groesste Abw.':>14}")
        schlimmste = 0.0
        for i, t in enumerate(punkte):
            ga = _graubild(args.datei_a, t, ordner, f"a{i}.gray")
            gb = _graubild(args.datei_b, t, ordner, f"b{i}.gray")
            werte = _abweichung(ga, gb)
            if werte is None:
                print(f"  {t:10.3f}  {'nicht lesbar':>14}")
                continue
            mittel, gross = werte
            schlimmste = max(schlimmste, mittel)
            print(f"  {t:10.3f}  {mittel:14.2f}  {gross:14d}")
    finally:
        shutil.rmtree(ordner, ignore_errors=True)

    print()
    if not ok:
        print("Ergebnis: die Wege liefern NICHT dasselbe. Siehe oben.")
        return 1
    if schlimmste < 3.0:
        print(f"Ergebnis: gleich lang, gleiche Bildanzahl, Bildinhalt praktisch\n"
              f"identisch (groesste mittlere Abweichung {schlimmste:.2f} von 255).\n"
              f"Ein Unterschied in dieser Groessenordnung ist normales\n"
              f"Encoder-Rauschen und nicht sichtbar.")
    else:
        print(f"Ergebnis: gleich lang und gleiche Bildanzahl, aber das Bild weicht\n"
              f"sichtbar ab (bis {schlimmste:.2f} von 255 im Mittel). Die Stellen\n"
              f"oben einzeln ansehen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
