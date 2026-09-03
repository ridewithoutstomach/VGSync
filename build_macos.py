# -*- coding: utf-8 -*-
#
# This file is part of KVRouite.
#
# Copyright (C) 2025-2026 by Bernd Eller
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
"""
Baut KVRouite als macOS-Anwendungsbuendel (KVRouite.app).

    python3 build_macos.py

Warum ein eigenes Skript und keine Erweiterung von build_with_pyinstaller.py:
der Windows-Weg baut einen Ordner mit KVRouite.exe, haengt _internal/ daneben,
entfernt Kommandozeilenwerkzeuge aus dem GStreamer-Paket und ruft am Ende Inno
Setup auf. Auf macOS ist das Ergebnis ein Buendel mit festgelegter innerer
Ordnung, das Symbol ist eine .icns statt einer .ico, und einen Installer gibt
es nicht - ausgeliefert wird das gezippte Buendel. Beides in einer Funktion mit
Weichen zu halten waere unuebersichtlicher als zwei Dateien.

GETEILT wird, was geteilt gehoert: die Gegenproben (kein ffmpeg, kein mpv, die
Rechtstexte) und die Pruefsumme kommen aus build_with_pyinstaller.py. Sie
duerfen nicht auseinanderlaufen - ein Mac-Buendel mit libmpv darin zoege
dieselbe GPL-Quellcodepflicht nach sich wie ein Windows-Build.

WO DIE DATEIEN LANDEN, und warum ausgerechnet dort: die Anwendung sucht
map_page.html neben ihrem Programm, sie rechnet in widgets/map_widget.py mit
os.path.dirname(sys.argv[0]). In einem Buendel ist das Contents/MacOS. Dort
liegen die Web-Dateien deshalb, obwohl Contents/Resources der uebliche Ort
waere. Wer das umstellen will, aendert zuerst die Suche im Programm.
"""

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Aus dem Windows-Skript: Gegenproben und Pruefsumme. Import statt Kopie, damit
# beide Wege dieselben Regeln anwenden und nicht auseinanderlaufen.
from build_with_pyinstaller import (      # noqa: E402
    GSTREAMER_PAKETE,
    check_ffmpeg_frei,
    check_mpv_frei,
    gio_module_entfernen,
    copy_only_pdfs,
    copy_tree_all,
    load_app_version,
    write_sha256,
)

LOCAL_GSTREAMER = os.path.join(BASE_DIR, "gstreamer")
LOCAL_QT = os.path.join(BASE_DIR, "qt")
LOCAL_THIRDPARTY = os.path.join(BASE_DIR, "third-party-licenses")

#: Neben das Programm im Buendel - die Anwendung sucht sie dort.
WEB_RESSOURCEN = ("ol.css", "ol.js", "map_page.html")


def lauf(befehl):
    print("[CMD]", " ".join(befehl))
    subprocess.run(befehl, check=True)


#: Die gi-Module, deren PyInstaller-Hooks auf ein systemweit installiertes
#: GObject-Introspection ausgelegt sind. Aus dem fehlgeschlagenen Lauf vom
#: 02.09.2026 - jedes davon meldete "Unable to find gir directory", und bei
#: Gio brach der Build ab.
#
#: "gi" selbst steht ABSICHTLICH nicht in der Liste: dessen Hook sammelt die
#: Python-Overrides von PyGObject, die zur Laufzeit gebraucht werden. Nur die
#: Hooks der einzelnen Bibliotheken suchen an Systemorten.
GI_MODULE = (
    "gi.repository.GLib", "gi.repository.GObject", "gi.repository.GModule",
    "gi.repository.Gio", "gi.repository.Gst", "gi.repository.GstBase",
    "gi.repository.GstApp", "gi.repository.GstAudio", "gi.repository.GstVideo",
    "gi.repository.GstController", "gi.repository.GstPbutils",
    "gi.repository.GstGL", "gi.repository.GstNet", "gi.repository.GstTag",
    "gi.repository.GstRtp", "gi.repository.GstSdp", "gi.repository.GstCheck",
    "gi.repository.GES",
)


