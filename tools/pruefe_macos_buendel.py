#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft ein fertiges macOS-Buendel auf die Fehler, die erst beim ANWENDER auffallen.

    python3 tools/pruefe_macos_buendel.py dist/KVRouite/KVRouite.app
    python3 tools/pruefe_macos_buendel.py <app> --erwartete-arch arm64 --min-os 13.0

Rueckgabewert 0 = kein Befund, 1 = mindestens ein Befund, 2 = die Pruefung
selbst konnte nicht durchgefuehrt werden.

WARUM ES DIESE DATEI GIBT
=========================
Ein Startversuch auf dem Bau-Rechner beweist fast nichts. Dort liegen Python,
site-packages, Qt und GStreamer ohnehin herum. Verweist eine .dylib im Buendel
auf einen Pfad AUSSERHALB des Buendels, findet der Bau-Rechner die Datei
trotzdem - und der Anwender, der sie nicht hat, bekommt einen Absturz beim
Start. Das ist der haeufigste PyInstaller-Fehler, und er ist auf dem
Bau-Rechner grundsaetzlich unsichtbar.

Diese Datei prueft deshalb NICHT, ob das Programm laeuft. Sie prueft
EIGENSCHAFTEN DER DATEIEN. Das ist der entscheidende Unterschied: eine
Eigenschaft der Datei gilt auf jedem Mac gleich, ein Startversuch gilt nur auf
dem Rechner, auf dem er lief. Alles, was hier gemeldet wird, ist beim Anwender
genauso wahr wie im Bauprotokoll.

Geprueft wird:

  1  Ist ueberhaupt signiert, und zwar ad hoc?
     Ohne mindestens ein Ad-hoc-Siegel beendet macOS auf Apple Silicon das
     Programm sofort - ohne Fenster, ohne Meldung.

  2  Steht jede Datei im Siegel (codesign --verify --deep --strict)?

  3  Passt die Architektur zu dem, was der Dateiname verspricht?

  4  Verweist irgendeine Mach-O-Datei nach draussen?
     Erlaubt sind @rpath, @loader_path, @executable_path, /usr/lib und
     /System - das sind entweder Buendel-relative Wege oder Bestandteile von
     macOS. Alles andere (/opt/homebrew, /usr/local, Python.framework, ein
     Pfad in einem Bau-Ordner) ist ein Befund.

  5  Ab welcher macOS-Fassung laeuft das Buendel wirklich?
     Die README verspricht macOS 13. Nachpruefen laesst sich das nicht durch
     Ausprobieren - es gibt keinen macOS-13-Laeufer mehr. Es laesst sich aber
     ABLESEN: jede Mach-O-Datei traegt ihr Minimum im Ladebefehl
     LC_BUILD_VERSION. Liegt auch nur eine Datei darueber, ist das Versprechen
     nachweislich falsch.

WAS DIESE DATEI NICHT KANN
==========================
Sie sagt nichts darueber, ob die Karte erscheint, ob OpenGL funktioniert oder
ob GStreamer ein bestimmtes Video oeffnet. Das haengt am Rechner des Anwenders
und ist von hier aus nicht erreichbar.

