# views/overlay_setup_dialog.py

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox

class OverlaySetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay Setup (Dummy)")
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel("Hier könnte deine Overlay-Konfiguration stehen.\n(Später füllen.)")
        layout.addWidget(info_label)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(btn_box)
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
