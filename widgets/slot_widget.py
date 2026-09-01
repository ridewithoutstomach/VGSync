# -*- coding: utf-8 -*-
"""Ein Fenster ("Slot") der Oberflaeche, dessen Inhalt waehlbar ist.

Das Fenster selbst bleibt immer an seinem Platz im Splitter - gewechselt
wird nur, welches Modul darin liegt (Karte, Chart, Chart-Flow, GPX-Tabelle,
beim oberen Paar auch das Video).

Zum Umschalten gibt es absichtlich DREI Wege nebeneinander, damit sich im
Betrieb zeigt, welcher taugt:

  1. Kopfzeile     - schmale Leiste mit dem Modulnamen, Klick oeffnet die
                     Liste. Immer sichtbar, kostet rund 20 px Hoehe.
  2. Schwebeknopf  - erscheint nur, solange die Maus im Fenster ist, und
                     liegt ueber dem Inhalt. Kostet keinen Platz.
  3. Rechtsklick   - oeffnet dieselbe Liste, ohne jedes sichtbare Element.

Die Kopfzeilen lassen sich ueber das View-Menue ausblenden; nur dann sieht
man, was die beiden anderen Wege an Platz sparen.
"""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QToolButton, QSizePolicy,
)


KOPF_HOEHE = 20


class SlotWidget(QWidget):
    """Container fuer genau ein Modul, mit drei Wegen zum Umschalten."""

    # Der Slot meldet nur den Wunsch - welches Modul wohin wandert und was
    # dabei mit dem bisherigen Inhalt passiert, entscheidet das MainWindow.
    modulGewuenscht = Signal(str, str)   # (slot_id, modul_id)

    def __init__(self, slot_id: str, titel: str = "", parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self._modul_id = None
        self._inhalt = None
        # [(modul_id, Anzeigename)] - wird vom MainWindow gesetzt, weil nur
        # dort bekannt ist, was gerade wo liegt.
        self._auswahl = []

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(0)

        # ---- 1) Kopfzeile ----
        self._kopf = QWidget(self)
        self._kopf.setFixedHeight(KOPF_HOEHE)
        self._kopf.setCursor(Qt.PointingHandCursor)
        self._kopf.setStyleSheet(
            "background-color: #3a3a3a; border-bottom: 1px solid #555;")
        kopf_lay = QHBoxLayout(self._kopf)
        kopf_lay.setContentsMargins(6, 0, 4, 0)
        kopf_lay.setSpacing(4)

        self._titel = QLabel(titel, self._kopf)
        self._titel.setStyleSheet("color: #ddd; font-size: 11px; border: none;")
        kopf_lay.addWidget(self._titel)
        kopf_lay.addStretch(1)

        self._pfeil = QLabel("▾", self._kopf)          # kleines Dreieck
        self._pfeil.setStyleSheet("color: #ddd; font-size: 11px; border: none;")
        kopf_lay.addWidget(self._pfeil)

        # Klick auf die ganze Leiste, nicht nur auf den Pfeil.
        self._kopf.mousePressEvent = self._kopf_geklickt
        aussen.addWidget(self._kopf)

        # ---- Platz fuer das Modul ----
        self._buehne = QWidget(self)
        self._buehne_lay = QVBoxLayout(self._buehne)
        self._buehne_lay.setContentsMargins(0, 0, 0, 0)
        self._buehne_lay.setSpacing(0)
        aussen.addWidget(self._buehne, 1)

        # ---- 2) Schwebeknopf ----
        # Kind des Slots, nicht des Layouts - er liegt ueber dem Inhalt und
        # nimmt deshalb keinen Platz weg. Oben Mitte, weil die Ecken bei
        # Karte (Move/V-Sync, +/-) und Chart (Legende) schon belegt sind.
        self._knopf = QToolButton(self)
        self._knopf.setText("▾")
        self._knopf.setToolTip("Modul wechseln")
        self._knopf.setCursor(Qt.PointingHandCursor)
        self._knopf.setFixedSize(QSize(34, 18))
        self._knopf.setStyleSheet(
            "QToolButton { background: rgba(30,30,30,190); color: #eee;"
            " border: 1px solid #777; border-radius: 3px; font-size: 11px; }"
            "QToolButton:hover { background: rgba(60,60,60,230); }")
        self._knopf.clicked.connect(self._menue_zeigen)
        self._knopf.hide()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------------
    # Inhalt
    # ------------------------------------------------------------------
    def modul_id(self):
        return self._modul_id

    def inhalt(self):
        return self._inhalt

    def buehne(self):
        """Das Widget, unter dem der Inhalt haengt.

        Module sollten direkt damit als Vater erzeugt werden. Sonst muessten
        sie beim Einsetzen umgehaengt werden - und die Karte vertraegt das
        nicht, ihr natives Fenster wird dabei neu erzeugt.
        """
        return self._buehne

    def inhalt_entnehmen(self):
        """Modul aus dem Slot loesen und zurueckgeben (ohne es zu zerstoeren)."""
        w = self._inhalt
        if w is not None:
            self._buehne_lay.removeWidget(w)
            w.setParent(None)
        self._inhalt = None
        self._modul_id = None
        return w

    def inhalt_setzen(self, modul_id: str, widget: QWidget, titel: str):
        self._modul_id = modul_id
        self._inhalt = widget
        self._titel.setText(titel)
        self._buehne_lay.addWidget(widget)
        widget.show()
        self._knopf.raise_()

    def auswahl_setzen(self, eintraege):
        """eintraege: Liste aus (modul_id, Anzeigename).

        Leere Liste heisst: hier gibt es nichts zu waehlen (Video-Fenster).
        Dann verschwinden auch Pfeil und Schwebeknopf - ein Bedienelement,
        das auf nichts reagiert, ist schlimmer als keines.
        """
        self._auswahl = list(eintraege)
        hat_wahl = bool(self._auswahl)
        self._pfeil.setVisible(hat_wahl)
        self._kopf.setCursor(Qt.PointingHandCursor if hat_wahl else Qt.ArrowCursor)
        if not hat_wahl:
            self._knopf.hide()

    def kopf_zeigen(self, an: bool):
        self._kopf.setVisible(bool(an))

    # ------------------------------------------------------------------
    # Die drei Wege zum Menue
    # ------------------------------------------------------------------
    def _kopf_geklickt(self, event):
        self._menue_zeigen()

    def contextMenuEvent(self, event):
        # Nur greifen, wenn das Modul selbst kein eigenes Kontextmenue hat -
        # sonst wuerde der Slot der Timeline oder der Karte ihres wegnehmen.
        self._menue_zeigen()
        event.accept()

    def _menue_zeigen(self):
        if not self._auswahl:
            return
        menue = QMenu(self)
        for modul_id, name in self._auswahl:
            a = QAction(name, menue)
            a.setCheckable(True)
            a.setChecked(modul_id == self._modul_id)
            a.triggered.connect(
                lambda _=False, m=modul_id: self.modulGewuenscht.emit(self.slot_id, m))
            menue.addAction(a)
        menue.exec(QCursor.pos())

    # ------------------------------------------------------------------
    # Schwebeknopf ein-/ausblenden und platzieren
    # ------------------------------------------------------------------
    def enterEvent(self, event):
        super().enterEvent(event)
        if not self._auswahl:
            return
        self._knopf_platzieren()
        self._knopf.show()
        self._knopf.raise_()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._knopf.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._knopf_platzieren()

    def _knopf_platzieren(self):
        oben = KOPF_HOEHE + 2 if self._kopf.isVisible() else 2
        self._knopf.move(max(0, (self.width() - self._knopf.width()) // 2), oben)
