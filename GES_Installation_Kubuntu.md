# GES-Vorschau unter Kubuntu einrichten

Anleitung fuer das GStreamer/GES-Wiedergabe-Backend von KVRouite 6.0 unter
Kubuntu/Ubuntu. Stand 29.08.2026, Branch `dev_6.0GES`.

Ohne dieses Backend laeuft KVRouite wie bisher mit mpv - dann ist hier nichts
zu tun. Das GES-Backend wird nur gebraucht, damit **Ueberblendungen schon in
der Vorschau sichtbar** sind. mpv bleibt die Vorgabe.

Unter Windows kommt GStreamer als pip-Wheel (`requirements-ges.txt`, eine
Zeile). Unter Linux gibt es keine Wheels - dort kommt alles aus der
Distribution. Genau darum geht es hier.

---

## Kurzfassung

```bash
sudo apt update
sudo apt install ffmpeg libmpv-dev python3-venv git
sudo apt install python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-ges-1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-x

cd KVRouite
python3 -m venv --system-site-packages venv     # das Flag ist Pflicht!
source venv/bin/activate
pip install -r requirements.txt                 # NICHT requirements-ges.txt
python3 check_ges.py
python3 KVRouite.py
```

Danach in der Anwendung: **Config -> Video Backend -> ges**, dann neu starten.

Die beiden Punkte, an denen es sonst haengt, stehen in Schritt 3 und Schritt 5.

---

## Schritt 1 - Release feststellen

```bash
lsb_release -a
```

Welche GStreamer-Version dein Kubuntu mitbringt, haengt am Release:

| Release            | GStreamer / GES |
|--------------------|-----------------|
| 22.04 LTS jammy    | 1.20.1          |
| 24.04 LTS noble    | 1.24.2          |
| 25.10 questing     | 1.26.6          |
| 26.04 LTS resolute | 1.28.2          |

Unter Windows benutzt KVRouite 1.28.6. Das Backend verwendet keine API, die
juenger als 1.24 ist - ab 24.04 sollte es also passen. Wer nah an der
Windows-Version sein will, ist mit 26.04 (1.28.2) praktisch gleichauf.

Unter 22.04 (1.20) ist es ungetestet und eher unwahrscheinlich.

---

## Schritt 2 - Grundpakete

Die braucht KVRouite unabhaengig vom Backend:

```bash
sudo apt update
sudo apt install ffmpeg libmpv-dev python3-venv git
```

`ffmpeg` bleibt auch mit GES noetig: das Rendern laeuft weiterhin komplett
ueber ffmpeg, und auch die Blenden, die die Vorschau anzeigt, werden vorher
mit ffmpeg erzeugt.

---

## Schritt 3 - GStreamer und GES

```bash
sudo apt install python3-gi python3-gi-cairo \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-ges-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-x
```

Was die Pakete tun:

| Paket | wofuer |
|---|---|
| `python3-gi`, `python3-gi-cairo` | PyGObject - die Bruecke von Python zu GStreamer |
| `gir1.2-gstreamer-1.0` | Typelib fuer `Gst` |
| `gir1.2-gst-plugins-base-1.0` | Typelib fuer `GstVideo` (Fenstereinbettung) |
| `gir1.2-ges-1.0` | Typelib fuer `GES` - zieht `libges-1.0-0` nach, und darin stecken die eigentlichen Engine-Plugins `libgstnle.so` und `libgstges.so` |
| `gstreamer1.0-plugins-base/good/bad/ugly` | Demuxer, Parser, Konverter |
| `gstreamer1.0-libav` | H.264/H.265-Dekodierung (`avdec_h264`) |
| `gstreamer1.0-gl` | `glimagesink` - die bevorzugte Video-Senke |
| `gstreamer1.0-x` | `xvimagesink` als Rueckfallebene |

**Falls apt `gir1.2-ges-1.0` nicht findet:** das Paket liegt in der
Komponente *universe*, nicht in *main*. Auf einem Desktop-Kubuntu ist
universe normalerweise aktiv; sonst einmalig:

```bash
sudo add-apt-repository universe
sudo apt update
```

Kein Selbstbauen, kein Cerbero, kein MSYS2-Aequivalent. Genau daran ist der
Versuch von 2025 unter Windows gescheitert; unter Linux stellt sich die Frage
gar nicht erst.

---

## Schritt 4 - Projekt holen

```bash
git clone https://github.com/ridewithoutstomach/KVRouite.git
cd KVRouite
git checkout dev_6.0GES
```

---

## Schritt 5 - venv anlegen (der wichtige Teil)

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

**`--system-site-packages` ist nicht optional.** `python3-gi` ist ein
Systempaket und liegt in `/usr/lib/python3/dist-packages`. Ein normales venv
blendet dieses Verzeichnis aus - `import gi` scheitert dann mit
`ModuleNotFoundError`, obwohl alles korrekt installiert ist. Das ist der
Fehler, den man sonst eine Stunde lang sucht.

Ein bereits bestehendes venv laesst sich nicht nachtraeglich umstellen. Wenn
du schon eins hast: loeschen und neu anlegen.

```bash
rm -rf venv
python3 -m venv --system-site-packages venv
```

**`requirements-ges.txt` wird unter Linux nicht installiert.** Darin steht
`gstreamer-bundle`, und dafuer gibt es keine Linux-Wheels. pip wuerde
versuchen, aus dem Quelltext zu bauen, und das endet im Compiler.

