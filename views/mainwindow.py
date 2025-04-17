# -*- coding: utf-8 -*-
#
# This file is part of VGSync.
#
# Copyright (C) 2025 by Bernd Eller
#
# VGSync is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# VGSync is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with VGSync. If not, see <https://www.gnu.org/licenses/>.
#

# views/mainwindow.py
import os
import sys
import platform
import subprocess
import json
import shutil
import base64
import config
import path_manager  # your module above
import urllib.request
import copy
import tempfile
import datetime
import math
import platform
import subprocess
import re
import uuid
import hashlib



            


from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCore import QSettings

from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QGuiApplication
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtGui import QIcon


from PySide6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QFrame,
    QFileDialog, QMessageBox, QVBoxLayout,
    QLabel, QProgressBar, QHBoxLayout, QPushButton, QDialog,
    QApplication, QInputDialog, QSplitter, QSystemTrayIcon,
    QFormLayout, QComboBox, QSpinBox
)
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtWidgets import QLineEdit, QDialogButtonBox



from .encoder_setup_dialog import EncoderSetupDialog  # Import Dialog

from config import TMP_KEYFRAME_DIR, MY_GLOBAL_TMP_DIR, is_soft_opengl_enabled, set_soft_opengl_enabled

from widgets.video_editor_widget import VideoEditorWidget
from widgets.video_timeline_widget import VideoTimelineWidget
from widgets.video_control_widget import VideoControlWidget
from widgets.chart_widget import ChartWidget
from widgets.map_widget import MapWidget
from widgets.gpx_widget import GPXWidget
from widgets.gpx_control_widget import GPXControlWidget

from managers.step_manager import StepManager
from managers.end_manager import EndManager
from managers.cut_manager import VideoCutManager
from core.gpx_parser import parse_gpx  # Hier hinzufügen!

from managers.overlay_manager import OverlayManager

# ggf. import_export_manager, safe_manager etc.
from .dialogs import _IndexingDialog, _SafeExportDialog, DetachDialog
from widgets.mini_chart_widget import MiniChartWidget
from config import is_edit_video_enabled, set_edit_video_enabled
from core.gpx_parser import parse_gpx, ensure_gpx_stable_ids  # <--- Achte auf diesen Import!
from core.gpx_parser import recalc_gpx_data
from tools.merge_keyframes_incremental import merge_keyframes_incremental
from config import APP_VERSION

from path_manager import is_valid_mpv_folder
from core.gpx_parser import recalc_gpx_data
from config import reset_config
from managers.encoder_manager import EncoderDialog

from datetime import datetime, timedelta


