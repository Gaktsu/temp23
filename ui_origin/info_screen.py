from PyQt5.QtWidgets import QWidget, QLabel, QPushButton
from PyQt5.QtCore import Qt
import style

class InfoScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        self.title_label = QLabel("시스템 정보", self)
        self.title_label.setGeometry(300, 10, 200, 30)
        self.title_label.setStyleSheet(style.TITLE_LABEL)
        self.title_label.setAlignment(Qt.AlignCenter)

        info_text = """
        장비 모델: Jetson Nano
        소프트웨어 버전: v1.0.0
        운영체제: Ubuntu 18.04
        네트워크 상태: 연결됨
        카메라: 4채널 연동 완료
        """
        
        self.info_label = QLabel(info_text, self)
        self.info_label.setGeometry(50, 80, 700, 300)
        self.info_label.setStyleSheet(style.INFO_LABEL)
        self.info_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(style.BACK_BTN)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(1))