---

## Schritt 6 - pruefen

```bash
python3 check_ges.py
```

Das Skript startet die Anwendung nicht und veraendert nichts. Es prueft der
Reihe nach PySide6, PyGObject, die drei Typelibs, die GES-Engine, eine
brauchbare Video-Senke, einen H.264-Dekoder und ffmpeg - und nennt bei jedem
Fehlschlag das Paket, das fehlt. Erwartete Ausgabe sinngemaess:

```
Python   3.12.3  (Linux x86_64)
  ok       PySide6 6.11.2
  ok       PyGObject 3.48.2
  ok       GStreamer 1.24.2
  ok       GES-Engine (nle, ges)
  ok       GES-Timeline
  ok       Video-Senke: glimagesink, xvimagesink, autovideosink
  ok       H.264-Dekoder: avdec_h264
  ok       ffmpeg: /usr/bin/ffmpeg
  ok       ffprobe: /usr/bin/ffprobe
  ok       Sitzung: x11
```

Rueckgabewert 0 heisst vollstaendig, 1 heisst es fehlt etwas.

---

## Schritt 7 - Backend umschalten

```bash
python3 KVRouite.py
```

In der Anwendung **Config -> Video Backend -> ges** waehlen. Die Umstellung
wirkt erst nach einem Neustart, weil der Player beim Start aufgebaut wird.

Die Einstellung liegt in `~/.config/KVRouite/KVRouite.conf` unter
`[player] backend=ges`. Falls die Anwendung mit GES nicht mehr startet,
laesst sich das dort von Hand auf `mpv` zuruecksetzen - oder notfalls:

```bash
rm ~/.config/KVRouite/KVRouite.conf
```

Damit gehen allerdings auch die uebrigen Oberflaechen-Einstellungen verloren.

---

## Wenn etwas klemmt

| Meldung / Bild | Ursache | Abhilfe |
|---|---|---|
| `ModuleNotFoundError: No module named 'gi'` | venv ohne `--system-site-packages` | venv loeschen und mit dem Flag neu anlegen (Schritt 5) |
| `ValueError: Namespace GES not available` | Typelib fehlt | `sudo apt install gir1.2-ges-1.0` |
| `ValueError: Namespace GstVideo not available` | Typelib fehlt | `sudo apt install gir1.2-gst-plugins-base-1.0` |
| `Keine brauchbare GStreamer-Video-Senke gefunden` | weder glimagesink noch xvimagesink vorhanden | `sudo apt install gstreamer1.0-gl gstreamer1.0-x` |
| Ton laeuft, Bild bleibt schwarz | Fenstereinbettung ueber das X11-Handle schlaegt fehl, vermutlich Wayland-Sitzung | `QT_QPA_PLATFORM=xcb python3 KVRouite.py` |
| `No such element: ...` beim Abspielen | Plugin-Satz unvollstaendig | `sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav` |
| Ruckeln bei 4K, `check_ges.py` meldet nur `avdec_h264` | keine Hardware-Dekodierung | `sudo apt install gstreamer1.0-vaapi` plus Treiber (`intel-media-va-driver` bei Intel, `mesa-va-drivers` bei AMD) |
| `ffmpeg nicht im PATH` | Grundpaket fehlt | `sudo apt install ffmpeg` |

Zum genaueren Hinsehen hilft GStreamers eigene Ausgabe:

```bash
GST_DEBUG=2 python3 KVRouite.py
```

Stufe 2 zeigt Warnungen und Fehler, ab Stufe 4 wird es sehr gespraechig.

---

## Wieder entfernen

Alles Installierte sind normale apt-Pakete, ausserhalb der Paketverwaltung
liegt nichts:

```bash
sudo apt remove --purge python3-gi python3-gi-cairo \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-ges-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-x
sudo apt autoremove
```

Vorsicht: `python3-gi` und die Basis-Plugins haengen unter KDE an anderen
Programmen. Vor dem Ausfuehren die Liste lesen, die apt zum Entfernen
vorschlaegt. Wer nur das GES-Backend loswerden will, kommt mit dem Umschalten
auf mpv aus - dann wird von alldem nichts mehr geladen.

Das venv liegt komplett im Projektordner und verschwindet mit `rm -rf venv`.

---

## Was noch offen ist

Diese Anleitung ist gegen das Ubuntu-Paketarchiv geprueft: Paketnamen,
Versionen, Komponenten und der Inhalt von `libges-1.0-0` sind belegt. Ein
tatsaechlicher Durchlauf auf Kubuntu hat noch nicht stattgefunden - das
Backend lief bisher nur unter Windows mit 1.28.6.

Konkret ungeprueft:

- ob 1.24.2 sich in jedem Detail wie 1.28.6 verhaelt (die verwendete API gibt
  es dort, das Verhalten ist damit noch nicht bewiesen)
- die Fenstereinbettung auf einer Wayland-Sitzung
- Hardware-Dekodierung ueber VA-API

Wenn `check_ges.py` durchlaeuft und ein Projekt mit einer Blende sauber
abspielt, ist der Weg bestaetigt.

---

## Unterschied zu Windows, in einem Satz

Windows bekommt GStreamer als pip-Wheel ins venv und spaeter durch
PyInstaller in den Installer gepackt - der Endanwender installiert nichts
zusaetzlich. Linux nimmt die Distributionspakete, so wie heute schon bei
ffmpeg und libmpv.