def hooks_verzeichnis_anlegen():
    """Ein Hook-Verzeichnis, das die eingebauten gi-Hooks stilllegt.

    Warum das noetig ist: PyInstaller bringt fuer jedes gi.repository-Modul
    einen Hook mit, der die Bibliothek ueber den SYSTEMWEITEN Weg sucht -
    share/gir-1.0 und die dylibs an den ueblichen Orten. Bei uns kommt
    GStreamer aus den Wheels: die Typelibs liegen in
    gstreamer_libs/lib/girepository-1.0, ein gir-Verzeichnis gibt es gar
    nicht. Unter Windows faellt das nicht auf, weil die .pth-Datei den PATH
    setzt und die DLLs dort gefunden werden. Auf macOS brach der Lauf ab mit
    "Could not resolve any shared library of Gio 2.0".

    Die eigenen Hooks sind leer. Sie sammeln nichts, sie suchen nichts - was
    gebraucht wird, holen die --collect-all der gstreamer-Pakete ohnehin
    heran, samt der Typelibs.

    PyInstaller durchsucht die zusaetzlichen Verzeichnisse vor den eigenen;
    ein gleichnamiger Hook hier ersetzt also den eingebauten.
    """
    ordner = os.path.join(BASE_DIR, "build", "hooks_macos")
    if os.path.isdir(ordner):
        shutil.rmtree(ordner)
    os.makedirs(ordner)
    mit_override = 0
    for modul in GI_MODULE:
        # Die Python-Schicht ueber der Introspection MUSS mit. Ohne sie ist
        # zum Beispiel Gst.init(None) nicht erlaubt - das erste Buendel brach
        # daran ab mit "Argument 1 does not allow None as a value". Der
        # eingebaute Hook haette den Override eingesammelt; wenn wir ihn
        # stilllegen, muessen wir das selbst tun.
        kurz = modul.split(".")[-1]
        override = "gi.overrides." + kurz
        hat_override = importlib.util.find_spec(override) is not None
        if hat_override:
            mit_override += 1
        pfad = os.path.join(ordner, "hook-%s.py" % modul)
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("# Erzeugt von build_macos.py - siehe dort die Begruendung.\n")
            f.write("# Legt die Bibliothekssuche des eingebauten Hooks fuer\n")
            f.write("# %s still, nimmt den Override aber mit.\n" % modul)
            f.write("hiddenimports = %r\n" % ([override] if hat_override else []))
            f.write("datas = []\n")
            f.write("binaries = []\n")
            f.write("excludedimports = []\n")
    print("[INFO] %d eigene gi-Hooks in %s (%d mit Override)"
          % (len(GI_MODULE), ordner, mit_override))
    return ordner


def vorhandene_gstreamer_pakete():
    """Welche der GStreamer-Pakete auf DIESEM Rechner installiert sind.

    --collect-all fuer ein Paket, das es nicht gibt, laesst PyInstaller sofort
    abbrechen. Unter Windows liegen alle elf im Wheel; ob das auf macOS ebenso
    ist, entscheidet das dortige Wheel und nicht diese Liste. Deshalb wird
    gefragt statt angenommen - und was fehlt, steht im Log, damit man sieht,
    womit gebaut wurde.
    """
    da, fehlt = [], []
    for paket in GSTREAMER_PAKETE:
        if importlib.util.find_spec(paket) is not None:
            da.append(paket)
        else:
            fehlt.append(paket)
    print("[INFO] GStreamer-Pakete installiert: %d von %d"
          % (len(da), len(GSTREAMER_PAKETE)))
    for p in fehlt:
        print("   nicht installiert:", p)
    if not da:
        raise SystemExit("[ABBRUCH] Kein einziges GStreamer-Paket gefunden - "
                         "ohne die Laufzeit hat ein Buendel keinen Sinn. "
                         "Wurde requirements.txt installiert?")
    return da


def buendel_bauen(ziel_ordner):
    """PyInstaller aufrufen. Rueckgabe: Pfad des .app-Buendels."""
    symbol = os.path.join(BASE_DIR, "MyIcon.icns")
    if not os.path.isfile(symbol):
        print("[WARN] MyIcon.icns fehlt - das Buendel bekommt das Standardsymbol.")

    befehl = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",                 # erzeugt das .app-Buendel
        "--name=KVRouite",
        "--distpath=" + ziel_ordner,
        # Die Kennung taucht im Finder auf und wird fuer Fensterrechte gebraucht.
        "--osx-bundle-identifier=com.kvrouite.app",
    ]
    if os.path.isfile(symbol):
        befehl.append("--icon=" + symbol)
    befehl.append("--additional-hooks-dir=" + hooks_verzeichnis_anlegen())
    # selftest wird nur innerhalb von main() importiert; ausdruecklich nennen,
    # damit PyInstaller es nicht uebersieht.
    befehl.append("--hidden-import=selftest")
    # GStreamer muss ausdruecklich mit, aber nur was da ist: ein --collect-all
    # auf ein fehlendes Paket bricht PyInstaller sofort ab.
    befehl += ["--collect-all=" + paket for paket in vorhandene_gstreamer_pakete()]
    befehl.append("KVRouite.py")
    lauf(befehl)

    buendel = os.path.join(ziel_ordner, "KVRouite.app")
    if not os.path.isdir(buendel):
        raise SystemExit("[ABBRUCH] PyInstaller hat kein KVRouite.app erzeugt.")
    return buendel


