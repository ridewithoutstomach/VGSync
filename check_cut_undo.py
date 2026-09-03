#!/usr/bin/env python3
"""Prueft die Ruecknahme von Schnitten - ohne Oberflaeche, ohne Video.

    python3 check_cut_undo.py

Die Frage, die das Werkzeug beantwortet, ist nicht "stuerzt etwas ab", sondern
"kommt die GPX-Spur exakt so zurueck, wie sie vor dem Schnitt war". Das laesst
sich nicht durch Hinsehen entscheiden: eine um Sekundenbruchteile verschobene
Spur sieht im Chart richtig aus und faellt erst auf, wenn Video und Spur im
Export auseinanderlaufen.

DREI FRAGEN
-----------
1. Reihenfolge   Nimmt man bei zwei Schnitten den VORDEREN zuerst zurueck,
                 verschiebt sich die Spur unter der Aufzeichnung des hinteren
                 weg. Ohne Nachfuehren weichen dabei Punkte ab, ohne dass es
                 jemand merkt.
2. Projektdatei  Ueberstehen die Aufzeichnungen den Weg durch die Datei? Bis
                 6.03 standen sie nur im Speicher - nach jedem "Open Project"
                 war "Undo Cut" grau.
3. Verschobene   Eine Spur, deren Zeiten nachtraeglich veraendert wurden, darf
   Spur          NICHT zurueckgenommen werden. Der Fingerabdruck allein kann
                 das nach dem Laden nicht mehr entscheiden, weil er dabei
                 zwangslaeufig neu gerechnet wird - dafuer gibt es
                 naht_stimmt().

WAS ECHT IST UND WAS NACHGEBAUT
-------------------------------
Echt ist alles, worum es geht: aufzeichnung_merken(), spur_ohne_schnitt(),
aufzeichnungen_nachfuehren(), naht_stimmt(), get_cut_points()/set_cut_points()
und ruecknahme_moeglich() aus managers/cut_manager.py.

Nachgebaut sind zwei Dinge, die ohne Qt und ohne geladenes Video nicht zu
haben sind: das Anwenden eines Schnitts auf die Spur (Middle-Cut-Zweig aus
views/mainwindow.py, on_cut_clicked_video) und die beiden Stellen, an denen
das Programm aufzeichnungen_nachfuehren() ruft. Aendert sich dort etwas, muss
es hier mitgezogen werden - deshalb steht an beiden Stellen ein Hinweis.

Rueckgabe: 0 wenn alles stimmt, 1 wenn etwas abweicht.
"""

import copy
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from managers.cut_manager import VideoCutManager  # noqa: E402


BASIS = datetime(2025, 1, 1, 12, 0, 0)


# ----------------------------------------------------------------------
# Ersatz fuer Timeline und VideoEditor. Der CutManager meldet ihnen nur,
# dass sich etwas geaendert hat; fuer diese Pruefung ist das ohne Belang.
# ----------------------------------------------------------------------
class StummeTimeline:
    def clear_all_cuts(self):
        pass

    def add_cut_interval(self, a, b):
        pass

    def set_hard_cut_keys(self, keys):
        pass


class StummerEditor:
    def set_cut_intervals(self, intervalle):
        pass


def spur(n=60):
    """Eine Spur mit einem Punkt je Sekunde."""
    return [{"lat": 50.0 + i * 0.001,
             "lon": 7.0 + i * 0.001,
             "ele": 100.0 + i,
             "time": BASIS + timedelta(seconds=i)} for i in range(n)]


def _interp_point(pt1, pt2, new_time):
    """Wie in views/mainwindow.py."""
    t1, t2 = pt1.get("time"), pt2.get("time")
    if t1 is None or t2 is None or t2 == t1:
        ratio = 0.0
    else:
        ratio = (new_time - t1).total_seconds() / (t2 - t1).total_seconds()

    def _val(k):
        return pt1.get(k, 0.0) + ratio * (pt2.get(k, 0.0) - pt1.get(k, 0.0))

    return {"lat": _val("lat"), "lon": _val("lon"), "ele": _val("ele"),
            "time": new_time, "delta_m": 0.0, "speed_kmh": 0.0,
            "gradient": 0.0}


