import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QScroller, QMessageBox)
from PyQt5.QtCore import Qt
import style

class PlaybackSettingsScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        self.auto_delete_oldest = True
        self.auto_zip_backup = False
        self.playback_speed = "1.0 배속"
        self.sort_criterion = "최신순"

        self.title_label = QLabel("영상 재생 및 관리 설정", self)
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
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(2))

        self.add_toggle_row("저장 공간 부족 시 오래된 영상 자동 삭제", self.auto_delete_oldest, self.toggle_auto_delete)
        self.add_toggle_row("USB 백업 시 파일 자동 압축", self.auto_zip_backup, self.toggle_auto_zip)
        self.btn_speed = self.add_button_row("기본 재생 배속 설정", self.playback_speed, self.cycle_playback_speed)
        self.btn_sort = self.add_button_row("영상 정렬 기준 변경", self.sort_criterion, self.cycle_sort_criterion)
        self.add_button_row("전체 녹화 영상 삭제 (포맷)", "삭제하기", self.format_all_videos)

    def toggle_auto_delete(self, enabled):
        self.auto_delete_oldest = enabled

    def toggle_auto_zip(self, enabled):
        self.auto_zip_backup = enabled

    def cycle_playback_speed(self):
        speeds = ["1.0 배속", "1.5 배속", "2.0 배속", "0.5 배속"]
        current_idx = speeds.index(self.playback_speed)
        next_idx = (current_idx + 1) % len(speeds)
        self.playback_speed = speeds[next_idx]
        self.btn_speed.setText(self.playback_speed)

    def cycle_sort_criterion(self):
        criteria = ["최신순", "오래된순", "이름순"]
        current_idx = criteria.index(self.sort_criterion)
        next_idx = (current_idx + 1) % len(criteria)
        self.sort_criterion = criteria[next_idx]
        self.btn_sort.setText(self.sort_criterion)

    def format_all_videos(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("전체 삭제 경고")
        msg.setText("저장된 모든 녹화 영상이 영구적으로 삭제됩니다.\n정말 전부 삭제하시겠습니까?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setStyleSheet(style.MSG_BOX)
        
        if msg.exec_() == QMessageBox.Yes:
            record_dir = "records"
            delete_count = 0
            if os.path.exists(record_dir):
                for file_name in os.listdir(record_dir):
                    if file_name.endswith('.avi'):
                        file_path = os.path.join(record_dir, file_name)
                        try:
                            os.remove(file_path)
                            delete_count += 1
                        except Exception as e:
                            print(f"파일 삭제 실패: {e}")
                            
            succ_msg = QMessageBox(self)
            succ_msg.setWindowTitle("삭제 완료")
            succ_msg.setText(f"모든 녹화 영상이 삭제되었습니다.\n(삭제된 파일: {delete_count}개)")
            succ_msg.setStyleSheet(style.MSG_BOX)
            succ_msg.exec_()

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