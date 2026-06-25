"""
Force-release camera device owners.

Usage:
    python3 system/release_cameras.py
    python3 system/release_cameras.py --all --stop-app --kill
    python3 system/release_cameras.py --indices 0 2 4 6 --kill
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import CAMERA_INDICES
from system.camera_resources import (
    find_camera_device_owners,
    find_project_processes,
    release_camera_devices,
    release_processes,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release processes holding /dev/video camera devices.")
    parser.add_argument(
        "--indices",
        nargs="+",
        type=int,
        default=None,
        help=f"Camera indices to release. Default: settings.CAMERA_INDICES plus existing /dev/video* ({CAMERA_INDICES})",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan every existing /dev/video* device.",
    )
    parser.add_argument(
        "--stop-app",
        action="store_true",
        help="Stop this project's main.py/watchdog.py before releasing camera devices.",
    )
    parser.add_argument(
        "--process-groups",
        action="store_true",
        help="Terminate owner process groups instead of only individual PIDs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Seconds to wait after SIGTERM before checking again.",
    )
    parser.add_argument(
        "--kill",
        action="store_true",
        help="Send SIGKILL to remaining owners after timeout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print processes holding camera devices.",
    )
    return parser.parse_args()


def _print_owners(label: str, owners) -> None:
    if not owners:
        print(f"{label}: 카메라 장치 점유 프로세스 없음")
        return

    print(label)
    for owner in owners:
        suffix = f"  cmd={owner.command}" if getattr(owner, "command", "") else ""
        print(f"  {owner.device}: pid={owner.pid}{suffix}")


def _print_processes(label: str, processes) -> None:
    if not processes:
        print(f"{label}: 대상 프로세스 없음")
        return

    print(label)
    for process in processes:
        print(f"  pid={process.pid} pgid={process.pgid} cmd={process.command}")


def main() -> int:
    args = _parse_args()
    indices: Optional[List[int]] = args.indices

    project_processes = find_project_processes()
    if args.stop_app or args.dry_run:
        _print_processes("프로젝트 실행 프로세스", project_processes)

    before = find_camera_device_owners(indices=indices, all_video=args.all)
    _print_owners("현재 점유 프로세스", before)
    if args.dry_run:
        return 0

    if args.stop_app and project_processes:
        release_processes(
            project_processes,
            timeout_sec=args.timeout,
            kill_after_timeout=args.kill,
            process_groups=True,
        )

    if not before and not args.stop_app:
        return 0

    release_camera_devices(
        indices=indices,
        timeout_sec=args.timeout,
        kill_after_timeout=args.kill,
        all_video=args.all,
        process_groups=args.process_groups,
    )

    after = find_camera_device_owners(indices=indices, all_video=args.all)
    _print_owners("해제 시도 후 남은 프로세스", after)
    if args.stop_app:
        _print_processes("해제 시도 후 남은 프로젝트 프로세스", find_project_processes())
    if after:
        print(
            "일부 프로세스가 남았습니다. sudo 또는 --all --stop-app --process-groups --kill 조합으로 다시 실행하세요.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