def schneiden(gpx_data, start_dt, end_dt):
    """NACHGEBAUT: der Middle-Cut-Zweig aus on_cut_clicked_video().

    Gibt (neue_spur, entfernt, verworfen, interpoliert, dauer_s) zurueck -
    genau die Werte, die dort an aufzeichnung_merken() gehen.
    """
    dauer = (end_dt - start_dt).total_seconds()
    neu, naht, n, i = [], None, len(gpx_data), 0

    while i < n and gpx_data[i].get("time") < start_dt:
        neu.append(copy.deepcopy(gpx_data[i]))
        i += 1

    if i < n and gpx_data[i].get("time") != start_dt:
        if neu:
            vor, nach = neu[-1], gpx_data[i]
            if vor.get("time") < start_dt < nach.get("time"):
                naht = _interp_point(vor, nach, start_dt)
                neu.append(naht)
    elif i < n and gpx_data[i].get("time") == start_dt:
        neu.append(copy.deepcopy(gpx_data[i]))
        i += 1

    entfernt = []
    while i < n and gpx_data[i].get("time") <= end_dt:
        entfernt.append(copy.deepcopy(gpx_data[i]))
        i += 1
    interpoliert = copy.deepcopy(naht) if naht else None

    for j in range(i, n):
        p = copy.deepcopy(gpx_data[j])
        if p.get("time") is not None:
            p["time"] = p["time"] - timedelta(seconds=dauer)
        neu.append(p)

    verworfen = []
    if len(neu) >= 2:
        sauber = [neu[0]]
        for k in range(1, len(neu)):
            if neu[k].get("time") > sauber[-1].get("time"):
                sauber.append(neu[k])
            else:
                verworfen.append(copy.deepcopy(neu[k]))
        neu = sauber

    return neu, entfernt, verworfen, interpoliert, dauer


class Werkbank:
    """Spur und CutManager zusammen, mit den beiden Aktionen des Programms."""

    def __init__(self, punkte=60):
        self.cm = VideoCutManager(StummerEditor(), StummeTimeline())
        self.cm.set_video_durations([float(punkte)])
        self.gpx = spur(punkte)
        self.cm.fingerabdruck_merken(self.gpx)

    def _versatz(self, roh_s):
        """Um wie viel liegt Rohzeit roh_s in der Spur weiter vorn?

        Ersatz fuer get_final_time_for_global() bei Schnitten, die sich nicht
        ueberlappen: alles, was frueher herausgeschnitten wurde, faellt weg.
        """
        return sum((b - a) for (a, b) in self.cm._cut_intervals if b <= roh_s)

    def schnitt(self, roh_start, roh_ende):
        """NACHGEBAUT: die Reihenfolge aus on_cut_clicked_video()."""
        versatz = self._versatz(roh_start)
        beginn = BASIS + timedelta(seconds=roh_start - versatz)
        ende = BASIS + timedelta(seconds=roh_ende - versatz)
        neu, entfernt, verworfen, interp, dauer = schneiden(self.gpx, beginn, ende)
        self.gpx = neu
        self.cm._cut_intervals.append((roh_start, roh_ende))
        # ERST nachfuehren, DANN merken - sonst wuerde die frische
        # Aufzeichnung gleich wieder verschoben.
        self.cm.aufzeichnungen_nachfuehren(beginn, -dauer)
        self.cm.aufzeichnung_merken(roh_start, roh_ende, entfernt, verworfen,
                                    interp, dauer, beginn)
        self.cm.fingerabdruck_merken(self.gpx)

    def ruecknahme(self, roh_start, roh_ende):
        """NACHGEBAUT: die Reihenfolge aus _schnitt_zuruecknehmen()."""
        aufz = self.cm.aufzeichnung(roh_start, roh_ende) or {}
        ab = aufz.get("beginn_dt")
        um = float(aufz.get("dauer_s") or 0.0)
        neu = self.cm.spur_ohne_schnitt(roh_start, roh_ende, self.gpx)
        if not neu:
            return False
        self.cm.schnitt_entfernen(roh_start, roh_ende)
        self.cm.aufzeichnungen_nachfuehren(ab, +um)
        self.gpx = neu
        self.cm.fingerabdruck_merken(self.gpx)
        return True


