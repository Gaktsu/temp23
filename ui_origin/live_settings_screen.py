import cv2
import numpy as np
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QScrollArea, QFrame, QScroller, QDialog, QMessageBox, QRadioButton, QButtonGroup, QSlider)
from PyQt5.QtCore import Qt
import style

class CamOrderPopup(QDialog):
    def __init__(self, current_mapping, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet(style.POPUP_DIALOG)
        self.setFixedSize(500, 380)
        
        self.cam_mapping = list(current_mapping)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)

        title_label = QLabel("카메라 채널 순서 변경", self)
        title_label.setStyleSheet(style.POPUP_TITLE)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(15)

        positions = ["채널 1 (좌측 상단)", "채널 2 (우측 상단)", "채널 3 (좌측 하단)", "채널 4 (우측 하단)"]
        for i in range(4):
            row_layout = QHBoxLayout()
            pos_label = QLabel(positions[i])
            pos_label.setStyleSheet(style.POPUP_TEXT_LABEL)
            
            cam_btn = QPushButton(f"카메라 {self.cam_mapping[i] + 1}")
            cam_btn.setFixedSize(110, 45)
            cam_btn.setStyleSheet(style.POPUP_CAM_BTN)
            cam_btn.clicked.connect(lambda checked, idx=i, btn=cam_btn: self.cycle_cam(idx, btn))

            row_layout.addWidget(pos_label)
            row_layout.addStretch()
            row_layout.addWidget(cam_btn)
            layout.addLayout(row_layout)

        layout.addStretch()
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)
        
        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(50)
        cancel_btn.setStyleSheet(style.POPUP_CANCEL_BTN)
        cancel_btn.clicked.connect(self.reject) 

        apply_btn = QPushButton("적용")
        apply_btn.setFixedHeight(50)
        apply_btn.setStyleSheet(style.POPUP_APPLY_BTN)
        apply_btn.clicked.connect(self.accept) 

        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(apply_btn)
        layout.addLayout(bottom_layout)

    def cycle_cam(self, idx, btn):
        self.cam_mapping[idx] = (self.cam_mapping[idx] + 1) % 4
        btn.setText(f"카메라 {self.cam_mapping[idx] + 1}")

