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
Laedt die GStreamer-Quelltarballs zu einer bestimmten Version herunter.

Wozu: KVRouite verteilt im Windows-Build die GStreamer-Binaries aus den
pip-Wheels. Die Quellen dazu liegen beim GStreamer-Projekt selbst, und die
Rechtstexte (gstreamer/CORRESPONDING-SOURCE.txt) verweisen dorthin - das
deckt GPLv3 Abschnitt 6(d) ab. Fuer den Fall, dass diese Links irgendwann
nicht mehr erreichbar sind, bleibt der Verteiler aber trotzdem in der Pflicht.
Deshalb hier einmal pro angehefteter Version eine eigene Kopie ziehen.

Die Kopie muss NICHT veroeffentlicht werden. Sie muss nur existieren, damit
eine Anfrage beantwortet werden kann. Ein Ordner auf der Backup-Platte reicht.

    python tools/fetch_gstreamer_sources.py --out D:/Archiv/gstreamer-1.28.6

Ohne --version wird die Version aus requirements-ges.txt gelesen.
Bereits vorhandene, korrekt gepruefte Dateien werden uebersprungen, der Lauf
ist also wiederholbar.
"""

import argparse
import hashlib
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = "https://gstreamer.freedesktop.org/src"

# Modulname -> Verzeichnis auf dem Server. Beides ist hier gleich, die Tabelle
# steht trotzdem explizit da: gstreamer-vaapi und gnonlin gibt es nicht mehr,
# und wer die Liste anpasst, soll sehen, was gemeint ist.
MODULES = [
    "gstreamer",
    "gst-plugins-base",
    "gst-plugins-good",
    "gst-plugins-bad",
    "gst-plugins-ugly",
    "gst-libav",
    "gst-editing-services",
    "gst-python",
    "gst-rtsp-server",
    "gst-devtools",
]

# orc hat eine eigene Versionsreihe (0.4.x) und folgt der GStreamer-Version
# nicht. Es wird deshalb nicht mit heruntergeladen; die Version steht in den
# cerbero-Rezepten.


def read_pinned_version(repo_root):
    """Holt die Version aus requirements-ges.txt (Zeile 'gstreamer-bundle==x')."""
    path = os.path.join(repo_root, "requirements-ges.txt")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        print("[WARN] requirements-ges.txt nicht lesbar:", exc)
        return None
    match = re.search(r"^\s*gstreamer[-_]bundle\s*==\s*([0-9][0-9.]*)", text, re.M)
    if not match:
        print("[WARN] Keine Zeile 'gstreamer-bundle==...' in requirements-ges.txt.")
        return None
    return match.group(1)


def download(url, dest):
    """Laedt url nach dest. Gibt True zurueck, wenn die Datei danach da ist."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        print(f"    [{exc.code}] nicht vorhanden: {url}")
        return False
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"    [FEHLER] {url}: {exc}")
        return False
    with open(dest, "wb") as handle:
        handle.write(data)
    return True


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha256(sumfile):
    """Liest den Hash aus einer .sha256sum-Datei ('<hash>  <dateiname>')."""
    try:
        first = open(sumfile, encoding="ascii").read().split()
    except OSError:
        return None
    return first[0] if first else None


def fetch_module(module, version, out_dir):
    """
    Holt Tarball, Pruefsumme und Signatur eines Moduls.

    Rueckgabe: "ok", "uebersprungen", "fehlt" oder "hash-fehler".
    """
    name = f"{module}-{version}.tar.xz"
    url = f"{BASE_URL}/{module}/{name}"
    tarball = os.path.join(out_dir, name)
    sumfile = tarball + ".sha256sum"

    print(f"  {name}")

    if not os.path.isfile(sumfile):
        download(url + ".sha256sum", sumfile)
    if not os.path.isfile(tarball):
        if not download(url, tarball):
            return "fehlt"
    else:
        print("    schon vorhanden")

    want = expected_sha256(sumfile)
    if want is None:
        print("    [WARN] keine .sha256sum - Inhalt ungeprueft")
        return "ok"

    have = sha256_of(tarball)
    if have != want:
        print(f"    [FEHLER] SHA256 stimmt nicht:\n      erwartet {want}\n      erhalten {have}")
        return "hash-fehler"
    print("    SHA256 ok")

    # Signatur zusaetzlich mitnehmen, damit die Kopie vollstaendig ist.
    asc = tarball + ".asc"
    if not os.path.isfile(asc):
        download(url + ".asc", asc)
    return "ok"


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(
        description="Laedt die GStreamer-Quelltarballs fuer die Offline-Kopie.")
    parser.add_argument("--out", required=True,
                        help="Zielordner fuer die Tarballs")
    parser.add_argument("--version", default=None,
                        help="GStreamer-Version, z.B. 1.28.6 "
                             "(Standard: aus requirements-ges.txt)")
    args = parser.parse_args()

    version = args.version or read_pinned_version(repo_root)
    if not version:
        print("[ERROR] Keine Version ermittelbar - bitte --version angeben.")
        return 2

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    print(f"GStreamer {version} -> {out_dir}")
    print(f"Quelle: {BASE_URL}/")
    print("-" * 70)

    ergebnisse = {}
    for module in MODULES:
        ergebnisse[module] = fetch_module(module, version, out_dir)

    print("-" * 70)
    fehlend = [m for m, r in ergebnisse.items() if r == "fehlt"]
    kaputt = [m for m, r in ergebnisse.items() if r == "hash-fehler"]
    ok = [m for m, r in ergebnisse.items() if r == "ok"]

    print(f"{len(ok)} von {len(MODULES)} Modulen geladen.")
    if fehlend:
        print("Nicht gefunden:", ", ".join(fehlend))
        print("  Nicht jedes Modul erscheint zu jeder Version. Bitte einmal unter")
        print(f"  {BASE_URL}/<modul>/ nachsehen, ob es die Version dort wirklich gibt.")
    if kaputt:
        print("PRUEFSUMME FALSCH:", ", ".join(kaputt))
        print("  Diese Dateien loeschen und den Lauf wiederholen.")

    if kaputt:
        return 1
    if fehlend:
        return 1

    print()
    print("Fertig. Diesen Ordner sichern (Backup-Platte reicht, er muss nicht")
    print("veroeffentlicht werden) und in gstreamer/CORRESPONDING-SOURCE.txt")
    print("nachsehen, ob die dort genannte Version noch stimmt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
