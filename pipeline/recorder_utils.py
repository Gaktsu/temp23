"""
Recorder helper functions extracted from legacy vision.yolo_infer.
"""
from __future__ import annotations

import cv2
import os
import shutil
import stat
import subprocess
from typing import Any, Dict, Optional, Tuple

from config.settings import UPLOAD_COMBINED, UPLOAD_ENABLED
from pipeline.uploader import get_upload_status_snapshot, upload_video_file, upload_video_with_event
from utils.logger import get_logger, EventType
from utils.time_utils import epoch_to_tag

logger = get_logger("pipeline.recorder_utils")

# ──────────────────────────────────────────────────────────────
# GStreamer H.264 직접 저장 설정
#   speed-preset  : ultrafast / veryfast  (CPU 부담 조절)
#   bitrate       : kbps 단위, 해상도·프레임에 따라 아래 값 조정
#     예) 1280×720 @27fps → 1500~2000, 1920×1080 @27fps → 3000~4000
# ──────────────────────────────────────────────────────────────
_GST_H264_BITRATE: int = 5000      # kbps
_GST_H264_PRESET: str = "veryfast"  # ultrafast / veryfast / medium


def _build_gst_h264_pipeline(w: int, h: int, fps: float, file_path: str) -> str:
    r"""GStreamer appsrc → x264enc(소프트웨어) → mp4mux 파이프라인 문자열 반환.

    필요 GStreamer 플러그인:
        sudo apt install \
            gstreamer1.0-plugins-ugly \   # x264enc
            gstreamer1.0-plugins-good \   # mp4mux, videoconvert
            gstreamer1.0-plugins-base \   # appsrc, videoconvert
            gstreamer1.0-tools             # gst-launch-1.0 (디버깅용)
    """
    fps_int = max(1, round(fps))
    gop = fps_int * 2  # 2초 단위 키프레임 간격 (key-int-max)
    safe_path = file_path.replace("\\", "/")
    # Python 쪽에서 BGR→I420 변환 후 전달 — rawvideoparse BGR 미지원 보전성 확보
    frame_size = w * h * 3 // 2  # I420 한 프레임 바이트 크기
    return (
        f"fdsrc fd=0 ! "
        f"rawvideoparse width={w} height={h} format=I420 "
        f"framerate-n={fps_int} framerate-d=1 framesize={frame_size} ! "
        f"x264enc speed-preset={_GST_H264_PRESET} tune=zerolatency "
        f"bitrate={_GST_H264_BITRATE} key-int-max={gop} ! "
        f"h264parse ! "
        f"mp4mux ! "
        f"filesink location={safe_path} sync=false"
    )


def _check_gstreamer_available() -> bool:
    """ffmpeg 바이너리와 libx264 인코더가 사용 가능한지 확인한다."""
    if shutil.which("ffmpeg") is None:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "ffmpeg 바이너리를 찾을 수 없습니다.",
            {"hint": "sudo apt install ffmpeg"}
        )
        return False
    result = subprocess.run(
        ["ffmpeg", "-encoders"],
        capture_output=True, text=True
    )
    if "libx264" not in result.stdout:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "ffmpeg에서 libx264 인코더를 찾을 수 없습니다.",
            {"hint": "sudo apt install ffmpeg libx264-dev"}
        )
        return False
    return True


class GstH264Writer:
    """cv2.VideoWriter 호환 인터페이스로 ffmpeg libx264를 사용해 H.264를 실시간 저장하는 클래스.

    GStreamer 플러그인 호환성 문제를 우회하기 위해 ffmpeg stdin pipe 방식을 사용합니다.
    ffmpeg -f rawvideo -pix_fmt bgr24 -i pipe:0 으로 BGR 프레임을 실시간 인코딩합니다.
    """

    def __init__(self, w: int, h: int, fps_int: int, file_path: str) -> None:
        self._proc: Optional[subprocess.Popen] = None
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}",
            "-r", str(fps_int),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", _GST_H264_PRESET,
            "-tune", "zerolatency",
            "-b:v", f"{_GST_H264_BITRATE}k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            file_path,
        ]
        logger.event_info(
            EventType.MODULE_START,
            "H264Writer(ffmpeg stdin pipe) 시작",
            {"cmd": " ".join(cmd)}
        )
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "H264Writer 프로세스 시작 실패",
                {"error": str(e)}
            )
            self._proc = None

    def isOpened(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def write(self, frame) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            # ffmpeg -pix_fmt bgr24 으로 직접 BGR 수신 — 변환 불필요
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            pass

    def release(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "GstH264Writer 종료 타임아웃 — 프로세스를 강제 종료합니다.",
                {}
            )
        except Exception as e:
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "GstH264Writer release 실패",
                {"error": str(e)}
            )
        finally:
            self._proc = None