def ressourcen_einlegen(buendel):
    """Alles, was die Anwendung zur Laufzeit neben sich sucht."""
    macos_dir = os.path.join(buendel, "Contents", "MacOS")
    os.makedirs(macos_dir, exist_ok=True)

    for name in WEB_RESSOURCEN:
        quelle = os.path.join(BASE_DIR, name)
        if os.path.isfile(quelle):
            print("[COPY]", name, "->", macos_dir)
            shutil.copy2(quelle, os.path.join(macos_dir, name))
        else:
            print("[WARN]", name, "nicht gefunden - die Karte bliebe leer.")

    symbol_ordner = os.path.join(BASE_DIR, "icon")
    if os.path.isdir(symbol_ordner):
        print("[COPY] icon/ ->", macos_dir)
        copy_tree_all(symbol_ordner, os.path.join(macos_dir, "icon"))
    else:
        print("[WARN] icon/ fehlt - die Knoepfe blieben ohne Symbole.")


def rechtstexte_einlegen(buendel):
    """Die Lizenztexte ins Buendel. Rueckgabe: Liste der fehlenden."""
    resources = os.path.join(buendel, "Contents", "Resources")
    os.makedirs(resources, exist_ok=True)
    fehlen = []
    for quelle, ziel, was in ((LOCAL_GSTREAMER, "gstreamer", "GStreamer"),
                              (LOCAL_QT, "qt", "Qt/PySide6"),
                              (LOCAL_THIRDPARTY, "third-party-licenses",
                               "CPython, OpenSSL, Pillow, fitparse")):
        pfad = os.path.join(resources, ziel)
        if os.path.isdir(quelle):
            print("[INFO] Lizenztexte " + was + " -> " + pfad)
            copy_tree_all(quelle, pfad)
        else:
            print("[FEHLER] " + ziel + "/ fehlt - die Lizenztexte fuer " + was
                  + " wuerden NICHT mit ausgeliefert.")
            fehlen.append(ziel)

    lizenz = None
    for name in ("LICENSE", "LICENSE.txt"):
        kandidat = os.path.join(BASE_DIR, name)
        if os.path.isfile(kandidat):
            lizenz = kandidat
            break
    if lizenz:
        print("[COPY GPL]", lizenz, "-> Contents/Resources/LICENSE")
        shutil.copy2(lizenz, os.path.join(resources, "LICENSE"))
    else:
        print("[WARN] LICENSE fehlt im Projekt-Root.")
        fehlen.append("LICENSE")

    doc = os.path.join(BASE_DIR, "doc")
    if os.path.isdir(doc):
        ziel_doc = os.path.join(resources, "doc")
        print("[INFO] Nur die PDFs aus doc/ -> " + ziel_doc)
        copy_only_pdfs(doc, ziel_doc)
        # Das Kinomap-Logo ist kein PDF, wird aber gebraucht: es steht in der
        # GPX-Leiste und im Copyright-Fenster. Der Windows-Build kopiert es
        # ausdruecklich mit, hier fehlte es - der Selbsttest im ersten Buendel
        # hat es gemeldet.
        logo = os.path.join(doc, "Kinomap_Logo.png")
        if os.path.isfile(logo):
            os.makedirs(ziel_doc, exist_ok=True)
            print("[COPY] Kinomap_Logo.png -> " + ziel_doc)
            shutil.copy2(logo, os.path.join(ziel_doc, "Kinomap_Logo.png"))
        else:
            print("[WARN] doc/Kinomap_Logo.png fehlt im Projekt.")
    return fehlen


def gstreamer_pruefen(buendel):
    """Ist die GStreamer-Laufzeit wirklich im Buendel gelandet?

    core/ges_backend.py macht "import gi" auf Modulebene: fehlt die Laufzeit,
    startet das Buendel nicht, und zwar ohne brauchbare Meldung. Gesucht wird
    im ganzen Buendel, weil PyInstaller auf macOS anders einsortiert als unter
    Windows - Contents/Frameworks statt _internal.
    """
    erwartet = vorhandene_gstreamer_pakete()
    gefunden = set()
    for _wurzel, ordner, _dateien in os.walk(buendel):
        for name in ordner:
            if name in erwartet:
                gefunden.add(name)
    fehlend = [p for p in erwartet if p not in gefunden]
    print("[LIZENZ] GStreamer im Buendel: %d von %d installierten Paketen."
          % (len(gefunden), len(erwartet)))
    for p in sorted(gefunden):
        print("   vorhanden:", p)
    for p in fehlend:
        print("   FEHLT    :", p)
    return fehlend


