import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor
import style

class RoiSetupScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)
        
        self.base_frame = None
        self.display_frame = None
        self.current_cam_idx = 0
        self.pts_norm = []
        self.temp_pt_norm = None

        self.title_label = QLabel("위험구역 선 그리기 (ROI 설정)", self)
        self.title_label.setGeometry(0, 10, 800, 30)
        self.title_label.setStyleSheet(style.TITLE_LABEL)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.video_label = QLabel(self)
        self.video_label.setGeometry(80, 50, 640, 360) 
        self.video_label.setStyleSheet("background-color: #111; border: 2px solid #555;")
        self.video_label.setAlignment(Qt.AlignCenter)
        
        self.video_label.setMouseTracking(True)
        self.video_label.mousePressEvent = self.roi_mouse_press
        self.video_label.mouseMoveEvent = self.roi_mouse_move

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 415, 60, 50)
        self.back_btn.setStyleSheet(style.BACK_BTN.replace("font-size: 28px;", "font-size: 24px;"))
        self.back_btn.clicked.connect(self.cancel_setup)

        self.help_label = QLabel("4개의 점을 터치하여 사다리꼴 모양의 구역을 만들어주세요.", self)
        self.help_label.setGeometry(80, 420, 440, 40)
        self.help_label.setStyleSheet(style.ROI_HELP_LABEL_DEFAULT)
        self.help_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.reset_btn = QPushButton("초기화", self)
        self.reset_btn.setGeometry(525, 420, 110, 40)
        self.reset_btn.setStyleSheet(f"QPushButton {{ background-color: #555; {style.ROI_BTN_BASE} }} QPushButton:pressed {{ background-color: #777; }}")
        self.reset_btn.clicked.connect(self.reset_points)

        self.save_btn = QPushButton("저장 및 적용", self)
        self.save_btn.setGeometry(645, 420, 135, 40)
        self.save_btn.setStyleSheet(f"QPushButton {{ background-color: #28a745; {style.ROI_BTN_BASE} }} QPushButton:pressed {{ background-color: #34ce57; }}")
        self.save_btn.clicked.connect(self.save_roi)

    def set_base_frame(self, frame, cam_idx):
        self.base_frame = cv2.resize(frame, (640, 480)) 
        self.display_frame = self.base_frame.copy()
        self.current_cam_idx = cam_idx
        self.title_label.setText(f"CAM {cam_idx + 1} 위험구역 선 그리기 (ROI 설정)")
        
        current_pts = self.main_window.live_screen.ai.get_roi_points(cam_idx)
        self.pts_norm = []
        for pt in current_pts:
            self.pts_norm.append((pt[0] / 640.0, pt[1] / 480.0))
        self.update_display()

    def update_display(self):
        if self.base_frame is None:
            return
            
        img = self.base_frame.copy()
        h, w = img.shape[:2]
        
        q_img = QImage(img.data, w, h, w * 3, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap.fromImage(q_img)
        painter = QPainter(pixmap)
        
        pen_line = QPen(QColor(0, 255, 255), 3, Qt.SolidLine) 
        pen_line_temp = QPen(QColor(255, 255, 0), 2, Qt.DashLine) 
        pen_point = QPen(QColor(255, 255, 0), 8, Qt.SolidLine) 
        
        points_q = []
        for p in self.pts_norm:
            points_q.append(QPoint(int(p[0] * w), int(p[1] * h)))
            
        if len(points_q) > 0:
            painter.setPen(pen_point)
            for p in points_q:
                painter.drawPoint(p)
                
            painter.setPen(pen_line)
            if len(points_q) > 1:
                for i in range(len(points_q) - 1):
                    painter.drawLine(points_q[i], points_q[i+1])
            
            if self.temp_pt_norm is not None and len(points_q) < 4:
                temp_p = QPoint(int(self.temp_pt_norm[0] * w), int(self.temp_pt_norm[1] * h))
                painter.setPen(pen_line_temp)
                painter.drawLine(points_q[-1], temp_p)
                
            if len(points_q) == 4:
                painter.setPen(pen_line)
                painter.drawLine(points_q[3], points_q[0]) 
                painter.setBrush(QColor(0, 255, 255, 30)) 
                painter.drawPolygon(points_q)
                
        painter.end()
        self.video_label.setPixmap(pixmap.scaled(640, 360, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

    def roi_mouse_press(self, event):
        if self.base_frame is None or len(self.pts_norm) >= 4:
            return
            
        x = event.x()
        y = event.y()
        norm_x = max(0.0, min(1.0, x / 640.0))
        norm_y = max(0.0, min(1.0, y / 360.0))
        self.pts_norm.append((norm_x, norm_y))
        
        if len(self.pts_norm) == 4:
            self.temp_pt_norm = None
            self.help_label.setText("구역 완성! [저장 및 적용] 버튼을 눌러주세요.")
            self.help_label.setStyleSheet(style.ROI_HELP_LABEL_SUCCESS)
        else:
            self.help_label.setText(f"점 {len(self.pts_norm)}개 찍힘. 다음 점을 화면에 찍어주세요.")
            self.help_label.setStyleSheet(style.ROI_HELP_LABEL_DEFAULT)
            
        self.update_display()

    def roi_mouse_move(self, event):
        if self.base_frame is None or len(self.pts_norm) == 0 or len(self.pts_norm) >= 4:
            return
        self.temp_pt_norm = (event.x() / 640.0, event.y() / 360.0)
        self.update_display()

    def reset_points(self):
        self.pts_norm = []
        self.temp_pt_norm = None
        self.help_label.setText("4개의 점을 터치하여 사다리꼴 모양의 구역을 만들어주세요.")
        self.help_label.setStyleSheet(style.ROI_HELP_LABEL_DEFAULT)
        self.update_display()

    def cancel_setup(self):
        self.reset_points()
        self.main_window.switch_screen(6)

    def save_roi(self):
        if len(self.pts_norm) != 4:
            msg = QMessageBox(self)
            msg.setWindowTitle("알림")
            msg.setText("점을 4개 찍어서 도형을 완성해야 저장할 수 있습니다.")
            msg.setStyleSheet(style.MSG_BOX)
            msg.exec_()
            return

        final_pts = []
        for p in self.pts_norm:
            final_pts.append((int(p[0] * 640), int(p[1] * 480)))
            
        self.main_window.live_screen.ai.set_roi_points(self.current_cam_idx, final_pts)
        
        msg = QMessageBox(self)
        msg.setWindowTitle("저장 완료")
        msg.setText(f"CAM {self.current_cam_idx + 1} 위험 구역 설정이 저장되었습니다.")
        msg.setStyleSheet(style.MSG_BOX)
        
        if msg.exec_() == QMessageBox.Ok:
            self.cancel_setup()