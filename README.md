# Person Detection System

실시간 사람 탐지 및 경고 시스템

## 프로젝트 구조

```
project/
 ├─ main.py                 # 전체 흐름 제어
 │
 ├─ config/
 │   ├─ settings.py         # 상수, 경로, 파라미터
 │   ├─ roi_manager.py      # ROI JSON 읽기/쓰기
 │   └─ roi_setup.py        # ROI 캘리브레이션 도구
 │
 ├─ errors/
 │   └─ enums.py            # CameraError, IMUError 등
 │
 ├─ hardware/
 │   ├─ camera.py           # USB / CSI 초기화 + 캡처
 │   ├─ buzzer.py           # 부저 제어
 │   └─ imu.py              # IMU 센서
 │
 ├─ ai/
 │   ├─ detector.py         # Detection schema / ROI / TTC 경고 레벨
 │   └─ model.py            # YOLO 모델 로드 및 추론 래퍼
 │
 ├─ pipeline/
 │   ├─ capture.py          # 카메라 캡처 스레드
 │   ├─ inference.py        # 카메라별 추론 스레드
 │   ├─ recorder.py         # 이벤트/상시 녹화 워커
 │   ├─ recorder_utils.py   # 저장/인코딩 유틸
 │   ├─ sensors.py          # IMU 폴링
 │   ├─ shared_state.py     # 스레드 공유 상태
 │   └─ uploader.py         # 이벤트/영상 업로드
 │
 ├─ ui/
 │   ├─ renderer.py         # OpenCV 오버레이 렌더링
 │   └─ screens/            # PyQt5 화면들
 │
 ├─ system/
 │   ├─ autostart.py        # 부팅 자동 실행
 │   ├─ storage.py          # 용량 관리
 │   └─ watchdog.py         # 재시작 / 오류 감지
 │
 ├─ utils/
 │   ├─ logger.py           # 로그
 │   ├─ time_utils.py       # timestamp
 │   └─ sensor_sync.py      # 센서 데이터 동기화
 │
 ├─ SaveVideos/             # 녹화 영상 저장 디렉토리
 ├─ sounds/                 # 경고음 파일
 └─ models/                 # YOLO 모델 파일
```

## 설치

### 필수 패키지

```bash
pip install ultralytics opencv-python PyQt5 numpy coloredlogs smbus2
```

Jetson/Linux에서 IMX219 카메라 컨트롤(밝기, 노출, 게인, 초점 등)을 초기화하려면
`v4l2-ctl`이 필요합니다.

```bash
sudo apt install v4l-utils
```

### 하드웨어 요구사항

- USB 카메라 또는 CSI 카메라 (1개 이상)
- IMX219 CSI 카메라 사용 시 기본 권장 프로파일: `640x480 @ 15fps`
- IMU 센서 (선택사항)
- 경고음 출력 장치 (선택사항): `gst-launch-1.0` 또는 `ffplay`로 사운드 파일 재생

## 실행

### 기본 실행

```bash
python3 main.py
```

### Watchdog로 실행 (자동 재시작)

프로그램 오류 시 자동으로 재시작합니다:

```bash
python3 system/watchdog.py
```

### 실행 시 확인사항

1. 카메라가 올바르게 연결되어 있는지 확인
2. YOLO 모델 파일이 `models/` 디렉토리에 있는지 확인
3. IMU 센서가 연결되어 있는지 확인 (선택사항)
4. `SaveVideos/` 디렉토리에 쓰기 권한이 있는지 확인

### 카메라 리소스 강제 해제

프로그램 비정상 종료 후 `/dev/video*` 장치가 다른 프로세스에 잡혀 있어 카메라가 열리지 않으면
다음 명령으로 설정된 카메라 장치 점유 프로세스를 종료할 수 있습니다.

```bash
python3 system/release_cameras.py --dry-run --all --stop-app
python3 system/release_cameras.py --all --stop-app
python3 system/release_cameras.py --all --stop-app --process-groups --kill
```

권한 때문에 남는 프로세스가 있으면 `sudo`로 다시 실행하세요.

## 설정

`config/settings.py`에서 다음 항목을 수정할 수 있습니다:

### 카메라 설정
- `CAMERA_INDICES`: 사용할 카메라 인덱스 리스트 (예: `[0, 2]`, IMX219 4대 구성은 `[0, 2, 4, 6]`)
- `CAMERA_DEFAULT_WIDTH`: 캡처 해상도 가로 기본값 (현재 기본: `640`)
- `CAMERA_DEFAULT_HEIGHT`: 캡처 해상도 세로 기본값 (현재 기본: `480`)
- `CAMERA_DEFAULT_FPS`: 카메라 FPS 기본값 (현재 기본: `15.0`)
- `CAMERA_OUTPUT_WIDTH`, `CAMERA_OUTPUT_HEIGHT`: 화면/ROI 기준 출력 해상도 (현재 기본: `640x480`)
- `CAMERA_MAX_RETRIES`: 카메라 초기화 재시도 횟수
- `CAMERA_RETRY_DELAY`: 재시도 간 대기 시간 (초)
- `CAMERA_RESET_CONTROLS_TO_DEFAULT`: 카메라 open/reconnect 시 V4L2 컨트롤을 장치 기본값으로 초기화
- `CAMERA_DISABLE_AUTOFOCUS`: 지원되는 자동초점 컨트롤을 끔
- `CAMERA_AUTOFOCUS_CONTROL_NAMES`: 자동초점 off 적용 대상 V4L2 컨트롤 이름 목록

### YOLO 모델 설정
- `MODEL_PATH`: YOLO 모델 경로 (기본: `models/best.pt`)
- `CONFIDENCE_THRESHOLD`: 신뢰도 임계값
- `INFER_IOU_THRESHOLD`: Ultralytics 내부 NMS IoU 임계값. 겹치는 bbox 중복 제거 테스트에 사용
- `INFER_STRIDE`: 추론 간격 (N프레임마다)
- `REQUIRE_ROI_FOR_INTRUSION`: ROI가 없는 카메라는 침입/경고/녹화를 발생시키지 않음
- `DETECTION_STALE_SEC`: 오래된 탐지 결과가 경고 상태를 유지하지 않도록 만료하는 시간
- `DETECTION_OVERLAY_MODE`: 탐지 표시 방식 (`"dot"`: 기존 발끝 점, `"bbox"`: bbox + 내부 track id)
- `POSTPROCESS_IOU_NMS_ENABLED`: 앱 후처리 단계에서 bbox 중복 제거 IoU NMS 추가 적용 여부. 테스트용이며 기본은 비활성
- `POSTPROCESS_IOU_NMS_THRESHOLD`: 후처리 IoU NMS 임계값. 중복 bbox 중 confidence가 낮은 bbox를 제거
- `TTC_HISTORY_LEN`: 접근 판정에 사용할 bbox 면적 이력 길이
- `TTC_APPROACH_RATIO`: ROI 내부 사람 bbox 면적 증가율이 이 값보다 크면 `APPROACH`
- `TTC_URGENT_RATIO`: ROI 내부 사람 bbox 면적 증가율이 이 값보다 크면 `URGENT`
- `WARNING_SCREEN_FLASH_ENABLED`: `APPROACH`/`URGENT` 상태에서 전체 화면 점멸 사용 여부
- `WARNING_SCREEN_FLASH_ALPHA`: 전체 화면 점멸 오버레이 투명도 (`0.0~1.0` 또는 `0~255`)
- `WARNING_SCREEN_FLASH_INTERVAL_SEC`: 전체 화면 점멸 on/off 전환 주기

### 영상 저장 설정
- `RECORDING_MODE`: 녹화 모드 (`"event"`: 이벤트 발생 시만, `"full"`: 상시 녹화)
- `EVENT_RECORD_BUFFER_SEC`: 이벤트 발생 전 저장할 버퍼 시간 (현재 기본: `15.0`초)
- `EVENT_RECORD_POST_SEC`: 이벤트 종료 후 저장할 시간 (현재 기본: `15.0`초)
- `SAVE_DIR`: 영상 저장 디렉토리 경로

## 사용법

### 키보드 단축키

- **Q**: 프로그램 종료
- **C**: 카메라 전환 (여러 카메라가 연결된 경우)

PyQt5 UI에서는 라이브 화면, 설정 화면, ROI 설정 화면, 이벤트/재생 화면을 터치/버튼으로 전환합니다.

### 다중 카메라 설정

`config/settings.py`에서 카메라 인덱스를 설정하세요:

```python
# 아래 예시 중 실제 장치 구성에 맞는 하나만 사용하세요.
CAMERA_INDICES = [0, 2]        # 현재 2대 구성 예시
CAMERA_INDICES = [0, 2, 4, 6]  # IMX219 4대 구성 예시
```

모든 카메라는 백그라운드에서 동시에 캡처/추론되며, UI는 4분할 화면 또는 선택 화면으로 표시됩니다.

**중요**: 어느 한 카메라에서라도 침입이 감지되면 **모든 카메라가 동시에 녹화**됩니다. 이를 통해 다각도 영상 증거를 확보할 수 있습니다.

### IMX219 카메라 기본값 초기화 및 자동초점

