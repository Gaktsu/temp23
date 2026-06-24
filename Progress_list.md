# Progress List

다음은 리포지토리 검사 결과입니다. 각 항목 옆에 구현 상태와 간단한 근거를 적었습니다.

- PyQt5기반 실시간 관제 UI: 완료
  - 근거: `ui_app.py`, `ui/screens/*`에 PyQt5 기반 화면 구현 (LiveScreen, MenuScreen 등).

- 다중 카메라 실시간 연동: 부분 완료
  - 근거: `config/settings.py`의 `CAMERA_INDICES`, `hardware/camera.py`의 `init_cameras`, `pipeline/capture.py`로 다중 카메라 동작 지원.
  - 제약: 자동 핫플러그(플러그 시 자동 감지)는 미구현 — `CAMERA_INDICES` 설정으로 명시적 구성 필요.

- 분할 화면 관제: 완료
  - 근거: `main.py`의 `_build_split_frame`, `ui/screens/live_screen.py`의 4분할 표시 구현.

- 카메라 화면 확대: 완료
  - 근거: `ui/screens/live_screen.py`의 전체화면 확대/복귀 로직 구현.

- 전체 위험 상태 표시: 완료
  - 근거: `ui/screens/live_screen.py`의 `alert_bar`와 `_update_alert_bar` 구현.

- 실제 이벤트 로그 표시: 완료
  - 근거: `ui/screens/event_screen.py`가 `logs/event_project.log`을 파싱해 표시.

- 시스템 종료 버튼: 완료
  - 근거: `ui/screens/menu_screen.py`의 시스템 종료 버튼(`QApplication.instance().quit`).

- 카메라별 ROI 영역 설정 (Json): 완료
  - 근거: `config/roi_manager.py`, `config/roi_setup.py`, `ui/screens/roi_setup_screen.py` 및 `ai/detector.py`의 `load_roi_polygon` 지원.

- OpenCV기반 ROI 설정 안정화: 완료
  - 근거: `ui/screens/roi_setup_screen.py`와 `config/roi_setup.py`에서 정규화 좌표 및 파일 저장/로딩 처리.

- 카메라 연결 재시도: 완료
  - 근거: `hardware/camera.py`의 `open_camera_with_retry` 구현 (재시도/지연 설정 사용).

- 카메라 오류 진단: 완료
  - 근거: `hardware/camera.py`의 `diagnose_camera_error`와 `errors/enums.py`의 `CameraError`.

- 위험 상황 발생 시 즉시 피드백: 완료
  - 근거: UI 경고바, `pipeline/inference.py`의 이벤트 큐, `ui_app.py`의 부저 제어 연동.

- 전체 시스템 위험 단계 표시(위험, 경고, 주의): 완료
  - 근거: `ai/detector.py`의 `WarningLevel` 및 `live_screen`의 색상/문구 매핑.

- Jetson GPIO 부저 연동: 부분 완료
  - 근거: `hardware/buzzer.py`가 `RPi.GPIO` 사용 시 실제 제어, `main.py`에서 `Buzzer.start()` 호출.
  - 제약: Jetson에 `RPi.GPIO`가 설치되어 있어야 실제 HW 제어 가능. (대체 로직은 로그/프린트로 처리됨)

- 이벤트 기반 영상 녹화(사전 녹화 + 이벤트 발생 + 후속 녹화): 완료
  - 근거: `pipeline/recorder.py`의 pre-buffer, event start, post_seconds 처리.

- 모든 카메라 동시 녹화: 완료
  - 근거: `start_save_thread` + `save_loop`가 카메라별 writer 관리 및 동시 저장 지원.

- 상시 녹화 모드: 완료
  - 근거: `config/settings.py`의 `RECORDING_MODE='full'` 지원, `recorder.py`의 full 모드 처리.

- 이벤트별 영상 폴더 저장: 완료
  - 근거: `_create_event_folder` 및 파일명 로직 (`pipeline/recorder_utils.py`).

- H.264 MP4 저장: 완료(의존성 필요)
  - 근거: `pipeline/recorder_utils.py`의 `GstH264Writer`(ffmpeg) 및 `_transcode_to_h264` 구현.
  - 제약: `ffmpeg` 및 `libx264` 설치 필요.

- 영상 서버 업로드: 완료
  - 근거: `pipeline/uploader.py`의 `upload_video_file` (curl 기반 업로드) 호출 경로 존재.

- 업로드 재시도 / 타임아웃 처리: 완료
  - 근거: `pipeline/uploader.py`에서 `UPLOAD_MAX_RETRIES`, `UPLOAD_TIMEOUT_SEC`, `UPLOAD_RETRY_DELAY_SEC` 사용.

- 이벤트 JSON 전송 워커: 완료
  - 근거: `pipeline/uploader.py`의 `upload_event_log` 및 `start_event_upload_worker`.

- 중복 이벤트 전송 방지: 완료
  - 근거: 업로드 쿨다운(`EVENT_LOG_COOLDOWN_SEC`) 및 `_is_within_cooldown` 체크 구현.

- 구조화 로그: 완료
  - 근거: `utils/logger.py`의 `StructuredLogger` (JSON 포맷 로그).

- 성능 로그: 완료
  - 근거: `pipeline/inference.py`의 집계 로그, `pipeline/recorder.py`의 처리 로깅 등.

- Watchdog 자동 재시작: 완료
  - 근거: `system/watchdog.py` 구현 (메인 프로세스 재시작 로직).

- 저장 공간 관리 기능: 완료
  - 근거: `_cleanup_old_folders`가 오래된 event/full 폴더를 삭제 (`recorder_utils.py`).

- 안전한 종료 / 정리 절차: 완료
  - 근거: `main.py`의 `_cleanup`에서 스레드 종료, 저장 대기, 리소스 해제, `os._exit(0)` 처리.


요약: 전체 기능은 대부분 구현되어 있으며, 하드웨어·외부 의존성(예: ffmpeg, RPi.GPIO, curl)이나 런타임 설정(`CAMERA_INDICES`)에 따라 일부 동작은 환경 제약을 가집니다.

파일 생성일: 자동 생성
