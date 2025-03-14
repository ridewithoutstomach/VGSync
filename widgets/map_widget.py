import os
import sys
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel

from .map_bridge import MapBridge

class MapWidget(QWidget):
    """
    Neue Version: 2 Zustände => gelb (Video Play), blau (Pause-Klick).
    """
    # Signale
    pointClickedInPause = Signal(int)
    pointClickedInMap   = Signal(int)  # optional fürs MainWindow

    def __init__(self, mainwindow=None, parent=None):
        super().__init__(parent)
        self._mainwindow = mainwindow

        # Zustands-Variablen
        self._video_is_playing = False
        self._yellow_idx = None
        self._blue_idx   = None
        self._num_points = 0
        self._markB_idx  = None
        self._markE_idx  = None

        # Layout + QWebEngineView
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView(self)
        layout.addWidget(self.view)

        # Erlaubt: Remote URLs / z.B. OSM, MapTiler, Mapbox, Bing
        self.view.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )

        # WebChannel + Bridge
        self._bridge = MapBridge()
        self._bridge.pointClickedSignal.connect(self.onMapPointClicked)

        self._channel = QWebChannel()
        self._channel.registerObject("mapBridge", self._bridge)
        self.view.page().setWebChannel(self._channel)

        # map_page.html laden
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        html_path = os.path.join(base_dir, "map_page.html")
        self.view.load(QUrl.fromLocalFile(html_path))

        # Callback, wenn HTML fertig geladen ist
        self.view.loadFinished.connect(self._on_map_page_load_finished)

        # Weitere Bridge-Signale
        self._bridge.pointMovedSignal.connect(self.on_point_moved)
        self._bridge.syncClickedNoArg.connect(self._on_sync_noarg_from_js)
        self._bridge.newPointInsertedSignal.connect(self._on_new_point_inserted)

    @Slot(bool)
    def _on_map_page_load_finished(self, ok):
        """
        Wird aufgerufen, sobald map_page.html fertig geladen ist.
        Früher wurde hier der MapTiler-Key geladen,
        das macht jetzt aber NUR noch MainWindow (und sendet per JS).
        """
        if not ok:
            print("[WARN] Karte konnte nicht geladen werden.")
            return

        print("[DEBUG] Karte ist geladen ⇒ wende jetzt ggf. QSettings-Einstellungen an.")
        # Beispiel: Du könntest hier nur noch "apply map-sizes" o. Ä. aufrufen.
        # Falls du eine Funktion in MainWindow hast, z. B. _apply_map_sizes_from_settings():
        if self._mainwindow and hasattr(self._mainwindow, "_apply_map_sizes_from_settings"):
            self._mainwindow._apply_map_sizes_from_settings()

    @Slot(float, float, int)
    def _on_new_point_inserted(self, lat, lon, idx):
        """
        Ruft MainWindow.on_new_gpx_point_inserted(...) auf,
        falls vorhanden. So kann das GPX-Handling fortgesetzt werden.
        """
        if self._mainwindow and hasattr(self._mainwindow, "on_new_gpx_point_inserted"):
            self._mainwindow.on_new_gpx_point_inserted(lat, lon, idx)

    @Slot()
    def _on_sync_noarg_from_js(self):
        """
        JS => channelObj.syncClickedNoArg() => rufe mainwindow.on_map_sync_any().
        """
        if self._mainwindow and hasattr(self._mainwindow, "on_map_sync_any"):
            self._mainwindow.on_map_sync_any()

    def on_point_moved(self, index: int, lat: float, lon: float):
        """
        Wird gerufen, wenn man im Browser (Karte) einen Punkt draggt.
        Reicht an MainWindow weiter, falls on_point_moved existiert.
        """
        if self._mainwindow and hasattr(self._mainwindow, "on_point_moved"):
            self._mainwindow.on_point_moved(index, lat, lon)

    def loadRoute(self, route_geojson: dict, do_fit: bool = True):
        """
        Ruft loadRoute(...) in JS auf, um ein GeoJSON in der Karte darzustellen.
        """
        if not route_geojson or not isinstance(route_geojson, dict):
            return

        # Anzahl Points ermitteln
        features = route_geojson.get("features", [])
        self._num_points = sum(
            1 for feat in features
            if feat.get("geometry", {}).get("type") == "Point"
        )

        
        do_fit_str = "true" if do_fit else "false"
        js = f"loadRoute({json.dumps(route_geojson)}, {do_fit_str});"
        self.view.page().runJavaScript(js)

    # ----------------------------------------------------------
    # Markierungen B/E
    # ----------------------------------------------------------
    def set_markB_idx(self, b_idx: int):
        self._markB_idx = b_idx

    def set_markE_idx(self, e_idx: int):
        self._markE_idx = e_idx

    def set_markB_point(self, new_b: int):
        if new_b < 0:
            return
        self._markB_idx = new_b
        js_code = f"set_markB_point({new_b});"
        self.view.page().runJavaScript(js_code)

    def set_markE_point(self, new_e: int):
        if new_e < 0:
            return
        js_code = f"set_markE_point({new_e});"
        self.view.page().runJavaScript(js_code)

    def clear_marked_range(self):
        js_code = "clear_marked_range();"
        self.view.page().runJavaScript(js_code)

    # ----------------------------------------------------------
    # Play/Pause -> Video
    # ----------------------------------------------------------
    def set_video_playing(self, playing: bool):
        """
        Wird vom MainWindow aufgerufen, wenn Play/Pause umgeschaltet wird.
        """
        self._video_is_playing = playing
        js_bool = "true" if playing else "false"
        self.view.page().runJavaScript(f"setVideoPlayState({js_bool})")

        if playing:
            # alten blauen Marker entfernen
            if self._blue_idx is not None:
                self._color_point(self._blue_idx, "#000000", size=4)
                self._blue_idx = None
        else:
            # Bei Pause belassen wir ggf. den gelben Marker
            pass

    # ----------------------------------------------------------
    # Klick in der Karte => onMapPointClicked
    # ----------------------------------------------------------
    @Slot(int)
    def onMapPointClicked(self, index_clicked: int):
        """
        Wenn das Video pausiert, machen wir 'show_blue'.
        Danach benachrichtigen wir MainWindow, dass index_clicked geklickt wurde.
        """
        if self._video_is_playing:
            return
        self.show_blue(index_clicked)

        if self._mainwindow and hasattr(self._mainwindow, "on_user_selected_index"):
            self._mainwindow.on_user_selected_index(index_clicked)

    # ----------------------------------------------------------
    # Hilfsfunktion: JS highlightPoint(...)
    # ----------------------------------------------------------
    def _color_point(self, index: int, color: str, size: int=4, do_center: bool=False):
        """
        Intern: Ruft highlightPoint(index, color, size, do_center) in JS auf.
        """
        js_code = (
            f"highlightPoint({index}, '{color}', {size}, {str(do_center).lower()});"
        )
        self.view.page().runJavaScript(js_code)

    # ----------------------------------------------------------
    # show_blue / show_yellow
    # ----------------------------------------------------------
    def show_blue(self, index: int, do_center: bool=False):
        """
        Marker blau bei Pause-Klick.
        """
        if index < 0 or index >= self._num_points:
            return

        # Alten blauen Marker revert
        if self._blue_idx is not None and self._blue_idx != index:
            old_b = self._blue_idx
            color_old = self.get_default_color_for_index(old_b)
            self._color_point(old_b, color_old, size=4, do_center=False)
            self._blue_idx = None

        # Gelben Marker (wenn existiert) revert
        if self._yellow_idx is not None:
            old_y = self._yellow_idx
            color_old_y = self.get_default_color_for_index(old_y)
            self._color_point(old_y, color_old_y, size=4, do_center=False)
            self._yellow_idx = None

        # Jetzt den neuen Index blau
        self._blue_idx = index
        self._color_point(index, "#0000FF", size=6, do_center=do_center)

    def show_yellow(self, index: int, do_center: bool=False):
        """
        Marker gelb beim Video-Playback.
        """
        if index == self._yellow_idx:
            return
        if index < 0 or index >= self._num_points:
            return

        # alten gelben Marker revert
        if self._yellow_idx is not None:
            old_y = self._yellow_idx
            color_old = self.get_default_color_for_index(old_y)
            self._color_point(old_y, color_old, size=4, do_center=False)
            self._yellow_idx = None

        # Falls dieser Index blau war => revert
        if self._blue_idx == index:
            color_old_b = self.get_default_color_for_index(index)
            self._color_point(index, color_old_b, size=4, do_center=False)
            self._blue_idx = None

        # Neuer Index => gelb
        self._yellow_idx = index
        self._color_point(index, "#FFFF00", size=6, do_center=do_center)

    # ----------------------------------------------------------
    # Farblogik (rot bei MarkB..MarkE, sonst schwarz)
    # ----------------------------------------------------------
    def is_in_marked_range(self, idx: int) -> bool:
        if self._markB_idx is not None and self._markE_idx is not None:
            b = min(self._markB_idx, self._markE_idx)
            e = max(self._markB_idx, self._markE_idx)
            return (b <= idx <= e)
        elif self._markB_idx is not None:
            return (idx == self._markB_idx)
        elif self._markE_idx is not None:
            return (idx == self._markE_idx)
        else:
            return False

    def get_default_color_for_index(self, i: int) -> str:
        """
        - '#FF0000' (rot) in B..E
        - '#000000' sonst
        """
        if i < 0 or i >= self._num_points:
            return "#000000"

        if self._markB_idx is not None and self._markE_idx is not None:
            b = min(self._markB_idx, self._markE_idx)
            e = max(self._markB_idx, self._markE_idx)
            if b <= i <= e:
                return "#FF0000"
        elif self._markB_idx is not None:
            if i == self._markB_idx:
                return "#FF0000"
        elif self._markE_idx is not None:
            if i == self._markE_idx:
                return "#FF0000"

        return "#000000"