class MainWindow(QMainWindow):
    def __init__(self, user_wants_editing=False):
        
        super().__init__()
        
        self._counter_url = "http://vgsync.casa-eller.de/project/counter.php"
        
        
        self._maptiler_key = ""
        self._bing_key     = ""
        self._mapbox_key   = ""
        
        self._load_map_keys_from_settings()
        
        
               
       
        self._userDeclinedIndexing = False
        
        
        self._video_at_end = False   # Merker, ob wir wirklich am Ende sind
        self._autoSyncVideoEnabled = False
        self._autoSyncNewPointsWithVideoTime = False
        self.user_wants_editing = user_wants_editing
        
        
        
        self.setWindowTitle(f"VGSync v{APP_VERSION} - the simple Video and GPX-Sync Tool")
            
        
            
            
        
        
        
        self._map_floating_dialog = None
        self._map_placeholder = None
        
               
        self._gpx_data = []
        
        # Abkoppel-Dialoge
        self._video_area_floating_dialog = None
        self._video_placeholder = None
        

        # Playlist / Keyframe-Daten
        self.playlist = []
        self.video_durations = []
        self.playlist_counter = 0
        self.first_video_frame_shown = False
        self.real_total_duration = 0.0
        self.global_keyframes = []

        # Menüs
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        self.playlist_menu = menubar.addMenu("Playlist")
        
        load_gpx_action = QAction("Open GPX", self)
        load_gpx_action.triggered.connect(self.load_gpx_file)
        file_menu.addAction(load_gpx_action)


        load_mp4_action = QAction("Open MP4", self)
        load_mp4_action.triggered.connect(self.load_mp4_files)
        file_menu.addAction(load_mp4_action)
        

        dummy_action = QAction("New Project", self)
        file_menu.addAction(dummy_action)
        dummy_action.triggered.connect(self._on_new_project_triggered)
        
        view_menu = menubar.addMenu("View")

        classic_view_action = view_menu.addAction("Edit mode")
        classic_view_action.triggered.connect(self._set_classic_view)

        gpx_create_mode_action = view_menu.addAction("Create mode")
        gpx_create_mode_action.triggered.connect(self._set_map_video_view)

        self.action_toggle_video = QAction("Video (detach)", self)
        self.action_toggle_video.triggered.connect(self._toggle_video)
        view_menu.addAction(self.action_toggle_video)

        self.action_toggle_map = QAction("Map (detach)", self)
        self.action_toggle_map.triggered.connect(self._toggle_map)
        view_menu.addAction(self.action_toggle_map)
        
        
        setup_menu = menubar.addMenu("Config")
        
        
        # Neues Untermenü "Edit Video" mit drei checkbaren Actions
        edit_video_menu = setup_menu.addMenu("Edit Video")

        self.off_action = QAction("Off", self, checkable=True)
        self.copy_action = QAction("Copy-Mode", self, checkable=True)
        self.encode_action = QAction("Encode-Mode", self, checkable=True)

        self.edit_mode_group = QActionGroup(self)
        self.edit_mode_group.setExclusive(True)

        self.edit_mode_group.addAction(self.off_action)
        self.edit_mode_group.addAction(self.copy_action)
        self.edit_mode_group.addAction(self.encode_action)

        edit_video_menu.addAction(self.off_action)
        edit_video_menu.addAction(self.copy_action)
        edit_video_menu.addAction(self.encode_action)

        # Standard = Off
        self.off_action.setChecked(True)
        self._edit_mode = "off"
        self._userDeclinedIndexing = False  # Falls du es schon hattest

        # Verknüpfe klick => _set_edit_mode(...)
        self.off_action.triggered.connect(lambda: self._set_edit_mode("off"))
        self.copy_action.triggered.connect(lambda: self._set_edit_mode("copy"))
        self.encode_action.triggered.connect(lambda: self._set_edit_mode("encode"))
       
        
        
        
        self.encoder_setup_action = QAction("Encoder-Setup", self)
        self.encoder_setup_action.setEnabled(False)  # am Anfang ausgegraut
        setup_menu.addAction(self.encoder_setup_action)
        self.encoder_setup_action.triggered.connect(self._on_encoder_setup_clicked)
        
        self.overlay_setup_action = QAction("Overlay-Setup", self)
        self.overlay_setup_action.setEnabled(False)  # Standard: ausgegraut
        setup_menu.addAction(self.overlay_setup_action)
        self.overlay_setup_action.triggered.connect(self._on_overlay_setup_clicked)
        
        
        
        
        self.action_auto_sync_video = QAction("AutoCutVideo+GPX", self)
        self.action_auto_sync_video.setCheckable(True)
        self.action_auto_sync_video.setChecked(False)  # Standard = OFF
        self.action_auto_sync_video.triggered.connect(self._on_auto_sync_video_toggled)
        setup_menu.addAction(self.action_auto_sync_video)
        
        timer_menu = setup_menu.addMenu("Time: Final/Glogal")

        self.timer_action_group = QActionGroup(self)
        self.timer_action_group.setExclusive(True)

        self.action_global_time = QAction("Global Time", self)
        self.action_global_time.setCheckable(True)

        self.action_final_time = QAction("Final Time", self)
        self.action_final_time.setCheckable(True)

        self.timer_action_group.addAction(self.action_global_time)
        self.timer_action_group.addAction(self.action_final_time)
        
       
        
        
        
        
        ffmpeg_menu = setup_menu.addMenu("FFmpeg")

        action_show_ffmpeg_path = QAction("Show current path", self)
        action_show_ffmpeg_path.triggered.connect(self._on_show_ffmpeg_path)
        ffmpeg_menu.addAction(action_show_ffmpeg_path)
        
        action_set_ffmpeg_path = QAction("Set ffmpeg Path...", self)
        action_set_ffmpeg_path.triggered.connect(self._on_set_ffmpeg_path)
        ffmpeg_menu.addAction(action_set_ffmpeg_path)
    
        action_clear_ffmpeg_path = QAction("Clear ffmpeg Path", self)
        action_clear_ffmpeg_path.triggered.connect(self._on_clear_ffmpeg_path)
        ffmpeg_menu.addAction(action_clear_ffmpeg_path)
        
        mpv_menu = setup_menu.addMenu("libmpv")
        action_show_mpv_path = QAction("Show current libmpv path", self)
        action_show_mpv_path.triggered.connect(self._on_show_mpv_path)
        mpv_menu.addAction(action_show_mpv_path)

        action_set_mpv_path = QAction("Set libmpv path...", self)
        action_set_mpv_path.triggered.connect(self._on_set_mpv_path)
        mpv_menu.addAction(action_set_mpv_path)

        action_clear_mpv_path = QAction("Clear libmpv path", self)
        action_clear_mpv_path.triggered.connect(self._on_clear_mpv_path)
        mpv_menu.addAction(action_clear_mpv_path)

        
        
        chart_menu = setup_menu.addMenu("Chart-Settings")
        limit_speed_action = QAction("Limit Speed...", self)
        chart_menu.addAction(limit_speed_action)
        limit_speed_action.triggered.connect(self._on_set_limit_speed)
        
        zero_speed_action = QAction("ZeroSpeed...", self)
        zero_speed_action.triggered.connect(self._on_zero_speed_action)
        chart_menu.addAction(zero_speed_action)
        
        
        action_mark_stops = QAction("Mark Stops...", self)
        action_mark_stops.triggered.connect(self._on_set_stop_threshold)
        chart_menu.addAction(action_mark_stops)
        
        map_setup_menu = setup_menu.addMenu("Map Setup")
        
        
        
        # Action 1: Size Yellow Point
        
         # Action 3: Size Black Point
        action_size_black = QAction("Size Black Point", self)
        action_size_black.triggered.connect(lambda: self._on_set_map_point_size("black"))
        map_setup_menu.addAction(action_size_black)
        
        action_size_red = QAction("Size Red Point", self)
        action_size_red.triggered.connect(lambda: self._on_set_map_point_size("red"))
        map_setup_menu.addAction(action_size_red)
        
        # Action 2: Size blue Point
        action_size_blue = QAction("Size Blue Point", self)
        action_size_blue.triggered.connect(lambda: self._on_set_map_point_size("blue"))
        map_setup_menu.addAction(action_size_blue)
        
        
        action_size_yellow = QAction("Size Yellow Point", self)
        action_size_yellow.triggered.connect(lambda: self._on_set_map_point_size("yellow"))
        map_setup_menu.addAction(action_size_yellow)
        
        
        self._directions_enabled = False  # beim Start immer aus

        # 2) Eine neue Check-Action anlegen
        self.action_map_directions = QAction("Directions", self)
        self.action_map_directions.setCheckable(True)
        self.action_map_directions.setChecked(False)  # standard: aus
        

        # 3) Ins Menü einfügen
        map_setup_menu.addAction(self.action_map_directions)

        # 4) Signal verknüpfen
        self.action_map_directions.triggered.connect(self._on_map_directions_toggled)
        
        
        mapviews_menu = map_setup_menu.addMenu("MapViews")
        
        # --> About Keys
        about_keys_action = QAction("About Keys...", self)
        about_keys_action.triggered.connect(self._on_about_keys)
        mapviews_menu.addAction(about_keys_action)


        action_set_maptiler_key = QAction("Set MapTiler Key...", self)
        action_set_maptiler_key.triggered.connect(self._on_set_maptiler_key)
        mapviews_menu.addAction(action_set_maptiler_key)

       

        # --> Set Mapbox Key
        action_set_mapbox_key = QAction("Set Mapbox Key...", self)
        action_set_mapbox_key.triggered.connect(self._on_set_mapbox_key)
        mapviews_menu.addAction(action_set_mapbox_key)
        
        self.action_new_pts_video_time = QAction("Sync all with video", self)
        self.action_new_pts_video_time.setCheckable(True)
        self.action_new_pts_video_time.setChecked(False)  # Standard = OFF
        self.action_new_pts_video_time.triggered.connect(self._on_sync_point_video_time_toggled)
        setup_menu.addAction(self.action_new_pts_video_time)
                
        self.action_enable_soft_opengl = QAction("Use sofware OpenGL", self)
        self.action_enable_soft_opengl.setCheckable(True)
        self.action_enable_soft_opengl.setChecked(config.is_soft_opengl_enabled())  
        self.action_enable_soft_opengl.triggered.connect(self._on_enable_soft_opengl_toggled)
        setup_menu.addAction(self.action_enable_soft_opengl)
        
        reset_config_action = QAction("Reset Config", self)
        reset_config_action.triggered.connect(self._on_reset_config_triggered)
        setup_menu.addAction(reset_config_action)
        

        info_menu = menubar.addMenu("Info")
        
        copyright_action = info_menu.addAction("Copyright + License")
        copyright_action.triggered.connect(self._show_copyright_dialog)
        
       
        
        
        
        
        help_menu = menubar.addMenu("Help")

        docs_action = QAction("Show Documentation...", self)
        docs_action.triggered.connect(self._on_show_documentation)
        help_menu.addAction(docs_action)
        
        
        self.action_global_time.setChecked(True)
        timer_menu.addAction(self.action_global_time)
        timer_menu.addAction(self.action_final_time)

        self.action_global_time.triggered.connect(self._on_timer_mode_changed)
        self.action_final_time.triggered.connect(self._on_timer_mode_changed)
        self._time_mode = "global"


        
        # ========================= Zentrales Layout =========================
        #
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_h_layout = QHBoxLayout(central_widget)  
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        #
        # ============== Linke Spalte (Video + Map) ==============
        #
        left_column_widget = QWidget()
        self.left_v_layout = QVBoxLayout(left_column_widget)
        self.left_v_layout.setContentsMargins(0, 0, 0, 0)
        self.left_v_layout.setSpacing(0)
        
        # Video-Bereich
        self.video_area_widget = QWidget()
        video_area_layout = QVBoxLayout(self.video_area_widget)
        video_area_layout.setContentsMargins(0, 0, 0, 0)
        video_area_layout.setSpacing(0)
    
        # 1)     Video Editor oben (85% der Höhe dieses Blocks)
        self.video_editor = VideoEditorWidget()
        video_area_layout.addWidget(self.video_editor, stretch=85)
        
        # 2) Timeline + Control + Blaues Widget (15% der Höhe)
        timeline_control_widget = QWidget()
        timeline_control_layout = QHBoxLayout(timeline_control_widget)
        timeline_control_layout.setContentsMargins(0, 0, 0, 0)
        timeline_control_layout.setSpacing(0)
        
        # Linke Seite (70%): Timeline + Control übereinander
        left_timeline_control_layout = QVBoxLayout()
        left_timeline_control_layout.setContentsMargins(0, 0, 0, 0)
        left_timeline_control_layout.setSpacing(0)
        
        self.timeline = VideoTimelineWidget()
        self.video_control = VideoControlWidget()
        self.timeline.overlayRemoveRequested.connect(self._on_timeline_overlay_remove)

        
        left_timeline_control_layout.addWidget(self.timeline)
        left_timeline_control_layout.addWidget(self.video_control)
        
        timeline_control_layout.addLayout(left_timeline_control_layout, 7)
        
        # Rechte Seite (30%): Blaues Platzhalter-Widget
        self.mini_chart_widget = MiniChartWidget()
        timeline_control_layout.addWidget(self.mini_chart_widget, 3)
        
        # Fertig in den Video-Bereich
        video_area_layout.addWidget(timeline_control_widget, stretch=15)
        
        # Alles in den oberen Teil der linken Spalte
        self.left_v_layout.addWidget(self.video_area_widget, stretch=1)
        
        # Unten: Map (50%)
        self.map_widget = MapWidget(mainwindow=self, parent=None)
        self.left_v_layout.addWidget(self.map_widget, stretch=1)
        
        # ============== Rechte Spalte (Chart + GPX) ==============
        #
        right_column_widget = QWidget()
        self.right_v_layout = QVBoxLayout(right_column_widget)
        self.right_v_layout.setContentsMargins(0, 0, 0, 0)
        self.right_v_layout.setSpacing(0)
        
        # Oben: Chart (40%) => Stretch 2
        self.chart = ChartWidget()
        self.right_v_layout.addWidget(self.chart, stretch=2)
        
                
        
        # Unten: 60% => gpx_control (10%), gpx_list (50%)
        self.bottom_right_widget = QWidget()
        self.bottom_right_layout = QVBoxLayout(self.bottom_right_widget)
        self.bottom_right_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_right_layout.setSpacing(0)
        
        self.gpx_control = GPXControlWidget()
        self.bottom_right_layout.addWidget(self.gpx_control, stretch=1)
        
        
        self.gpx_widget = GPXWidget()
        
        
        
        self.bottom_right_layout.addWidget(self.gpx_widget, stretch=5)
        self.right_v_layout.addWidget(self.bottom_right_widget, stretch=3)
        
        #
        # ============== QSplitter (horizontal) ==============
        #
        splitter = QSplitter(Qt.Horizontal, central_widget)
        splitter.addWidget(left_column_widget)
        splitter.addWidget(right_column_widget)
        
        # Optional: Startverhältnis (z.B. Pixel oder Stretch)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        #
        # ============== Splitter ins Haupt-Layout ==============
        #
        main_h_layout.addWidget(splitter)
        
        
        
        
        
    
        #   Layout Ende
        ################################################################
        
        
        
        
        # ==    ============ Signale / z.B. chart, gpx_widget, etc. ==============
               
        #
        self.chart.markerClicked.connect(self._on_chart_marker_clicked)
        self.chart.set_gpx_data([])
        s = QSettings("VGSync", "VGSync")
        speed_cap = s.value("chart/speedCap", 70.0, type=float)
        self.chart.set_speed_cap(speed_cap)
        
        # GpxControl -> GpxList
        self.gpx_widget.gpx_list.markBSet.connect(self._on_markB_in_list)
        self.gpx_widget.gpx_list.markESet.connect(self._on_markE_in_list)
        self.gpx_widget.gpx_list.markRangeCleared.connect(self._on_clear_in_list)
        
        self.gpx_widget.gpx_list.markBSet.connect(self.gpx_control.highlight_markB_button)
        self.gpx_widget.gpx_list.markESet.connect(self.gpx_control.highlight_markE_button)

        # Wenn markRangeCleared (z.B. durch Deselect, Delete, Undo usw.) auftritt:
        self.gpx_widget.gpx_list.markRangeCleared.connect(self.gpx_control.reset_mark_buttons)
        
        self.gpx_control.cutClicked.connect(self.gpx_control.on_cut_range_clicked)
        self.gpx_control.removeClicked.connect(self.gpx_control.on_remove_range_clicked)
        self.gpx_control.undoClicked.connect(self.gpx_control.on_undo_range_clicked)
        
        
        
        
        self.gpx_control.saveClicked.connect(self.gpx_control.on_save_gpx_clicked)
            
        
        
        self.gpx_control.set_mainwindow(self)
        
        self.gpx_control.deleteWayErrorsClicked.connect(self.gpx_control.on_delete_way_errors_clicked)
        self.gpx_control.deleteTimeErrorsClicked.connect(self.gpx_control.on_delete_time_errors_clicked)
        self.gpx_control.closeGapsClicked.connect(self.gpx_control.on_close_gaps_clicked)
        self.gpx_control.minSpeedClicked.connect(self.gpx_control.on_min_speed_clicked)
        self.gpx_control.maxSpeedClicked.connect(self.gpx_control.on_max_speed_clicked)
        self.gpx_control.averageSpeedClicked.connect(self.gpx_control.on_average_speed_clicked)
        self.gpx_control.showMinSlopeClicked.connect(self.gpx_control._on_show_min_slope)
        self.gpx_control.showMaxSlopeClicked.connect(self.gpx_control._on_show_max_slope)







        
        
        # Ende Zentrales Layout
        ####################################################################################

        #
        # ============== StepManager, CutManager, EndManager, ... ==============
        #
        
        
        self.gpx_widget.gpx_list.rowClickedInPause.connect(self.on_user_selected_index)
        self.map_widget.pointClickedInPause.connect(self._on_map_pause_clicked)
        
        self.step_manager = StepManager(self.video_editor)
        self.step_manager.set_mainwindow(self)

        self.video_control.play_pause_clicked.connect(self.on_play_pause)
        self.video_control.stop_clicked.connect(self.on_stop)
        self.video_control.step_value_changed.connect(self.on_step_mode_changed)
        self.video_control.multiplier_value_changed.connect(self.on_multiplier_changed)
        self.video_control.backward_clicked.connect(self.step_manager.step_backward)
        self.video_control.forward_clicked.connect(self.step_manager.step_forward)
        
        self.video_control.overlayClicked.connect(self._on_overlay_button_clicked)
       
        self.cut_manager = VideoCutManager(self.video_editor, self.timeline, self)
        self._overlay_manager = OverlayManager(self.timeline, self)
        
        
        self.end_manager = EndManager(
            video_editor=self.video_editor,
            timeline=self.timeline,
            cut_manager=self.cut_manager,  # <-- NEU
            mainwindow=self,
            parent=self
        )

        self.video_control.goToEndClicked.connect(self.end_manager.go_to_end)
        self.video_control.markBClicked.connect(self.cut_manager.on_markB_clicked)
        self.video_control.markEClicked.connect(self.cut_manager.on_markE_clicked)
        self.video_control.cutClicked.connect(self.on_cut_clicked_video)
        self.video_control.undoClicked.connect(self.on_undo_clicked_video)
        
        self.video_control.markClearClicked.connect(self.cut_manager.on_markClear_clicked)
        self.cut_manager.cutsChanged.connect(self._on_cuts_changed)
        self.step_manager.set_cut_manager(self.cut_manager)
        self.video_control.syncClicked.connect(self.on_sync_clicked)
        
        self.gpx_control.markBClicked.connect(self.on_markB_clicked_gpx)
        self.gpx_control.deselectClicked.connect(self.on_deselect_clicked)
        
        self.video_control.markBClicked.connect(self.on_markB_clicked_video)
        self.video_control.markEClicked.connect(self._on_markE_from_video)
        self.gpx_control.markEClicked.connect(self._on_markE_from_gpx)
        self.video_control.markClearClicked.connect(self.on_deselect_clicked)
        
        
       
            
        
        self.video_control.safeClicked.connect(self.on_safe_clicked)

       

        # Geschwindigkeiten / Rate
        self.vlc_speeds = [0.5, 0.67, 1.0, 1.5, 2.0, 4.0, 8.0, 16.0, 32.0]
        self.speed_index = 2
        self.current_rate = self.vlc_speeds[self.speed_index]

        # Video-Abspiel-Ende
        self.video_editor.play_ended.connect(self.on_play_ended)

        # Marker Timer
        self.marker_timer = QTimer(self)
        self.marker_timer.timeout.connect(self.update_timeline_marker)
        self.marker_timer.start(200)

        self.timeline.markerMoved.connect(self._on_timeline_marker_moved)
        self.video_control.timeHMSSetClicked.connect(self.on_time_hms_set_clicked)
        
        self.gpx_widget.gpx_list.rowClickedInPause.connect(self._on_gpx_list_pause_clicked)
        self.map_widget.pointClickedInPause.connect(self._on_map_pause_clicked)
        
        self.gpx_control.chTimeClicked.connect(self.gpx_control.on_chTime_clicked_gpx)
        self.gpx_control.chEleClicked.connect(self.gpx_control.on_chEle_clicked)
        self.gpx_control.chPercentClicked.connect(self.gpx_control.on_chPercent_clicked)
        
        self.gpx_control.smoothClicked.connect(self.gpx_control.on_smooth_clicked)
        self.video_control.set_beginClicked.connect(self.on_set_begin_clicked)
        
        edit_on = is_edit_video_enabled()
        self.video_control.set_editing_mode(edit_on)
        self.map_widget.view.loadFinished.connect(self._on_map_page_loaded)
        self.video_editor.set_final_time_callback(self._compute_final_time)
        
    

    def _on_overlay_button_clicked(self):
        marker_s = self.timeline.marker_position()
        self._overlay_manager.ask_user_for_overlay(marker_s, parent=self)   
        
    
    def _on_map_directions_toggled(self, checked: bool):
        """
        Wird aufgerufen, wenn im Menü 'Map Setup -> Directions' an/aus gehakt wird.
        """
        # Nur wenn der Nutzer das Häkchen setzt (checked=True) prüfen wir den Key
        if checked:
            # Nehmen wir an, self._mapbox_key hält den entschlüsselten Mapbox-Key
            if not self._mapbox_key or not self._mapbox_key.strip():
                # => Kein gültiger Key => Warnung und Abbruch
                
                QMessageBox.warning(
                    self,
                    "Directions not available",
                    "This feature requires a valid Mapbox key.\n"
                    "Please set your Mapbox key first in the Config menu."
                )
                # Häkchen sofort zurücksetzen
                self.action_map_directions.setChecked(False)
                return

        # An dieser Stelle Key vorhanden oder Häkchen = False => fortfahren
        self._directions_enabled = checked
        if self.gpx_control:
            self.gpx_control.set_directions_mode(checked)

        # map_page.html aufrufen
        if self.map_widget and self.map_widget.view:
            page = self.map_widget.view.page()
            js_bool = "true" if checked else "false"
            code = f"setDirectionsEnabled({js_bool});"
            page.runJavaScript(code)

        print(f"[DEBUG] Directions enabled => {checked}")
        
    def _compute_final_time(self, g_s: float) -> float:
        return self.get_final_time_for_global(g_s)    
        
    def _on_show_documentation(self):
        # Pfad zum PDF ermitteln
        base_dir = os.path.dirname(os.path.dirname(__file__))
        pdf_path = os.path.join(base_dir, "doc", "Documentation.pdf")

        if not os.path.isfile(pdf_path):
            QMessageBox.warning(self, "Not found", f"File not found: {pdf_path}")
            return

        # => Im Standard-PDF-Reader öffnen
        

        QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))    
    
    def _set_classic_view(self):
        self.left_v_layout.addWidget(self.map_widget, stretch=1)
        self.map_widget.setParent(self.left_v_layout.parentWidget())
        self.map_widget.show()

        self.chart.show()
        self.bottom_right_widget.show()

        self.map_widget.view.page().runJavaScript("enableVideoMapMode(false);")

        # Update the check state and call handler of "sync all with video" and "directions"
        self.action_new_pts_video_time.setChecked(False)
        self._on_sync_point_video_time_toggled(False)
        self.action_map_directions.setChecked(False)
        self._on_map_directions_toggled(False)


    def _set_map_video_view(self):
        self.right_v_layout.removeWidget(self.chart)
        self.chart.hide()

        self.right_v_layout.removeWidget(self.bottom_right_widget)
        self.bottom_right_widget.hide()

        self.right_v_layout.addWidget(self.map_widget, stretch=1)
        self.map_widget.view.page().runJavaScript("enableVideoMapMode(true);")
        self.right_v_layout.update()

        # Update the check state and call handler of "sync all with video" and "directions"
        self.action_new_pts_video_time.setChecked(True)
        self._on_sync_point_video_time_toggled(True)
        self.action_map_directions.setChecked(True)
        self._on_map_directions_toggled(True)
        
    def _on_show_mpv_path(self):
        s = QSettings("VGSync", "VGSync")
        path_stored = s.value("paths/mpv", "", type=str)
        if path_stored and os.path.isfile(os.path.join(path_stored, "libmpv-2.dll")):
            msg = f"Currently stored libmpv path:\n{path_stored}"
        else:
            msg = "No valid libmpv path stored in QSettings (or file not found)."
        QMessageBox.information(self, "libmpv Path", msg)


    def _on_set_mpv_path(self):
        """
        1) Dialog: User wählt Ordner
        2) Prüfen, ob dort eine libmpv-2.dll liegt und ob sie sich laden lässt
        3) Ggfs. in QSettings speichern
        4) Hinweis: "Bitte neustarten"
        """
        
        folder = QFileDialog.getExistingDirectory(self, "Select folder containing libmpv-2.dll")
        if not folder:
            return  # abgebrochen

        if not is_valid_mpv_folder(folder):
            QMessageBox.warning(self, "Invalid libmpv folder",
                f"No valid 'libmpv-2.dll' found or library cannot be loaded:\n{folder}\n\n"
                "We will continue using the default library.")
            return
    
        # -> Okay, wir speichern es
        s = QSettings("VGSync", "VGSync")
        s.setValue("paths/mpv", folder)
        QMessageBox.information(self, "libmpv Path set",
            f"libmpv-2.dll path set to:\n{folder}\n\n"
            "Please restart the application to take effect.")


    def _on_clear_mpv_path(self):
        s = QSettings("VGSync", "VGSync")
        s.remove("paths/mpv")
        QMessageBox.information(self, "libmpv Path cleared",
            "The libmpv path has been removed from QSettings.\n"
            "We will fallback to the built-in mpv/lib.\n"
            "Please restart the application.")    
        
        
        
    def _increment_counter_on_server(self, mode: str):
        """
        Erhöht den Zähler auf dem Server (mode='video' oder 'gpx').
        Ruft z. B. https://.../counter.php?action=increment_video auf
        und gibt das Ergebnis (videoCount, gpxCount) als Tupel zurück.
        Bei Fehler -> None.
        """
        if mode not in ("video", "gpx"):
            print("[WARN] _increment_counter_on_server: Ungültiger mode=", mode)
            return None

        action = "increment_video" if mode == "video" else "increment_gpx"
        url = f"{self._counter_url}?action={action}"
        print("[DEBUG] increment request =>", url)
        
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read().decode("utf-8")
                counts = json.loads(data)
                return (counts.get("video", 0), counts.get("gpx", 0))
        except Exception as e:
            print("[WARN] Fehler beim Serveraufruf increment:", e)
            return None


    def _fetch_counters_from_server(self):
        """
        Liest die aktuellen Zählerstände ohne Hochzählen.
        Ruft also https://.../counter.php auf (ohne action).
        Gibt bei Erfolg ein Dict { 'video': number, 'gpx': number } zurück,
        sonst None.
        """
        url = self._counter_url  # ohne ?action
        #print("[DEBUG] fetch counters =>", url)
        
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read().decode("utf-8")
                counts = json.loads(data)
                return counts
        except Exception as e:
            print("[WARN] Fehler beim Serveraufruf fetch:", e)
            return None    
        
        
    def _load_map_keys_from_settings(self):
        """
        Liest aus QSettings:
         - mapTiler/key
         - bing/key
         - mapbox/key
        (jeweils Base64-kodiert) und schreibt sie in self._maptiler_key etc.
        """
        s = QSettings("VGSync", "VGSync")

        def decode(b64text):
            if not b64text:
                return ""
            try:
                return base64.b64decode(b64text.encode("utf-8")).decode("utf-8")
            except:
                return ""

        enc_mt = s.value("mapTiler/key", "", str)
        enc_bi = s.value("bing/key", "", str)
        enc_mb = s.value("mapbox/key", "", str)

        self._maptiler_key = decode(enc_mt)
        self._bing_key     = decode(enc_bi)
        self._mapbox_key   = decode(enc_mb)
    
    def _save_map_key_to_settings(self, provider: str, plain_key: str):
        """
        Speichert den Key in Base64, z. B. provider='mapTiler'|'bing'|'mapbox'.
        """
        s = QSettings("VGSync", "VGSync")
        enc = base64.b64encode(plain_key.encode("utf-8")).decode("utf-8")

        if provider == "mapTiler":
            s.setValue("mapTiler/key", enc)
            self._maptiler_key = plain_key
        elif provider == "bing":
            s.setValue("bing/key", enc)
            self._bing_key = plain_key
        elif provider == "mapbox":
            s.setValue("mapbox/key", enc)
            self._mapbox_key = plain_key

        # Jetzt sofort updaten => an map_page.html schicken
        self._update_map_page_keys()    
    
    def _update_map_page_keys(self):
        """
        Sendet die aktuellen Keys an map_page.html.
        Dort definieren wir setMapTilerKey(...), setBingKey(...), setMapboxKey(...).
        """
        if not self.map_widget or not self.map_widget.view:
            return

        page = self.map_widget.view.page()
        # JS-Aufrufe
        js_mt = f"setMapTilerKey('{self._maptiler_key}')"
        page.runJavaScript(js_mt)

        js_bi = f"setBingKey('{self._bing_key}')"
        page.runJavaScript(js_bi)

        js_mb = f"setMapboxKey('{self._mapbox_key}')"
        page.runJavaScript(js_mb)


    def _on_set_maptiler_key(self):
        self._show_key_dialog("mapTiler", self._maptiler_key)

    def _on_set_bing_key(self):
        self._show_key_dialog("bing", self._bing_key)

    def _on_set_mapbox_key(self):
        self._show_key_dialog("mapbox", self._mapbox_key)

    def _show_key_dialog(self, provider_name: str, current_val: str):
        """
        Generischer Dialog zum Eingeben des neuen Keys.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Set {provider_name} Key")

        vbox = QVBoxLayout(dlg)
        lbl = QLabel(f"Enter your {provider_name} key:")
        vbox.addWidget(lbl)

        edit = QLineEdit()
        edit.setText(current_val)
        vbox.addWidget(edit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        vbox.addWidget(btns)

        def on_ok():
            new_key = edit.text().strip()
            self._save_map_key_to_settings(provider_name, new_key)
            dlg.accept()

        def on_cancel():
            dlg.reject()

        btns.accepted.connect(on_ok)
        btns.rejected.connect(on_cancel)

        dlg.exec()

    def _on_about_keys(self):
        """
        Zeigt einen Dialog, wofür die Keys sind, wo man sie bekommt usw.
        """
        msg_html = (
            "<h3>Map Keys Information</h3>"
            "<p>Mit diesem Tool kannst du verschiedene Kartendienste nutzen:</p>"
            "<ul>"
            "<li>MapTiler (Satelliten-Kacheln)</li>"
            "<li>Mapbox (Satellite)</li>"
            "</ul>"
            "<p>Bitte registriere dich bei jedem gewünschten Anbieter "
            "und füge hier deinen API-Key ein. Beachte jeweils die Limits (Free-Tier) "
            "und die Nutzungsbedingungen.</p>"
        )

        QMessageBox.information(self, "About Map Keys", msg_html)


    ###############################################################################
        
    def _on_about_keys(self):
        """
        Zeigt einen Hinweis, wozu die Keys da sind, Links zu den 
        Anbietern, Limits, etc. (Demo-Text).
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("About Map Keys")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<h3>Information about Map Keys</h3>"
            "<p>You can use different satellite tile providers. "
            "Enter your own API keys for MapTiler or Mapbox. "
            "Each provider has its own usage limits and Terms of Service.</p>"
            "<ul>"
            "<li><b>MapTiler:</b> <a href='https://www.maptiler.com/'>maptiler.com</a></li>"
            "<li><b>Mapbox:</b> <a href='https://www.mapbox.com/'>mapbox.com</a></li>"
            "</ul>"
            "<p>Please ensure you comply with each provider's usage policies.</p>"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()    
        
        
    def _on_set_stop_threshold(self):
        # Aktuellen Wert holen (z.B. aus chart._stop_threshold)
        current_val = self.chart._stop_threshold
    
        
        new_val, ok = QInputDialog.getDouble(
            self,
            "Stop Threshold",
            "Mark stops greater than X seconds:",
            current_val,
            0.1,    # minimaler Wert
            1000.0, # maximaler Wert
            1       # 1 Nachkommastelle
        )
        if not ok:
            return

        # Im ChartWidget setzen
        self.chart.set_stop_threshold(new_val)    
    
    def _on_map_page_loaded(self, ok: bool):
        """
        Wird aufgerufen, sobald deine map.html im QWebEngineView fertig geladen ist.
        Dann existieren erst die JS-Funktionen.
        """
        if not ok:
            print("[WARN] Karte konnte nicht geladen werden.")
            return
        #print("[DEBUG] Karte ist geladen ⇒ wende jetzt die Größen aus QSettings an.")
        self._apply_map_sizes_from_settings()  # ruft erst hier de    
        self._update_map_page_keys()
        # NEU: Directions-Status an JS geben
        js_bool = "true" if self._directions_enabled else "false"
        js_code = f"setDirectionsEnabled({js_bool});"
        self.map_widget.view.page().runJavaScript(js_code)

    def _apply_map_sizes_from_settings(self):
        """
        Liest aus QSettings *nur noch* "black", "red", "blue", "yellow"
        und setzt fallback=4 für black/red/blue, fallback=6 für yellow.
        Anschließend wird colorSizeMap[...] in JavaScript aktualisiert.
        """
        s = QSettings("VGSync", "VGSync")

        defaults = {
            "black": 4,
            "red": 4,
            "blue": 4,
            "yellow": 6
        }

        for color_name, default_size in defaults.items():
            size_val = s.value(f"mapSize/{color_name}", default_size, type=int)
            # An JS: colorSizeMap['black']=4 etc.
            js_code = f"colorSizeMap['{color_name}'] = {size_val};"
            self.map_widget.view.page().runJavaScript(js_code)

        print("[DEBUG] colorSizeMap updated in JS with QSettings (color names).")

        
    def _on_set_map_point_size(self, color_str: str):
        """
        Bekommt z.B. 'black', 'red', 'blue', 'yellow' rein.
        Fragt neuen Wert ab und speichert in QSettings => "mapSize/black" etc.
        Übergibt dann an JS => updateAllPointsByColor('black', new_val).
        """
        s = QSettings("VGSync", "VGSync")

        default_size = 6 if color_str == "yellow" else 4
        current_val = s.value(f"mapSize/{color_str}", default_size, type=int)

        new_val, ok = QInputDialog.getInt(
            self,
            f"Set Map Size for {color_str}",
            f"Current size = {current_val}. Enter new size (1..20):",
            current_val,
            1, 20
        )
        if not ok:
            return  # User hat abgebrochen

        # In QSettings speichern
        s.setValue(f"mapSize/{color_str}", new_val)
        s.sync()

        # Jetzt JS-Funktion anstoßen: updateAllPointsByColor("black", new_val)
        self.map_widget.view.page().runJavaScript(
            f"updateAllPointsByColor('{color_str}', {new_val});"
        )
    
        QMessageBox.information(
            self,
            "Map Size Updated",
            f"{color_str.capitalize()} points changed to size={new_val}."
        )
    
    


    
            
    def _update_map_points_of_color(self, color_str: str, new_size: int):
        """
        Ruft in map_page.html => updateAllPointsByColor(color_str, new_size) auf.
        'color_str' ist einer der Farbnamen: 'black', 'red', 'blue', 'yellow'.
        """
        if not self.map_widget:
            return

        # Wenn 'color_str' mal was Unbekanntes ist, fallback auf 'black':
        valid_colors = {'black', 'red', 'blue', 'yellow'}
        color_lower = color_str.lower()
        if color_lower not in valid_colors:
            color_lower = 'black'

        # Dann direkt mit dem Farbnamen ins JS
        js_code = f"updateAllPointsByColor('{color_lower}', {new_size});"
        self.map_widget.view.page().runJavaScript(js_code)

    
    
    
   
    
    
     


    def _highlight_index_everywhere(self, idx: int):
        # Map
        self.map_widget.show_blue(idx, do_center=True)
        # Chart
        self.chart.highlight_gpx_index(idx)
        # GpxList
        self.gpx_widget.gpx_list.select_row_in_pause(idx)
        # MiniChart
        if self.mini_chart_widget:
            self.mini_chart_widget.set_current_index(idx)    
        
        
    def _on_zero_speed_action(self):
        """
        Wird aufgerufen, wenn der Nutzer im Menü "Config -> Chart-Settings -> ZeroSpeed..." klickt.
        Öffnet einen Dialog, in dem der Anwender die 'Zero-Speed-Grenze' in km/h eingeben kann.
        """
        # Aktuellen Wert holen (z.B. 1.0 km/h als Default)
        current_value = self.chart.zero_speed_threshold()

        # QInputDialog für einen float-Wert
        #   Titel: Zero Speed Threshold
        #   Label: "Enter km/h"
        #   Default-Wert: current_value
        #   Min: 0.0 / Max: 200.0 / Schrittweite: 1 Stelle nach dem Komma
        new_value, ok = self.QInputDialog.getDouble(
            self,
            "Zero Speed Threshold",
            "Enter km/h:",
            current_value,
            0.0,
            200.0,
            1
        )

        if ok:
            # Den Wert ans ChartWidget weitergeben
            self.chart.set_zero_speed_threshold(new_value)    
            self._update_gpx_overview()
        
        
    from PySide6.QtWidgets import QInputDialog

    def _on_set_limit_speed(self):
        """
        Wird aufgerufen, wenn der Menüpunkt 'Limit Speed...' angeklickt wird.
        Fragt per QInputDialog den Speed-Limit-Wert ab und wendet ihn an.
        """
        # 1) Aktuellen Wert vom Chart holen
        current_limit = self.chart._speed_cap  # Oder self.chart.get_speed_cap() falls du eine Getter-Methode hast

        # 2) QInputDialog: Eingabe eines float-Wertes
    
        new_val, ok = self.QInputDialog.getDouble(
            self,
            "Set Speed Limit",
            "Enter max. speed (km/h):",
            current_limit,
            0.0,    # min
            9999.0, # max
            1       # decimals
        )
        if not ok:
            return  # User hat abgebrochen

        # 3) Wert im ChartWidget setzen
        self.chart.set_speed_cap(new_val)

        # 4) Optional: in QSettings speichern
       
        s = QSettings("VGSync", "VGSync")
        s.setValue("chart/speedCap", new_val)
    
        
    def _on_show_ffmpeg_path(self):
        
        

        s = QSettings("VGSync", "VGSync")
        path_stored = s.value("paths/ffmpeg", "", type=str)
        if path_stored and os.path.isdir(path_stored):
            msg = f"Currently stored FFmpeg path:\n{path_stored}"
        else:
            msg = "No FFmpeg path stored in QSettings (or path is invalid)."
        QMessageBox.information(self, "FFmpeg Path", msg)

    def _on_set_ffmpeg_path(self):
        """
        Manually pick a folder with ffmpeg.exe
        """
       

        QMessageBox.information(
            self,
            "Set FFmpeg Path",
            "Please select the folder where ffmpeg is installed.\n"
            "e.g. C:\\ffmpeg\\bin"
        )

        folder = QFileDialog.getExistingDirectory(self, "Select FFmpeg Folder")
        if not folder:
            return
        
        exe_name = "ffmpeg.exe" if platform.system().lower().startswith("win") else "ffmpeg"
        path_exe = os.path.join(folder, exe_name)
        if not os.path.isfile(path_exe):
            QMessageBox.critical(self, "Invalid FFmpeg",
                f"No {exe_name} found in:\n{folder}")
            return
    
        # store in QSettings
        s = QSettings("VGSync", "VGSync")
        s.setValue("paths/ffmpeg", folder)
    
        # optionally add to PATH
        old_path = os.environ.get("PATH", "")
        new_path = folder + os.pathsep + old_path
        os.environ["PATH"] = new_path
        
        QMessageBox.information(
            self,
            "FFmpeg Path updated",
            f"FFmpeg path set to:\n{folder}\n\n"
            "Please restart the application to ensure the new setting takes effect."
        )

        
        
    def _set_edit_mode(self, new_mode: str):
        old_mode = self._edit_mode
        if new_mode == old_mode:
            return  # Nichts geändert

        self._edit_mode = new_mode
        if new_mode == "off":
            self.video_control.set_editing_mode(False)
            print("[DEBUG] => OFF")
            self.encoder_setup_action.setEnabled(False)
            self.video_control.show_ovl_button(False)
            self.overlay_setup_action.setEnabled(False)
        elif new_mode == "copy":
            self.video_control.set_editing_mode(True)
            print("[DEBUG] => COPY")
            self.encoder_setup_action.setEnabled(False)
            self.video_control.show_ovl_button(False)
            self.overlay_setup_action.setEnabled(False)
        elif new_mode == "encode":
            self.video_control.set_editing_mode(True)
            print("[DEBUG] => ENCODE")
            self.encoder_setup_action.setEnabled(True)
            self.video_control.show_ovl_button(True)
            self.overlay_setup_action.setEnabled(True)

        # Abfrage: nur wenn alter Modus 'off' war + neuer Modus copy/encode
        if old_mode == "off" and new_mode in ("copy", "encode"):
            answer = QMessageBox.question(
                self,
                "Index Videos?",
                "Do you want to index all currently loaded videos now?\n"
                "(Currently loaded videos: %d)\n\n"
                "Any *new* video you load from now on will also be indexed automatically."
                % len(self.playlist),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                # Selbst wenn playlist leer ist, tut das einfach nichts
                for video_path in self.playlist:
                    self.start_indexing_process(video_path)
            else:
                self._userDeclinedIndexing = True    
    

    def _on_encoder_setup_clicked(self):
        # Hier öffnen wir den Dialog
        dlg = EncoderSetupDialog(self)
        if dlg.exec() == dlg.accepted:
            print("[DEBUG] => Encoder-Setup saved.")
        else:
            print("[DEBUG] => Encoder-Setup canceled.")
            
    def _on_overlay_setup_clicked(self):
        """
        Wird aufgerufen, wenn im Menü "Overlay-Setup" geklickt wird.
        Öffnet ein Dummy-Fenster (OverlaySetupDialog).
        """
        from .overlay_setup_dialog import OverlaySetupDialog  # wir importieren gleich die neue Klasse
        dlg = OverlaySetupDialog(self)
        result = dlg.exec()
        
        if result == QDialog.Accepted:
            print("[DEBUG] => Overlay-Setup: changes saved.")
        else:
            print("[DEBUG] => Overlay-Setup: canceled or closed.")
        

    def _on_clear_ffmpeg_path(self):
        """
        Removes ffmpeg path from QSettings, 
        so that next time it might auto-detect or prompt again.
        """
       
        s = QSettings("VGSync", "VGSync")
        s.remove("paths/ffmpeg")
    
        QMessageBox.information(self, "FFmpeg Path cleared",
            "The FFmpeg path has been removed from QSettings.")
            
        QMessageBox.information(
            self,
            "FFmpeg Path cleared",
            "Please restart the application to ensure the new setting takes effect."
        )    
        
            
        
        
    

    def on_set_begin_clicked(self):
       
        
        ret = QMessageBox.question(
            self,
            "Confirm Cut Begin",
            "Have you set the video exactly to the same crossing/place\n"
            "as the corresponding GPX point?\n"
            "Press Yes to proceed, No to abort.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            # => Abbrechen
            return
        
        
        

        # 1) Markierten GPX-Punkt
        row_idx = self.gpx_widget.gpx_list.table.currentRow()
        if row_idx < 0:
            QMessageBox.warning(self, "No GPX Selection", 
                "Please select a GPX point first!")
            return

        # 2) Videozeit => global_video_s
        current_local_s = self.video_editor.get_current_position_s()
        if current_local_s < 0:
            current_local_s = 0.0
        vid_idx = self.video_editor.get_current_index()
        offset_s = sum(self.video_durations[:vid_idx])
        global_video_s = offset_s + current_local_s
        print(f"[DEBUG] set_begin => global_video_s={global_video_s:.2f}")
    
        # 3) GPX => rel_s_marked
        gpx_data = self.gpx_widget.gpx_list._gpx_data
        if not gpx_data or row_idx >= len(gpx_data):
            QMessageBox.warning(self, "GPX Error", "Invalid row in GPX data.")
            return
    
        rel_s_marked = gpx_data[row_idx].get("rel_s", 0.0)
        print(f"[DEBUG] set_begin => row_idx={row_idx}, rel_s_marked={rel_s_marked:.2f}")

        # ----------------------------------------------
        # FALL A) AutoVideoSync=OFF
        # ----------------------------------------------
        if not self._autoSyncVideoEnabled:
            print("[DEBUG] set_begin => CASE A (OFF)")
    
            if abs(global_video_s) < 0.01:
                # => Videozeit ~0 => wir schneiden GPX am markierten Punkt
                cut_start = rel_s_marked
                if cut_start < 0:
                    cut_start = 0.0
    
                # => Erstellen wir Undo-Snapshot => JETZT, weil wir sicher was ändern
                old_data = copy.deepcopy(gpx_data)
                self.gpx_widget.gpx_list._history_stack.append(old_data)
    
                i0 = 0
                while i0 < len(gpx_data):
                    if gpx_data[i0].get("rel_s", 0.0) >= cut_start:
                        break
                    i0 += 1
    
                if i0 > 0:
                    self.gpx_widget.gpx_list.set_markB_row(0)
                    self.gpx_widget.gpx_list.set_markE_row(i0 - 1)
                    self.gpx_widget.gpx_list.delete_selected_range()
    
                new_data = self.gpx_widget.gpx_list._gpx_data
                if new_data:
                    shift_s = new_data[0].get("rel_s", 0.0)
                    if shift_s > 0:
                        for pt in new_data:
                            pt["rel_s"] -= shift_s
                        recalc_gpx_data(new_data)
                    self.gpx_widget.set_gpx_data(new_data)
    
                QMessageBox.information(
                    self,
                    "Set Begin (OFF / Video=0s)",
                    "Cut GPX at the marked point.\n"
                    "Undo possible in GPX-liste."
                )
    
            else:
                # => global_video_s>0 => wir behalten global_video_s sek. vor markiertem
                cut_start = rel_s_marked - global_video_s
                if cut_start < 0:
                    # => Fehlermeldung => ABBRUCH => KEIN Undo
                    QMessageBox.warning(
                        self,
                        "Not enough GPX data",
                        f"You want to keep {global_video_s:.2f}s before {rel_s_marked:.2f}s,\n"
                        f"that starts at {cut_start:.2f}s < 0 => impossible.\n"
                        "Operation canceled."
                    )
                    return
    
                # => JETZT erst Undo-Snapshot => weil wir sicher etwas löschen
                old_data = copy.deepcopy(gpx_data)
                self.gpx_widget.gpx_list._history_stack.append(old_data)
    
                i0 = 0
                while i0 < len(gpx_data):
                    if gpx_data[i0].get("rel_s", 0.0) >= cut_start:
                        break
                    i0 += 1
    
                if i0 > 0:
                    self.gpx_widget.gpx_list.set_markB_row(0)
                    self.gpx_widget.gpx_list.set_markE_row(i0 - 1)
                    self.gpx_widget.gpx_list.delete_selected_range()
    
                new_data = self.gpx_widget.gpx_list._gpx_data
                if new_data:
                    shift_s = new_data[0].get("rel_s", 0.0)
                    if shift_s > 0:
                        for pt in new_data:
                            pt["rel_s"] -= shift_s
                        recalc_gpx_data(new_data)
                    self.gpx_widget.set_gpx_data(new_data)
    
                QMessageBox.information(
                    self,
                    "Set Begin (OFF / keepVideoTime)",
                    f"Kept {global_video_s:.2f}s before the marked GPX point.\n"
                    "Video remains unchanged.\n"
                    "Undo possible in GPX-liste."
                )
    
        # ----------------------------------------------
        # FALL B) AutoVideoSync=ON
        # ----------------------------------------------
        else:
            print("[DEBUG] set_begin => CASE B (ON)")
    
            # => wir schneiden in GPX am markierten Punkt => SHIFT => 0
            cut_start = rel_s_marked
            if cut_start < 0:
                cut_start = 0.0
    
            # => Undo-Snapshot => wir ändern definitiv was
            old_data = copy.deepcopy(gpx_data)
            self.gpx_widget.gpx_list._history_stack.append(old_data)
    
            i0 = 0
            while i0 < len(gpx_data):
                if gpx_data[i0].get("rel_s", 0.0) >= cut_start:
                    break
                i0 += 1
    
            if i0 > 0:
                self.gpx_widget.gpx_list.set_markB_row(0)
                self.gpx_widget.gpx_list.set_markE_row(i0 - 1)
                self.gpx_widget.gpx_list.delete_selected_range()
    
            new_data = self.gpx_widget.gpx_list._gpx_data
            if new_data:
                shift_s = new_data[0].get("rel_s", 0.0)
                if shift_s > 0:
                    for pt in new_data:
                        pt["rel_s"] -= shift_s
                    recalc_gpx_data(new_data)
                self.gpx_widget.set_gpx_data(new_data)
    
            # => Video => cut 0..global_video_s
            if global_video_s <= 0.01:
                QMessageBox.information(
                    self, "Set Begin (ON)",
                    "Video near 0s => no cut.\n"
                    "GPX cut at the point.\n"
                    "Undo in GPX-liste + Video possible."
                )
            else:
                self.cut_manager.markB_time_s = 0.0
                self.cut_manager.markE_time_s = global_video_s
                self.timeline.set_markB_time(0.0)
                self.timeline.set_markE_time(global_video_s)
                self.cut_manager.on_cut_clicked()
    
                QMessageBox.information(
                    self, "Set Begin (ON)",
                    f"Video cut at {global_video_s:.2f}s.\n"
                    f"GPX cut at {rel_s_marked:.2f}s.\n"
                    "Undo in GPX-liste + Video possible."
                )
    
        # -------------------------------------------
        #  (3) Chart / Map / MiniChart aktualisieren
        # -------------------------------------------
        final_data = self.gpx_widget.gpx_list._gpx_data
        if final_data:
            # chart
            self.chart.set_gpx_data(final_data)
            # mini chart
            if self.mini_chart_widget:
                self.mini_chart_widget.set_gpx_data(final_data)
            # map
            route_geojson = self._build_route_geojson_from_gpx(final_data)
            self.map_widget.loadRoute(route_geojson, do_fit=False)
        else:
            self.chart.set_gpx_data([])
            if self.mini_chart_widget:
                self.mini_chart_widget.set_gpx_data([])
            self.map_widget.loadRoute(None, do_fit=False)
    
        print("[DEBUG] on_set_begin_clicked => done.")
    
    def on_new_gpx_point_inserted(self, lat: float, lon: float, idx: int):
        """
        Wird aufgerufen, wenn aus dem map_page.html-JavaScript
        channelObj.newPointInserted(lat, lon, idx) getriggert wurde.
        
        - lat, lon: Koordinaten des neu eingefügten Punktes
        - idx: Kann sein:
            - -3 => kein Punkt selektiert (also "vor dem ersten" GPX-Punkt)
            - -2 => Punkt VOR dem ersten
            - -1 => Punkt HINTER dem letzten
            - >=0 => Punkt zwischen idx und idx+1 (also 'zwischen zwei vorhandenen GPX-Punkten').

        NEU/ERWEITERT:
        Wenn Directions aktiviert sind (self._directions_enabled=True) und
        in der GPX-Liste aktuell der erste oder letzte Punkt selektiert ist,
        überschreiben wir das idx-Verhalten:

        1) Falls letzter Punkt selektiert => idx = -1 (Ans Ende anhängen)
        2) Falls erster Punkt selektiert  => idx = -2 (Vorne einfügen)

        Dadurch wird die Route – je nach gewähltem Startpunkt (B/E) – vorn oder hinten angefügt.
        """
       

        gpx_data = self._gpx_data
        row_selected = self.gpx_widget.gpx_list.table.currentRow()

        if self._autoSyncNewPointsWithVideoTime and self.video_editor.is_video_loaded(): #if video loaded, insert a new point at current video time without shift
            self.append_gpx_history(gpx_data) #for undo
            video_time = self.video_editor.get_current_position_s()
            insert_idx = self.ordered_insert_new_point(lat,lon,video_time)

            if(insert_idx > 0 and self._directions_enabled):
                t1 = gpx_data[insert_idx-1]["time"]
                t2 = gpx_data[insert_idx]["time"]
                dt = (t2 - t1).total_seconds()
                if dt > 2 :
                    prof = self.gpx_control._ask_profile_mode()
                    if prof:
                        self.gpx_control._close_gaps_mapbox(insert_idx-1, insert_idx, dt, prof)

        else: #insert with shift
            if idx == -3:
                QMessageBox.information(
                self,
                "No point selected",
                "No point selected ⇒ cannot insert new point."
            )
                
            # --- NEU: Falls Directions aktiv und es ist eindeutig "erster" oder "letzter" Punkt selektiert ---
            if self._directions_enabled:
                # Prüfen, welcher GPX-Punkt in der Liste selektiert ist
                n = len(gpx_data)

                if row_selected >= 0 and n > 0:
                    is_first = (row_selected == 0)
                    is_last  = (row_selected == n-1)

                    if is_last:
                        # => Wir wollen unbedingt ans Ende anfügen
                        idx = -1
                        # (markB=letzter, markE=neuer => B->E => "append")
                    elif is_first:
                        # => Vor dem ersten einfügen
                        idx = -2
                        # (markE=erster, markB=neuer => B->E => "prepend")
                    # Falls weder erster noch letzter => idx bleibt wie vom JS gesendet (z.B. -1 oder "zwischen")
        
            # --- Nun das "alte" Einfüge-Verhalten ---
            # Undo-Snapshot
            self.append_gpx_history(gpx_data)

            now = datetime.now()  # Fallback, falls Zeit gar nicht existiert

            if idx == -2:
                # =============== Punkt VOR dem ersten einfügen ===============
                if not gpx_data:
                    # Noch gar nichts drin => erster Punkt
                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": 0.0,
                        "time": now,
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    gpx_data.append(new_pt)
                else:
                    t_first = gpx_data[0]["time"]
                    if not t_first:
                        t_first = now
                    # NEUEN Punkt "vorne" einfügen => 
                    # wir geben ihm dieselbe Zeit wie den alten ersten oder 1s davor
                    new_time = t_first  # oder t_first - timedelta(seconds=1)
                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": gpx_data[0].get("ele", 0.0),
                        "time": new_time,
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    gpx_data.insert(0, new_pt)
        
                    # jetzt alle nachfolgenden +1s verschieben
                    for i in range(1, len(gpx_data)):
                            oldt = gpx_data[i]["time"]
                            if oldt:
                                gpx_data[i]["time"] = oldt + timedelta(seconds=1)
                    
            elif idx == -1:
                # =============== Punkt NACH dem letzten einfügen ===============
                if not gpx_data:
                    # ganz leer => erster Punkt
                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": 0.0,
                        "time": now,
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    gpx_data.append(new_pt)
                else:
                    last_pt = gpx_data[-1]
                    t_last = last_pt.get("time")
                    if not t_last:
                        t_last = now
                    new_time = t_last + timedelta(seconds=1)
                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": last_pt.get("ele", 0.0),
                        "time": new_time, 
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    gpx_data.append(new_pt)
        
            else:
                # =============== Punkt "zwischen" idx..idx+1 einfügen ===============
                if idx < 0:
                    idx = 0
                if idx >= len(gpx_data):
                    idx = len(gpx_data) -1  # safety

                if not gpx_data:
                    # Falls wirklich nix da => wie "ende"
                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": 0.0,
                        "time": now,
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    gpx_data.append(new_pt)
                else:
                    base_pt = gpx_data[idx]
                    t_base = base_pt.get("time")
                    if not t_base:
                        t_base = now
                    new_time = t_base + timedelta(seconds=1)

                    new_pt = {
                        "lat": lat,
                        "lon": lon,
                        "ele": base_pt.get("ele", 0.0),
                        "time": new_time,
                        "delta_m": 0.0,
                        "speed_kmh": 0.0,
                        "gradient": 0.0,
                        "rel_s": 0.0
                    }
                    insert_pos = idx + 1
                    if insert_pos > len(gpx_data):
                        insert_pos = len(gpx_data)
                    gpx_data.insert(insert_pos, new_pt)

                    # alle folgenden => +1s
                    for j in range(insert_pos+1, len(gpx_data)):
                            t_old = gpx_data[j].get("time")
                            if t_old:
                                gpx_data[j]["time"] = t_old + timedelta(seconds=1)      

        #  => recalc
        recalc_gpx_data(gpx_data)
        self.gpx_widget.set_gpx_data(gpx_data)
        self._gpx_data = gpx_data
    
        # Chart, Mini-Chart usw. aktualisieren
        self.chart.set_gpx_data(gpx_data)
        if self.mini_chart_widget:
            self.mini_chart_widget.set_gpx_data(gpx_data)

        # Map neu laden
        route_geojson = self._build_route_geojson_from_gpx(gpx_data)
        self.map_widget.loadRoute(route_geojson, do_fit=False)

        print(f"[INFO] Inserted new GPX point (DirectionsEnabled={self._directions_enabled}); total now {len(gpx_data)} pts.")

    def append_gpx_history(self, gpx_data: list):
        old_data = copy.deepcopy(gpx_data)
        self.gpx_widget.gpx_list._history_stack.append(old_data)            
            
    ####################################################################
    def _on_reset_config_triggered(self):
       
    
        answer = QMessageBox.question(
            self,
            "Reset Config",
            "Do you really want to reset all QSettings?\n"
            "This will remove disclaimers, keys etc.\n"
            "You may have to restart the application.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            reset_config()  # ruft s.clear()
            QMessageBox.information(
                self,
                "Reset done",
                "All config settings have been removed.\n"
                "Please restart the application."
            )
    
        
        
    
    def on_undo_clicked_video(self):
        """
        Wird aufgerufen, wenn im VideoControlWidget 'undo' geklickt wird.
        1) Video-Cut-Undo via cut_manager
        2) Falls autoSyncVideo=ON => GPX-Liste => undo_delete()
        """
        # 1) Video-Undo:
        self.map_widget.view.page().runJavaScript("showLoading('Undo GPX-Range...');")
        self.cut_manager.on_undo_clicked()
        self._overlay_manager.undo_overlay()

        # 2) Falls autosync ON => GPX-Liste => undo_delete
        if self._autoSyncVideoEnabled:
            print("[DEBUG] on_undo_clicked_video => autoSyncVideo=ON => gpx_list.undo_delete()")
            self.gpx_widget.gpx_list.undo_delete()
    
        # ggf. Chart, Map updaten => du machst das schon in on_undo_range_clicked ?
        self._update_gpx_overview()
        self._gpx_data = self.gpx_widget.gpx_list._gpx_data
        route_geojson = self._build_route_geojson_from_gpx(self._gpx_data)
        self.map_widget.loadRoute(route_geojson, do_fit=False)
        self.chart.set_gpx_data(self._gpx_data)
        if self.mini_chart_widget:
            self.mini_chart_widget.set_gpx_data(self._gpx_data)
    
        self.map_widget.view.page().runJavaScript("hideLoading();")
        
    def on_cut_clicked_video(self):
        """
        Wird aufgerufen, wenn der 'cut'-Button im VideoControlWidget gedrückt wird.
        1) Führt den normalen Video-Cut via cut_manager durch
        2) Falls autoSyncVideo ON => Löschen wir im GPXList ebenfalls B..E
        """
        # 1) Video-Cut
        self.cut_manager.on_cut_clicked()
        

        # 2) autoSyncVideo?
        if self._autoSyncVideoEnabled and self._edit_mode in ("copy", "encode"):
            self.map_widget.view.page().runJavaScript("showLoading('Deleting GPX-Range...');")
            print("[DEBUG] autoSyncVideo=ON => rufe gpx_list.delete_selected_range()")
            self.gpx_widget.gpx_list.delete_selected_range()
            self.map_widget.clear_marked_range()
        
            self._update_gpx_overview()  
            self._gpx_data = self.gpx_widget.gpx_list._gpx_data
            route_geojson = self._build_route_geojson_from_gpx(self._gpx_data)
            self.map_widget.loadRoute(route_geojson, do_fit=False)
            self.chart.set_gpx_data(self._gpx_data)
            self.map_widget.view.page().runJavaScript("hideLoading();")
        else:
            pass    
        
        
    def _on_auto_sync_video_toggled(self, checked: bool):
        """
        Wird aufgerufen, wenn der Menüpunkt "AutoSyncVideo" an-/abgehakt wird.
        => Speichere den Zustand in self._autoSyncVideoEnabled
        """    
        if checked and self._edit_mode == "off":
            # -> nicht erlaubt
            QMessageBox.warning(
                self,
                "AutoCutVideo+GPX requires Edit Mode",
                "You can only enable AutoCutVideo+GPX if 'Edit Video' is enabled.\n"
                "Please enable 'Edit Video' first."
            )
            # Checkbox zurücksetzen
            self.action_auto_sync_video.setChecked(False)
            return

        
        print(f"[DEBUG] _on_auto_sync_video_toggled => {checked}")
        self._autoSyncVideoEnabled = checked
        self.gpx_control.set_markE_visibility(not checked)
        
        
        if checked:
            self.video_editor.acut_status_label.setText("V&G:On")
            self.video_editor.acut_status_label.setStyleSheet(
                "background-color: rgba(0,0,0,120); "
                "color: red; "
                "font-size: 14px; "
                "font-weight: bold;"
                "padding: 2px;"
            )
        else:
            self.video_editor.acut_status_label.setText("")
            #self.video_editor.acut_status_label.setText("V&G:Off")
            #self.video_editor.acut_status_label.setStyleSheet(
            #    "background-color: rgba(0,0,0,120); "
            #    "color: grey; "
            #    "font-size: 14px; "
            #    "font-weight: normal;"
            #    "padding: 2px;"
            #)
        
        if self.gpx_control:
            self.gpx_control.update_set_gpx2video_state(
                video_edit_on=self.action_edit_video.isChecked(),
                auto_sync_on=checked
            )
            
    def _on_sync_point_video_time_toggled(self, checked: bool):
        self._autoSyncNewPointsWithVideoTime = checked
        self.map_widget.view.page().runJavaScript(f"enableVSyncMode({str(checked).lower()});")
        
    def _on_enable_soft_opengl_toggled(self, checked: bool):
        config.set_soft_opengl_enabled(checked)
        QMessageBox.information(self,"Restart needed","Please restart the application to apply the changes.")   

    def _update_gpx_overview(self):
        data = self.gpx_widget.gpx_list._gpx_data
        if not data:
            self.gpx_control.update_info_line(
                video_time_str="00:00:00",
                length_km=0.0,
                duration_str="00:00:00",
                elev_gain=0.0
            )
            return

        # 1) Länge in km
        total_dist_m = sum(pt.get("delta_m", 0.0) for pt in data)
        length_km = total_dist_m / 1000.0
    
        # 2) Höhengewinn
        elev_gain = 0.0
        for i in range(1, len(data)):
            dh = data[i]["ele"] - data[i-1]["ele"]
            if dh > 0:
                elev_gain += dh

        # 3) GPX-Dauer berechnen (time[-1] - time[0])
       
        start_t = data[0].get("time")
        end_t   = data[-1].get("time")
        if start_t and end_t:
            total_sec = (end_t - start_t).total_seconds()
        else:
            total_sec = 0.0
        if total_sec < 0:
            total_sec = 0.0
    
        # => In h:mm:ss formatieren
        gpx_hh = int(total_sec // 3600)
        gpx_mm = int((total_sec % 3600) // 60)
        gpx_ss = int(total_sec % 60)
        gpx_duration_str = f"{gpx_hh:02d}:{gpx_mm:02d}:{gpx_ss:02d}"
    
        # 4) Videolänge (z.B. final nach Cuts)
        total_dur = self.real_total_duration        # Roh-Gesamtlänge aller Videos
        sum_cuts  = self.cut_manager.get_total_cuts()
        final_dur = total_dur - sum_cuts
        if final_dur < 0:
            final_dur = 0
        vid_hh = int(final_dur // 3600)
        vid_mm = int((final_dur % 3600) // 60)
        vid_ss = int(final_dur % 60)
        video_time_str = f"{vid_hh:02d}:{vid_mm:02d}:{vid_ss:02d}"
    
        # 5) Weitere Werte wie slope_max/min etc.
        slope_vals = [pt.get("gradient", 0.0) for pt in data]
        slope_max = max(slope_vals) if slope_vals else 0.0
        slope_min = min(slope_vals) if slope_vals else 0.0
    
        zero_thr = self.chart.zero_speed_threshold()
        zero_speed_count = sum(
            1
            for i, pt in enumerate(data)
            if i > 0 and pt.get("speed_kmh", 0.0) < zero_thr
        )
    
        paused_count = 0
        for i in range(1, len(data)):
            dt = data[i]["rel_s"] - data[i-1]["rel_s"]
            if dt > 1.0:
                paused_count += 1
    
        # 6) An Dein gpx_control_widget übergeben
        self.gpx_control.update_info_line(
            video_time_str=video_time_str,     # Das ist Deine Video-Dauer
            length_km=length_km,
            duration_str=gpx_duration_str,     # DAS ist die Track-Dauer 
            elev_gain=elev_gain,
            slope_max=slope_max,
            slope_min=slope_min,
            zero_speed_count=zero_speed_count,
            paused_count=paused_count
        )


    
        
      
    def on_map_sync_idx(self, gpx_index: int):
       
        print(f"[DEBUG] on_map_sync_idx => idx={gpx_index}")

        # 0) Index-Prüfung
        if not (0 <= gpx_index < len(self._gpx_data)):
            print("[DEBUG] on_map_sync_idx => invalid gpx_index or no gpx_data loaded.")
            return

        # 1) GPX-Punkt auslesen
        point = self._gpx_data[gpx_index]
        print(f"[DEBUG] on_map_sync_idx => point={point}")

        rel_s = point.get("rel_s", 0.0)

        hh = int(rel_s // 3600)
        mm = int((rel_s % 3600) // 60)
        ss = int(rel_s % 60)

        
    
        # Extra Debug:
        print(f"[DEBUG] => resolved time => hh={hh}, mm={mm}, ss={ss}")

        # 4) Aufruf => on_time_hms_set_clicked(hh, mm, ss)
        self.on_time_hms_set_clicked(hh, mm, ss)
        #self.on_time_hms_set_clicked(hh, mm, ss)
        
    
        
        
    def on_user_selected_index(self, new_index: int):
        """
        Zentrale Methode für Klicks in Map oder GPX-Liste (im Pause-Modus).
        Wir entfernen die 'Loch'-Logik, sodass ein roter Punkt beim Anklicken
        NICHT mehr schwarz wird, sondern auch gelb.

        1) Alten gelben Punkt revertieren,
        2) Neuer Punkt => immer gelb (egal ob B..E oder nicht),
        3) Liste -> dieselbe Zeile gelb selektieren.
        """

        # 1) Bisherigen gelben Punkt in Map revertieren, falls vorhanden
       
        if self.video_editor.is_playing:
            self.map_widget.show_yellow(new_index)
        else:
            self.map_widget.show_blue(new_index)
        

        # 3) Liste: dieselbe Zeile gelb machen
        #    => so bleibt Map und Liste synchron
        self.gpx_widget.gpx_list.select_row_in_pause(new_index)
        self.chart.highlight_gpx_index(new_index)


    
        
    def _on_markB_in_list(self, b_idx: int):
        """ 
        Wird ausgelöst, wenn die GPXList MarkB gesetzt hat.
        => Wir rufen jetzt map_widget.set_markB_point(...) (neue JS-Funktion).
        """
        if self.map_widget:
            self.map_widget.set_markB_point(b_idx)
            self.map_widget.set_markB_idx(b_idx)

    def _on_markE_in_list(self, e_idx: int):
        if self.map_widget:
            self.map_widget.set_markE_point(e_idx)
            self.map_widget.set_markE_idx(e_idx)

    def _on_clear_in_list(self):
        if self.map_widget:
            self.map_widget.clear_marked_range()
            self.map_widget.set_markB_idx(None)
            self.map_widget.set_markE_idx(None)
        
    
    def on_point_moved(self, index: int, lat: float, lon: float):
        
        gpx_data = self.gpx_widget.gpx_list._gpx_data
        if not gpx_data:
            return
    
        # 1) Undo-Snapshot (gesamte GPX-Daten kopieren)
        
        old_data = copy.deepcopy(gpx_data)
        self.gpx_widget.gpx_list._history_stack.append(old_data)
        
        """
        Wird aufgerufen, wenn der User in der Karte einen GPX-Punkt verschoben hat.
        """
        print(f"[MainWindow] on_point_moved => idx={index}, lat={lat}, lon={lon}")

        if 0 <= index < len(self._gpx_data):
            self._gpx_data[index]["lat"] = lat
            self._gpx_data[index]["lon"] = lon
            
            recalc_gpx_data(self._gpx_data)
            

            # Falls du Distanz/Speed neu berechnen willst => optional
            #new_geojson = self._build_route_geojson_from_gpx(self._gpx_data)

            # ENTSCHEIDUNG: 
            # => do_fit=False => bleibe im aktuellen Ausschnitt 
            # => do_fit=True  => zoome wieder raus
            #self.map_widget.loadRoute(new_geojson, do_fit=False)

            # Tabelle updaten (damit man es auch sieht)
            self.gpx_widget.set_gpx_data(self._gpx_data)  
            self._update_gpx_overview()
            self.chart.set_gpx_data(self._gpx_data)
        else:
            print("[WARN] Index war außerhalb des GPX-Datenbereichs.")

    

    def _build_route_geojson_from_gpx(self, data):
        """
        data: Liste von Dicts => [{'lat':..., 'lon':...}, ...]
        Gibt FeatureCollection mit 1x Linestring + Nx Points zurück,
        wobei jeder Point => properties.index = i hat.
        """
        features = []

        # Linestring-Koords
        coords_line = []
        for i, pt in enumerate(data):
            coords_line.append([pt["lon"], pt["lat"]])

        line_feat = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords_line
            },
            "properties": { "color": "#000000" }
        }
        features.append(line_feat)

        # Einzelne Punkt-Features
        for i, pt in enumerate(data):
            point_feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [pt["lon"], pt["lat"]]
                },
                "properties": {
                    "index": i,
                    "color": "#000000"
                }
            }
            features.append(point_feat)

        return {
            "type": "FeatureCollection",
            "features": features
        }

    
    # -----------------------------------------------------------------------
    # Methoden und Slots (weitgehend unverändert)
    # -----------------------------------------------------------------------
    
    def format_seconds_to_hms(self, secs: float) -> tuple[int,int,int]:
        s_rounded = round(secs)
        h = s_rounded // 3600
        m = (s_rounded % 3600) // 60
        s = (s_rounded % 60)
        return (h, m, s)
    
    
    
   
    def on_markB_clicked_video(self):
        """
        Wird     aufgerufen, wenn man im VideoControlWidget den Button '[-' klickt.
        """
        # 1) Falls AutoSync=OFF => verhalte dich wie bisher (ohne +1).
        # 2) Falls AutoSync=ON  => *erst* Video/GPS syncen, dann +1 in der GPX-Liste.
        #
        if not self._autoSyncVideoEnabled:
            # => KEIN +1
            row = self.gpx_widget.gpx_list.table.currentRow()
            if row < 0:
                return
            #self.gpx_widget.gpx_list.set_markB_row(row)
            self.map_widget.set_markB_point(row)
        
            # cut_manager, timeline
            global_s = self.video_editor.get_current_position_s()  # = globale Sekunde
            self.cut_manager.markB_time_s = global_s
            self.timeline.set_markB_time(global_s)
            
            
        
        else:
            # => AutoCutVideo+GPX = ON
            #    typischerweise machen wir 'Sync': wir holen uns die globale Zeit
            global_s = self.video_editor.get_current_position_s()
            final_s = self.get_final_time_for_global(global_s)  # falls du final<->global rechnest
            best_idx = self.gpx_widget.get_closest_index_for_time(final_s)
        
            # Das +1:
            row = best_idx + 1
        
            # Klemme, falls row jenseits der letzten Zeile liegt
            maxrow = len(self.gpx_widget.gpx_list._gpx_data) - 1
            if row > maxrow:
                row = maxrow
        
            E_s = self.cut_manager.markE_time_s
            if E_s >= 0 and global_s >= E_s:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Invalid MarkB",
                    f"You cannot set MarkB ({global_s:.2f}s) behind MarkE ({E_s:.2f}s)!"
                )
                return  # => Abbruch, nichts weiter setzen
        
            self.gpx_widget.gpx_list.set_markB_row(row)
            self.map_widget.set_markB_point(row)
            
            # Und analog ins cut_manager
            self.cut_manager.markB_time_s = global_s
            self.timeline.set_markB_time(global_s)

    

    def on_markE_clicked(self):
        print("[DEBUG] Alter markE")
        return
        
       

    
    def _on_markE_from_video(self):
        print("[DEBUG] MarkE from Video")
        
        if not self._autoSyncVideoEnabled:
            row = self.gpx_widget.gpx_list.table.currentRow()
            if row < 0:
                return
            #self.gpx_widget.gpx_list.set_markE_row(row)
            self.map_widget.set_markE_point(row)
            
            global_s = self.video_editor.get_current_position_s()
            self.cut_manager.markE_time_s = global_s
            self.timeline.set_markE_time(global_s)
        else:
            # AutoSync=ON
            global_s = self.video_editor.get_current_position_s()
            final_s  = self.get_final_time_for_global(global_s)
            best_idx = self.gpx_widget.get_closest_index_for_time(final_s)
            
           
            row = best_idx
            # clamp ...
            if row < 0:
                return
            maxrow = len(self.gpx_widget.gpx_list._gpx_data)-1
            if row > maxrow:
                row = maxrow
                
            B_s = self.cut_manager.markB_time_s
            if B_s >= 0 and global_s <= B_s:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Invalid MarkE",
                    f"You cannot set MarkE ({global_s:.2f}s) in front of MarkB ({B_s:.2f}s)!"
                )
                return  # => Abbruch    
            
            self.gpx_widget.gpx_list.set_markE_row(row)
            self.map_widget.set_markE_point(row)
            
            self.cut_manager.markE_time_s = global_s
            self.timeline.set_markE_time(global_s)
    
    def _on_markE_from_gpx(self):
        print("[DEBUG] Mark E from gpx")
        
        
        if not self._autoSyncVideoEnabled:
            row = self.gpx_widget.gpx_list.table.currentRow()
            if row < 0:
                return
            self.gpx_widget.gpx_list.set_markE_row(row)
            self.map_widget.set_markE_point(row)
            
            #global_s = self.video_editor.get_current_position_s()
            #self.cut_manager.markE_time_s = global_s
            #self.timeline.set_markE_time(global_s)
        else:
            # AutoSync=ON
            global_s = self.video_editor.get_current_position_s()
            final_s  = self.get_final_time_for_global(global_s)
            best_idx = self.gpx_widget.get_closest_index_for_time(final_s)
            
           
            row = best_idx
            # clamp ...
            if row < 0:
                return
            maxrow = len(self.gpx_widget.gpx_list._gpx_data)-1
            if row > maxrow:
                row = maxrow
                
            B_s = self.cut_manager.markB_time_s
            if B_s >= 0 and global_s <= B_s:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Invalid MarkE",
                    f"You cannot set MarkE ({global_s:.2f}s) in front of MarkB ({B_s:.2f}s)!"
                )
                return  # => Abbruch    
            
            self.gpx_widget.gpx_list.set_markE_row(row)
            self.map_widget.set_markE_point(row)
            
            self.cut_manager.markE_time_s = global_s
            self.timeline.set_markE_time(global_s)
    
    
    
    
    #neu2
    def _on_gpx_list_pause_clicked(self, row_idx: int):
        if not self.video_editor.is_playing:
            # Statt select_point_in_pause => show_blue
            #self.map_widget.show_blue(row_idx)
            self.map_widget.show_blue(row_idx, do_center=True)
            self.chart.highlight_gpx_index(row_idx)
            if self._autoSyncNewPointsWithVideoTime and self.video_editor.is_video_loaded():
                self.on_map_sync_any()

    def _on_map_pause_clicked(self, index: int):
        """
        Wird aufgerufen, wenn im Pause-Modus in der Karte
        ein Punkt geklickt wurde.
        => Markiere denselben Index in der GPX-Liste!
        """
        if not self.video_editor.is_playing:
            self.gpx_widget.gpx_list.select_row_in_pause(index)
            self.chart.highlight_gpx_index(index)
    #neu2


    def _show_copyright_dialog(self):
        
        counts = self._fetch_counters_from_server()
        if counts:
            vcount = counts.get("video", 0)
            gcount = counts.get("gpx", 0)
        else:
            vcount, gcount = 0, 0
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Copyright")
        msg.setText(
            "<h3>VGSync - Video and GPX Sync Tool</h3>"
            f"Version: {APP_VERSION}<br><br>"
            
            "Copyright (C) 2025 Bernd Eller<br>"
            "This program is free software: you can redistribute it and/or modify "
            "it under the terms of the GNU General Public License as published by "
            "the Free Software Foundation, either version 3 of the License, or "
            "(at your option) any later version.<br><br>"
        
            "This program is distributed in the hope that it will be useful, "
            "but WITHOUT ANY WARRANTY; without even the implied warranty of "
            "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. "
            "See the GNU General Public License for more details.<br><br>"
            
            "You should have received a copy of the GNU General Public License "
            "along with this program. If not, see "
            "<a href='https://www.gnu.org/licenses/'>https://www.gnu.org/licenses/</a>.<br><br>"
            
            "<h3>Third-Party Libraries & Patent Notice</h3>"
            "This application includes and distributes open-source libraries:<br>"
            "<b>1. FFmpeg</b> - <a href='https://ffmpeg.org'>ffmpeg.org</a> (GPL build)<br>"
            "<b>2. mpv</b> - <a href='https://mpv.io'>mpv.io</a> (GPL build)<br><br>"
             "Full license texts for these libraries are located in the <br>"
             "<code>_internal/ffmpeg</code> and <code>_internal/mpv</code> folders.<br>"            
            "The complete source code for these libraries as used in this software "
            "is available at "
            "<a href='http://vgsync.casa-eller.de'>http://vgsync.casa-eller.de</a>.<br><br>"
            
            "<b>Patent Encumbrance Notice:</b><br>"
            "Some codecs (such as x265) may be patent-encumbered in certain jurisdictions. "
            "It is the user's responsibility to ensure compliance with all applicable "
            "laws and regulations, and to obtain any necessary patent licenses.<br><br>"
            
            "<b>By clicking 'I Accept', you acknowledge that you have read and "
            "understood the GNU General Public License terms.</b><br><br>"
            f"V: {vcount}  G: {gcount}"
)
        msg.exec()
    
   

    
        

    def _on_timer_mode_changed(self):
        if self.action_global_time.isChecked():
            self._time_mode = "global"
        elif self.action_final_time.isChecked():
            self._time_mode = "final"
        self.update_timeline_marker()
        self.video_editor.set_time_mode(self._time_mode)    

    def _get_offset_for_filepath(self, video_path):
        try:
            idx = self.playlist.index(video_path)
        except ValueError:
            return 0.0
        return sum(self.video_durations[:idx])

   

   
    # Im MainWindow (oder ImportExportManager, wo du es hast)
    def start_indexing_process(self, video_path):
       

        dlg = _IndexingDialog(video_path, parent=self)
        dlg.indexing_extracted.connect(self.on_extract_finished)
        dlg.start_indexing()

        # => Wichtig:
        dlg.show()
        
        QApplication.processEvents()

        dlg.raise_()
        dlg.activateWindow()

        result = dlg.exec()
        if result == QDialog.Accepted:
            print("[DEBUG] IndexingDialog => Accepted")
        else:
            print("[DEBUG] IndexingDialog => Rejected/Closed")

   


    def on_extract_finished(self, video_path, temp_dir):
        """
        Wird aufgerufen, wenn das Indexing-Tool die CSV-Datei erstellt hat.
        Hier rufen wir dann self.run_merge(...) auf.
        """
        print("[DEBUG] on_extract_finished => rufe run_merge an ...")
    
        
        base_name = os.path.splitext(os.path.basename(video_path))[0]
    
        # BAUE den CSV-Dateinamen
        csv_path = os.path.join(temp_dir, f"keyframes_{base_name}_ffprobe.csv")
    
        # Jetzt run_merge aufrufen
        self.run_merge(
            video_path=video_path,
            csv_file=csv_path,     # <-- Hier definieren wir csv_path
            temp_dir=temp_dir
        )
    
    # -----------------------------------------------------------------------
    # Detach-Funktionen Video
    # -----------------------------------------------------------------------
    def _toggle_video(self):
        if self._video_area_floating_dialog is None:
            self._detach_video_area_widget()
            self.action_toggle_video.setText("Video (attach)")
        else:
            self._reattach_video_area_widget()
            self.action_toggle_video.setText("Video (detach)")

    def _reattach_video_area_widget(self):
        if not self._video_area_floating_dialog:
            return

        # 1) Dialog schließen
        self._video_area_floating_dialog.close()
        self._video_area_floating_dialog = None
    
        # 2) Platzhalter entfernen
        if self._video_placeholder is not None:
            idx = self.left_v_layout.indexOf(self._video_placeholder)
            if idx >= 0:
                self.left_v_layout.removeWidget(self._video_placeholder)
            self._video_placeholder.deleteLater()
            self._video_placeholder = None

        # 3) Video wieder einfügen (am selben Index)
        #    Falls du es wieder ganz oben haben willst, kannst du idx=0 nehmen
        self.left_v_layout.insertWidget(0, self.video_area_widget, 1)

       


    def _detach_video_area_widget(self):
        if self._video_area_floating_dialog is not None:
            # Schon abgekoppelt
            return

        # 1) Platzhalter erstellen (falls du ihn farblich hervorheben willst)
        #self._video_placeholder = QFrame()
        #self._video_placeholder.setStyleSheet("background-color: #444;")

        # 2) Index des video_area_widget im left_v_layout suchen
        idx = self.left_v_layout.indexOf(self.video_area_widget)
        if idx < 0:
            # Falls nicht gefunden => wir brechen lieber ab
            return
            
            
        self.left_v_layout.removeWidget(self.video_area_widget)
        self._video_placeholder = QFrame()
        self._video_placeholder.setStyleSheet("background-color: #444;")    

        # 3) An dieser Position den Platzhalter einfügen
        self.left_v_layout.insertWidget(idx, self._video_placeholder, 1)

        # 4) Das video_area_widget aus dem Layout entfernen
        #self.left_v_layout.removeWidget(self.video_area_widget)

        # 5) In einem neuen Dialog unterbringen
        dlg = DetachDialog(self)
        dlg.setWindowTitle("Video Editor (Detached)")
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        layout = QVBoxLayout(dlg)
        layout.addWidget(self.video_area_widget)

        # Signale für + / - / Reattach
        dlg.requestPlus.connect(self._on_detached_plus)
        dlg.requestMinus.connect(self._on_detached_minus)
        dlg.requestReattach.connect(self._on_request_reattach_floating)

        self._video_area_floating_dialog = dlg
        dlg.show()

        # Nach dem Anzeigen neu binden
        QTimer.singleShot(10, lambda: self._after_show_detached(dlg))
        
    
    

    def _after_show_detached(self, dlg: QDialog):
        this_screen = dlg.screen()
        if not this_screen:
            from PySide6.QtGui import QGuiApplication
            this_screen = QGuiApplication.primaryScreen()
        scr_geom = this_screen.availableGeometry()

        new_w = int(scr_geom.width() * 0.7)
        new_h = int(scr_geom.height() * 0.7)
        dlg.resize(new_w, new_h)

        frame_geo = dlg.frameGeometry()
        frame_geo.moveCenter(scr_geom.center())
        dlg.move(frame_geo.topLeft())

        

    def _on_request_reattach_floating(self):
        self._reattach_video_area_widget()

    def _on_detached_plus(self):
        if self.speed_index < len(self.vlc_speeds) - 1:
            self.speed_index += 1
        self.current_rate = self.vlc_speeds[self.speed_index]
        self.video_editor.set_playback_rate(self.current_rate)

    def _on_detached_minus(self):
        if self.speed_index > 0:
            self.speed_index -= 1
        self.current_rate = self.vlc_speeds[self.speed_index]
        self.video_editor.set_playback_rate(self.current_rate)    

    
   
    def load_mp4_files(self):
       
        
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Load MP4 files",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi)",
        )
        if not files:
            return

        # 1) Alle ausgewählten Dateien in die Playlist hängen,
        #    ohne zwischendurch den Player zu starten:
        for file_path in files:
            self.add_to_playlist(file_path)

        # 2) Timeline neu berechnen
        self.rebuild_timeline()

        # 3) Erst am Ende einmal den ersten Frame vom allerersten Video zeigen:
        if self.playlist:
            self.video_editor.show_first_frame_at_index(0)

        QMessageBox.information(self, "Loaded", f"{len(files)} video(s) added to the playlist.")
    
   
    def _set_gpx_data(self, gpx_data):
        """Integriere die Daten in UI + merke sie in self._gpx_data."""
        self._gpx_data = gpx_data
        self.gpx_widget.set_gpx_data(gpx_data)

        self.chart.set_gpx_data(gpx_data)
        if self.mini_chart_widget:
            self.mini_chart_widget.set_gpx_data(gpx_data)

        route_geojson = self._build_route_geojson_from_gpx(gpx_data)
        self.map_widget.loadRoute(route_geojson, do_fit=True)
        self._apply_map_sizes_from_settings()
        self._update_gpx_overview()
        self.check_gpx_errors(gpx_data)

    def _parse_and_set_gpx(self, file_path, mode="new"):
        """
        Parst die GPX-Datei und hängt sie je nach mode ("new" vs. "append")
        an die vorhandene self._gpx_data an.
        """
        # 1) Kurzes Loading-Overlay oder Statusmeldung
        self.map_widget.view.page().runJavaScript("showLoading('Parsing GPX...');")
        QApplication.processEvents()

        # 2) PARSEN
        try:
            new_data = parse_gpx(file_path)
            ensure_gpx_stable_ids(new_data)
            if not new_data:
                QMessageBox.warning(self, "Load GPX", "File is empty or invalid.")
                self.map_widget.view.page().runJavaScript("hideLoading();")
                return
        except Exception as e:
            QMessageBox.critical(self, "Load GPX", f"Error parsing file:\n{e}")
            self.map_widget.view.page().runJavaScript("hideLoading();")
            return

        # 3) Je nach mode: "new" vs "append"
        if mode == "new" or (not self._gpx_data):
            # => alte Daten verwerfen
            self._set_gpx_data(new_data)
            QMessageBox.information(self, "Load GPX", "New GPX loaded successfully.")
        elif mode == "append":
            if not self._gpx_data:
                # falls aus irgendeinem Grund doch leer => wie "new"
                self._set_gpx_data(new_data)
            else:
                # => an vorhandene Daten dranhängen
                old_data = self._gpx_data

                # Optional: Undo-Snapshot
                old_snapshot = self.copy.deepcopy(old_data)
                self.gpx_widget.gpx_list._history_stack.append(old_snapshot)

                old_end_time = old_data[-1]["time"]  # datetime
                gap_start = old_end_time + timedelta(seconds=1)
                shift_dt = gap_start - new_data[0]["time"]
                shift_s = shift_dt.total_seconds()

                # alle Zeitstempel verschieben
                for pt in new_data:
                    pt["time"] = pt["time"] + shift_dt
                    pt["rel_s"] += shift_s

                merged_data = old_data + new_data
                recalc_gpx_data(merged_data)
                self._set_gpx_data(merged_data)

                QMessageBox.information(self, "Load GPX", "GPX appended successfully.")

        # 4) Overlay beenden
        self.map_widget.view.page().runJavaScript("hideLoading();")

   
    def load_gpx_file(self):
        # (A) Wenn schon GPX da ist => sofort Dialog
        if self._gpx_data:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Load GPX")
            msg_box.setText("A GPX is already loaded.\n"
                            "Do you want to start a new GPX or append the new file?")
            new_btn = msg_box.addButton("New", QMessageBox.AcceptRole)
            append_btn = msg_box.addButton("Append", QMessageBox.YesRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.RejectRole)

            msg_box.setWindowModality(Qt.WindowModal)
            msg_box.show()
            QApplication.processEvents()  # damit man ihn sofort sieht

            msg_box.exec()
            clicked = msg_box.clickedButton()
            if clicked == cancel_btn:
                return  # Nutzer hat abgebrochen
            elif clicked == new_btn:
                mode = "new"
            else:
                mode = "append"
        else:
            # => Noch keine GPX => Modus: new
            mode = "new"
    
            
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GPX File",
            "",
            "GPX Files (*.gpx)",
        )
        if not file_path:
            return  # Abbruch
    
        
        self.map_widget.view.page().runJavaScript("showLoading('Loading GPX...');")
        QApplication.processEvents()
    
        # parse, ensureIDs, etc.
        new_data = parse_gpx(file_path)
        if not new_data:
            QMessageBox.warning(self, "Load GPX", "File is empty or invalid.")
            self.map_widget.view.page().runJavaScript("hideLoading();")
            return
    
        if mode == "new":
            self._set_gpx_data(new_data)
            QMessageBox.information(self, "Load GPX", "New GPX loaded successfully.")
        elif mode == "append":
            if not self._gpx_data:
                # Falls doch leer => wie new
                self._set_gpx_data(new_data)
            else:
                # => alte + neue zusammen
                old_data = self._gpx_data
    
                # optional Undo
                old_snapshot = self.copy.deepcopy(old_data)
                self.gpx_widget.gpx_list._history_stack.append(old_snapshot)
    
                from datetime import timedelta
                old_end_time = old_data[-1]["time"]
                gap_start = old_end_time + timedelta(seconds=1)
                shift_dt = gap_start - new_data[0]["time"]
    
                shift_s = shift_dt.total_seconds()
                for pt in new_data:
                    pt["time"] = pt["time"] + shift_dt
                    pt["rel_s"] += shift_s
    
                merged_data = old_data + new_data
                recalc_gpx_data(merged_data)
                self._set_gpx_data(merged_data)
                QMessageBox.information(self, "Load GPX", "GPX appended successfully.")
    
        self.map_widget.view.page().runJavaScript("hideLoading();")
        
    
    
    def update_timeline_marker(self):
        
        """
        Wird periodisch aufgerufen (z.B. alle 200ms) und aktualisiert:
        - Timeline:   Setzt den Marker
        - VideoEditor-Label:  Zeigt die aktuelle Zeit
        - VideoControl:       Setzt h:m:s
        - GPX/Map/Chart:      Wandert mit, solange is_playing=True
        """
        # 1) Aktuelle (globale) Videoposition abfragen:
        global_s = self.video_editor.get_current_global_time()
        if global_s < 0:
            global_s = 0.0
    
        # 2) Unterscheide, ob wir final oder global anzeigen wollen:
        if self._time_mode == "final":
            display_time = self.get_final_time_for_global(global_s)
        else:
            display_time = global_s
        
        # 3) Timeline-Marker (immer in "global" Koordinaten):
        self.timeline.set_marker_position(global_s)
        
        # 4) Zeit im VideoEditor-Label & VideoControl anzeigen
        s_rounded = round(display_time)
        hh = s_rounded // 3600
        mm = (s_rounded % 3600) // 60
        ss = s_rounded % 60
    
        self.video_editor.set_current_time(display_time)
        self.video_control.set_hms_time(hh, mm, ss)

        # 5) Wenn das Video gerade läuft => aktualisieren wir GPX/Map/Chart
        if self.video_editor.is_playing:
            # a) Welche "finale" Zeit markiert werden soll, hängt wieder vom Mode ab
            if self._time_mode == "final":
                final_s = display_time
            else:
                # falls _time_mode == "global", konvertieren wir global_s zu final_s
                final_s = self.get_final_time_for_global(global_s)
        
            # b) GPX-Widget highlighten
            self.gpx_widget.highlight_video_time(final_s, is_playing=True)

            # c) Index im GPX finden
            i = self.gpx_widget.get_closest_index_for_time(final_s)
        
            # d) Chart-Index highlighten
            self.chart.highlight_gpx_index(i)
        
            # e) Mini-Chart ebenfalls
            if self.mini_chart_widget:
                self.mini_chart_widget.set_current_index(i)
        
            # f) Map => gelben Marker
            self.map_widget.show_yellow(i)
        else:
            # Video pausiert => kein automatisches "Mitlaufen" in Map/GPX
            pass

    
    
    def _on_chart_marker_clicked(self, index: int):
        """
        Wird aufgerufen, wenn man im ChartWidget an Position index klickt.
        => Dann selektieren wir diesen index in gpx_list und Map, 
        und ggf. Video an diese Stelle spulen.
        """
        print(f"[DEBUG] _on_chart_marker_clicked => idx={index}")
        # 1) gpx_list => select_row_in_pause
        if not self.video_editor.is_playing:
            self.gpx_widget.gpx_list.select_row_in_pause(index)
            # => map
            #self.map_widget.select_point_in_pause(index)
            self.map_widget.show_blue(index, do_center=True)
            #self.map_widget.show_blue(index)
            self.chart.highlight_gpx_index(index)
        else:
            # Wenn Video gerade läuft => evtl. jump dorthin
            # ... oder du pausierst / oder was du willst
            pass

       
        self.chart.highlight_gpx_index(index)


    

    
    def add_to_playlist(self, filepath):
        if filepath not in self.playlist:
            self.playlist.append(filepath)
            self.playlist_counter += 1
            label_text = f"{self.playlist_counter}: {os.path.basename(filepath)}"
            action = self.playlist_menu.addAction(label_text)
            action.triggered.connect(lambda checked, f=filepath, a=action: self.confirm_remove(f, a))

            
            self.video_editor.set_playlist(self.playlist)
            
            if self._edit_mode in ("copy", "encode") and (not self._userDeclinedIndexing):
                self.start_indexing_process(filepath)
            else:
                print("[DEBUG] Kein Indexing, weil der User es abgelehnt hat oder EditVideo=OFF.")                
           

    def confirm_remove(self, filepath, action):
        msg = QMessageBox(self)
        msg.setWindowTitle("Delete?")
        msg.setText(f"Delete {os.path.basename(filepath)} from playlist?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        r = msg.exec()
        if r == QMessageBox.Yes:
            self.remove_from_playlist(filepath, action)
   
   
    def remove_from_playlist(self, filepath, action):
        if filepath in self.playlist:
            idx = self.playlist.index(filepath)
            self.playlist.remove(filepath)
            if idx < len(self.video_durations):
                self.video_durations.pop(idx)

            self.playlist_menu.removeAction(action)
            
            # STATT rebuild_vlc_playlist():
            self.video_editor.set_playlist(self.playlist)

            # Timeline anpassen:
            self.rebuild_timeline()
    
    
    def rebuild_timeline(self):
        self.video_durations = []
        offset = 0.0
        for path in self.playlist:
            dur = self.get_video_length_ffprobe(path)
            self.video_durations.append(dur)
            offset += dur
        self.real_total_duration = offset
        self.timeline.set_total_duration(self.real_total_duration)

        boundaries = []
        ofs = 0.0
        for d in self.video_durations:
            ofs += d
            boundaries.append(ofs)
        self.timeline.set_boundaries(boundaries)

        self.video_editor.set_total_length(self.real_total_duration)
        self.video_editor.set_multi_durations(self.video_durations)
        self.cut_manager.set_video_durations(self.video_durations)
        self._update_gpx_overview()

    def get_video_length_ffprobe(self, filepath):
        cmd = [
            "ffprobe", "-v", "quiet", "-of", "csv=p=0",
            "-show_entries", "format=duration", filepath
        ]
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            val = float(out.strip())
            if val > 0:
                return val
            return 0.0
        except:
            return 0.0

    def run_merge(self, video_path, csv_file, temp_dir):
        print("[DEBUG] run_merge => direkt merge_keyframes_incremental aufrufen ...")
        offset_value = self._get_offset_for_filepath(video_path)
        label = os.path.basename(video_path)
        json_file = os.path.join(temp_dir, "merged_keyframes.json")
    
        try:
            merge_keyframes_incremental(
                csv_file=csv_file,
                json_file=json_file,
                label=label,
                offset=offset_value,
                do_sort=True
            )
            # Danach ggf. self.on_indexing_finished(temp_dir) aufrufen
            self.on_indexing_finished(temp_dir)

        except Exception as e:
            print("Fehler beim Merge:", e)
            QMessageBox.warning(self, "Merge Error", "Merge step failed.")

    def on_indexing_finished(self, temp_dir):
        merged_json = os.path.join(temp_dir, "merged_keyframes.json")
        if not os.path.exists(merged_json):
            print("[DEBUG] merged_keyframes.json nicht gefunden in", temp_dir)
            return

        try:
            with open(merged_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            new_kfs = []
            for entry in data:
                try:
                    gt = float(entry.get("global_time", 0.0))
                    new_kfs.append(gt)
                except:
                    pass
            new_kfs.sort()

            self.global_keyframes.extend(new_kfs)
            self.global_keyframes = sorted(set(self.global_keyframes))
            print("[DEBUG] %d Keyframes global geladen (gesamt)." % len(self.global_keyframes))

        except Exception as e:
            print("[DEBUG] Fehler beim Laden der JSON:", e)

    # -----------------------------------------------------------------------
    # Marker- und Player-Funktionen ...
    # -----------------------------------------------------------------------
    
    def on_play_pause(self):
        if self.video_editor.is_playing:
            # => Pause
            self.video_editor.play_pause()
            self.video_control.update_play_pause_icon(False)

            # GPX-List / Map: Pause
            self.gpx_widget.set_video_playing(False)
            self.map_widget.set_video_playing(False)

            # (A) => Falls wir noch einen gelben Play-Marker hatten, revertieren:
            #if self._last_map_idx is not None:
            #    # => Schwarz oder Rot? Da du ggf. in "update_timeline_marker" 
            #    #    den gelben Marker setzt, revertieren wir hier einfach auf schwarz:
            #    self.map_widget.highlight_gpx_point(self._last_map_idx, "#000000", 4, False)
            #    self._last_map_idx = None
            
            self.cut_manager.stop_skip_timer()

        else:
            
            if not self.cut_manager._has_active_file():
                if self.playlist:
                    self.video_editor.show_first_frame_at_index(0)
            
            if self._video_at_end:
                # => Wir waren am Ende => also erst "stoppen"
                self.on_stop()             # ruft dein Stop-Verhalten auf
                self._video_at_end = False # Reset dieses Merkers
            
            
            # => PLAY
            self.video_editor.play_pause()
            self.video_control.update_play_pause_icon(True)

            # GPX-List / Map: Play
            self.gpx_widget.set_video_playing(True)
            self.map_widget.set_video_playing(True)

            # Optional: Einmalig Karte zentrieren
            ...
            self.cut_manager.start_skip_timer()
    
    
    def _get_cut_end_if_any(self) -> float:
        """
        Falls es in cut_manager._cut_intervals einen Bereich (0.0, end_s) gibt,
        gib end_s zurück. Sonst 0.0
        """
        cut_intervals = self.cut_manager.get_cut_intervals()  # Liste (start_s, end_s)
        for (start_s, end_s) in cut_intervals:
            # Prüfen mit kleinem Toleranzwert:
            if abs(start_s) < 0.0001:
                return end_s
        return 0.0
        
    
      
    
    def on_stop(self):
        self.video_editor.stop()
        
    def on_play_ended(self):
        self.video_control.update_play_pause_icon(False)

        # 1) Player manuell in "Pause"-State
        # mpv self.video_editor.media_player.pause()
        self.video_editor._player.pause = True
        self.video_editor.is_playing = False

        # 2) GPX/Map => wir sind in Pause
        self.gpx_widget.set_video_playing(False)
        self.map_widget.set_video_playing(False)

        # 3) Gelben Marker entfernen
        lw = self.gpx_widget.gpx_list
        if lw._last_video_row is not None:
            lw._mark_row_bg_except_markcol(lw._last_video_row, Qt.white)
            lw._last_video_row = None
        
        self._video_at_end = True
    
    def _jump_player_to_time(self, new_s: float):
        total = sum(self.video_durations)
        if total <= 0:
            return
        new_s = max(0.0, min(new_s, total))

        # boundaries + local_s berechnen
        boundaries = []
        offset = 0.0
        for dur in self.video_durations:
            offset += dur
            boundaries.append(offset)

        new_idx = 0
        offset_prev = 0.0
        for i, b in enumerate(boundaries):
            if new_s < b:
                new_idx = i
                break
            offset_prev = b
    
        local_s = new_s - offset_prev
        if local_s < 0:
            local_s = 0
    
        old_idx = self.video_editor._current_index
    
        # 1) Falls wir das Video wechseln müssen:
        if new_idx != old_idx:
            self.video_editor._player.command('stop')
            self.video_editor.is_playing = False
            self.video_editor._current_index = new_idx
    
            if new_idx < len(self.playlist):
                path_ = self.playlist[new_idx]
                self.video_editor._player.command('loadfile', path_)
                # => local_s
                self.video_editor._player.seek(local_s, reference='absolute')
                self.video_editor._player.pause = True
                self.video_editor.is_playing = False
        else:
            # Gleicher Index => nur seek
            self.video_editor._player.seek(local_s, reference='absolute')
            self.video_editor._player.pause = True
            self.video_editor.is_playing = False
            


    def on_step_mode_changed(self, new_value):
        self.step_manager.set_step_mode(new_value)

    def on_multiplier_changed(self, new_value):
        numeric = new_value.replace("x", "")
        try:
            val = float(numeric)
        except:
            val = 1.0
        self.step_manager.set_step_multiplier(val)

    def _on_timeline_marker_moved(self, new_time_s: float):
        #self._jump_player_to_time(new_time_s)
        self.video_editor._jump_to_global_time(new_time_s)
        
    def _on_timeline_overlay_remove(self, start_s, end_s):
        self._overlay_manager.remove_overlay_interval(start_s, end_s)    

    def on_time_hms_set_clicked(self, hh: int, mm: int, ss: int, ms=0):
        """
        Empfängt das Signal vom VideoControlWidget (SetTime-Button).
        Rechnet hh:mm:ss => globale Sekunde => springt dorthin.
        """
        # 1) h/m/s in float-Sekunden
        total_s = hh * 3600 + mm * 60 + ss + (ms / 1000.0)
        
        
        if self.cut_manager.is_in_cut_segment(total_s):
            QMessageBox.warning(
                self,
                "Invalid Time",
                "This time is inside a cut segment.\nCannot jump there!"
            )
            return  # Abbruch

    
        # 2) Begrenzen auf [0 .. real_total_duration]
        if total_s < 0:
            total_s = 0.0
        if total_s > self.real_total_duration:
            total_s = self.real_total_duration
    
        # 3) Aufruft der mpv-Funktion => "globaler" Sprung
        self.video_editor.set_time(total_s)
        #
        # Damit ruft Ihr intern mpv._jump_to_global_time(total_s) auf,
        # das berechnet, in welchem Clip wir landen und spult dorthin.
        #
    
    
    
    def _after_hms_switch(self, local_s):
        """
        1) Setzt die local_s
        2) Startet kurz das Abspielen (ohne is_playing=True zu setzen), 
        damit VLC das Frame dekodieren kann.
        3) Ein kleiner Timer pausiert wieder => Frame ist sichtbar.
        """
        # mpv self.video_editor.media_player.set_time(int(local_s * 1000))
        self.video_editor.set_time(local_s)  # (float Sek in MPV)
        self.video_editor.media_player.play()
    
        
        #QTimer.singleShot(80, lambda: self._really_pause)
        QTimer.singleShot(80, lambda: self._really_pause())
    

    def _really_pause(self):
        """
        Pausiert das Video => wir bleiben direkt am Zielbild stehen
        (statt weiterzulaufen wie zuvor).
        """
        # mpv self.video_editor.media_player.pause()
        self.video_editor._player.pause = True
        # Falls du NICHT willst, dass "is_playing=True" war, 
        # lässt du es weg - hier also is_playing=False, 
        # oder gar nicht verändern.
        self.video_editor.is_playing = False


    def _pause_player_popup(self):
        # mpv self.video_editor.media_player.pause()
        self.video_editor._player.pause = True
        self.video_editor.is_playing = False
        real_s = self.video_editor.get_current_position_s()
        self.video_editor.set_current_time(real_s)

        hh = int(real_s // 3600)
        mm = int((real_s % 3600) // 60)
        ss = int(real_s % 60)
        #self.video_control.set_hms_time(hh, mm, ss)
    
    
    def _on_cuts_changed(self, sum_of_cuts_s):
        print("[DEBUG] _on_cuts_changed => sum_of_cuts_s:", sum_of_cuts_s)
        new_duration = self.real_total_duration - sum_of_cuts_s
        if new_duration < 0:
            new_duration = 0
        self.video_editor.set_old_time(self.real_total_duration)
        self.video_editor.set_cut_time(new_duration)
        self._update_gpx_overview()    
        
        
    ## on_safe_click
    def on_safe_clicked(self):
        # 1) Sicherheitsabfrage
        msg = QMessageBox(self)
        msg.setWindowTitle("Are you sure?")
        msg.setText("We are now creating the final video, changes are no longer possible! Sure?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        r = msg.exec()
        if r == QMessageBox.No:
            return

        if not self.playlist:
            QMessageBox.warning(self, "Error", "No videos in playlist!")
            return
            
        # -------------------------------------------------
        # NEUE LOGIK: Wenn Edit-Mode == "encode" => JSON schreiben
        if self._edit_mode == "encode":
            
            # 1) Daten aus QSettings lesen (Encoder Setup)
            s = QSettings("VGSync","VGSync")
            xfade_val   = s.value("encoder/xfade", 2, type=int)
            hw_encode   = s.value("encoder/hw", "none", type=str)
            container   = s.value("encoder/container", "x265", type=str)
            crf_val     = s.value("encoder/crf", 25, type=int)
            fps_val     = s.value("encoder/fps", 30, type=int)
            preset_val  = s.value("encoder/preset", "fast", type=str)
            width_val   = s.value("encoder/res_w", 1280, type=int)

            # 2) Cuts => skip_instructions
            #   Format [start_s, end_s, xfade]
            cuts = self.cut_manager.get_cut_intervals()  # Liste (start_s, end_s)
            skip_array = []
            total_dur = self.real_total_duration
            sorted_cuts = sorted(cuts, key=lambda x: x[0])
            
            for (cstart, cend) in sorted_cuts:
                if abs(cstart - 0.0) < 0.1:
                    skip_array.append([cstart, cend, -2])  # Startcut
                elif abs(cend - total_dur) < 0.1:
                    skip_array.append([cstart, cend, -1])  # Endcut
                else:
                    skip_array.append([cstart, cend, xfade_val])
        
            # Debug-Ausgabe, damit du siehst, was wirklich passiert:
            print("DEBUG skip_array:", skip_array)
            
            print("DEBUG: Chronologisch sortierte skip_array:", skip_array)



            # 3) Overlays => overlay_instructions
            #   Jedes Overlay = dict mit "start","end","fade_in","fade_out","image","scale","x","y"
            all_ovls = self._overlay_manager.get_all_overlays()
            overlay_list = []
            for ovl in all_ovls:
                overlay_list.append({
                    "start":    ovl["start"],
                    "end":      ovl["end"],
                    "fade_in":  ovl.get("fade_in", 0),
                    "fade_out": ovl.get("fade_out", 0),
                    "image":    ovl.get("image",""),
                    "scale":    ovl.get("scale",1.0),
                    "x":        ovl.get("x","0"),
                    "y":        ovl.get("y","0"),
                })

            # 4) Ziel-Dateinamen (können Sie frei anpassen)
            merged_out = "merged.mp4"
            final_out  = "final_out.mp4"

            # 5) JSON-Dict bauen
            export_data = {
                "videos": self.playlist,
                "skip_instructions": skip_array,
                "overlay_instructions": overlay_list,
                "merged_output": merged_out,
                "final_output": final_out,
                "hardware_encode": hw_encode,
                # "encoder" könnte z.B. "libx264"/"libx265" heißen:
                "encoder": f"lib{container}",  
                "crf": crf_val,
                "fps": fps_val,
                "width": width_val,
                "preset": preset_val
            }

            
            #temp_dir = tempfile.gettempdir()
            # 6) In unser VGSync-Temp speichern
            
            temp_dir = MY_GLOBAL_TMP_DIR
            json_path = os.path.join(temp_dir, "vg_encoder_job.json")
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)

            #dlg = EncoderDialog(parent=self)
            #dlg.run_encoding(json_path)
            #dlg.exec()
            #self.setWindowTitle("Encoding in progress – please wait…")
            
            dlg = EncoderDialog(parent=self)
            dlg.show()  # ⬅️ Fenster sofort zeigen!
            QApplication.processEvents()  # ⬅️ wichtig, damit GUI reagiert

            dlg.run_encoding(json_path)  # ⬅️ d
            
            
            return
        
            

        total_dur = self.real_total_duration
        sum_cuts = self.cut_manager.get_total_cuts()
        final_duration_s = total_dur - sum_cuts
        if final_duration_s < 0:
            final_duration_s = 0

        out_file, _ = QFileDialog.getSaveFileName(
            self,
            "Select output file",
            "output_final.mp4",
            "Video Files (*.mp4 *.mov *.mkv *.avi)"
        )
        if not out_file:
            return

        keep_intervals = self._compute_keep_intervals(self.cut_manager._cut_intervals, total_dur)
        if not keep_intervals:
            QMessageBox.warning(self, "Error", "All time ranges are cut! Nothing to export.")
            return

       
        tmp_dir = MY_GLOBAL_TMP_DIR  # denselben Ordner nutzen
        

        # 2) Statt direkt ffmpeg aufzurufen => wir bauen eine Liste an Commands
        segment_commands = []
        segment_files = []
        seg_index = 0

        for (global_start, global_end) in keep_intervals:
            partials = self._resolve_partial_intervals(global_start, global_end)
            for (vid_idx, local_st, local_en) in partials:
                source_path = self.playlist[vid_idx]
                seg_len = local_en - local_st
                if seg_len <= 0.01:
                    continue
                out_segment = os.path.join(tmp_dir, f"segment_{seg_index:03d}.mp4")
                segment_files.append(out_segment)

                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{local_st:.3f}",
                    "-to", f"{local_en:.3f}",
                    "-i", source_path,
                    "-c", "copy",
                    out_segment
                ]
                segment_commands.append(cmd)
                seg_index += 1

        # 3) Concat-File
        concat_file = os.path.join(tmp_dir, "concat_list.txt")
        with open(concat_file, "w") as f:
            for segpath in segment_files:
                f.write(f"file '{segpath}'\n")

        final_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            out_file
        ]

        # 4) Nun unser asynchroner Dialog
        dlg = _SafeExportDialog(self)
        dlg.set_commands(segment_commands, final_cmd, out_file)
        dlg.start_export()  # startet direkt den ersten ffmpeg-Aufruf
        dlg.exec()

        # Wenn du hierher kommst, ist der Dialog geschlossen => entweder fertig oder abgebrochen
        # Ggf. könntest du ein "if dlg.result() == QDialog.Accepted" => print("OK!") etc.
        if dlg.result() == QDialog.Accepted:
            print("Export was successful!")
            ret = self._increment_counter_on_server("video")
            if ret is not None:
                vcount, gcount = ret
                print(f"[INFO] Server-Counter nun: Video={vcount}, GPX={gcount}")
            else:
                print("[WARN] Konnte Video-Zähler nicht hochsetzen.")
        else:
            print("Export canceled or error.")

        
   
        

    def _compute_keep_intervals(self, cut_intervals, total_duration):
        if not cut_intervals:
            return [(0.0, total_duration)]

        sorted_cuts = sorted(cut_intervals, key=lambda x: x[0])
        merged = []
        current_start, current_end = sorted_cuts[0]
        for i in range(1, len(sorted_cuts)):
            (st, en) = sorted_cuts[i]
            if st <= current_end:
                if en > current_end:
                    current_end = en
            else:
                merged.append((current_start, current_end))
                current_start, current_end = st, en
        merged.append((current_start, current_end))

        keep_list = []
        pos = 0.0
        for (cst, cen) in merged:
            if cst > pos:
                keep_list.append((pos, cst))
            pos = cen
        if pos < total_duration:
            keep_list.append((pos, total_duration))

        return keep_list

    def _resolve_partial_intervals(self, global_start, global_end):
        results = []
        if global_end <= global_start:
            return results
        if len(self.video_durations) == 0:
            return results

        boundaries = []
        offset = 0.0
        for dur in self.video_durations:
            offset += dur
            boundaries.append(offset)

        current_s = global_start
        end_s = global_end

        idx = 0
        prev_offset = 0.0
        for i, b in enumerate(boundaries):
            if current_s < b:
                idx = i
                prev_offset = boundaries[i - 1] if i > 0 else 0.0
                break

        while current_s < end_s and idx < len(boundaries):
            video_upper = boundaries[idx]
            local_st = current_s - prev_offset
            segment_end_global = min(end_s, video_upper)
            local_en = segment_end_global - prev_offset

            if local_en > local_st:
                results.append((idx, local_st, local_en))

            current_s = segment_end_global
            idx += 1
            if idx < len(boundaries):
                prev_offset = boundaries[idx - 1]

        return results

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Plus or event.text() == '+':
            if self.speed_index < len(self.vlc_speeds) - 1:
                self.speed_index += 1
                self.current_rate = self.vlc_speeds[self.speed_index]
                self.video_editor.set_playback_rate(self.current_rate)
        elif event.key() == Qt.Key_Minus or event.text() == '-':
            if self.speed_index > 0:
                self.speed_index -= 1
                self.current_rate = self.vlc_speeds[self.speed_index]
                self.video_editor.set_playback_rate(self.current_rate)
        else:
            super(MainWindow, self).keyPressEvent(event)

    def get_final_time_for_global(self, global_s: float) -> float:
        """
        Konvertiert 'global_s' (Rohvideo-Zeit) => 'final_s' (geschnittenes Video).
        Liegen wir exakt auf dem Start eines Cuts, springen wir an den Endpunkt
        des vorherigen Keep-Segments.
        """
        cut_intervals = self.cut_manager._cut_intervals
        total_dur = self.real_total_duration
        if not cut_intervals:
            return min(global_s, total_dur)

        keep_list = self._compute_keep_intervals(cut_intervals, total_dur)
        final_time = 0.0
        EPS = 1e-9

        for (kstart, kend) in keep_list:
            seg_len = (kend - kstart)
            if global_s < (kstart - EPS):
                break
            elif abs(global_s - kstart) <= EPS:
                # exact Start => final bleibt am Ende des letzten
                return final_time
            elif kstart <= global_s < (kend - EPS):
                final_time += (global_s - kstart)
                return final_time
            else:
                final_time += seg_len

        return final_time
        
        
    def get_global_time_for_final(self, final_s: float) -> float:
        """
        Konvertiert 'final_s' (geschnittenes Video) => 'global_s' (Rohvideo-Zeit).
        Liegt final_s exakt am Keep-Segmentende, springen wir ins nächste Segment.
        """
        cut_intervals = self.cut_manager._cut_intervals
        total_dur = self.real_total_duration
        if not cut_intervals:
            return min(final_s, total_dur)

        keep_list = self._compute_keep_intervals(cut_intervals, total_dur)
        remaining = final_s
        EPS = 1e-9

        for (seg_start, seg_end) in keep_list:
            seg_len = (seg_end - seg_start)

            if remaining < seg_len - EPS:
                return seg_start + remaining
            elif abs(remaining - seg_len) <= EPS:
                # exakt Segmentende => Skip in den Anfang des nächsten Keep
                remaining = 0.0
            else:
                remaining -= seg_len

        return total_dur    
        
    def on_sync_clicked(self):
        """
        Sync-Button aus VideoControlWidget: 
        Wir nutzen die *final* Time (falls Cuts) und 
        zeigen in der GPX-Liste + Map (blau) den passenden Punkt.
        """
        # 1) Aktuelle Videoposition => global
        """
        local_time_s = self.video_editor.get_current_position_s()
        if local_time_s < 0:
            local_time_s = 0.0
        video_idx = self.video_editor.get_current_index()
        offset = sum(self.video_durations[:video_idx])
        global_s = offset + local_time_s
        """
        global_s = self.video_editor.get_current_position_s()
        print(f"[DEBUG] on_sync_clicked => get_current_position_s()={global_s:.3f}")

        # 2) => final_s, falls Cuts
        final_s = self.get_final_time_for_global(global_s)

        # 3) => best_idx in GPX
        best_idx = self.gpx_widget.get_closest_index_for_time(final_s)

        # 4) GPX-Liste => Pause => also "select_row_in_pause"
        self.gpx_widget.gpx_list.select_row_in_pause(best_idx)

        # 5) Map => blau => "show_blue"
        #self.map_widget.show_blue(best_idx)
        self.map_widget.show_blue(best_idx, do_center=True)


        # 6) Falls du dein Chart mitziehen möchtest:
        self.chart.highlight_gpx_index(best_idx)


        
    def on_map_sync_any(self):
        """
        Wird von map_widget._on_sync_noarg_from_js aufgerufen,
        wenn der Sync-Button in map_page.html geklickt wird.

        1) Index => map_widget._blue_idx oder fallback => gpx_list.currentRow()
        2) final_s = gpx_data[idx]["rel_s"]
        3) global_s = get_global_time_for_final(final_s)
        4) => on_time_hms_set_clicked => Video
        """
        print("[DEBUG] on_map_sync_any() aufgerufen (Map-Sync)")

        # 1) Welcher Punkt in der Karte? (blau_idx)
        idx_map = self.map_widget._blue_idx
        if idx_map is None or idx_map < 0:
            # fallback => nimm Zeile aus gpx_list
            idx_map = self.gpx_widget.gpx_list.table.currentRow()

        # Prüfung
        row_count = self.gpx_widget.gpx_list.table.rowCount()
        if not (0 <= idx_map < row_count):
            print("[DEBUG] on_map_sync_any => invalid index => Abbruch.")
            return

        # 2) final_s
        point = self._gpx_data[idx_map]
        final_s = point.get("rel_s", 0.0)

        # 3) global_s => Falls Cuts => global_s = get_global_time_for_final(final_s)
        global_s = self.get_global_time_for_final(final_s)

        # => h,m,s
        hh = int(global_s // 3600)
        mm = int((global_s % 3600) // 60)
        s_float = (global_s % 60)      # z.B. 13.456
        ss = int(s_float)             # 13
        ms = int(round((s_float - ss)*1000))  # 456
        
        # 4) => Video-Position
        print(f"[DEBUG] on_map_sync_any => idx={idx_map}, final_s={final_s:.2f}, global_s={global_s:.2f}")
        self.on_time_hms_set_clicked(hh, mm, ss, ms)
        
    

    def _save_gpx_to_file(self, gpx_points, out_file: str):
        """
        Schreibt gpx_points als valides GPX 1.1 in die Datei `out_file`.
        gpx_points: list of dicts with lat, lon, ele, time, rel_s, ...
    
        Zeitformat => "YYYY-MM-DDTHH:MM:SS.xxxZ"
        Beispiel: "2024-07-20T06:50:42.000Z"
        """
       

        if not gpx_points:
            return

        start_time = gpx_points[0].get("time", None)
        end_time   = gpx_points[-1].get("time", None)
        if not start_time:
            start_time = datetime.datetime.now()
        if not end_time:
            end_time = start_time

        # Bsp: 2024-07-20T06:50:42.000Z
        def _format_dt(dt):
            # dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ") => hat 6 Mikrosekunden
            # Wir kürzen auf 3 Stellen => .%f => .xxx
            s = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")  # z.B. 2024-07-20T06:50:42.123456
            # => wir wollen nur die ersten 3 Nachkommastellen
            return s[:-3] + "Z"  # => 2024-07-20T06:50:42.123Z

        start_str = _format_dt(start_time)
        end_str   = _format_dt(end_time)

        track_name = "Exported GPX"
        track_desc = "Cut to final video length"

        with open(out_file, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<gpx version="1.1" creator="MyApp" ')
            f.write('xmlns="http://www.topografix.com/GPX/1/1" ')
            f.write('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
            f.write('xsi:schemaLocation="http://www.topografix.com/GPX/1/1 ')
            f.write('http://www.topografix.com/GPX/1/1/gpx.xsd">\n')

            # Metadata
            f.write('  <metadata>\n')
            f.write(f'    <time>{start_str}</time>\n')
            f.write('  </metadata>\n')

            f.write('  <trk>\n')
            f.write(f'    <name>{track_name}</name>\n')
            f.write(f'    <desc>{track_desc}</desc>\n')
            f.write('    <trkseg>\n')
            for pt in gpx_points:
                lat = pt.get("lat", 0.0)
                lon = pt.get("lon", 0.0)
                ele = pt.get("ele", 0.0)
                dt = pt.get("time", None)
                if dt is None:
                    dt = datetime.datetime.now()
                time_str = _format_dt(dt)
    
                f.write(f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">\n')
                f.write(f'        <ele>{ele:.2f}</ele>\n')
                f.write(f'        <time>{time_str}</time>\n')
                f.write('      </trkpt>\n')
            f.write('    </trkseg>\n')
            f.write('  </trk>\n')
            f.write('</gpx>\n')
    
        print(f"[DEBUG] _save_gpx_to_file => wrote {len(gpx_points)} points to {out_file}")
        
        
   

    ###############################################################################        
    
    def on_chPercent_clicked(self):
        """
        Called when the user clicks the 'ch%' button.
        - If no valid range is selected (or only 1 point in that range),
        it changes the slope for a single point (row) relative to row-1.
        - If a valid range [markB..markE] with >=2 points is selected,
        it applies one consistent slope across that entire range,
        and shifts subsequent points accordingly.
        All user-facing texts are in English.
        """
       
        gpx_data = self.gpx_widget.gpx_list._gpx_data
        if not gpx_data:
            QMessageBox.warning(self, "No GPX Data", "No GPX data available.")
            return
    
        n = len(gpx_data)
        if n < 2:
            QMessageBox.warning(self, "Too few points", "At least 2 GPX points are required.")
            return

        # --- Check if we have a valid markB..markE range ---
        b_idx = self.gpx_widget.gpx_list._markB_idx
        e_idx = self.gpx_widget.gpx_list._markE_idx
    
        valid_range = False
        if b_idx is not None and e_idx is not None:
            if b_idx > e_idx:
                b_idx, e_idx = e_idx, b_idx
            if 0 <= b_idx < n and 0 <= e_idx < n and (e_idx - b_idx) >= 1:
                valid_range = True

        # ------------------------------------------------------------------
        # CASE A) No valid range => single-point slope change
        # ------------------------------------------------------------------
        if not valid_range:
            row = self.gpx_widget.gpx_list.table.currentRow()
            if row < 1:
                QMessageBox.warning(self, "Invalid Selection",
                    "Please select a point with row >= 1.\n"
                    "Cannot compute slope for the very first point (row=0).")
                return
            if row >= n:
                return
    
            # => Undo
            old_data = copy.deepcopy(gpx_data)
            self.gpx_widget.gpx_list._history_stack.append(old_data)
    
            # lat/lon/ele for row-1 and row
            lat1, lon1, ele1 = (
                gpx_data[row-1].get("lat", 0.0),
                gpx_data[row-1].get("lon", 0.0),
                gpx_data[row-1].get("ele", 0.0)
            )
            lat2, lon2, ele2 = (
                gpx_data[row].get("lat", 0.0),
                gpx_data[row].get("lon", 0.0),
                gpx_data[row].get("ele", 0.0)
            )
    
            # Dist2D => we can reuse a small helper or do a direct haversine:
            dist_2d = self._haversine_m(lat1, lon1, lat2, lon2)
            if dist_2d < 0.01:
                QMessageBox.warning(self, "Zero Distance",
                    f"Points {row-1} and {row} have nearly no distance => slope undefined.")
                return
    
            old_slope = 100.0 * ((ele2 - ele1) / dist_2d)
    
            # Dialog => new slope
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Change Slope (Single Point) - Row {row}")
            vbox = QVBoxLayout(dlg)
    
            lbl_info = QLabel(
                f"Current slope between row {row-1} and row {row}: {old_slope:.2f}%\n"
                "Please enter the new slope (in %)."
            )
            vbox.addWidget(lbl_info)
    
            spin_slope = QDoubleSpinBox()
            spin_slope.setRange(-200.0, 200.0)  # e.g. -200%.. 200%
            spin_slope.setDecimals(2)
            spin_slope.setSingleStep(0.01)
            spin_slope.setValue(old_slope)
            vbox.addWidget(spin_slope)
    
            h_btn = QHBoxLayout()
            btn_ok = QPushButton("OK")
            btn_cancel = QPushButton("Cancel")
            h_btn.addWidget(btn_ok)
            h_btn.addWidget(btn_cancel)
            vbox.addLayout(h_btn)
    
            def on_ok():
                dlg.accept()
    
            def on_cancel():
                dlg.reject()
    
            btn_ok.clicked.connect(on_ok)
            btn_cancel.clicked.connect(on_cancel)
    
            if not dlg.exec():
                return
    
            new_slope = spin_slope.value()
            if abs(new_slope - old_slope) < 1e-9:
                QMessageBox.information(self, "No change", "Slope unchanged.")
                return
    
            # => new ele2 = ele1 + dist_2d*(new_slope/100)
            new_ele2 = ele1 + dist_2d * (new_slope / 100.0)
            gpx_data[row]["ele"] = new_ele2
    
            # recalc
            recalc_gpx_data(gpx_data)
            self.gpx_widget.set_gpx_data(gpx_data)
            self._gpx_data = gpx_data
            self._update_gpx_overview()
    
            self.chart.set_gpx_data(gpx_data)
            if self.mini_chart_widget:
                self.mini_chart_widget.set_gpx_data(gpx_data)
    
            # Map
            #route_geojson = self._build_route_geojson_from_gpx(gpx_data)
            #self.map_widget.loadRoute(route_geojson, do_fit=False)

            diff_val = new_slope - old_slope
            QMessageBox.information(
                self, "Done",
                f"Slope changed from {old_slope:.2f}% to {new_slope:.2f}%.\n"
                f"Elevation of row {row} updated accordingly."
            )
            return

        # ------------------------------------------------------------------
        # CASE B) Valid range => single linear slope for [b_idx..e_idx]
        # ------------------------------------------------------------------
        else:
            # => Undo
            old_data = copy.deepcopy(gpx_data)
            self.gpx_widget.gpx_list._history_stack.append(old_data)
    
            lat_b, lon_b, ele_b = (
                gpx_data[b_idx].get("lat", 0.0),
                gpx_data[b_idx].get("lon", 0.0),
                gpx_data[b_idx].get("ele", 0.0)
            )
            lat_e, lon_e, ele_e = (
                gpx_data[e_idx].get("lat", 0.0),
                gpx_data[e_idx].get("lon", 0.0),
                gpx_data[e_idx].get("ele", 0.0)
            )
    
            # (1) Compute the total 2D distance from b_idx.. e_idx
            #     Summation of each segment's distance in [b_idx.. e_idx-1].
            total_2d = 0.0
            for i in range(b_idx, e_idx):
                la1, lo1 = gpx_data[i]["lat"], gpx_data[i]["lon"]
                la2, lo2 = gpx_data[i+1]["lat"], gpx_data[i+1]["lon"]
                dist_2d = self._haversine_m(la1, lo1, la2, lo2)
                total_2d += dist_2d
    
            if total_2d < 0.01:
                QMessageBox.warning(self, "Zero Distance",
                    f"The range {b_idx}..{e_idx} has almost no distance => slope undefined.")
                return
    
            # (2) old average slope
            old_dz = ele_e - ele_b
            old_slope = 100.0 * (old_dz / total_2d)
    
            # (3) Dialog => new slope
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Change Average Slope - Range {b_idx}..{e_idx}")
            vbox = QVBoxLayout(dlg)
    
            lbl_info = QLabel(
                f"You have selected a range from {b_idx} to {e_idx}.\n"
                f"Current average slope in this range: {old_slope:.2f}%\n\n"
                "Please enter the new slope in % (e.g., 5.0 means 5%)."
            )
            vbox.addWidget(lbl_info)
    
            spin_slope = QDoubleSpinBox()
            spin_slope.setRange(-200.0, 200.0)  # e.g. -200..+200%
            spin_slope.setDecimals(2)
            spin_slope.setSingleStep(0.01)
            spin_slope.setValue(old_slope)
            vbox.addWidget(spin_slope)
    
            h_btn = QHBoxLayout()
            btn_ok = QPushButton("OK")
            btn_cancel = QPushButton("Cancel")
            h_btn.addWidget(btn_ok)
            h_btn.addWidget(btn_cancel)
            vbox.addLayout(h_btn)
    
            def on_ok_range():
                dlg.accept()
    
            def on_cancel_range():
                dlg.reject()
    
            btn_ok.clicked.connect(on_ok_range)
            btn_cancel.clicked.connect(on_cancel_range)
    
            if not dlg.exec():
                return
    
            new_slope = spin_slope.value()
            if abs(new_slope - old_slope) < 1e-9:
                QMessageBox.information(self, "No change", "Slope unchanged.")
                return
    
            # (4) new total height difference => new_dz
            new_dz = total_2d * (new_slope / 100.0)
            shift_dz = new_dz - old_dz   # how much we add from e_idx onward
    
            # (5) Recompute elevations linearly from b_idx.. e_idx
            #     Keep ele[b_idx] as it is, 
            #     then for each i in [b_idx+1.. e_idx], 
            #     compute the cumulative distance from b_idx to i.
            def cumulative_distance(b_i, i_i):
                dist_sum = 0.0
                for x in range(b_i, i_i):
                    la1, lo1 = gpx_data[x]["lat"], gpx_data[x]["lon"]
                    la2, lo2 = gpx_data[x+1]["lat"], gpx_data[x+1]["lon"]
                    dist_sum += self._haversine_m(la1, lo1, la2, lo2)
                return dist_sum
    
            for i in range(b_idx+1, e_idx+1):
                dist_i = cumulative_distance(b_idx, i)
                # slope-based new altitude
                new_ele_i = ele_b + (new_slope / 100.0) * dist_i
                gpx_data[i]["ele"] = new_ele_i
    
            # (6) Shift all points after e_idx by shift_dz
            if e_idx < n-1 and abs(shift_dz) > 1e-9:
                for j in range(e_idx+1, n):
                    gpx_data[j]["ele"] = gpx_data[j]["ele"] + shift_dz
    
            # (7) recalc + update
            recalc_gpx_data(gpx_data)
            self.gpx_widget.set_gpx_data(gpx_data)
            self._gpx_data = gpx_data
            self._update_gpx_overview()
    
            self.chart.set_gpx_data(gpx_data)
            if self.mini_chart_widget:
                self.mini_chart_widget.set_gpx_data(gpx_data)
    
            #route_geojson = self._build_route_geojson_from_gpx(gpx_data)
            #self.map_widget.loadRoute(route_geojson, do_fit=False)

            QMessageBox.information(
                self, "Done",
                f"Average slope in {b_idx}..{e_idx} changed from {old_slope:.2f}% to {new_slope:.2f}%.\n"
                f"Subsequent points have been shifted by {shift_dz:+.2f} m in elevation."
            )
    
    
            
   
  
            
    def _partial_recalc_gpx(self, i: int):
        """
        Neuberechnung nur für index i und i+1 
        (sowie i-1.. i, falls i>0)
        """
       
        gpx = self.gpx_widget.gpx_list._gpx_data
        n = len(gpx)
        if n < 2:
            return

        start_i = max(0, i-1)
        end_i   = min(n-1, i+1)

        # => Einfacher Weg: extrahiere Subarray, recalc, schreibe zurück
        sub = gpx[start_i:end_i+1]

        # recalc_gpx_data kann das gesamte Array => wir machen 
        # --> Variante A) sub
        # --> Variante B) In-Place code (selber berechnen).

        # Hier der "grosse" Weg: wir rufen recalc_gpx_data auf ALLE, 
        # ist simpler & kein Performanceproblem
       
        recalc_gpx_data(gpx)

        # Falls du nur sub recalc willst, ist das aufwändiger.
        
    def _on_new_project_triggered(self):
        """
        Führt einen "Soft-Reset" durch, ohne das Programm neu zu starten.
        Alle Daten (GPX, Videos, Markierungen) werden entfernt.
        """
        

        answer = QMessageBox.question(
            self,
            "New Project",
            "All data (GPX, video playlist, cuts, marks) will be removed.\n"
            "Do you really want to start a new project?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            # 1) Playback stoppen
            self.on_stop()  # oder self.video_editor.stop(), + selbst is_playing=False etc.
    
            # 2) Video-Cuts entfernen
            self.cut_manager._cut_intervals.clear()  # or use an API remove_all_cuts()
            self.cut_manager.markB_time_s = -1
            self.cut_manager.markE_time_s = -1

            # 3) Timeline zurücksetzen
            self.timeline.set_markB_time(-1)
            self.timeline.set_markE_time(-1)
            self.timeline._cut_intervals.clear()  # interne Liste
            self.timeline.set_marker_position(0.0)
            self.timeline.set_total_duration(0.0)

            # 4) GPX-Widget + GPX-Daten leeren
            self.gpx_widget.set_gpx_data([])
            self._gpx_data = []
            # Undo-Stack der gpx_list leeren
            self.gpx_widget.gpx_list._history_stack.clear()
            # Markierungen
            self.gpx_widget.gpx_list.clear_marked_range()

            # 5) Playlist und Video-Durations leeren
            self.playlist.clear()
            self.video_durations.clear()
            #self.video_editor.rebuild_vlc_playlist([])  # leere Liste => kein Video
            self.video_editor.set_playlist([])
            
            self.playlist_menu.clear()  # <-- Wichtig!
            self.video_editor.set_total_length(0.0)
            self.video_editor.set_cut_time(0.0)


            # 6) Falls du globale Keyframes (self.global_keyframes) hast:
            self.global_keyframes.clear()

            # 7) Ggf. GUI-Anzeigen zurücksetzen (z.B. chart, map)
            self.chart.set_gpx_data([])
            if self.mini_chart_widget:
                self.mini_chart_widget.set_gpx_data([])
            self.map_widget.loadRoute(None, do_fit=False)
            
            self.map_widget.loadRoute({"type":"FeatureCollection","features":[]}, do_fit=False)
    
            # 8) Info an den User
            QMessageBox.information(
                self,
                "Project Cleared",
                "All data was cleared. You can now load new GPX/videos."
            )

    def add_or_update_point_on_map(self, stable_id: str, lat: float, lon: float, 
                                color: str="#000000", size: int=4):
        """
        Ruft in map_page.html => addOrUpdatePoint(...) auf.
        """
        js_code = (f"addOrUpdatePoint('{stable_id}', {lat}, {lon}, "
                f"'{color}', {size});")
        self.map_widget.view.page().runJavaScript(js_code)

    def remove_point_on_map(self, stable_id: str):
        """
        Ruft in map_page.html => removePoint(...) auf.
        """
        

        js_code = f"removePoint('{stable_id}');"
        self.map_widget.view.page().runJavaScript(js_code)

    
    
     

    
            
    
    
        
    def _go_to_gpx_index(self, idx: int):
        """
        Highlights the GPX index 'idx' in the map, the gpx list, the chart, 
        and optionally the mini-chart or the video timeline.
        """
        # 1) Table (GPXList) -> Pause-Selection
        self.gpx_widget.gpx_list.select_row_in_pause(idx)
    
        # 2) Map -> show blue + center
        self.map_widget.show_blue(idx, do_center=True)

        # 3) Chart
        self.chart.highlight_gpx_index(idx)
    
        # 4) MiniChart
        if self.mini_chart_widget:
            self.mini_chart_widget.set_current_index(idx)

        # 5) (Optional) => Video 
        #    Falls du direkt zum passenden Zeitpunkt springen willst:
        # global_s = gpx_data[idx]["rel_s"]   # oder wie auch immer du es nennst
        # => self.on_time_hms_set_clicked(....) 
        # or do nothing if you prefer just highlighting
        
        
    def on_markB_clicked_gpx(self):
        
        """
        Wird aufgerufen, wenn im GPXControlWidget der Button 'MarkB' geklickt wird.
        => current_row ohne +1
        """
        current_row = self.gpx_widget.gpx_list.table.currentRow()
        if current_row < 0:
            print("[DEBUG] Keine Zeile ausgewählt in gpx_list!")
            return

        # Ohne +1
        self.gpx_widget.gpx_list.set_markB_row(current_row)
        self.map_widget.set_markB_point(current_row)           
    
   
    def on_deselect_clicked(self):
        
        """
        Wird aufgerufen, wenn der Deselect-Button gedrückt wird 
        (VideoControlWidget oder GPXControlWidget).
        => Wir entfernen alle roten Markierungen in der GPX-Liste.
        """
        self.gpx_widget.gpx_list.clear_marked_range()
        self.map_widget.clear_marked_range()        
        
    def check_gpx_errors(self, gpx_data):
        """
        Checks for:
        1) Time errors (points with time[i] == time[i-1])
        2) Way errors (points with lat/lon identical to next point)
        If any errors are found, shows an English warning message:
        - Only time errors
        - Only way errors
        - Both time & way errors
        Otherwise, no message.
        """
       

        if not gpx_data or len(gpx_data) < 2:
            return  # zu wenige Punkte -> auch keine Warnung

        # 1) Time Errors zählen
        time_err_count = 0
        for i in range(1, len(gpx_data)):
            if gpx_data[i]["time"] == gpx_data[i-1]["time"]:
                time_err_count += 1

        # 2) Way Errors zählen
        way_err_count = 0
        for i in range(len(gpx_data) - 1):
            lat1 = gpx_data[i]["lat"]
            lon1 = gpx_data[i]["lon"]
            lat2 = gpx_data[i+1]["lat"]
            lon2 = gpx_data[i+1]["lon"]
            # Vergleiche Koordinaten - fast identisch?
            if abs(lat1 - lat2) < 1e-12 and abs(lon1 - lon2) < 1e-12:
                way_err_count += 1
    
        # Nichts gefunden => keine Meldung
        if time_err_count == 0 and way_err_count == 0:
            return
    
        # Mindestens eines vorhanden => Warnmeldung bauen:
        if time_err_count > 0 and way_err_count > 0:
            msg = (
                f"Warning:\n"
                f"We found {time_err_count} time errors (0s step) and {way_err_count} way errors (duplicate coordinates).\n"
                "Please fix them via the more-menu \"...\" -> Time Errors / Way Errors!"
            )
        elif time_err_count > 0:
            msg = (
                f"Warning:\n"
                f"We found {time_err_count} time errors (0s step).\n"
                "Please fix them via the more-menu \"...\" -> Time Errors!"
            )
        else:  # way_err_count > 0
            msg = (
                f"Warning:\n"
                f"We found {way_err_count} way errors (duplicate coordinates).\n"
                "Please fix them via the more-menu \"...\" -> (Way Errors)!"
            )
    
        QMessageBox.warning(self, "GPX Errors Detected", msg)
        
    def _toggle_map(self):
        """Menü-Aktion: 'Map (detach)' oder 'Map (attach)'."""
        if self._map_floating_dialog is None:
            self._detach_map_widget()
            self.action_toggle_map.setText("Map (attach)")
        else:
            self._reattach_map_widget()
            self.action_toggle_map.setText("Map (detach)")


    def _detach_map_widget(self):
        if self._map_floating_dialog is not None:
            return
    
        # Index des map_widget im Layout finden
        idx = self.left_v_layout.indexOf(self.map_widget)
        if idx < 0:
            return
    
        # Platzhalter
        self._map_placeholder = QFrame()
        self._map_placeholder.setStyleSheet("background-color: #444;")
    
        # Platzhalter an die alte Stelle des map_widget
        self.left_v_layout.insertWidget(idx, self._map_placeholder, 1)
        self.left_v_layout.removeWidget(self.map_widget)
    
        # DetachDialog
        dlg = DetachDialog(self)
        dlg.setWindowTitle("Map (Detached)")
        dlg.setMinimumSize(800, 600)  # <-- WICHTIG: Mindestens 800×600
    
        layout = QVBoxLayout(dlg)
        layout.addWidget(self.map_widget)
    
        # Optional: + / - / reattach
        dlg.requestPlus.connect(self._on_map_plus)
        dlg.requestMinus.connect(self._on_map_minus)
        dlg.requestReattach.connect(self._on_request_reattach_map)
    
        self._map_floating_dialog = dlg
        dlg.show()
    
        # Zeitverzögertes Resize
        QTimer.singleShot(50, lambda: self._after_show_map_detached(dlg))
    
    
    def _after_show_map_detached(self, dlg: QDialog):
        screen = dlg.screen()
        if not screen:
           
            screen = QGuiApplication.primaryScreen()
    
        sg = screen.availableGeometry()
        w = int(sg.width() * 0.5)
        h = int(sg.height() * 0.5)
        dlg.resize(w, h)
    
        fg = dlg.frameGeometry()
        fg.moveCenter(sg.center())
        dlg.move(fg.topLeft())
    
    
    def _reattach_map_widget(self):
        if not self._map_floating_dialog:
            return
    
        self._map_floating_dialog.close()
        self._map_floating_dialog = None
    
        if self._map_placeholder:
            idx = self.left_v_layout.indexOf(self._map_placeholder)
            if idx >= 0:
                self.left_v_layout.removeWidget(self._map_placeholder)
            self._map_placeholder.deleteLater()
            self._map_placeholder = None
    
        # Map wieder unten einfügen (z.B. am Ende des Layouts)
        self.left_v_layout.addWidget(self.map_widget, 1)
    
    
    def _on_request_reattach_map(self):
        """Vom Dialog-Signal aufgerufen."""
        self._reattach_map_widget()
    
    
    # (Optional) Falls du + / – für Zoom willst:
    def _on_map_plus(self):
        # Angenommen, du hast in map_page.html JS-Funktionen "mapZoomIn()"
        js_code = "mapZoomIn();"
        self.map_widget.view.page().runJavaScript(js_code)
    
    def _on_map_minus(self):
        js_code = "mapZoomOut();"
        self.map_widget.view.page().runJavaScript(js_code)

    def ordered_insert_new_point(self,lat: float, lon: float, video_time: float) -> int:
        gpx_data = self._gpx_data
        t_first = gpx_data[0].get("time", 0) if gpx_data else datetime.now()  # Fallback, falls Zeit gar nicht existiert
        video_ts = t_first + timedelta(seconds=video_time)

        idx = 0
        for i in range(0, len(gpx_data)):
            if (gpx_data[i].get("time") > video_ts):
                break
            else:
                idx = i

        ele = 0
        if idx > 0:
            base_pt = gpx_data[idx]
            ele = base_pt.get("ele", 0.0)

        new_pt = {
            "lat": lat,
            "lon": lon,
            "ele": ele,
            "time": video_ts,
            "delta_m": 0.0,
            "speed_kmh": 0.0,
            "gradient": 0.0,
            "rel_s": 0.0
        }
        insert_pos = idx + 1
        if insert_pos > len(gpx_data):
            insert_pos = len(gpx_data)
        gpx_data.insert(insert_pos, new_pt)
        return insert_pos  # Index des neuen Punktes in gpx_data
    
    

