import os
import cv2
import threading
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QDialog, QSlider, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from config.settings import SAVE_CLEANUP_THRESHOLD_PERCENT
from system.storage import (
    cleanup_old_files,
    is_video_important,
    toggle_video_important,
)


class VideoDecodeWorker(QThread):
    frame_ready = pyqtSignal(object, int)
    playback_finished = pyqtSignal()
    playback_error = pyqtSignal(str)

    def __init__(self, filepath, target_size=(640, 480), parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.target_size = target_size
        self._lock = threading.Lock()
        self._running = True
        self._playing = True
        self._seek_position = None

    def set_playing(self, playing):
        with self._lock:
            self._playing = playing

    def seek(self, position):
        with self._lock:
            self._seek_position = int(position)

    def stop(self):
        with self._lock:
            self._running = False

    def run(self):
        cap = cv2.VideoCapture(self.filepath)
        if not cap.isOpened():
            self.playback_error.emit("영상을 열 수 없습니다.")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 15.0
        interval_sec = 1.0 / fps

        while True:
            with self._lock:
                running = self._running
                playing = self._playing
                seek_position = self._seek_position
                self._seek_position = None

            if not running:
                break

            if seek_position is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, seek_position)
                ret, frame = cap.read()
                if not ret:
                    self.playback_finished.emit()
                    with self._lock:
                        self._playing = False
                    continue
                self._emit_frame(cap, frame)
                continue

            if not playing:
                self.msleep(20)
                continue

            started_at = time.time()
            ret, frame = cap.read()
            if not ret:
                with self._lock:
                    self._playing = False
                self.playback_finished.emit()
                break

            self._emit_frame(cap, frame)

            elapsed = time.time() - started_at
            sleep_ms = int(max(0.0, interval_sec - elapsed) * 1000)
            if sleep_ms > 0:
                self.msleep(sleep_ms)

        cap.release()

    def _emit_frame(self, cap, frame):
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, self.target_size)
        h, w, _ = frame_resized.shape
        q_img = QImage(frame_resized.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        self.frame_ready.emit(q_img, current_frame)

# [1] 비디오 플레이어 팝업창 클래스
class VideoPlayerPopup(QDialog):
    def __init__(self, filepath, filename, parent=None):
        super().__init__(parent)
        # 기본 윈도우 창 테두리를 없애고 팝업 형태로 설정
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet("background-color: #1a1a1a; border: 2px solid #555; border-radius: 10px;")
        self.setFixedSize(680, 580) # 팝업창의 전체 크기

        self.filepath = filepath
        self.is_playing = True # 처음 창이 열릴 때 바로 재생되도록 설정

        # 전체 세로 정렬 레이아웃
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 상단: 재생 중인 파일명을 보여주는 텍스트
        title = QLabel(f"재생 중: {filename}", self)
        title.setStyleSheet("color: #00FFCC; font-size: 18px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 중앙: 실제 영상이 출력될 라벨
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(640, 480)
        self.video_label.setStyleSheet("background-color: black; border: 1px solid #333;")
        self.video_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.video_label, alignment=Qt.AlignCenter)

        # 하단: 조작 버튼들을 가로로 배치하기 위한 레이아웃
        controls_layout = QHBoxLayout()
        
        # 재생/일시정지 버튼
        self.play_btn = QPushButton("일시정지")
        self.play_btn.setFixedSize(100, 40)
        self.play_btn.setStyleSheet("""
            QPushButton { background-color: #0055aa; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; border: none; }
            QPushButton:pressed { background-color: #0077ff; }
        """)
        self.play_btn.clicked.connect(self.toggle_play)

        # 영상 탐색을 위한 슬라이더
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: #333; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #00FFCC; border: 1px solid #5c5c5c; width: 18px; margin: -5px 0; border-radius: 9px; }
        """)
        self.slider.sliderMoved.connect(self.set_position) # 드래그 시 영상 위치 이동

        # 창 닫기 버튼
        self.close_btn = QPushButton("닫기")
        self.close_btn.setFixedSize(80, 40)
        self.close_btn.setStyleSheet("""
            QPushButton { background-color: #aa0000; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; border: none; }
            QPushButton:pressed { background-color: #ff4444; }
        """)
        self.close_btn.clicked.connect(self.close_player)

        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.slider)
        controls_layout.addWidget(self.close_btn)
        layout.addLayout(controls_layout)

        # 메타데이터만 먼저 확인하고 실제 디코딩은 백그라운드 스레드에서 수행
        meta_cap = cv2.VideoCapture(self.filepath)
        self.total_frames = int(meta_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = meta_cap.get(cv2.CAP_PROP_FPS)
        meta_cap.release()
        if self.fps <= 0: 
            self.fps = 15.0 # FPS를 읽어오지 못할 경우 기본값 15로 설정
        self.current_frame = 0

        # 슬라이더의 범위를 0부터 영상의 끝(총 프레임 수)까지로 설정
        self.slider.setRange(0, self.total_frames)

        # 프레임 디코딩은 별도 스레드에서 처리해 UI 정체를 줄임
        self.worker = VideoDecodeWorker(self.filepath, target_size=(640, 480), parent=self)
        self.worker.frame_ready.connect(self.on_frame_ready)
        self.worker.playback_finished.connect(self.on_playback_finished)
        self.worker.playback_error.connect(self.on_playback_error)
        self.worker.start()

    def on_frame_ready(self, q_img, current_frame):
        self.current_frame = current_frame
        self.video_label.setPixmap(QPixmap.fromImage(q_img))
        self.slider.blockSignals(True)
        self.slider.setValue(current_frame)
        self.slider.blockSignals(False)

    def on_playback_finished(self):
        self.is_playing = False
        self.play_btn.setText("재생")

    def on_playback_error(self, message):
        msg = QMessageBox(self)
        msg.setWindowTitle("알림")
        msg.setText(message)
        msg.setStyleSheet("QMessageBox { background-color: #222; } QLabel { color: white; font-size: 16px; font-weight: bold; } QPushButton { background-color: #0055aa; color: white; padding: 8px 20px; font-weight: bold; border-radius: 4px; font-size: 14px; }")
        msg.exec_()

    # 재생 및 일시정지 버튼을 눌렀을 때 실행되는 함수
    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self.worker.set_playing(False)
            self.play_btn.setText("재생")
        else:
            # 영상 끝에서 다시 재생을 누르면 맨 처음으로 되돌아가서 재생
            if self.current_frame >= self.total_frames - 1:
                self.worker.seek(0)
            self.is_playing = True
            self.worker.set_playing(True)
            self.play_btn.setText("일시정지")

    # 슬라이더를 마우스로 잡고 끌었을 때 해당 위치로 영상을 탐색하는 함수
    def set_position(self, position):
        """ 합니다. """
        self.worker.seek(position)
    # 닫기 버튼을 누르면 재생을 멈추고 파일을 메모리에서 해제한 뒤 창을 닫는 함수
    def close_player(self):
        self.worker.stop()
        self.worker.wait(1000)
        self.reject()



# [2] 영상 재생 목록 창 클래스
class PlaybackScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: black;")

        # 영상 목록이 많아질 것을 대비해 스크롤이 가능한 영역
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(0, 50, 800, 350) 
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(10) 
        self.scroll_area.setWidget(self.list_widget)

        overlay_style = "background-color: rgba(0, 0, 0, 150); color: white; font-weight: bold; border-radius: 5px; padding: 5px;"

        # 좌측 상단: 저장된 영상들의 총 용량을 보여주는 텍스트
        self.capacity_label = QLabel("총 용량: 계산중...", self)
        self.capacity_label.setGeometry(10, 10, 200, 30)
        self.capacity_label.setStyleSheet(overlay_style + "font-size: 14px;")
        self.capacity_label.setAlignment(Qt.AlignCenter)

        # 중앙 상단 타이틀
        self.title_label = QLabel("녹화 영상 목록", self)
        self.title_label.setGeometry(300, 10, 200, 30)
        self.title_label.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        self.title_label.setAlignment(Qt.AlignCenter)

        btn_style = """
            QPushButton { background-color: rgba(0, 0, 0, 150); color: white; font-size: 28px; font-weight: bold; border-radius: 10px; border: 2px solid #555; }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 100); }
        """

        # 좌측 하단 뒤로가기 버튼
        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(btn_style)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(1))

        # 우측 하단 영상 재생 전용 설정 버튼
        self.set_btn = QPushButton("⚙", self)
        self.set_btn.setGeometry(730, 410, 60, 60)
        self.set_btn.setStyleSheet(btn_style)
        self.set_btn.clicked.connect(lambda: self.main_window.switch_screen(7))

    # 화면이 열릴 때마다 SaveVideos 폴더를 읽어서 파일 목록 UI를 최신화하는 함수
    def load_files(self):
        # 목록을 새로 구성하기 위해 기존에 화면에 표시되던 항목들을 모두 지움
        for i in reversed(range(self.list_layout.count())): 
            widget = self.list_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

        record_dir = "SaveVideos"
        total_size_bytes = 0

        # 저장 폴더가 없으면 먼저 만든 뒤 정리/표시를 진행
        if not os.path.exists(record_dir):
            os.makedirs(record_dir)

        # 설정 용량을 넘겼으면 오래된 일반 영상부터 자동 정리
        cleanup_old_files(record_dir, SAVE_CLEANUP_THRESHOLD_PERCENT)

        # 폴더가 없으면 새로 만듬
        if not os.path.exists(record_dir):
            os.makedirs(record_dir)

        # 폴더 내의 .mp4 파일들을 가져와서 최신순(내림차순)으로 정렬
        files = sorted([f for f in os.listdir(record_dir) if os.path.isfile(os.path.join(record_dir, f)) and f.lower().endswith('.mp4')], reverse=True)

        # 파일이 하나도 없을 경우 안내 메시지 출력
        if not files:
            empty_lbl = QLabel("저장된 녹화 영상이 없습니다.")
            empty_lbl.setStyleSheet("color: gray; font-size: 18px;")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.list_layout.addWidget(empty_lbl)
            self.capacity_label.setText("총 용량: 0 MB")
            return

        # 파일을 하나씩 꺼내어 화면 목록에 추가하고, 파일 용량을 누적
        for file in files:
            filepath = os.path.join(record_dir, file)
            total_size_bytes += os.path.getsize(filepath) 
            
            row = self.create_file_row(file, filepath)
            self.list_layout.addWidget(row)

        # 계산된 총 용량을 MB 또는 GB 단위로 변환해서 화면 상단에 표시
        total_mb = total_size_bytes / (1024 * 1024)
        if total_mb >= 1024:
            total_gb = total_mb / 1024
            self.capacity_label.setText(f"총 용량: {total_gb:.2f} GB")
        else:
            self.capacity_label.setText(f"총 용량: {total_mb:.1f} MB")

    # 동영상 파일 1개당 [파일명 + 백업버튼 + 재생버튼] 으로 구성된 가로 한 줄을 만드는 함수
    def create_file_row(self, filename, filepath):
        row_frame = QFrame()
        row_frame.setStyleSheet("background-color: #222; border-radius: 8px; border: 1px solid #444;")
        row_frame.setFixedHeight(70)

        row_layout = QHBoxLayout(row_frame)
        row_layout.setContentsMargins(15, 10, 15, 10)

        # 파일명을 분석해서 보기 편하게 날짜, 시간 단위로 분리
        try:
            base_name = os.path.splitext(filename)[0]
            date_part, cam_part = base_name.split(" No.", 1)
            date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
            time_str = f"{date_part[9:11]}:{date_part[11:13]}:{date_part[13:15]}"
            display_name = f"일자: {date_str}  |  시간: {time_str}  |  CAM {cam_part}"
        except:
            display_name = filename # 형식이 다를 경우 원본 이름 그대로 표시

        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet("color: white; font-size: 18px; font-weight: bold; border: none; background: transparent;")

        is_important = is_video_important(filename, "SaveVideos")
        star_btn = QPushButton("★" if is_important else "☆")
        star_btn.setFixedSize(36, 36)
        star_btn.setStyleSheet(self._star_button_style(is_important))
        star_btn.clicked.connect(lambda chk, btn=star_btn, fn=filename: self.toggle_star(btn, fn))

        # 재생 버튼 설정
        play_btn = QPushButton("재생")
        play_btn.setStyleSheet("""
            QPushButton { background-color: #0055aa; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; padding: 10px 20px; border: none; }
            QPushButton:pressed { background-color: #0077ff; }
        """)
        play_btn.clicked.connect(lambda chk, fp=filepath, fn=filename: self.open_player_popup(fp, fn))

        row_layout.addWidget(star_btn)
        row_layout.addWidget(name_lbl, 1)
        row_layout.addWidget(play_btn)

        return row_frame

    def _star_button_style(self, is_important: bool) -> str:
        if is_important:
            return """
                QPushButton { background-color: transparent; color: #ffd54a; font-size: 24px; font-weight: bold; border: none; }
                QPushButton:pressed { color: #fff2a8; }
            """
        return """
            QPushButton { background-color: transparent; color: #999; font-size: 24px; font-weight: bold; border: none; }
            QPushButton:pressed { color: white; }
        """

    def toggle_star(self, button, filename):
        is_important = toggle_video_important(filename, "SaveVideos")
        button.setText("★" if is_important else "☆")
        button.setStyleSheet(self._star_button_style(is_important))
        cleanup_old_files("SaveVideos", SAVE_CLEANUP_THRESHOLD_PERCENT)

    # 영상 재생 팝업창을 화면 중앙에 띄움
    def open_player_popup(self, filepath, filename):
        popup = VideoPlayerPopup(filepath, filename, self)
        popup.exec_()
