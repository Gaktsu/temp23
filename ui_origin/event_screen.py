from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea
from PyQt5.QtCore import Qt
import style

class EventScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(0, 50, 800, 350)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(style.SCROLL_AREA)

        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(10)
        self.scroll_area.setWidget(self.list_widget)

        self.title_label = QLabel("이벤트 로그", self)
        self.title_label.setGeometry(300, 10, 200, 30)
        self.title_label.setStyleSheet(style.TITLE_LABEL)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(style.BACK_BTN)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(1))

        self.load_events()

    def load_events(self):
        events = [
            "2026-04-03 15:30:22 - 충격 감지 (CAM 1)", 
            "2026-04-03 14:15:00 - 접근 경고 (CAM 3)", 
            "2026-04-03 08:00:15 - 시스템 시작"
        ]
        for evt in events:
            lbl = QLabel(evt)
            lbl.setStyleSheet(style.EVENT_ROW_LABEL)
            self.list_layout.addWidget(lbl)