class QualityFramePopup(QDialog):
    def __init__(self, current_quality, current_fps, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet(style.POPUP_DIALOG)
        self.setFixedSize(450, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("녹화 화질 및 프레임 설정", self)
        title.setStyleSheet(style.POPUP_TITLE)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(15)

        q_label = QLabel("녹화 화질 선택")
        q_label.setStyleSheet(style.POPUP_GREEN_LABEL)
        layout.addWidget(q_label)

        q_layout = QHBoxLayout()
        self.q_group = QButtonGroup(self)
        qualities = ["High (1080p)", "Medium (720p)", "Low (480p)"]
        for i, q_text in enumerate(qualities):
            rb = QRadioButton(q_text)
            rb.setStyleSheet(style.POPUP_RADIO_BTN)
            q_layout.addWidget(rb)
            self.q_group.addButton(rb, i)
            if q_text.startswith(current_quality):
                rb.setChecked(True)
        layout.addLayout(q_layout)
        layout.addSpacing(20)

        f_label = QLabel("녹화 프레임(FPS) 선택")
        f_label.setStyleSheet(style.POPUP_GREEN_LABEL)
        layout.addWidget(f_label)

        f_layout = QHBoxLayout()
        self.f_group = QButtonGroup(self)
        fps_options = ["30 fps", "15 fps", "10 fps"]
        for i, f_text in enumerate(fps_options):
            rb = QRadioButton(f_text)
            rb.setStyleSheet(style.POPUP_RADIO_BTN)
            f_layout.addWidget(rb)
            self.f_group.addButton(rb, i)
            if f_text == current_fps:
                rb.setChecked(True)
        layout.addLayout(f_layout)
        layout.addStretch()

        bottom_layout = QHBoxLayout()
        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(45)
        cancel_btn.setStyleSheet(style.POPUP_CANCEL_SMALL_BTN)
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("적용")
        apply_btn.setFixedHeight(45)
        apply_btn.setStyleSheet(style.POPUP_APPLY_SMALL_BTN)
        apply_btn.clicked.connect(self.accept)

        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(apply_btn)
        layout.addLayout(bottom_layout)

    def get_selected_values(self):
        q_dict = {0: "High", 1: "Medium", 2: "Low"}
        f_dict = {0: "30 fps", 1: "15 fps", 2: "10 fps"}
        return q_dict[self.q_group.checkedId()], f_dict[self.f_group.checkedId()]

class BrightnessContrastPopup(QDialog):
    def __init__(self, current_b, current_c, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet(style.POPUP_DIALOG)
        self.setFixedSize(450, 350)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("카메라 영상 조절", self)
        title.setStyleSheet(style.POPUP_TITLE)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(20)

        b_label = QLabel("카메라 밝기 조절")
        b_label.setStyleSheet(style.POPUP_GREEN_LABEL)
        layout.addWidget(b_label)

        b_row = QHBoxLayout()
        self.b_slider = QSlider(Qt.Horizontal)
        self.b_slider.setRange(0, 100)
        self.b_slider.setValue(current_b)
        self.b_slider.setStyleSheet(style.POPUP_SLIDER)
        self.b_val_label = QLabel(str(current_b))
        self.b_val_label.setStyleSheet(style.POPUP_VAL_LABEL)
        self.b_slider.valueChanged.connect(lambda val: self.b_val_label.setText(str(val)))
        b_row.addWidget(self.b_slider)
        b_row.addWidget(self.b_val_label)
        layout.addLayout(b_row)
        layout.addSpacing(15)

        c_label = QLabel("카메라 명암 조절")
        c_label.setStyleSheet(style.POPUP_GREEN_LABEL)
        layout.addWidget(c_label)

        c_row = QHBoxLayout()
        self.c_slider = QSlider(Qt.Horizontal)
        self.c_slider.setRange(0, 100)
        self.c_slider.setValue(current_c)
        self.c_slider.setStyleSheet(style.POPUP_SLIDER)
        self.c_val_label = QLabel(str(current_c))
        self.c_val_label.setStyleSheet(style.POPUP_VAL_LABEL)
        self.c_slider.valueChanged.connect(lambda val: self.c_val_label.setText(str(val)))
        c_row.addWidget(self.c_slider)
        c_row.addWidget(self.c_val_label)
        layout.addLayout(c_row)
        layout.addStretch()

        bottom_layout = QHBoxLayout()
        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(45)
        cancel_btn.setStyleSheet(style.POPUP_CANCEL_SMALL_BTN)
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("적용")
        apply_btn.setFixedHeight(45)
        apply_btn.setStyleSheet(style.POPUP_APPLY_SMALL_BTN)
        apply_btn.clicked.connect(self.accept)

        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(apply_btn)
        layout.addLayout(bottom_layout)

    def get_values(self):
        return self.b_slider.value(), self.c_slider.value()

class LiveSettingsScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        self.current_quality = "Medium"
        self.current_fps = "15 fps"
        self.current_split_minutes = 5
        self.current_brightness = 50
        self.current_contrast = 50

        self.title_label = QLabel("실시간 녹화 설정", self)
        self.title_label.setGeometry(300, 10, 200, 30)
        self.title_label.setStyleSheet(style.TITLE_LABEL)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(0, 50, 800, 350)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(style.SCROLL_AREA)

        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.LeftMouseButtonGesture)

        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(10)
        self.scroll_area.setWidget(self.list_widget)

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(style.BACK_BTN)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(0))

        initial_detection_state = self.main_window.live_screen.ai.detection_enabled
        self.add_toggle_row("AI 위험구역 감지 기능", initial_detection_state, self.toggle_detection)
        
        self.add_button_row("CAM 1 위험구역 설정", "설정하기", lambda: self.open_roi_setup(0))
        self.add_button_row("CAM 2 위험구역 설정", "설정하기", lambda: self.open_roi_setup(1))
        self.add_button_row("CAM 3 위험구역 설정", "설정하기", lambda: self.open_roi_setup(2))
        self.add_button_row("CAM 4 위험구역 설정", "설정하기", lambda: self.open_roi_setup(3))
        
        self.add_toggle_row("위험 경고음 (부저) 소리", True)
        self.add_toggle_row("서버 클라우드 자동 백업", False)
        
        self.add_button_row("카메라 채널(1~4번) 순서 변경", "설정하기", self.show_cam_popup)
        self.add_button_row("녹화 화질 및 프레임 설정", "설정하기", self.open_quality_popup)
        self.btn_split = self.add_button_row("녹화 파일 자동 분할 시간", f"{self.current_split_minutes}분 (변경)", self.cycle_split_time)
        self.add_button_row("카메라 밝기 / 명암 조절", "설정하기", self.open_brightness_popup)
        self.add_button_row("시스템 초기화", "초기화", self.reset_system_settings)

    def toggle_detection(self, enabled):
        self.main_window.live_screen.ai.set_detection_enabled(enabled)

    def show_cam_popup(self):
        current_mapping = self.main_window.live_screen.cam_mapping
        popup = CamOrderPopup(current_mapping, self)
        if popup.exec_() == QDialog.Accepted:
            self.main_window.live_screen.cam_mapping = list(popup.cam_mapping)

    def open_roi_setup(self, cam_idx):
        raw_frame = self.main_window.live_screen.current_raw_frames[cam_idx]
        if raw_frame is None:
            raw_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(raw_frame, f"CAM {cam_idx + 1}", (250, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
            cv2.putText(raw_frame, "NO SIGNAL (TEST MODE)", (120, 260), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        self.main_window.roi_setup_screen.set_base_frame(raw_frame.copy(), cam_idx)
        self.main_window.switch_screen(8)

    def open_quality_popup(self):
        popup = QualityFramePopup(self.current_quality, self.current_fps, self)
        if popup.exec_() == QDialog.Accepted:
            self.current_quality, self.current_fps = popup.get_selected_values()
            msg = QMessageBox(self)
            msg.setWindowTitle("설정 적용")
            msg.setText(f"녹화 설정이 변경되었습니다.\n화질: {self.current_quality}\n프레임: {self.current_fps}")
            msg.setStyleSheet(style.MSG_BOX)
            msg.exec_()

    def cycle_split_time(self):
        time_options = [1, 3, 5, 10]
        current_idx = time_options.index(self.current_split_minutes)
        next_idx = (current_idx + 1) % len(time_options)
        self.current_split_minutes = time_options[next_idx]
        self.btn_split.setText(f"{self.current_split_minutes}분 (변경)")

    def open_brightness_popup(self):
        popup = BrightnessContrastPopup(self.current_brightness, self.current_contrast, self)
        if popup.exec_() == QDialog.Accepted:
            self.current_brightness, self.current_contrast = popup.get_values()

    def reset_system_settings(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("초기화 확인")
        msg.setText("위험구역(ROI) 좌표 및 모든 녹화 설정을\n처음 상태로 초기화하시겠습니까?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setStyleSheet(style.MSG_BOX)
        
        if msg.exec_() == QMessageBox.Yes:
            self.current_quality = "Medium"
            self.current_fps = "15 fps"
            self.current_split_minutes = 5
            self.current_brightness = 50
            self.current_contrast = 50
            self.btn_split.setText(f"{self.current_split_minutes}분 (변경)")
            
            default_roi = [[220, 340], [420, 340], [420, 140], [220, 140]]
            for i in range(4):
                self.main_window.live_screen.ai.set_roi_points(i, default_roi)
                
            complete = QMessageBox(self)
            complete.setWindowTitle("초기화 완료")
            complete.setText("시스템 설정 초기화가 완료되었습니다.")
            complete.setStyleSheet(style.MSG_BOX)
            complete.exec_()

    def add_toggle_row(self, title_text, initial_state, callback=None):
        row_frame = QFrame()
        row_frame.setStyleSheet(style.ROW_FRAME)
        row_frame.setFixedHeight(70)
        layout = QHBoxLayout(row_frame)
        layout.setContentsMargins(20, 10, 20, 10)

        title = QLabel(title_text)
        title.setStyleSheet(style.ROW_TITLE)

        toggle_btn = QPushButton("ON" if initial_state else "OFF")
        toggle_btn.setFixedSize(100, 40)
        self.update_toggle_style(toggle_btn, initial_state)
        
        def on_clicked():
            is_on = toggle_btn.text() == "ON"
            new_state = not is_on
            toggle_btn.setText("ON" if new_state else "OFF")
            self.update_toggle_style(toggle_btn, new_state)
            if callback:
                callback(new_state)

        toggle_btn.clicked.connect(on_clicked)
        layout.addWidget(title, 1)
        layout.addWidget(toggle_btn)
        self.list_layout.addWidget(row_frame)

    def add_button_row(self, title_text, btn_text, callback=None):
        row_frame = QFrame()
        row_frame.setStyleSheet(style.ROW_FRAME)
        row_frame.setFixedHeight(70)
        layout = QHBoxLayout(row_frame)
        layout.setContentsMargins(20, 10, 20, 10)

        title = QLabel(title_text)
        title.setStyleSheet(style.ROW_TITLE)

        action_btn = QPushButton(btn_text)
        action_btn.setFixedSize(120, 40)
        action_btn.setStyleSheet(style.ROW_ACTION_BTN)
        
        if callback:
            action_btn.clicked.connect(callback)

        layout.addWidget(title, 1)
        layout.addWidget(action_btn)
        self.list_layout.addWidget(row_frame)
        return action_btn

    def update_toggle_style(self, btn, is_on):
        btn.setStyleSheet(style.TOGGLE_ON if is_on else style.TOGGLE_OFF)