def _transcode_to_h264(file_path: str) -> Optional[str]:
    """
    저장된 MJPG .avi 파일을 H.264 .mp4로 변환 (ffmpeg 사용).
    변환 성공 시 원본(.avi)을 삭제하고 생성된 .mp4 경로를 반환합니다.
    변환 실패 시 임시 파일을 삭제하고 원본을 보존한 뒤 None을 반환합니다.

    Args:
        file_path: 변환할 .avi 파일 경로 (MJPG 코덱)

    Returns:
        성공 시 생성된 .mp4 파일 경로, 실패 시 None
    """
    tmp_path = file_path.replace(".avi", "_h264_tmp.mp4")
    out_path  = file_path.replace(".avi", ".mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-movflags", "+faststart",
        tmp_path
    ]
    try:
        logger.event_info(
            EventType.MODULE_START,
            "H.264 변환 시작",
            {"original_file": file_path, "tmp_file": tmp_path}
        )
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            # 1단계: 원본(.avi) 파일 삭제
            try:
                os.remove(file_path)
                logger.event_info(
                    EventType.MODULE_STOP,
                    "원본 avi 파일 삭제 완료",
                    {"file": file_path}
                )
            except Exception as e:
                logger.event_error(
                    EventType.ERROR_OCCURRED,
                    "원본 avi 파일 삭제 실패",
                    {"file": file_path, "error": str(e)}
                )
                # 원본 삭제 실패 시 임시 파일도 정리
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                return None

            # 2단계: H.264 임시 파일을 .mp4 출력 경로로 이동
            try:
                os.rename(tmp_path, out_path)
                # 3단계: chmod +x (소유자/그룹/기타 실행 권한 추가)
                current = stat.S_IMODE(os.stat(out_path).st_mode)
                os.chmod(out_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                logger.event_info(
                    EventType.MODULE_STOP,
                    "H.264 변환 완료 (chmod +x 적용)",
                    {"file": out_path}
                )
                return out_path
            except Exception as e:
                logger.event_error(
                    EventType.ERROR_OCCURRED,
                    "H.264 파일 이동 실패 (원본은 이미 삭제됨)",
                    {"tmp_file": tmp_path, "dest": out_path, "error": str(e)}
                )
                return None
        else:
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "H.264 변환 실패 (ffmpeg 오류) - 원본 파일 보존",
                {"file": file_path, "stderr": result.stderr[-500:]}
            )
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return None
    except subprocess.TimeoutExpired:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "H.264 변환 타임아웃 (300초 초과) - 원본 파일 보존",
            {"file": file_path}
        )
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return None
    except Exception as e:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "H.264 변환 중 예외 - 원본 파일 보존",
            {"file": file_path, "error": str(e)}
        )
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return None


def _upload_video(
    file_path: str,
    event_type: str = "",
    cam_id: int = -1,
    speed_level: int = 0,
    max_severity: Optional[int] = None,
) -> None:
    """GStreamer X264로 저장된 .mp4 파일을 업로드한다.

    UPLOAD_COMBINED = True 이고 event_type/cam_id 가 유효하면
    upload_video_with_event() 로 영상+이벤트를 단일 요청으로 전송한다.
    max_severity 가 전달되면 녹화 중 측정된 최대값을 severity 로 사용한다.
    그 외에는 기존 upload_video_file() 을 사용한다.
    """
    if not UPLOAD_ENABLED:
        return
    if UPLOAD_COMBINED and event_type and cam_id >= 0:
        success = upload_video_with_event(file_path, event_type, cam_id, speed_level, severity_override=max_severity)
    else:
        success = upload_video_file(file_path)
    if not success:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "영상 업로드 실패 기록",
            {"file": file_path, "upload_status": get_upload_status_snapshot()},
        )


