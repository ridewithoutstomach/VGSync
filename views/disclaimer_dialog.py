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
        
        disclaimer_html = (
            "<p><b>IMPORTANT NOTICE (GPLv3 Disclaimer):</b><br><br>"
            "This software is provided under the terms of the "
            "<a href='https://www.gnu.org/licenses/gpl-3.0.en.html'>GNU General Public License v3 (GPLv3)</a>. "
            "You may redistribute it and/or modify it under these terms.<br><br>"
    
            "<b>No Warranty:</b><br>"
            "THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW.<br> "
            "EXCEPT WHEN OTHERWISE STATED IN WRITING, THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES<br> "
            "PROVIDE THE PROGRAM “AS IS” WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED,<br> "
            "INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS<br> "
            "FOR A PARTICULAR PURPOSE. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM<br> "
            "IS WITH YOU. SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY<br> "
            "SERVICING, REPAIR OR CORRECTION.<br><br>"
            
            "<b>Patent Encumbrance Notice:</b><br>"
            "Some codecs (e.g., x264, x265, AAC, MP3, AC-3, DTS) may be patent-encumbered<br> "
            "in certain jurisdictions.<br> "
            "It is the user's responsibility to ensure compliance with all applicable laws and regulations,<br> "
            "and to obtain any necessary patent licenses.<br><br>"
        
            "By clicking OK or using this software, you confirm that you have read and accept<br> "
            "these terms, including the GPLv3 License.<br><br>"
            
            "<b>Third-Party Libraries:</b><br>"
            "This application includes and distributes open-source libraries:<br>"
            "<ul>"
            "<li><b>FFmpeg 7.1 (GPL build)</b> – GPL-3.0-or-later – "
            "<a href='https://ffmpeg.org'>ffmpeg.org</a></li>"
            "<li><b>GStreamer 1.28.6, incl. GStreamer Editing Services (GES) "
            "and PyGObject</b> – LGPL-2.1-or-later; the bundled x264 and x265 "
            "encoder plugins are GPL-2.0-or-later – "
            "<a href='https://gstreamer.freedesktop.org'>gstreamer.freedesktop.org</a></li>"
            "</ul>"
            "GStreamer is what plays, cuts and renders video in KVRouite, so it is "
            "always loaded.<br>"
            "On Linux, GStreamer is not distributed with KVRouite at all – it is "
            "installed<br>from your distribution's own packages.<br><br>"
            "Full license texts for these libraries are located in the <br>"
            "<code>_internal/ffmpeg</code> and <code>_internal/gstreamer</code> "
            "folders.<br>"
            "Corresponding source code for FFmpeg is available at<br>"
            "<a href='https://kvrouite.com/downloads/index.php'>kvrouite.com/downloads</a>. "
            "The GStreamer binaries are the GStreamer Project's own, passed on<br>"
            "unchanged; their source is published by that project at "
            "<a href='https://gstreamer.freedesktop.org/src/'>gstreamer.freedesktop.org/src</a><br>"
            "in the same version - see <code>_internal/gstreamer/CORRESPONDING-SOURCE.txt</code>.<br>"
            "Either way you may request the sources from "
            "<a href='mailto:bernd@kvrouite.com'>bernd@kvrouite.com</a><br>"
            "for at least three (3) years.<br><br>"
            
            
            "</p>"
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