def architektur():
    """Fuer welche CPU dieser Lauf baut - "arm64" oder "x86_64".

    Der Wert kommt aus platform.machine(), also aus dem Python, das gerade
    laeuft, und damit aus genau dem, was PyInstaller gleich baut. Nicht aus
    dem Namen der Maschine: GitHub nennt seine Runner "macos-15" und
    "macos-15-intel", das ist die macOS-Version plus ein Zusatz und sagt ueber
    den Prozessor nichts Verlaessliches. Und wer auf einem Apple-Silicon-Mac
    ein Python unter Rosetta startet, baut x86_64 - platform.machine() sagt
    dann x86_64, der Maschinenname weiter arm64. Der Name des Archivs muss
    dem folgen, was drin ist.

    Warum das zaehlt: bis zum 02.09.2026 hiessen beide Archive gleich
    (KVRouite_6.02_macOS.zip). Nebeneinander gelegt ueberschrieb eines das
    andere, und die Pruefsummendatei zeigte danach auf die falsche Datei.
    """
    return platform.machine()


def signieren(buendel):
    """Das Buendel signieren - ZUM SCHLUSS, wenn nichts mehr dazukommt.

    PyInstaller signiert das Buendel selbst (ad hoc; auf Apple Silicon MUSS es
    das, sonst startet gar nichts). Danach legen ressourcen_einlegen() und
    rechtstexte_einlegen() aber noch Dateien hinein, und die stehen dann nicht
    im Siegel. Auf einem fremden Mac sieht das so aus:

        KVRouite.app: a sealed resource is missing or invalid
        file added: .../Contents/MacOS/ol.css
        file added: .../Contents/MacOS/map_page.html
        file added: .../Contents/Resources/qt/NOTICE.txt
        ...

    So gemeldet am 02.09.2026 von einem Anwender - die Liste war Zeile fuer
    Zeile unsere eigene Kopierliste.

    Auf dem Bauserver faellt das nicht auf, und zwar aus zwei Gruenden: das
    Buendel entsteht dort lokal und traegt deshalb kein Quarantaene-Merkmal,
    ohne das schaut Gatekeeper gar nicht hin; und gestartet wird ueber die
    Signatur des HAUPTPROGRAMMS, die unveraendert gueltig ist - das Siegel
    ueber die Beidateien wird nur bei einer ausdruecklichen Pruefung
    ausgewertet. Der Lauf war also gruen, das Buendel trotzdem kaputt.

    Deshalb wird hier zum Schluss neu signiert und sofort gegengeprueft.
    Ad hoc ("-"), nicht mit einem Zertifikat: das nimmt Gatekeeper die Meldung
    ueber das kaputte Siegel. Die Meldung ueber den unbekannten Entwickler
    bleibt - dafuer braeuchte es ein Apple-Entwicklerzertifikat.
    """
    codesign = shutil.which("codesign")
    if codesign is None:
        raise SystemExit("[ABBRUCH] codesign nicht gefunden - ohne gueltiges "
                         "Siegel darf das Buendel nicht ausgeliefert werden.")
    print("[SIGN] Buendel neu signieren (ad hoc), jetzt liegt alles darin")
    lauf([codesign, "--force", "--deep", "--sign", "-", buendel])
    print("[SIGN] Gegenprobe - meldet jede Datei, die nicht im Siegel steht")
    lauf([codesign, "--verify", "--deep", "--strict", "--verbose=2", buendel])
    print("[SIGN] Siegel in Ordnung")


