from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QSizePolicy, QApplication
from PyQt5.QtCore import Qt
import style

class MenuScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)

        def create_menu_btn(text, btn_style_str):
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style_str)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            return btn

        btn_live = create_menu_btn("실시간 녹화", style.MENU_BTN)
        btn_live.clicked.connect(lambda: self.main_window.switch_screen(0))

        btn_playback = create_menu_btn("영상 재생", style.MENU_BTN)
        btn_playback.clicked.connect(lambda: self.main_window.switch_screen(2))

        btn_event = create_menu_btn("이벤트 로그", style.MENU_BTN)
        btn_event.clicked.connect(lambda: self.main_window.switch_screen(3))
        
        btn_info = create_menu_btn("시스템 정보", style.MENU_BTN)
        btn_info.clicked.connect(lambda: self.main_window.switch_screen(4))

        btn_settings = create_menu_btn("시스템 설정", style.MENU_BTN)
        btn_settings.clicked.connect(lambda: self.main_window.switch_screen(5))
        
        btn_exit = create_menu_btn("시스템 종료", style.EXIT_BTN)
        btn_exit.clicked.connect(QApplication.instance().quit)

        grid_layout.addWidget(btn_live, 0, 0)
        grid_layout.addWidget(btn_playback, 0, 1)
        grid_layout.addWidget(btn_event, 0, 2)
        grid_layout.addWidget(btn_info, 1, 0)
        grid_layout.addWidget(btn_settings, 1, 1)
        grid_layout.addWidget(btn_exit, 1, 2)

        layout.addLayout(grid_layout)