def gleich(a, b):
    """Lage, Hoehe und Zeit vergleichen.

    delta_m, speed_kmh und gradient bleiben aussen vor - die rechnet
    recalc_gpx_data() aus diesen Werten neu.
    """
    if len(a) != len(b):
        return False, "Anzahl: %d statt %d" % (len(a), len(b))
    for i, (x, y) in enumerate(zip(a, b)):
        if (round(float(x.get("lat", 0.0)), 9) != round(float(y.get("lat", 0.0)), 9)
                or round(float(x.get("lon", 0.0)), 9) != round(float(y.get("lon", 0.0)), 9)
                or round(float(x.get("ele", 0.0)), 4) != round(float(y.get("ele", 0.0)), 4)
                or x.get("time") != y.get("time")):
            return False, ("erste Abweichung bei Index %d: %s statt %s"
                           % (i, x.get("time"), y.get("time")))
    return True, "%d Punkte identisch" % len(a)


# ----------------------------------------------------------------------
# Die drei Pruefungen
# ----------------------------------------------------------------------
def pruefe_reihenfolge():
    """Beide Reihenfolgen muessen exakt zur Ausgangsspur zurueckfuehren."""
    ergebnisse = []
    for reihenfolge in (["B", "A"], ["A", "B"]):
        w = Werkbank()
        vorher = copy.deepcopy(w.gpx)
        w.schnitt(10.0, 15.0)   # A
        w.schnitt(30.0, 36.0)   # B
        for name in reihenfolge:
            s, e = (10.0, 15.0) if name == "A" else (30.0, 36.0)
            if not w.ruecknahme(s, e):
                ergebnisse.append((False, "%s: keine Aufzeichnung" % name))
                break
        else:
            ok, text = gleich(w.gpx, vorher)
            ergebnisse.append((ok, "%s zuerst: %s" % (reihenfolge[0], text)))
    return ergebnisse


def pruefe_projektdatei():
    """Der Weg durch die Datei darf nichts veraendern."""
    w = Werkbank()
    vorher = copy.deepcopy(w.gpx)
    w.schnitt(10.0, 15.0)
    w.schnitt(30.0, 36.0)

    # So schreibt save_project(), so liest process_open_project().
    roh = json.dumps({"cut_points": w.cm.get_cut_points(),
                      "gpx_fingerabdruck": w.cm.get_gpx_abdruck(),
                      "cut_intervals": list(w.cm._cut_intervals)},
                     indent=2, default=str)
    daten = json.loads(roh)

    geladen = VideoCutManager(StummerEditor(), StummeTimeline())
    geladen.set_video_durations([60.0])
    geladen._cut_intervals = [tuple(iv) for iv in daten["cut_intervals"]]
    anzahl = geladen.set_cut_points(daten.get("cut_points", []))
    geladen.set_gpx_abdruck(daten.get("gpx_fingerabdruck"))

    ergebnisse = [(anzahl == 2,
                   "%d von 2 Aufzeichnungen aus der Datei uebernommen "
                   "(%.1f kB)" % (anzahl, len(roh) / 1024.0))]

    # Genau der Fall, der bis 6.03 grau war.
    moeglich, grund, _ = geladen.ruecknahme_moeglich(30.0, 36.0, w.gpx)
    ergebnisse.append((moeglich,
                       "Undo Cut nach dem Laden: %s%s"
                       % ("moeglich" if moeglich else "GESPERRT",
                          "" if moeglich else " - " + grund)))

    # Und das Ergebnis muss dasselbe sein wie ohne den Weg durch die Datei.
    ohne_datei = w.cm.spur_ohne_schnitt(30.0, 36.0, w.gpx)
    aus_datei = geladen.spur_ohne_schnitt(30.0, 36.0, w.gpx)
    if aus_datei is None:
        ergebnisse.append((False, "aus der Datei kam keine Spur zurueck"))
    else:
        ok, text = gleich(aus_datei, ohne_datei)
        ergebnisse.append((ok, "Ergebnis mit und ohne Datei: " + text))
    return ergebnisse