Jetson/Linux에서는 카메라를 열 때마다 `v4l2-ctl --list-ctrls`로 컨트롤 목록을 읽고,
각 컨트롤의 `default=` 값을 다시 적용합니다. 이 동작은 카메라마다 밝기, 대비,
채도, 노출, 게인 등이 제각각 남아 있는 상황을 줄이기 위한 것입니다.

자동초점은 다음 순서로 비활성화를 시도합니다.

1. OpenCV `CAP_PROP_AUTOFOCUS = 0`
2. V4L2 컨트롤 `focus_auto`, `auto_focus`, `focus_automatic_continuous`, `continuous_auto_focus`를 `0`으로 설정

IMX219 고정초점 모듈처럼 자동초점 컨트롤이 없는 장치는 로그만 남기고 계속 실행됩니다.

### ROI 및 경고 조건

경고음, 이벤트 업로드, 이벤트 녹화는 객체 탐지만으로 발생하지 않습니다.
현재 침입 조건은 ROI 내부 발끝 판정 또는 ROI 기반 경고 레벨입니다.

- IoU/NMS 설정은 겹치는 bbox 중복 제거용이며, ROI 침입 판정 기준은 변경하지 않음
- ROI 침입 판정은 bbox 전체 겹침이 아니라 bbox 하단 중앙점(발끝)이 ROI 내부에 있는지로 판단
- ROI 파일이 없거나 깨진 카메라: `SAFE` 처리
- ROI 밖 사람 탐지: 탐지 박스/점은 표시하지만 경고/부저/녹화는 발생하지 않음
- `SAFE`, `BLIND_SPOT`: 전체 화면 점멸 없음
- `APPROACH`: SAFE/BLIND_SPOT으로 돌아올 때까지 주황색 반투명 전체 화면 점멸
- `URGENT`: SAFE/BLIND_SPOT으로 돌아올 때까지 빨간색 반투명 전체 화면 점멸
- 접근 판정은 실제 거리값이 아니라 같은 `track_id`의 bbox 면적 증가율을 사용하며, `TTC_*` 설정값으로 현장 조정 가능

### 영상 저장 동작 방식

#### 이벤트 기반 녹화 (`RECORDING_MODE = "event"`)
1. 침입 감지 시 모든 카메라 녹화 시작
2. 이벤트 발생 전 프레임부터 저장 (기본 `EVENT_RECORD_BUFFER_SEC = 15.0`)
3. 침입이 계속되는 동안 녹화 지속
4. 마지막 침입 종료 후 추가 녹화 (기본 `EVENT_RECORD_POST_SEC = 15.0`)
5. 후속 녹화 시간 안에 재침입 발생 시 녹화 자동 연장
6. 저장 파일명: `{timestamp} No.{camera_id}.mp4`

#### 전체 녹화 (`RECORDING_MODE = "full"`)
- 프로그램 실행 중 모든 카메라 상시 녹화

## 지원 플랫폼

- **Windows**: DirectShow (CAP_DSHOW) 백엔드 사용
- **Jetson (NVIDIA)**: Video4Linux2 (CAP_V4L2) 백엔드 자동 사용
- **Linux (일반)**: Video4Linux2 (CAP_V4L2) 백엔드 사용

카메라 백엔드는 운영체제를 자동으로 감지하여 설정됩니다.

## 기능

### 핵심 기능
- ✅ 실시간 사람 탐지 (YOLO)
- ✅ ROI 기반 침입 감지
- ✅ FPS, 시간, 탐지 수 표시
- ✅ 다중 카메라 지원 및 실시간 전환
- ✅ 모든 카메라 백그라운드 동시 촬영
- ✅ OS별 카메라 백엔드 자동 감지 (Windows/Jetson/Linux)
- ✅ 카메라 오류 진단 및 자동 재시도
- ✅ 카메라 재연결 시 동일 해상도/FPS/FourCC 재적용
- ✅ Jetson/Linux V4L2 카메라 컨트롤 기본값 초기화
- ✅ 지원되는 자동초점 컨트롤 비활성화

### 경고 시스템
- ✅ 경고음 재생 (ROI 침입 감지 시 자동 알림)
- ✅ `APPROACH`, `URGENT` 위험도 색상으로 전체 화면 반투명 점멸

### 센서 통합
- ✅ IMU 센서 연동
- ✅ 센서 데이터 동기화 및 버퍼링

### 영상 저장
- ✅ 이벤트 기반 녹화 (침입 감지 시 자동 녹화)
- ✅ 전체 녹화 모드 (상시 녹화)
- ✅ 사전 버퍼링 (기본 15초)
- ✅ 후속 녹화 (기본 15초)
- ✅ 이벤트 재발생 시 녹화 자동 연장
- ✅ **다중 카메라 동시 녹화** (한 카메라에서 이벤트 발생 시 모든 카메라 동시 저장)
- ✅ 타임스탬프 기반 영상 파일 관리