def zippen(buendel, ziel_ordner, app_version):
    """Das Buendel als ZIP - so wird es abgelegt und weitergegeben.

    Gepackt wird mit ditto und nicht mit zipfile, und dafuer gibt es zwei
    Gruende. Erstens die Rechte: ohne das Ausfuehrbar-Bit an
    Contents/MacOS/KVRouite startet das entpackte Buendel nicht. Zweitens die
    Verweise: in Contents/Frameworks stehen Symlinks (Versions/Current zeigt
    auf A). zipfile legt fuer jeden davon eine VOLLE KOPIE ab - das Archiv
    waechst, und die Struktur eines Frameworks ist danach nicht mehr die, die
    macOS erwartet.

    ditto gehoert zu macOS und ist genau dafuer da. Der Rueckfall auf zipfile
    steht nur fuer den Fall, dass es einmal fehlt; er ist ausdruecklich die
    schlechtere Fassung und sagt das auch.
    """
    name = "KVRouite_%s_macOS_%s.zip" % (app_version, architektur())
    ziel = os.path.join(ziel_ordner, name)
    print("[INFO] Packe", ziel)

    ditto = shutil.which("ditto")
    if ditto:
        lauf([ditto, "-c", "-k", "--sequesterRsrc", "--keepParent",
              buendel, ziel])
        print("[INFO] ZIP erstellt (ditto):", ziel)
        return ziel

    print("[WARN] ditto nicht gefunden - packe mit zipfile. Symlinks werden "
          "dabei zu Kopien, und die Rechte haengen am Dateisystem.")
    wurzel_oben = os.path.dirname(buendel)
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as archiv:
        for wurzel, _ordner, dateien in os.walk(buendel):
            for datei in dateien:
                voll = os.path.join(wurzel, datei)
                drin = os.path.relpath(voll, wurzel_oben)
                eintrag = zipfile.ZipInfo.from_file(voll, drin)
                eintrag.external_attr = (os.stat(voll).st_mode & 0xFFFF) << 16
                eintrag.compress_type = zipfile.ZIP_DEFLATED
                with open(voll, "rb") as f:
                    archiv.writestr(eintrag, f.read())
    print("[INFO] ZIP erstellt (zipfile):", ziel)
    return ziel


def build_macos():
    if sys.platform != "darwin":
        raise SystemExit("[ABBRUCH] Dieses Skript baut fuer macOS und laeuft "
                         "nur dort. Fuer Windows: build_with_pyinstaller.py")

    app_version = load_app_version()
    print("[INFO] APP_VERSION:", app_version)
    print("[INFO] Architektur:", architektur())

    ziel_ordner = os.path.join(
        BASE_DIR, "dist",
        "KVRouite_%s_macOS_%s" % (app_version, architektur()))
    if os.path.isdir(ziel_ordner):
        print("[INFO] Alten Ordner entfernen:", ziel_ordner)
        shutil.rmtree(ziel_ordner)
    os.makedirs(ziel_ordner, exist_ok=True)

    buendel = buendel_bauen(ziel_ordner)
    ressourcen_einlegen(buendel)
    fehlende_rechtstexte = rechtstexte_einlegen(buendel)
    fehlende_gstreamer = gstreamer_pruefen(buendel)

    # Das GIO-Proxy-Modul heraus - VOR dem Signieren, sonst waere das Siegel
    # sofort wieder ungueltig.
    gio_module_entfernen(buendel)

    # Die Gegenproben ganz zum Schluss, wenn nichts mehr dazukommt.
    if check_mpv_frei(buendel):
        raise SystemExit("[ABBRUCH] Buendel enthaelt mpv - nicht ausliefern.")
    if check_ffmpeg_frei(buendel):
        raise SystemExit("[ABBRUCH] Buendel enthaelt ffmpeg - nicht ausliefern.")
    if fehlende_gstreamer:
        raise SystemExit("[ABBRUCH] GStreamer ist unvollstaendig (%s) - das "
                         "Buendel wuerde nicht starten."
                         % ", ".join(fehlende_gstreamer))
    if fehlende_rechtstexte:
        raise SystemExit("[ABBRUCH] Rechtstexte fehlen (%s) - so darf das "
                         "Buendel nicht ausgeliefert werden."
                         % ", ".join(fehlende_rechtstexte))

    # Signieren als LETZTER Schritt, der das Buendel anfasst - danach wird nur
    # noch gepackt. Kommt hier jemals etwas dazu, muss es DAVOR passieren.
    signieren(buendel)

    archiv = zippen(buendel, ziel_ordner, app_version)
    write_sha256(archiv)

    print("")
    print("[FERTIG] Buendel:", buendel)
    print("[FERTIG] Archiv :", archiv)
    print("")
    print("Das Buendel ist ad hoc signiert - das Siegel ist vollstaendig und")
    print("passt zum Inhalt. Es ist NICHT notarisiert: auf einem fremden Mac")
    print("meldet Gatekeeper einen unbekannten Entwickler. Der Anwender oeffnet")
    print("es einmal ueber Systemeinstellungen -> Datenschutz & Sicherheit ->")
    print("\"Trotzdem oeffnen\"; der frueher uebliche Rechtsklick -> Oeffnen ist")
    print("seit macOS 15 (Sequoia) abgeschafft. Fuer den Wegfall auch dieser")
    print("Meldung braeuchte es ein Entwicklerzertifikat von Apple.")
    return buendel


def main():
    build_macos()


if __name__ == "__main__":
    main()
