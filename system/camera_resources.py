"""
Camera device ownership helpers.

Linux에서 /dev/videoN을 점유 중인 프로세스를 찾아 종료 신호를 보낼 때 사용한다.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from glob import glob
from typing import Dict, List, Optional, Sequence, Set

from config.settings import CAMERA_INDICES, PROJECT_ROOT


@dataclass(frozen=True)
class CameraDeviceOwner:
    device: str
    pid: int
    command: str = ""


@dataclass(frozen=True)
class ProcessOwner:
    pid: int
    pgid: int
    command: str


def camera_device_paths(indices: Optional[Sequence[int]] = None, all_video: bool = False) -> List[str]:
    if all_video:
        paths = sorted(glob("/dev/video*"))
        if paths:
            return paths

    selected = CAMERA_INDICES if indices is None else list(indices)
    paths = [f"/dev/video{idx}" for idx in selected]
    paths.extend(path for path in sorted(glob("/dev/video*")) if path not in paths)
    return paths


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(list(args), 127, "", "")


def _parse_pids(text: str) -> Set[int]:
    pids: Set[int] = set()
    for match in re.finditer(r"\b(\d+)[A-Za-z]*\b", text):
        try:
            pids.add(int(match.group(1)))
        except ValueError:
            pass
    return pids


def _read_cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read().replace(b"\x00", b" ").strip()
        return raw.decode(errors="replace")
    except OSError:
        return ""


def _scan_proc_fd_owners(devices: Sequence[str]) -> Dict[str, Set[int]]:
    owners: Dict[str, Set[int]] = {device: set() for device in devices}
    device_realpaths = {device: os.path.realpath(device) for device in devices}

    for proc_path in glob("/proc/[0-9]*"):
        try:
            pid = int(os.path.basename(proc_path))
        except ValueError:
            continue

        fd_dir = os.path.join(proc_path, "fd")
        try:
            fd_names = os.listdir(fd_dir)
        except OSError:
            continue

        for fd_name in fd_names:
            fd_path = os.path.join(fd_dir, fd_name)
            try:
                target = os.path.realpath(os.readlink(fd_path))
            except OSError:
                continue

            for device, realpath in device_realpaths.items():
                if target == device or target == realpath:
                    owners[device].add(pid)

    return owners


def find_camera_device_owners(
    indices: Optional[Sequence[int]] = None,
    all_video: bool = False,
    include_self: bool = False,
) -> List[CameraDeviceOwner]:
    owners: List[CameraDeviceOwner] = []
    self_pid = os.getpid()
    devices = [device for device in camera_device_paths(indices, all_video=all_video) if os.path.exists(device)]
    proc_owners = _scan_proc_fd_owners(devices)

    for device in devices:
        pids: Set[int] = set()
        fuser = _run_command(["fuser", device])
        pids.update(_parse_pids(fuser.stdout))

        if not pids:
            lsof = _run_command(["lsof", "-t", device])
            pids.update(_parse_pids(lsof.stdout))

        pids.update(proc_owners.get(device, set()))

        for pid in sorted(pids):
            if pid == self_pid and not include_self:
                continue
            owners.append(CameraDeviceOwner(device=device, pid=pid, command=_read_cmdline(pid)))

    return owners


def find_project_processes(include_self: bool = False) -> List[ProcessOwner]:
    """현재 프로젝트의 main/watchdog 프로세스를 찾는다."""
    self_pid = os.getpid()
    project_root = os.path.realpath(PROJECT_ROOT)
    targets: List[ProcessOwner] = []

    for proc_path in glob("/proc/[0-9]*"):
        try:
            pid = int(os.path.basename(proc_path))
        except ValueError:
            continue
        if pid == self_pid and not include_self:
            continue

        command = _read_cmdline(pid)
        if not command:
            continue
        if "main.py" not in command and "system/watchdog.py" not in command and "watchdog.py" not in command:
            continue

        try:
            cwd = os.path.realpath(os.readlink(os.path.join(proc_path, "cwd")))
        except OSError:
            cwd = ""
        if cwd and cwd != project_root:
            continue

        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = pid
        targets.append(ProcessOwner(pid=pid, pgid=pgid, command=command))

    return sorted(targets, key=lambda item: item.pid)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def release_camera_devices(
    indices: Optional[Sequence[int]] = None,
    timeout_sec: float = 3.0,
    kill_after_timeout: bool = False,
    all_video: bool = False,
    include_self: bool = False,
    process_groups: bool = False,
) -> List[CameraDeviceOwner]:
    """카메라 장치 점유 프로세스에 종료 신호를 보내고 대상 목록을 반환한다."""
    owners = find_camera_device_owners(indices=indices, all_video=all_video, include_self=include_self)
    pids = sorted({owner.pid for owner in owners})
    own_pgid = os.getpgrp()

    for pid in pids:
        try:
            pgid = os.getpgid(pid)
            if process_groups and pgid != own_pgid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass

    deadline = time.time() + max(0.0, timeout_sec)
    while time.time() < deadline:
        if not any(_pid_exists(pid) for pid in pids):
            return owners
        time.sleep(0.1)

    if kill_after_timeout:
        for pid in pids:
            if not _pid_exists(pid):
                continue
            try:
                pgid = os.getpgid(pid)
                if process_groups and pgid != own_pgid:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass

    return owners


def release_processes(
    processes: Sequence[ProcessOwner],
    timeout_sec: float = 3.0,
    kill_after_timeout: bool = False,
    process_groups: bool = True,
) -> None:
    seen: Set[int] = set()
    own_pgid = os.getpgrp()
    for process in processes:
        use_group = process_groups and process.pgid != own_pgid
        target = process.pgid if use_group else process.pid
        if target in seen:
            continue
        seen.add(target)
        try:
            if use_group:
                os.killpg(target, signal.SIGTERM)
            else:
                os.kill(target, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.time() + max(0.0, timeout_sec)
    pids = [process.pid for process in processes]
    while time.time() < deadline:
        if not any(_pid_exists(pid) for pid in pids):
            return
        time.sleep(0.1)

    if not kill_after_timeout:
        return

    seen.clear()
    for process in processes:
        if not _pid_exists(process.pid):
            continue
        use_group = process_groups and process.pgid != own_pgid
        target = process.pgid if use_group else process.pid
        if target in seen:
            continue
        seen.add(target)
        try:
            if use_group:
                os.killpg(target, signal.SIGKILL)
            else:
                os.kill(target, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
