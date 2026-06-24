import cv2
import numpy as np

# [1] 외부 라이브러리 불러오기 및 환경 테스트
# AI 객체 인식 모델인 YOLO 라이브러리를 불러옵니다.
try:
    from ultralytics import YOLO
    HAS_YOLO = True # 불러오기 성공
except Exception as e:
    HAS_YOLO = False # 윈도우 환경 등에서 에러가 나면 AI 기능을 끄고 진행
    print(f"AI 모듈을 건너뜁니다 (윈도우 테스트 모드). 사유: {e}")

# 젯슨 나노의 하드웨어 핀(부저 등)을 제어하는 라이브러리를 불러옴
try:
    import Jetson.GPIO as GPIO
    HAS_GPIO = True # 불러오기 성공
except Exception as e:
    HAS_GPIO = False # 일반 PC 환경에서는 하드웨어 제어 기능을 끄고 진행
    print(f"Jetson.GPIO 모듈을 건너뜁니다. 사유: {e}")


# [2] 위험 감지기 메인 클래스
class DangerDetector:
    def __init__(self, model_path='ai_module/best.pt', buzzer_pin=18):
        # 환경 설정 상태와 부저 핀 번호를 클래스 변수로 저장
        self.has_yolo = HAS_YOLO
        self.has_gpio = HAS_GPIO
        self.buzzer_pin = buzzer_pin
        
        # UI에서 AI 감지 기능을 켜고 끌 수 있도록 상태를 저장하는 변수
        self.detection_enabled = True

        # 4개의 카메라 각각의 기본 좌표(사다리꼴)를 독립적으로 생성
        # 화면 정중앙 쯤에 임시 박스를 그림
        default_roi = [[220, 340], [420, 340], [420, 140], [220, 140]]
        # 딕셔너리 형태로 {0: 좌표, 1: 좌표, 2: 좌표, 3: 좌표} 를 만듬
        self.rois = {i: np.array(default_roi, np.int32) for i in range(4)}

        # AI 모델이 사용 가능하다면 학습된 파일(best.pt)을 불러와 준비
        if self.has_yolo:
            try:
                self.model = YOLO(model_path)
            except Exception as e:
                print(f"YOLO 모델 로드 실패: {e}")
                self.has_yolo = False

        # 하드웨어 제어가 가능하면 부저 핀을 출력 모드로 설정하고 소리를 끔
        if self.has_gpio:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.buzzer_pin, GPIO.OUT)
                GPIO.output(self.buzzer_pin, GPIO.LOW)
            except Exception as e:
                print(f"GPIO 초기화 실패: {e}")
                self.has_gpio = False


    # [3] 설정값 연동 함수들
    # UI 설정창에서 사용자가 그린 새로운 4개의 점 좌표를 받아 업데이트
    def set_roi_points(self, cam_idx, points):
        if points is not None and len(points) == 4:
            self.rois[cam_idx] = np.array(points, np.int32)
            print(f"CAM {cam_idx+1} 위험 구역 좌표 업데이트 완료: {self.rois[cam_idx]}")

    # UI 설정창을 열 때 기존에 그려둔 좌표를 넘김
    def get_roi_points(self, cam_idx):
        return self.rois[cam_idx].tolist()

    # UI 설정창의 토글 버튼에 맞춰 AI 감지 기능을 켜거나 끔
    def set_detection_enabled(self, enabled):
        self.detection_enabled = enabled
        print(f"위험 구역 감지 기능: {'켜짐' if enabled else '꺼짐'}")
        
        # 기능을 끌 때 혹시라도 울리고 있던 부저 소리를 확실하게 끔
        if not enabled and self.has_gpio:
            GPIO.output(self.buzzer_pin, GPIO.LOW)


    # [4] 실시간 영상 분석 및 그리기 메인 함수
    # 실시간 카메라 프레임을 한 장씩 넘겨받아 사람을 찾고 선을 그림
    def process_frame(self, frame, cam_idx):
        danger_detected = False
        current_roi = self.rois[cam_idx]
        
        # 💡 수정 1: YOLO 모듈 유무와 상관없이 영상에 ROI 선부터 무조건 그립니다.
        try:
            cv2.polylines(frame, [current_roi], True, (255, 255, 0), 2)
        except Exception:
            if frame.shape[0] > 100:
                cv2.putText(frame, "[AI ROI SET]", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # 💡 수정 2: AI 모듈이 없거나(PC 테스트), 설정에서 기능을 껐다면 여기서 종료
        if not self.has_yolo or not self.detection_enabled:
            return frame, False

        try:
            results = self.model(frame, stream=True, verbose=False)
            
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cx, cy = (x1 + x2) // 2, y2 

                    is_inside = cv2.pointPolygonTest(current_roi, (cx, cy), False) >= 0
                    
                    if is_inside:
                        danger_detected = True
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        cv2.putText(frame, "DANGER!", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    else:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        except Exception:
            pass 

        if self.has_gpio:
            if danger_detected:
                GPIO.output(self.buzzer_pin, GPIO.HIGH)
            else:
                GPIO.output(self.buzzer_pin, GPIO.LOW)

        return frame, danger_detected

    # 프로그램 종료 시 하드웨어 부저 장치를 안전하게 해제
    def cleanup(self):
        if self.has_gpio:
            GPIO.output(self.buzzer_pin, GPIO.LOW)
            GPIO.cleanup()