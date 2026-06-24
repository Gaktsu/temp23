"""
저장소 용량 관리
"""
import json
import os
import shutil
from typing import List
from config.settings import SAVE_DIR

IMPORTANT_VIDEO_META_FILENAME = ".important_videos.json"


def _important_video_meta_path(path: str = SAVE_DIR) -> str:
    return os.path.join(path, IMPORTANT_VIDEO_META_FILENAME)


def load_important_video_map(path: str = SAVE_DIR) -> dict:
    meta_path = _important_video_meta_path(path)
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(key): bool(value) for key, value in data.items()}
    except Exception:
        pass
    return {}


def save_important_video_map(important_map: dict, path: str = SAVE_DIR) -> None:
    os.makedirs(path, exist_ok=True)
    meta_path = _important_video_meta_path(path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(important_map, f, ensure_ascii=False, indent=2)


def is_video_important(filename: str, path: str = SAVE_DIR) -> bool:
    return bool(load_important_video_map(path).get(filename, False))


def set_video_important(filename: str, important: bool, path: str = SAVE_DIR) -> None:
    important_map = load_important_video_map(path)
    if important:
        important_map[filename] = True
    else:
        important_map.pop(filename, None)
    save_important_video_map(important_map, path)


def toggle_video_important(filename: str, path: str = SAVE_DIR) -> bool:
    important = not is_video_important(filename, path)
    set_video_important(filename, important, path)
    return important


def get_disk_usage(path: str = SAVE_DIR) -> dict:
    """
    디스크 사용량 확인
    
    Args:
        path: 확인할 경로
    
    Returns:
        {'total': total_bytes, 'used': used_bytes, 'free': free_bytes, 'percent': percent}
    """
    if not os.path.exists(path):
        return {'total': 0, 'used': 0, 'free': 0, 'percent': 0.0}

    usage = shutil.disk_usage(path)
    return {
        'total': usage.total,
        'used': usage.used,
        'free': usage.free,
        'percent': (usage.used / usage.total) * 100
    }


def get_directory_size(path: str = SAVE_DIR) -> int:
    """
    디렉토리 크기 계산 (바이트)
    
    Args:
        path: 디렉토리 경로
    
    Returns:
        총 크기 (bytes)
    """
    if not os.path.exists(path):
        return 0

    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def list_old_files(path: str = SAVE_DIR, limit: int = 10) -> List[tuple]:
    """
    오래된 파일 목록 반환
    
    Args:
        path: 디렉토리 경로
        limit: 반환할 파일 개수
    
    Returns:
        [(파일경로, 수정시간), ...] 리스트 (오래된 순)
    """
    if not os.path.exists(path):
        return []

    files = []
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            if not filename.lower().endswith(".mp4"):
                continue
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                mtime = os.path.getmtime(filepath)
                files.append((filepath, mtime))
    
    # 오래된 순 정렬
    files.sort(key=lambda x: x[1])
    return files[:limit]


def cleanup_old_files(path: str = SAVE_DIR, threshold_percent: float = 80.0) -> int:
    """
    디스크 용량이 임계값을 초과하면 오래된 파일 삭제
    
    Args:
        path: 디렉토리 경로
        threshold_percent: 임계값 (%)
    
    Returns:
        삭제된 파일 개수
    """
    if not os.path.exists(path):
        return 0

    usage = get_disk_usage(path)
    if usage['percent'] < threshold_percent:
        return 0
    
    deleted_count = 0
    important_map = load_important_video_map(path)
    old_files = list_old_files(path, limit=50)
    
    for filepath, mtime in old_files:
        filename = os.path.basename(filepath)
        if important_map.get(filename, False):
            continue
        try:
            os.remove(filepath)
            deleted_count += 1
            important_map.pop(filename, None)
            print(f"삭제됨: {filepath}")
            
            # 용량 재확인
            usage = get_disk_usage(path)
            if usage['percent'] < threshold_percent:
                break
        except Exception as e:
            print(f"삭제 실패: {filepath}, 오류: {e}")

    save_important_video_map(important_map, path)
    
    return deleted_count


def format_bytes(bytes_size: int) -> str:
    """바이트를 읽기 쉬운 형식으로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def format_save_dir(path: str = SAVE_DIR) -> int:
    """
    저장소(기본: SAVE_DIR) 내 모든 파일/폴더를 삭제합니다.

    Returns:
        삭제한 항목(파일+폴더) 수
    """
    deleted = 0
    if not os.path.exists(path):
        return 0
    for name in os.listdir(path):
        item = os.path.join(path, name)
        try:
            if os.path.isdir(item):
                shutil.rmtree(item)
                deleted += 1
            else:
                os.remove(item)
                deleted += 1
        except Exception:
            # 무시하고 계속 진행
            continue
    return deleted
