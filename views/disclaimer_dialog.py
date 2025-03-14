# views/disclaimer_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

class DisclaimerDialog(QDialog):
    """
    Zeigt einen Haftungsausschluss (Disclaimer) mit anklickbarem Link.
    Der User muss ein Häkchen setzen, dann wird OK aktiv.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Disclaimer – Important Notice")

        layout = QVBoxLayout(self)

        # (1) HTML-Text mit Link
        # Achtung: openExternalLinks=True alleine kann buggy sein,
        # deshalb setzen wir openExternalLinks=False und fangen linkActivated ab.
        """
        disclaimer_html = (
            "<p><b>IMPORTANT:</b><br><br>"
            "You use this software at your own risk. We provide no warranty<br>"
            "and cannot be held liable for any damage or loss.<br>"
            "Commercial usage is strictly prohibited. Redistributio<br>"
            "of this application is also strictly prohibited.</p>"

            "<p>By clicking OK, you confirm acceptance of these terms.</p>"

            "<p>Additionally, by sending the fingerprint to our address,<br> "
            "you confirm that you accept our "
            "<a href='http://vgsync.casa-eller.de/vgsync_eula.pdf'>EULA</a> "
            "(opens in your default browser).</p><br>"
        )
        """
        disclaimer_html = (
            "<p><b>IMPORTANT NOTICE:</b><br><br>"
            "You use this software at your own risk. We provide no warranty<br>"
            "and cannot be held liable for any damage or loss.<br>"
            "Commercial usage is strictly prohibited. Redistribution<br>"
            "of this application is also strictly prohibited.</p>"

            "<p>By clicking OK, you confirm acceptance of these terms.</p>"

            "<p><b>Third-Party Libraries:</b><br>"
            "This application uses open-source software:</p>"
            
            "<ul>"
            "<li><b>FFmpeg</b> - <a href='https://ffmpeg.org'>ffmpeg.org</a> (LGPL v2.1 or later)</li>"
            "<li><b>mpv</b> - <a href='https://mpv.io'>mpv.io</a> (LGPL v2.1 or later)</li>"
            "</ul>"

            "<p>The full license texts can be found in the <code>LICENSES</code> inside the mpv and ffmpeg directories.</p>"

            "<p>Additionally, by sending the fingerprint to our address,<br> "
            "you confirm that you accept our "
            "<a href='http://vgsync.casa-eller.de/vgsync_eula.pdf'>EULA</a> "
            "(opens in your default browser).</p><br>"
        )


        self.label_info = QLabel()
        self.label_info.setTextFormat(Qt.RichText)
        self.label_info.setOpenExternalLinks(False)  # Wir handeln das selbst
        self.label_info.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
        self.label_info.setText(disclaimer_html)
        layout.addWidget(self.label_info)

        # (2) Signal abfangen ⇒ Linkklick
        self.label_info.linkActivated.connect(self._on_link_clicked)

        # (3) CheckBox
        self.chkConfirm = QCheckBox("I confirm I have read and accept these terms.", self)
        layout.addWidget(self.chkConfirm)

        # (4) ButtonBox => OK / Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(btn_box)

        self.btn_ok = btn_box.button(QDialogButtonBox.Ok)
        self.btn_ok.setEnabled(False)

        self.chkConfirm.stateChanged.connect(self.on_checkbox_changed)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

    def on_checkbox_changed(self, state):
        self.btn_ok.setEnabled(self.chkConfirm.isChecked())

    def _on_link_clicked(self, url: str):
        """
        Wird aufgerufen, wenn der User auf den HTML-Link klickt.
        Öffnet die URL im Standardbrowser.
        """
        QDesktopServices.openUrl(QUrl(url))
