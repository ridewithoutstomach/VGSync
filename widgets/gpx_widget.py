# widgets/gpx_widget.py

from PySide6.QtWidgets import QWidget, QVBoxLayout
from .gpx_list_widget import GPXListWidget

class GPXWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.gpx_list = GPXListWidget(self)
        layout.addWidget(self.gpx_list)

    def set_gpx_data(self, data):
        self.gpx_list.set_gpx_data(data)

    def highlight_video_time(self, current_s: float, is_playing: bool):
        self.gpx_list.highlight_video_time(current_s, is_playing)

    def get_closest_index_for_time(self, current_s: float) -> int:
        return self.gpx_list.get_closest_index_for_time(current_s)
        
    def set_video_playing(self, playing: bool):
        """ Delegiert an die Methode der gpx_list. """
        self.gpx_list.set_video_playing(playing)    

    def set_flag(self, index: int, color: str, size: int, label_text: str):
        """
        Weist JavaScript an, ein Flag an Punkt 'index' zu setzen,
        z.B. mit bestimmter Farbe und Label (B/E).
        """
        js_code = (
            f"setFlag({index}, '{color}', {size}, '{label_text}')"
        )
        self.view.page().runJavaScript(js_code)
        
    def remove_all_flags(self):
        """
        Weist JavaScript an, alle Flag-Icons zu entfernen.
        """
        js_code = "removeAllFlags();"
        self.view.page().runJavaScript(js_code)    