Teil von KVRouite. GPL-3.0-or-later.
"""

import argparse
import os
import shutil
import subprocess
import sys

#: Praefixe, die ein Verweis haben DARF.
#:
#: @rpath/@loader_path/@executable_path zeigen ins Buendel selbst, /usr/lib und
#: /System gehoeren zu macOS und sind auf jedem Mac vorhanden. Wichtig: der
#: Vergleich laeuft ueber den Anfang der Zeichenkette, denn genau darum geht
#: es - ein absoluter Pfad, der woanders anfaengt, zeigt nach draussen.
ERLAUBTE_PRAEFIXE = (
    "@rpath",
    "@loader_path",
    "@executable_path",
    "/usr/lib/",
    "/System/",
)

#: Magische Zahlen am Dateianfang einer Mach-O-Datei, so wie sie auf der
#: Platte liegen. Danach wird gesucht, statt sich auf die Endung zu verlassen:
#: im Buendel stecken ausfuehrbare Dateien ohne jede Endung (die Qt-Helfer),
#: und .so-Dateien von Python sind ebenfalls Mach-O.
MACH_O_MAGIE = {
    b"\xcf\xfa\xed\xfe",   # 64 bit
    b"\xce\xfa\xed\xfe",   # 32 bit
    b"\xca\xfe\xba\xbe",   # fat (mehrere Architekturen in einer Datei)
    b"\xbe\xba\xfe\xca",   # fat, andere Bytereihenfolge
}


class Befund(object):
    """Ein einzelner Fund. Gesammelt, nicht sofort abgebrochen.

    Der erste Entwurf brach beim ersten Fehler ab. Das war unpraktisch: wer
    drei kaputte Bibliotheken hat, will sie in EINEM Lauf sehen und nicht
    dreimal bauen muessen.
    """

    def __init__(self, bereich, text):
        self.bereich = bereich
        self.text = text

    def __str__(self):
        return "[%s] %s" % (self.bereich, self.text)


befunde = []


def melde(bereich, text):
    befunde.append(Befund(bereich, text))
    print("  BEFUND   %s" % text)


def ok(text):
    print("  ok       %s" % text)


def info(text):
    print("           %s" % text)


def abbruch(text):
    """Die Pruefung selbst ist nicht durchfuehrbar.

    Bewusst ein eigener Rueckgabewert (2). Ein fehlendes otool darf NICHT als
    "keine Befunde" durchgehen - eine Pruefung, die nichts geprueft hat, ist
    schlimmer als gar keine, weil sie gruen aussieht.
    """
    print("")
    print("[ABBRUCH] %s" % text)
    sys.exit(2)


def lauf(befehl):
    """Programm starten, (Rueckgabewert, Ausgabe) liefern. Ausgabe = stdout+stderr.

    codesign schreibt seine Begruendung nach stderr, otool nach stdout.
    Beides wird gebraucht, deshalb zusammengelegt.
    """
    ergebnis = subprocess.run(
        befehl,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    return ergebnis.returncode, ergebnis.stdout


# ---------------------------------------------------------------------------
# 1 + 2: Signatur
# ---------------------------------------------------------------------------

def signatur_pruefen(app):
    print("")
    print("--- 1  Signatur: wer hat signiert? ---")
    rc, ausgabe = lauf(["codesign", "-dv", "--verbose=4", app])
    if rc != 0:
        melde("Signatur",
              "codesign kann das Buendel nicht lesen. Vermutlich ist es gar "
              "nicht signiert. Auf Apple Silicon wird ein solches Buendel "
              "sofort beendet.\n%s" % einruecken(ausgabe))
        return

    # codesign meldet die Art der Signatur in einer Zeile "Signature=...".
    # "Signature=adhoc" ist genau der Stand, den dieses Projekt anstrebt:
    # kein Entwicklerzertifikat, aber ein gueltiges Siegel.
    zeilen = [z.strip() for z in ausgabe.splitlines()]
    signaturzeile = next((z for z in zeilen if z.startswith("Signature=")), None)
    if signaturzeile is None:
        melde("Signatur",
              "codesign nennt keine Signature-Zeile. Ausgabe:\n%s"
              % einruecken(ausgabe))
    elif signaturzeile == "Signature=adhoc":
        ok("ad hoc signiert - das ist der beabsichtigte Stand.")
    else:
        # Kein Befund: ein echtes Zertifikat waere besser, nicht schlechter.
        # Gemeldet wird es trotzdem, weil es eine Abweichung vom Erwarteten
        # ist und im Protokoll stehen soll.
        ok("signiert (%s)" % signaturzeile)

    for schluessel in ("Identifier=", "TeamIdentifier=", "Format="):
        zeile = next((z for z in zeilen if z.startswith(schluessel)), None)
        if zeile:
            info(zeile)

    print("")
    print("--- 2  Signatur: steht jede Datei im Siegel? ---")
    rc, ausgabe = lauf(["codesign", "--verify", "--deep", "--strict",
                        "--verbose=2", app])
    if rc != 0:
        melde("Signatur",
              "Das Siegel ist unvollstaendig oder ungueltig. Genau das "
              "passiert, wenn nach dem Signieren noch Dateien ins Buendel "
              "gelegt werden.\n%s" % einruecken(ausgabe))
    else:
        ok("Siegel vollstaendig, jede Datei ist erfasst.")


# ---------------------------------------------------------------------------
# 3: Architektur
# ---------------------------------------------------------------------------

def architektur_pruefen(programm, erwartet):
    print("")
    print("--- 3  Architektur ---")
    rc, ausgabe = lauf(["lipo", "-archs", programm])
    if rc != 0:
        melde("Architektur", "lipo kann %s nicht lesen:\n%s"
              % (programm, einruecken(ausgabe)))
        return
    gebaut = ausgabe.strip()
    info("im Programm: %s" % gebaut)
    if erwartet is None:
        info("keine Erwartung angegeben (--erwartete-arch), nur zur Kenntnis.")
        return
    if gebaut != erwartet:
        melde("Architektur",
              "Das Buendel enthaelt '%s', der Name verspricht aber '%s'. "
              "Wer sich das falsche Archiv herunterlaedt, kann es nicht "
              "starten." % (gebaut, erwartet))
    else:
        ok("passt zu '%s'." % erwartet)


# ---------------------------------------------------------------------------
# 4 + 5: jede Mach-O-Datei einzeln
# ---------------------------------------------------------------------------

def ist_mach_o(pfad):
    """True, wenn die Datei mit einer Mach-O-Magie beginnt.

    Symlinks werden uebersprungen. In Contents/Frameworks liegen viele davon
    (Versions/Current -> Versions/A); wuerde man ihnen folgen, saehe man jede
    Bibliothek mehrfach und das Protokoll waere unbrauchbar lang.
    """
    if os.path.islink(pfad) or not os.path.isfile(pfad):
        return False
    try:
        with open(pfad, "rb") as datei:
            return datei.read(4) in MACH_O_MAGIE
    except (IOError, OSError):
        return False


def mach_o_dateien_sammeln(app):
    gefunden = []
    for ordner, unterordner, dateien in os.walk(app):
        # Symlink-Ordner nicht betreten, sonst laeuft os.walk durch die
        # Framework-Struktur mehrfach.
        unterordner[:] = [u for u in unterordner
                          if not os.path.islink(os.path.join(ordner, u))]
        for name in dateien:
            pfad = os.path.join(ordner, name)
            if ist_mach_o(pfad):
                gefunden.append(pfad)
    return sorted(gefunden)


def verweise_lesen(pfad):
    """Die Liste der Bibliotheken, die diese Datei zur Laufzeit braucht.

    otool -L gibt in der ersten Zeile den Dateinamen selbst aus, danach je
    Zeile einen Verweis mit angehaengter Versionsangabe in Klammern. Bei
    einer fat-Datei wiederholt sich der Block je Architektur; doppelte
    Eintraege werden hier zusammengefasst.
    """
    rc, ausgabe = lauf(["otool", "-L", pfad])
    if rc != 0:
        return None, ausgabe
    verweise = []
    for zeile in ausgabe.splitlines():
        if not zeile.startswith("\t"):
            continue          # Ueberschriftszeile mit dem Dateinamen
        eintrag = zeile.strip()
        klammer = eintrag.rfind(" (")
        if klammer > 0:
            eintrag = eintrag[:klammer]
        if eintrag and eintrag not in verweise:
            verweise.append(eintrag)
    return verweise, ausgabe


def minimum_lesen(pfad):
    """Die Mindest-macOS-Fassung dieser Datei, als Liste von Zeichenketten.

    Zwei Ladebefehle kommen vor:

        LC_BUILD_VERSION      (heute ueblich)     ... platform / minos / sdk
        LC_VERSION_MIN_MACOSX (aeltere Dateien)   ... version / sdk

    Bei einer fat-Datei steht der Block je Architektur einmal drin, deshalb
    koennen mehrere Werte herauskommen.
    """
    rc, ausgabe = lauf(["otool", "-l", pfad])
    if rc != 0:
        return []
    werte = []
    aktueller_befehl = None
    plattform = None
    for rohzeile in ausgabe.splitlines():
        zeile = rohzeile.strip()
        if zeile.startswith("cmd "):
            aktueller_befehl = zeile.split(None, 1)[1]
            plattform = None
        elif zeile.startswith("platform "):
            plattform = zeile.split(None, 1)[1]
        elif zeile.startswith("minos ") and aktueller_befehl == "LC_BUILD_VERSION":
            # platform 1 ist macOS. Alles andere (iOS-Simulator, Catalyst)
            # gehoert hier nicht her und wuerde das Ergebnis verfaelschen.
            if plattform in ("1", "MACOS", "macos", None):
                werte.append(zeile.split(None, 1)[1])
        elif zeile.startswith("version ") and aktueller_befehl == "LC_VERSION_MIN_MACOSX":
            werte.append(zeile.split(None, 1)[1])
    return werte


def als_zahl(fassung):
    """'13.0' -> (13, 0, 0). Zum Vergleichen, damit 13.10 nicht kleiner ist als 13.9."""
    teile = []
    for stueck in fassung.split("."):
        try:
            teile.append(int(stueck))
        except ValueError:
            teile.append(0)
    while len(teile) < 3:
        teile.append(0)
    return tuple(teile[:3])


def dateien_pruefen(app, min_os):
    print("")
    print("--- 4  Verweise nach draussen ---")
    dateien = mach_o_dateien_sammeln(app)

    # Eine Pruefung, die nichts angesehen hat, darf nicht gruen sein.
    if not dateien:
        abbruch("Im Buendel wurde keine einzige Mach-O-Datei gefunden. "
                "Entweder ist der Pfad falsch, oder das Buendel ist leer. "
                "So oder so ist hier nichts geprueft worden.")
    info("untersucht werden %d Mach-O-Dateien" % len(dateien))

    aussenverweise = {}
    for pfad in dateien:
        verweise, rohausgabe = verweise_lesen(pfad)
        if verweise is None:
            melde("Verweise", "otool kann %s nicht lesen:\n%s"
                  % (kurz(pfad, app), einruecken(rohausgabe)))
            continue
        for verweis in verweise:
            if verweis.startswith(ERLAUBTE_PRAEFIXE):
                continue
            aussenverweise.setdefault(verweis, []).append(kurz(pfad, app))

    if aussenverweise:
        for verweis in sorted(aussenverweise):
            nutzer = aussenverweise[verweis]
            melde("Verweise",
                  "%s\n           gebraucht von %d Datei(en), z.B. %s"
                  % (verweis, len(nutzer), nutzer[0]))
        info("")
        info("Diese Pfade gibt es auf dem Bau-Rechner, aber nicht "
             "zwangslaeufig beim Anwender. Genau daran startet ein Buendel "
             "beim Anwender nicht, das hier durchlaeuft.")
    else:
        ok("Kein einziger Verweis zeigt aus dem Buendel heraus.")

    print("")
    print("--- 5  Ab welcher macOS-Fassung laeuft das? ---")
    hoechstes = None
    hoechste_datei = None
    ohne_angabe = 0
    for pfad in dateien:
        werte = minimum_lesen(pfad)
        if not werte:
            ohne_angabe += 1
            continue
        for wert in werte:
            if hoechstes is None or als_zahl(wert) > als_zahl(hoechstes):
                hoechstes = wert
                hoechste_datei = kurz(pfad, app)

    if hoechstes is None:
        melde("Mindestfassung",
              "Keine einzige Datei nennt eine Mindestfassung. Damit ist die "
              "Angabe in der README nicht belegbar.")
        return

    info("hoechste Anforderung im Buendel: macOS %s" % hoechstes)
    info("gefordert von: %s" % hoechste_datei)
    if ohne_angabe:
        info("%d Datei(en) machen keine Angabe (aeltere Bauart, unkritisch)"
             % ohne_angabe)

    if min_os is None:
        info("kein Vergleichswert angegeben (--min-os), nur zur Kenntnis.")
        return

    if als_zahl(hoechstes) > als_zahl(min_os):
        melde("Mindestfassung",
              "Das Buendel verlangt macOS %s, versprochen ist aber macOS %s. "
              "Auf einem Mac mit %s startet es nicht - und das laesst sich "
              "durch Ausprobieren nicht finden, weil es keinen Laeufer mit "
              "dieser Fassung gibt." % (hoechstes, min_os, min_os))
    else:
        ok("macOS %s genuegt - das Versprechen 'macOS %s' ist eingehalten."
           % (hoechstes, min_os))


# ---------------------------------------------------------------------------
# Kleinkram
# ---------------------------------------------------------------------------

def kurz(pfad, app):
    """Pfad ohne das immer gleiche Vorgeplaenkel, damit die Zeilen lesbar bleiben."""
    eltern = os.path.dirname(os.path.abspath(app))
    return os.path.relpath(pfad, eltern)


def einruecken(text):
    return "\n".join("           " + z for z in text.rstrip().splitlines())


def werkzeuge_pruefen():
    """Ohne diese Programme ist hier nichts zu holen - dann lieber ehrlich abbrechen."""
    fehlend = [w for w in ("codesign", "otool", "lipo") if shutil.which(w) is None]
    if fehlend:
        abbruch("Diese Programme fehlen: %s. Sie gehoeren zu den Xcode "
                "Command Line Tools. Auf einem Nicht-Mac ist diese Pruefung "
                "nicht durchfuehrbar." % ", ".join(fehlend))


def main():
    zerleger = argparse.ArgumentParser(
        description="Prueft ein fertiges KVRouite.app auf Fehler, die erst "
                    "beim Anwender auffallen.")
    zerleger.add_argument("app", help="Pfad zu KVRouite.app")
    zerleger.add_argument("--erwartete-arch", default=None,
                          help="arm64 oder x86_64 - was der Archivname verspricht")
    zerleger.add_argument("--min-os", default=None,
                          help="z.B. 13.0 - was die README verspricht")
    argumente = zerleger.parse_args()

    if sys.platform != "darwin":
        abbruch("Diese Pruefung laeuft nur auf macOS. Sie liest Mach-O-Dateien "
                "mit codesign, otool und lipo, und die gibt es nur dort.")
    werkzeuge_pruefen()

    app = os.path.abspath(argumente.app.rstrip(os.sep))
    if not os.path.isdir(app):
        abbruch("Kein Buendel unter %s" % app)

    programm = os.path.join(app, "Contents", "MacOS", "KVRouite")
    if not os.path.isfile(programm):
        abbruch("Kein Programm unter %s" % programm)

    print("=" * 70)
    print("Pruefung des Buendels: %s" % app)
    print("=" * 70)

    signatur_pruefen(app)
    architektur_pruefen(programm, argumente.erwartete_arch)
    dateien_pruefen(app, argumente.min_os)

    print("")
    print("=" * 70)
    if befunde:
        print("ERGEBNIS: %d Befund(e)" % len(befunde))
        for eintrag in befunde:
            print("  - %s" % str(eintrag).splitlines()[0])
        print("=" * 70)
        return 1
    print("ERGEBNIS: kein Befund.")
    print("")
    print("Das heisst: das Buendel ist in sich vollstaendig, richtig signiert")
    print("und verweist nirgends nach draussen. Es heisst NICHT, dass die")
    print("Anwendung auf dem Rechner des Anwenders fehlerfrei laeuft - das")
    print("sagt keine Pruefung, die hier laufen kann.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
