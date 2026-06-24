import os
import platform
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import Qt
import style

class SettingsScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(style.SCREEN_BG)

        self.title_label = QLabel("시스템 설정", self)
        self.title_label.setGeometry(300, 10, 200, 30)
        self.title_label.setStyleSheet(style.TITLE_LABEL)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.settings_widget = QWidget(self)
        self.settings_widget.setGeometry(100, 80, 600, 300)
        self.settings_layout = QVBoxLayout(self.settings_widget)
        self.settings_layout.setSpacing(20)

        self.btn_format = QPushButton("저장소 포맷 (모든 영상 삭제)")
        self.btn_format.setStyleSheet(style.SYSTEM_SETTING_BTN)
        self.btn_format.clicked.connect(self.format_storage) 
        
        self.btn_reboot = QPushButton("시스템 재부팅")
        self.btn_reboot.setStyleSheet(style.SYSTEM_SETTING_BTN)
        self.btn_reboot.clicked.connect(self.reboot_system) 

        self.settings_layout.addWidget(self.btn_format)
        self.settings_layout.addWidget(self.btn_reboot)
        self.settings_layout.addStretch()

        self.back_btn = QPushButton("←", self)
        self.back_btn.setGeometry(10, 410, 60, 60)
        self.back_btn.setStyleSheet(style.BACK_BTN)
        self.back_btn.clicked.connect(lambda: self.main_window.switch_screen(1))

    def format_storage(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("경고")
        msg.setText("저장된 모든 녹화 영상이 영구적으로 삭제됩니다.\n정말 포맷하시겠습니까?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setStyleSheet(style.MSG_BOX)
        
        if msg.exec_() == QMessageBox.Yes:
            record_dir = "records"
            delete_count = 0
            if os.path.exists(record_dir):
                for file_name in os.listdir(record_dir):
                    if file_name.endswith('.avi'):
                        try:
                            os.remove(os.path.join(record_dir, file_name))
                            delete_count += 1
                        except Exception as e:
                            print(f"파일 삭제 실패: {e}")
            
            succ_msg = QMessageBox(self)
            succ_msg.setWindowTitle("포맷 완료")
            succ_msg.setText(f"포맷이 완료되었습니다.\n(삭제된 파일: {delete_count}개)")
            succ_msg.setStyleSheet(style.MSG_BOX)
            succ_msg.exec_()

    def reboot_system(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("재부팅 확인")
        msg.setText("시스템을 재부팅하시겠습니까?\n진행 중인 녹화는 안전하게 저장 후 종료됩니다.")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setStyleSheet(style.MSG_BOX)
        
        if msg.exec_() == QMessageBox.Yes:
            self.main_window.closeEvent(None) 
            if platform.system() == "Windows":
                os.system("shutdown /r /t 1") 
            else:
                os.system("sudo reboot")