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

# core/overlay_library.py
"""Bibliothek der Overlay-Bilder.

Frueher gab es genau drei feste Plaetze in den Einstellungen
("overlay/1..3"), gepflegt im Overlay-Setup. Alles darueber hinaus musste
beim Einfuegen jedes Mal neu eingetippt werden - Bild, Ecke, Abstaende - und
war danach wieder vergessen.

Hier liegt stattdessen eine Liste beliebiger Laenge. Aufgenommen wird aber
nur, was ausdruecklich behalten werden soll: ein einmal benutztes Bild
verschwindet wieder, sonst stehen nach ein paar Jahren tausend Eintraege
darin, durch die niemand mehr durchsieht.

Die drei alten Plaetze wandern beim ersten Zugriff einmalig herueber; sie
bleiben unangetastet stehen, damit nichts verlorengeht.
"""

import json
import os

from PySide6.QtCore import QSettings

#: Schluessel der Bibliothek in den Einstellungen. Der Inhalt ist JSON - eine
#: Liste von Woerterbuechern laesst sich in QSettings sonst nicht sauber
#: ablegen, ohne es in Einzelschluessel zu zerlegen.
SCHLUESSEL = "overlay/bibliothek"

#: Die alten festen Plaetze, aus denen einmalig uebernommen wird.
ALTE_PLAETZE = (1, 2, 3)

ECKEN = ("top-left", "top-right", "bottom-left", "bottom-right", "center")


def _einstellungen():
    return QSettings("KVRouite", "KVRouite")


def ausdruecke(ecke, dx, dy):
    """Ecke + Abstaende -> die beiden Koordinatenausdruecke.

    Zeichengleich zu dem, was Overlay-Setup und der alte Einfuegedialog
    erzeugen. Die Ausdruecke werden spaeter mit W/H (Videogroesse) und w/h
    (Overlaygroesse) ausgewertet, in der Vorschau wie im Export mit derselben
    Funktion - deshalb darf es hier keine zweite Lesart geben.
    """
    dx = int(dx or 0)
    dy = int(dy or 0)
    if ecke == "top-left":
        return f"{dx}", f"{dy}"
    if ecke == "top-right":
        return f"(W-w)-{dx}", f"{dy}"
    if ecke == "bottom-left":
        return f"{dx}", f"(H-h)-{dy}"
    if ecke == "bottom-right":
        return f"(W-w)-{dx}", f"(H-h)-{dy}"
    return f"((W-w)/2)-{dx}", f"((H-h)/2)-{dy}"


def _saeubern(eintrag):
    """Einen Eintrag auf die erwartete Form bringen, oder None."""
    if not isinstance(eintrag, dict):
        return None
    pfad = str(eintrag.get("pfad", "") or "").strip()
    if not pfad:
        return None
    ecke = str(eintrag.get("ecke", "top-left") or "top-left")
    if ecke not in ECKEN:
        ecke = "top-left"
    try:
        skalierung = float(eintrag.get("scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        skalierung = 1.0
    try:
        dx = int(eintrag.get("dx", 10) or 0)
        dy = int(eintrag.get("dy", 10) or 0)
    except (TypeError, ValueError):
        dx, dy = 10, 10
    return {"pfad": pfad, "scale": skalierung, "ecke": ecke, "dx": dx, "dy": dy}


def _aus_alten_plaetzen():
    """Die drei alten Einstellungsplaetze als Bibliothekseintraege."""
    s = _einstellungen()
    raus = []
    for i in ALTE_PLAETZE:
        pfad = str(s.value(f"overlay/{i}/image", "", str) or "").strip()
        if not pfad:
            continue
        eintrag = _saeubern({
            "pfad": pfad,
            "scale": s.value(f"overlay/{i}/scale", 1.0, float),
            "ecke": s.value(f"overlay/{i}/corner", "top-left", str),
            "dx": s.value(f"overlay/{i}/dx", 10, int),
            "dy": s.value(f"overlay/{i}/dy", 10, int),
        })
        if eintrag:
            raus.append(eintrag)
    return raus


def eintraege():
    """Alle Bibliothekseintraege, aelteste zuerst.

    Beim allerersten Aufruf werden die drei alten Plaetze uebernommen, damit
    vorhandene Overlays nicht ploetzlich fehlen.
    """
    s = _einstellungen()
    roh = s.value(SCHLUESSEL, "", str)
    if roh is None or str(roh).strip() == "":
        gewandert = _aus_alten_plaetzen()
        if gewandert:
            speichern(gewandert)
        return gewandert
    try:
        liste = json.loads(roh)
    except (ValueError, TypeError):
        return []
    if not isinstance(liste, list):
        return []
    return [e for e in (_saeubern(x) for x in liste) if e]


def speichern(liste):
    s = _einstellungen()
    sauber = [e for e in (_saeubern(x) for x in (liste or [])) if e]
    s.setValue(SCHLUESSEL, json.dumps(sauber, ensure_ascii=False))
    s.sync()
    return sauber


def _gleicher_pfad(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def enthalten(pfad):
    return any(_gleicher_pfad(e["pfad"], pfad) for e in eintraege())


def aufnehmen(pfad, scale=1.0, ecke="top-left", dx=10, dy=10):
    """Bild in die Bibliothek aufnehmen. Ein bereits vorhandenes wird ersetzt.

    True, wenn danach ein Eintrag dafuer existiert.
    """
    eintrag = _saeubern({"pfad": pfad, "scale": scale, "ecke": ecke,
                         "dx": dx, "dy": dy})
    if eintrag is None:
        return False
    liste = [e for e in eintraege() if not _gleicher_pfad(e["pfad"], eintrag["pfad"])]
    liste.append(eintrag)
    speichern(liste)
    return True


def entfernen(pfad):
    """Eintrag entfernen. Die Bilddatei selbst wird nicht angefasst."""
    vorher = eintraege()
    nachher = [e for e in vorher if not _gleicher_pfad(e["pfad"], pfad)]
    if len(nachher) == len(vorher):
        return False
    speichern(nachher)
    return True