def pruefe_verschobene_spur():
    """Nach einer Zeitaenderung muss gesperrt werden - auch nach dem Laden."""
    w = Werkbank()
    w.schnitt(10.0, 15.0)

    # Wie chT, Close Gaps oder Resample: die Zeiten wandern.
    verschoben = copy.deepcopy(w.gpx)
    for pt in verschoben:
        pt["time"] = pt["time"] + timedelta(seconds=1)

    # Der Fingerabdruck stammt noch von vorher - hier sperrt schon er.
    moeglich, _, _ = w.cm.ruecknahme_moeglich(10.0, 15.0, verschoben)
    ergebnisse = [(not moeglich, "mit altem Fingerabdruck: %s"
                   % ("gesperrt" if not moeglich else "FREIGEGEBEN"))]

    # Und jetzt derselbe Fall ueber die Projektdatei: gespeichert wird die
    # VERSCHOBENE Spur, der Abdruck stammt aber noch vom Schnitt. Genau
    # deshalb wird er mitgespeichert statt beim Laden neu gerechnet - neu
    # gerechnet passte er zur verschobenen Spur und gaebe sie frei.
    datei = json.loads(json.dumps(
        {"cut_points": w.cm.get_cut_points(),
         "gpx_fingerabdruck": w.cm.get_gpx_abdruck()}, default=str))

    geladen = VideoCutManager(StummerEditor(), StummeTimeline())
    geladen.set_video_durations([60.0])
    geladen._cut_intervals = list(w.cm._cut_intervals)
    geladen.set_cut_points(datei["cut_points"])
    geladen.set_gpx_abdruck(datei["gpx_fingerabdruck"])
    moeglich, grund, _ = geladen.ruecknahme_moeglich(10.0, 15.0, verschoben)
    ergebnisse.append((not moeglich, "nach dem Laden, Abdruck aus der Datei: %s"
                       % ("gesperrt" if not moeglich
                          else "FREIGEGEBEN - das waere still falsch")))

    # Gegenprobe: dieselbe geladene Lage, aber die unveraenderte Spur.
    moeglich, grund, _ = geladen.ruecknahme_moeglich(10.0, 15.0, w.gpx)
    ergebnisse.append((moeglich, "Gegenprobe unveraenderte Spur: %s%s"
                       % ("moeglich" if moeglich else "GESPERRT",
                          "" if moeglich else " - " + grund)))
    return ergebnisse


def main():
    schritte = [("Reihenfolge der Ruecknahme", pruefe_reihenfolge),
                ("Weg durch die Projektdatei", pruefe_projektdatei),
                ("Sperre bei veraenderten Zeiten", pruefe_verschobene_spur)]
    fehler = 0
    for titel, fn in schritte:
        print(titel)
        for ok, text in fn():
            print("  %s %s" % ("ok  " if ok else "FEHL", text))
            if not ok:
                fehler += 1
        print()
    if fehler:
        print("%d Pruefung(en) fehlgeschlagen" % fehler)
        return 1
    print("Alles in Ordnung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
