import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget
import style

from live_screen import LiveScreen
from menu_screen import MenuScreen
from playback_screen import PlaybackScreen
from event_screen import EventScreen
from info_screen import InfoScreen
from settings_screen import SettingsScreen
from live_settings_screen import LiveSettingsScreen
from playback_settings_screen import PlaybackSettingsScreen
from roi_setup_screen import RoiSetupScreen

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 중앙 스타일 정의 파일에서 타이틀을 동적으로 연결
        self.setWindowTitle(style.WINDOW_TITLE)
        self.setGeometry(100, 100, 800, 480)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.live_screen = LiveScreen(self)
        self.menu_screen = MenuScreen(self)
        self.playback_screen = PlaybackScreen(self)
        self.event_screen = EventScreen(self)
        self.info_screen = InfoScreen(self)
        self.settings_screen = SettingsScreen(self)
        self.live_settings_screen = LiveSettingsScreen(self)
        self.playback_settings_screen = PlaybackSettingsScreen(self)
        self.roi_setup_screen = RoiSetupScreen(self)

        self.stacked_widget.addWidget(self.live_screen)
        self.stacked_widget.addWidget(self.menu_screen)
        self.stacked_widget.addWidget(self.playback_screen)
        self.stacked_widget.addWidget(self.event_screen)
        self.stacked_widget.addWidget(self.info_screen)
        self.stacked_widget.addWidget(self.settings_screen)
        self.stacked_widget.addWidget(self.live_settings_screen)
        self.stacked_widget.addWidget(self.playback_settings_screen)
        self.stacked_widget.addWidget(self.roi_setup_screen)

        self.switch_screen(0)

    def switch_screen(self, index):
        if index == 2:
            self.playback_screen.load_files()
        self.stacked_widget.setCurrentIndex(index)

    def closeEvent(self, event):
        for cap in self.live_screen.caps:
            if cap is not None and cap.isOpened(): 
                cap.release()
        for writer in self.live_screen.writers:
            if writer is not None: 
                writer.release()
        self.live_screen.ai.cleanup()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())