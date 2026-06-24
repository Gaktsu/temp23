# style.py

# 프로그램 전역 윈도우 타이틀
WINDOW_TITLE = "AI 스마트 지게차 안전 관제 시스템"

# [1] 공통 배경 및 기본 컴포넌트 스타일
SCREEN_BG = "background-color: black;"
TITLE_LABEL = "color: white; font-size: 20px; font-weight: bold; background: transparent;"
SCROLL_AREA = "QScrollArea { border: none; background-color: transparent; }"

# [2] 메인 메뉴 화면 전용 버튼 스타일
MENU_BTN = """
    QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #333); color: white; font-size: 24px; font-weight: bold; border-radius: 12px; border: 2px solid #555; }
    QPushButton:pressed { background-color: #00FFCC; color: black; border: 2px solid #fff; }
"""
EXIT_BTN = """
    QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #aa0000, stop:1 #660000); color: white; font-size: 24px; font-weight: bold; border-radius: 12px; border: 2px solid #ff4444; }
    QPushButton:pressed { background-color: #ff4444; color: white; }
"""

# [3] 뒤로가기 및 내비게이션 아이콘 버튼 스타일
BACK_BTN = """
    QPushButton { background-color: rgba(0, 0, 0, 150); color: white; font-size: 28px; font-weight: bold; border-radius: 10px; border: 2px solid #555; }
    QPushButton:pressed { background-color: rgba(255, 255, 255, 100); }
"""

# [4] 실시간 모니터링 화면용 스타일
CAM_LABEL_NO_SIGNAL = "background-color: #111; color: red; font-size: 20px; font-weight: bold; border: 1px solid #333;"
OVERLAY_BASE = "background-color: rgba(0, 0, 0, 150); color: white; font-weight: bold; border-radius: 5px; padding: 5px;"
STATUS_TIME_LABEL = OVERLAY_BASE + "font-size: 14px;"

# [5] 설정 리스트의 아이템 로우(Row) 스타일
ROW_FRAME = "background-color: #222; border-radius: 8px; border: 1px solid #444;"
ROW_TITLE = "color: white; font-size: 18px; font-weight: bold; border: none; background: transparent;"
ROW_ACTION_BTN = """
    QPushButton { background-color: #555; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; border: none; }
    QPushButton:pressed { background-color: #777; }
"""
ROW_PLAY_BACKUP_BTN = """
    QPushButton { background-color: #555; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; padding: 10px 20px; border: none; }
    QPushButton:pressed { background-color: #00FFCC; color: black; }
"""

# [6] 토글 스위치 스타일 (ON / OFF)
TOGGLE_ON = "QPushButton { background-color: #0055aa; color: white; font-size: 18px; font-weight: bold; border-radius: 20px; border: 2px solid #0077ff; }"
TOGGLE_OFF = "QPushButton { background-color: #444; color: gray; font-size: 18px; font-weight: bold; border-radius: 20px; border: 2px solid #555; }"

# [7] 시스템 전체 설정 버튼 전용 스타일 (포맷, 재부팅용)
SYSTEM_SETTING_BTN = """
    QPushButton { background-color: #333; color: white; font-size: 20px; font-weight: bold; border-radius: 8px; padding: 15px; border: 1px solid #555; }
    QPushButton:pressed { background-color: #aa0000; border: 1px solid #ff4444; }
"""

# [8] 커스텀 설정 팝업창(QDialog) 스타일
POPUP_DIALOG = "background-color: #1a1a1a; border: 2px solid #555; border-radius: 15px;"
POPUP_DIALOG_PLAYER = "background-color: #1a1a1a; border: 2px solid #555; border-radius: 10px;"
POPUP_TITLE = "color: white; font-size: 22px; font-weight: bold; border: none;"
POPUP_TITLE_PLAYER = "color: #00FFCC; font-size: 18px; font-weight: bold; border: none;"
POPUP_TEXT_LABEL = "color: white; font-size: 18px; font-weight: bold; border: none;"
POPUP_GREEN_LABEL = "color: #00FFCC; font-size: 16px; font-weight: bold; border: none;"
POPUP_RADIO_BTN = "QRadioButton { color: white; font-size: 15px; border: none; } QRadioButton::indicator { width: 18px; height: 18px; }"
POPUP_SLIDER = "border: none; min-height: 30px;"
POPUP_VAL_LABEL = "color: white; font-size: 16px; font-weight: bold; border: none; min-width: 30px;"

POPUP_CAM_BTN = """
    QPushButton { background-color: #0055aa; color: white; font-size: 18px; font-weight: bold; border-radius: 8px; border: none; }
    QPushButton:pressed { background-color: #0077ff; }
"""
POPUP_CANCEL_BTN = """
    QPushButton { background-color: #666666; color: white; font-size: 20px; font-weight: bold; border-radius: 8px; border: none; }
    QPushButton:pressed { background-color: #444444; }
"""
POPUP_APPLY_BTN = """
    QPushButton { background-color: #007BFF; color: white; font-size: 20px; font-weight: bold; border-radius: 8px; border: none; }
    QPushButton:pressed { background-color: #0056b3; }
"""
POPUP_CANCEL_SMALL_BTN = "QPushButton { background-color: #666; color: white; font-size: 18px; font-weight: bold; border-radius: 6px; border: none; }"
POPUP_APPLY_SMALL_BTN = "QPushButton { background-color: #007BFF; color: white; font-size: 18px; font-weight: bold; border-radius: 6px; border: none; }"

# [9] 비디오 플레이어 컨트롤 스타일
PLAYER_VIDEO_LABEL = "background-color: black; border: 1px solid #333;"
PLAYER_PLAY_BTN = """
    QPushButton { background-color: #0055aa; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; border: none; }
    QPushButton:pressed { background-color: #0077ff; }
"""
PLAYER_CLOSE_BTN = """
    QPushButton { background-color: #aa0000; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; border: none; }
    QPushButton:pressed { background-color: #ff4444; }
"""
PLAYER_SLIDER = """
    QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: #333; margin: 2px 0; border-radius: 4px; }
    QSlider::handle:horizontal { background: #00FFCC; border: 1px solid #5c5c5c; width: 18px; margin: -5px 0; border-radius: 9px; }
"""

# [10] 개별 화면 전용 유니크 컴포넌트 스타일
INFO_LABEL = "color: white; font-size: 22px; line-height: 1.5; background-color: #222; border-radius: 10px; padding: 20px;"
EVENT_ROW_LABEL = "color: white; font-size: 18px; padding: 15px; background-color: #222; border-radius: 8px; border: 1px solid #444;"
ROI_HELP_LABEL_DEFAULT = "color: #00FFCC; font-size: 13px; font-weight: bold; background: transparent;"
ROI_HELP_LABEL_SUCCESS = "color: #28a745; font-size: 13px; font-weight: bold; background: transparent;"
ROI_BTN_BASE = "color: white; font-size: 16px; font-weight: bold; border-radius: 8px; border: none;"

# [11] QMessageBox 경고창 유저 테마 스타일 (검은색 묻힘 버그 해결판)
MSG_BOX = """
    QMessageBox { background-color: #222; border: 1px solid #555; } 
    QLabel { color: white; font-size: 16px; font-weight: bold; } 
    QPushButton { 
        background-color: #0055aa; color: #ffffff; 
        padding: 8px 24px; font-weight: bold; 
        border-radius: 4px; font-size: 14px; 
        border: 2px solid #0077ff; min-width: 70px; 
    }
    QPushButton:hover { background-color: #0077ff; }
"""