### 로깅 시스템
- ✅ 구조화된 로깅 (JSON 형식)
- ✅ 이벤트 타입별 로그 분류
- ✅ 콘솔 및 파일 로그 동시 출력

## 로그 확인

로그 파일은 `logs/` 디렉토리에 저장됩니다:

```bash
logs/
 ├─ event_project.log    # 이벤트 로그
 ├─ debug_project.log    # 디버그 로그
 └─ watchdog.log         # watchdog 로그
```

로그 레벨:
- `DEBUG`: 상세한 디버깅 정보
- `INFO`: 일반 정보 메시지
- `WARNING`: 경고 메시지
- `ERROR`: 오류 메시지
- `CRITICAL`: 치명적인 오류

## 문제 해결 (Troubleshooting)

### 카메라 연결 실패

```
오류: 카메라 초기화 실패
```

**해결방법:**
1. 카메라가 물리적으로 올바르게 연결되어 있는지 확인
2. 다른 프로그램에서 카메라를 사용 중인지 확인
3. `CAMERA_INDICES` 설정이 올바른지 확인
4. USB 포트를 변경해보거나 카메라 재연결

### IMX219 카메라별 밝기/노출이 다름

**해결방법:**
1. `v4l2-ctl` 설치 여부 확인: `which v4l2-ctl`
2. `CAMERA_RESET_CONTROLS_TO_DEFAULT = True` 확인
3. 카메라를 사용하는 다른 프로세스를 종료한 뒤 프로그램 재시작
4. 장치가 제공하는 기본값 확인: `v4l2-ctl -d /dev/video0 --list-ctrls`

### 자동초점이 계속 동작함

**해결방법:**
1. `CAMERA_DISABLE_AUTOFOCUS = True` 확인
2. 장치에 초점 컨트롤이 있는지 확인: `v4l2-ctl -d /dev/video0 --list-ctrls | grep -i focus`
3. 컨트롤 이름이 다르면 `CAMERA_AUTOFOCUS_CONTROL_NAMES`에 해당 이름 추가
4. IMX219 고정초점 모듈은 자동초점 컨트롤이 없을 수 있으며, 이 경우 끌 대상이 없습니다.

### YOLO 모델 로드 실패

```
오류: YOLO 모델 로드 실패
```

**해결방법:**
1. `MODEL_PATH`가 올바른지 확인
2. 모델 파일이 `models/` 디렉토리에 있는지 확인
3. 모델 파일이 손상되지 않았는지 확인

### IMU 센서 연결 실패

```
경고: IMU 초기화 실패
```

**해결방법:**
1. 센서가 올바른 포트에 연결되어 있는지 확인
2. 시리얼 포트 권한 확인 (Linux: `/dev/ttyUSB0` 등)
3. 센서는 선택사항이므로 시스템은 센서 없이도 작동 가능

### 영상 저장 실패

```
오류: 영상 저장기 생성 실패
```

**해결방법:**
1. `SaveVideos/` 디렉토리가 존재하는지 확인
2. 디렉토리 쓰기 권한 확인
3. 디스크 공간이 충분한지 확인
4. 코덱이 시스템에서 지원되는지 확인

### 낮은 FPS

**해결방법:**
1. 카메라 FPS를 낮춤 (기본 권장: 15fps)
2. `INFER_STRIDE` 값을 증가 (예: 3 → 5)
3. YOLO 모델을 더 가벼운 버전으로 변경 (yolov8n 권장)
4. `imgsz` 값을 낮춤 (예: 640 → 320)
5. 카메라 해상도 조정

## 성능 최적화

### 권장 설정

- **단일 카메라**: `INFER_STRIDE = 1-2`, `imgsz = 640`
- **다중 카메라 (2개)**: `640x480 @ 15fps`, `INFER_STRIDE = 3-5`, `imgsz = 320-640`
- **IMX219 4대**: `CAMERA_INDICES = [0, 2, 4, 6]`, `640x480 @ 15fps`, 필요 시 `INFER_STRIDE` 증가
- **저사양 PC**: YOLO 모델 `yolov8n.pt` 사용, `imgsz = 320`

### 멀티스레딩 구조

- **캡처 스레드**: 각 카메라마다 1개
- **추론 스레드**: 중앙 1개 (모든 카메라 공유)
- **저장 스레드**: 1개 (모든 카메라 공유)
- **센서 스레드**: IMU 1개