def _cleanup_old_folders(
    parent_dir: str,
    max_folders: int,
    is_full_mode: bool = False
) -> None:
    """
    오래된 폴더 정리
    
    Args:
        parent_dir: 부모 디렉토리 (event 모드: SaveVideos, full 모드: SaveVideos/full_recording)
        max_folders: 최대 폴더 개수 (0이면 정리하지 않음)
        is_full_mode: full 모드 여부
    """
    if max_folders <= 0:
        return
    
    try:
        # event_로 시작하는 폴더만 필터링
        folders = []
        for item in os.listdir(parent_dir):
            item_path = os.path.join(parent_dir, item)
            if os.path.isdir(item_path) and item.startswith("event_"):
                folders.append(item_path)
        
        # 폴더가 최대 개수를 초과하면 오래된 것부터 삭제
        if len(folders) > max_folders:
            # 생성 시간 기준 정렬 (오래된 것부터)
            folders.sort(key=lambda x: os.path.getctime(x))
            
            # 초과된 폴더 삭제
            folders_to_delete = folders[:len(folders) - max_folders]
            mode_name = "full" if is_full_mode else "event"
            
            for folder in folders_to_delete:
                try:
                    shutil.rmtree(folder)
                    logger.event_info(
                        EventType.MODULE_STOP,
                        f"{mode_name} 모드 오래된 폴더 삭제",
                        {"path": folder}
                    )
                except Exception as e:
                    logger.event_error(
                        EventType.ERROR_OCCURRED,
                        f"{mode_name} 모드 폴더 삭제 실패",
                        {"path": folder, "error": str(e)}
                    )
    except Exception as e:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "폴더 정리 중 오류",
            {"parent_dir": parent_dir, "error": str(e)}
        )


def _create_writer(
    save_dir: str,
    cam_id: int,
    timestamp: float,
    frame: cv2.Mat,
    fps_map: dict[int, float],
    codec: str,
    sensor_data: Optional[Dict[str, Any]],
    event_folder: Optional[str] = None
) -> Optional[Tuple[cv2.VideoWriter, str]]:
    try:
        h, w = frame.shape[:2]
        fps = fps_map.get(cam_id, 30.0) or 30.0
        fps_int = max(1, round(fps))  # GStreamer caps 와 VideoWriter 에 동일하게 사용

        logger.event_info(
            EventType.MODULE_START,
            "_create_writer 시작",
            {"cam_id": cam_id, "fps": fps, "fps_int": fps_int, "codec": codec, "frame_size": (w, h), "event_folder": event_folder}
        )

        file_path = _build_event_filename(save_dir, cam_id, timestamp, event_folder)

        # X264 코덱 요청 시 확장자를 .mp4 로 교체 (GStreamer 직접 저장)
        if codec == "X264":
            file_path = os.path.splitext(file_path)[0] + ".mp4"

        logger.event_info(
            EventType.MODULE_START,
            "파일 경로 생성 완료",
            {"file_path": file_path}
        )

        if codec == "X264":
            # ffmpeg libx264 사용 가능 여부 사전 확인
            if not _check_gstreamer_available():
                return None
            writer = GstH264Writer(w, h, fps_int, file_path)
        else:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(file_path, fourcc, fps, (w, h))

        logger.event_info(
            EventType.MODULE_START,
            "VideoWriter 객체 생성 완료",
            {"isOpened": writer.isOpened() if writer else False}
        )

        if not writer.isOpened():
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "영상 저장기 생성 실패 — ffmpeg 프로세스를 시작할 수 없습니다.",
                {
                    "camera": cam_id,
                    "path": file_path,
                    "hint": "ffmpeg -encoders | grep libx264 로 인코더 지원 여부 확인"
                }
            )
            return None
        
        logger.event_info(
            EventType.MODULE_START,
            "_create_writer 성공",
            {"cam_id": cam_id, "path": file_path}
        )
        
        return writer, file_path
    except Exception as e:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "_create_writer 예외 발생",
            {"cam_id": cam_id, "error": str(e), "error_type": type(e).__name__}
        )
        return None


def _build_event_filename(
    save_dir: str,
    cam_id: int,
    event_ts: float,
    event_folder: Optional[str] = None
) -> str:
    """
    영상 파일 경로 생성
    
    Args:
        save_dir: 기본 저장 디렉토리
        cam_id: 카메라 ID
        event_ts: 이벤트 타임스탬프
        event_folder: 이벤트 폴더 경로 (있으면 해당 폴더에 저장)
    
    Returns:
        파일 경로
    """
    time_tag = epoch_to_tag(event_ts)
    filename = f"{time_tag} No.{cam_id}.avi"
    return os.path.join(save_dir, filename)
