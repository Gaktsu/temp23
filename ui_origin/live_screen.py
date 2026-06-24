import cv2
import datetime
import os
import platform
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from ai_module.ai_detector import DangerDetector
import style # 분리한 디자인 스타일 적용

class LiveScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setStyleSheet(style.SCREEN_BG)
        
        self.expanded_pos_index = None
        self.cam_mapping = [0, 1, 2, 3]
        self.current_raw_frames = [None] * 4

        self.ai = DangerDetector(model_path='ai_module/best.pt', buzzer_pin=18)

        self.cam_labels = []
        positions = [(0, 0), (400, 0), (0, 240), (400, 240)]
        for i in range(4):
            lbl = QLabel(f"CAM {i+1}\nNO SIGNAL", self)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(style.CAM_LABEL_NO_SIGNAL)
            lbl.setGeometry(positions[i][0], positions[i][1], 400, 240)
            self.cam_labels.append(lbl)

        self.full_screen_label = QLabel(self)
        self.full_screen_label.setGeometry(0, 0, 800, 480)
        self.full_screen_label.setStyleSheet(style.SCREEN_BG)
        self.full_screen_label.setAlignment(Qt.AlignCenter)
        self.full_screen_label.hide()

        self.time_label = QLabel("Loading...", self)
        self.time_label.setGeometry(10, 10, 220, 30)
        self.time_label.setStyleSheet(style.STATUS_TIME_LABEL)
        self.time_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("REC | 서버 ON | AI ON", self)
        self.status_label.setGeometry(590, 10, 200, 30)
        self.status_label.setStyleSheet(style.STATUS_TIME_LABEL)
        self.status_label.setAlignment(Qt.AlignCenter)

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(style.BACK_BTN)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(1))

        self.set_btn = QPushButton("⚙", self)
        self.set_btn.setGeometry(730, 410, 60, 60)
        self.set_btn.setStyleSheet(style.BACK_BTN)
        self.set_btn.clicked.connect(lambda: self.main_window.switch_screen(6))

        self.full_screen_label.lower()
        self.back_btn.raise_()
        self.set_btn.raise_()
        self.time_label.raise_()
        self.status_label.raise_()

        self.caps = []
        self.writers = []
        
        if not os.path.exists("records"):
            os.makedirs("records")

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fourcc = cv2.VideoWriter_fourcc(*'XVID')

        for i in range(4):
            if platform.system() == "Windows":
                cap = cv2.VideoCapture(i)
            else:
                cap = cv2.VideoCapture(i, cv2.CAP_V4L2) 
                
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480) 
                self.caps.append(cap)
                
                filename = f"records/{now_str}_CAM{i+1}.avi"
                out = cv2.VideoWriter(filename, fourcc, 15.0, (640, 480))
                self.writers.append(out)
            else:
                self.caps.append(None)
                self.writers.append(None)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frames) 
        self.timer.start(50) 

    def update_frames(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(now)

        frames = [None] * 4

        for i, cap in enumerate(self.caps):
            if cap is not None and cap.isOpened():
                ret, frame = cap.read() 
                if ret:
                    # 💡 핵심 수정: 카메라가 제멋대로 보낸 고해상도 이미지를 
                    # AI 처리 및 선을 그리기 전에 무조건 640x480 표준 크기로 강제 조정합니다.
                    frame = cv2.resize(frame, (640, 480))
                    
                    self.current_raw_frames[i] = frame.copy()
                    
                    # 표준 크기로 맞춰진 사진을 AI에 넘겨서 선을 그립니다.
                    frame, _ = self.ai.process_frame(frame, i)
                    
                    if self.writers[i] is not None:
                        # 이미 640x480으로 맞춰졌으므로 별도 처리 없이 바로 녹화 파일에 저장합니다.
                        self.writers[i].write(frame)
                        
                    frames[i] = frame

        # 💡 전체 화면 모드일 경우의 처리 로직 (버그 완벽 수정)
        if self.expanded_pos_index is not None:
            pos = self.expanded_pos_index
            cam_idx = self.cam_mapping[pos] 
            frame = frames[cam_idx]
            
            if frame is not None:
                self.full_screen_label.setStyleSheet(style.SCREEN_BG)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_resized = cv2.resize(frame_rgb, (800, 480))
                h, w, c = frame_resized.shape
                q_img = QImage(frame_resized.data, w, h, 3 * w, QImage.Format_RGB888)
                self.full_screen_label.setPixmap(QPixmap.fromImage(q_img))
            else:
                # 카메라가 안 켜진 화면도 전체 화면으로 볼 수 있도록 처리
                self.full_screen_label.clear()
                self.full_screen_label.setText(f"CAM {cam_idx+1}\nNO SIGNAL")
                self.full_screen_label.setStyleSheet("background-color: #111; color: red; font-size: 40px; font-weight: bold;")
            
            self.full_screen_label.show() 
            # 💡 전체 화면과 상단/하단 버튼들이 뒤로 숨지 않도록 맨 앞으로 계속 끌어올림
            self.full_screen_label.raise_()
            self.back_btn.raise_()
            self.set_btn.raise_()
            self.time_label.raise_()
            self.status_label.raise_()
            
        # 💡 4분할 화면 모드일 경우의 처리 로직
        else:
            self.full_screen_label.hide() 
            for pos in range(4):
                cam_idx = self.cam_mapping[pos]
                frame = frames[cam_idx]
                
                if frame is not None:
                    self.cam_labels[pos].setStyleSheet("border: 1px solid #333;")
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_resized = cv2.resize(frame_rgb, (400, 240))
                    h, w, c = frame_resized.shape
                    q_img = QImage(frame_resized.data, w, h, 3 * w, QImage.Format_RGB888)
                    self.cam_labels[pos].setPixmap(QPixmap.fromImage(q_img))
                else:
                    self.cam_labels[pos].clear()
                    self.cam_labels[pos].setText(f"CAM {cam_idx+1}\nNO SIGNAL")
                    self.cam_labels[pos].setStyleSheet(style.CAM_LABEL_NO_SIGNAL)
    
    def mousePressEvent(self, event):
        x, y = event.x(), event.y()
        
        # 버튼이 있는 영역 클릭 시 화면 확대를 무시함
        if (x < 80 and y > 400) or (x > 720 and y > 400):
            return super().mousePressEvent(event)

        if self.expanded_pos_index is not None:
            self.expanded_pos_index = None
            self.full_screen_label.hide()
        else:
            if x < 400 and y < 240: pos = 0     
            elif x >= 400 and y < 240: pos = 1  
            elif x < 400 and y >= 240: pos = 2  
            else: pos = 3                       
            
            # 💡 기존 버그 원인 삭제: 카메라가 없어도 빈 화면이 확대될 수 있게 조건문 제거
            self.expanded_pos_index = pos
            
            # 확대 시 즉시 화면들을 맨 위로 갱신
            self.full_screen_label.raise_()
            self.back_btn.raise_()
            self.set_btn.raise_()
            self.time_label.raise_()
            self.status_label.raise_()

    def closeEvent(self, event):
        self.ai.cleanup()
        for cap in self.caps:
            if cap is not None: cap.release()
        for writer in self.writers:
            if writer is not None: writer.release()