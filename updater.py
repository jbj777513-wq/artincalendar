"""
updater.py  -  GitHub Releases 기반 자동 업데이트 (EXE 환경 완전 대응)

[버전 관리 방식]
  - EXE 폴더의 version.txt 파일에서 현재 버전을 읽음
  - version.txt가 없으면 BASE_VERSION 상수를 사용
  - 업데이트 완료 시 배치 스크립트가 version.txt를 자동 갱신
  - 따라서 updater.py의 BASE_VERSION을 매번 올리지 않아도 됨

[배포 시 주의]
  GitHub에 올리는 zip은 반드시 EXE 빌드 결과물이어야 합니다.
  올바른 구조:
    아트인캘린더/
      아트인캘린더.exe
      _internal/
        ...
  이렇게 해야 업데이트 시 EXE 파일 자체가 교체됩니다.
"""

import sys
import os
import json
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path

try:
    import urllib.request as urlreq
except ImportError:
    urlreq = None

# ── 설정 ──────────────────────────────────────────────────────
BASE_VERSION = "1.0.0"   # version.txt 없을 때 fallback
GITHUB_OWNER = "jbj777513-wq"
GITHUB_REPO  = "artincalendar"
# ──────────────────────────────────────────────────────────────

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def _is_frozen():
    return getattr(sys, "frozen", False)


def _exe_path():
    if _is_frozen():
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def _app_dir():
    return _exe_path().parent


def _version_file():
    return _app_dir() / "version.txt"


def get_current_version():
    """
    현재 버전을 반환.
    EXE 폴더의 version.txt → 없으면 BASE_VERSION 사용.
    """
    vf = _version_file()
    if vf.exists():
        try:
            v = vf.read_text(encoding="utf-8").strip()
            if v:
                return v
        except Exception:
            pass
    return BASE_VERSION


# 모듈 수준 VERSION (import 시 한 번만 읽힘)
VERSION = get_current_version()


def _parse_version(tag):
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except Exception:
        return (0, 0, 0)


def check_update(timeout=8):
    if urlreq is None:
        return None
    try:
        current = get_current_version()

        req = urlreq.Request(API_URL, headers={"User-Agent": "ArtInCalendar-Updater"})
        with urlreq.urlopen(req, timeout=timeout) as resp:
            raw  = resp.read()
            data = json.loads(raw.decode())

        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            print(f"[Updater] tag_name 없음. API 응답: {list(data.keys())}")
            return None

        print(f"[Updater] 현재={current}, 최신={latest_tag}")

        if _parse_version(latest_tag) <= _parse_version(current):
            print(f"[Updater] 최신 버전 사용 중 ({current})")
            return None

        # zip asset 찾기
        dl_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            print(f"[Updater] asset: {name}")
            if name.endswith(".zip"):
                dl_url = asset.get("browser_download_url")
                break

        if not dl_url:
            print("[Updater] zip asset 없음. Releases에 zip 파일이 첨부되지 않았습니다.")
            return None

        return {
            "version"     : latest_tag,
            "download_url": dl_url,
            "notes"       : (data.get("body") or "")[:300],
        }
    except Exception as e:
        print(f"[Updater] check_update 오류: {e}")
        return None


def _find_exe_in_dir(directory):
    for f in Path(directory).iterdir():
        if f.suffix.lower() == ".exe" and f.is_file():
            return f
    return None


def download_and_install(download_url, on_progress=None, target_version=""):
    try:
        tmp      = tempfile.mkdtemp(prefix="aic_upd_")
        zip_path = os.path.join(tmp, "update.zip")

        # 1. 다운로드
        req = urlreq.Request(download_url, headers={"User-Agent": "ArtInCalendar-Updater"})
        with urlreq.urlopen(req, timeout=180) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            with open(zip_path, "wb") as f:
                while True:
                    buf = resp.read(32768)
                    if not buf:
                        break
                    f.write(buf)
                    done += len(buf)
                    if on_progress and total > 0:
                        on_progress(min(99, int(done / total * 100)))

        if on_progress:
            on_progress(100)

        # 2. 압축 해제
        extract_root = os.path.join(tmp, "extracted")
        os.makedirs(extract_root, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_root)

        # 3. EXE가 있는 실제 폴더 찾기
        extract_dir = extract_root
        if _is_frozen():
            top_items = list(Path(extract_root).iterdir())
            if len(top_items) == 1 and top_items[0].is_dir():
                candidate = top_items[0]
                if _find_exe_in_dir(candidate):
                    extract_dir = str(candidate)

            if not _find_exe_in_dir(extract_dir):
                print("[Updater] zip 안에 EXE 파일이 없습니다. EXE 빌드 결과물을 zip으로 올려주세요.")
                return False

        # 4. 교체 실행
        if _is_frozen():
            _schedule_exe_update(tmp, extract_dir, target_version)
        else:
            _apply_files_directly(extract_dir, target_version)

        return True

    except Exception as e:
        print(f"[Updater] 오류: {e}")
        return False


def _apply_files_directly(extract_dir, target_version=""):
    app_dir = _app_dir()
    for item in Path(extract_dir).iterdir():
        dst = app_dir / item.name
        try:
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(str(item), str(dst))
            else:
                shutil.copy2(str(item), str(dst))
        except Exception as e:
            print(f"[Updater] 파일 교체 실패 {item.name}: {e}")
    # version.txt 갱신
    if target_version:
        try:
            _version_file().write_text(
                target_version.lstrip("v"), encoding="utf-8")
        except Exception:
            pass


def _schedule_exe_update(tmp_dir, extract_dir, target_version=""):
    exe_path    = str(_exe_path())
    app_dir     = str(_app_dir())
    current_pid = os.getpid()
    ver_clean   = target_version.lstrip("v")
    ver_file    = str(_version_file())

    # 배치 스크립트
    bat_path = os.path.join(tmp_dir, "apply.bat")
    lines = [
        "@echo off",
        "chcp 65001 > nul",
        "",
        ":: 현재 EXE 종료 대기",
        ":waitloop",
        f'tasklist /FI "PID eq {current_pid}" /NH 2>nul | findstr "{current_pid}" >nul',
        "if not errorlevel 1 (",
        "    timeout /t 1 /nobreak > nul",
        "    goto waitloop",
        ")",
        "",
        ":: 1초 추가 대기",
        "timeout /t 1 /nobreak > nul",
        "",
        ":: 새 버전 파일 복사",
        f'robocopy "{extract_dir}" "{app_dir}" /E /IS /IT /IM /NFL /NDL /NJH /NJS > nul 2>&1',
        "",
        ":: version.txt 갱신 (핵심: 다음 실행 시 최신 버전으로 인식)",
        f'echo {ver_clean}> "{ver_file}"',
        "",
        ":: 재시작",
        f'start "" "{exe_path}"',
        "",
        'del "%~f0" > nul 2>&1',
    ]

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

    # VBScript로 배치 실행 (창 없이 백그라운드)
    vbs_path = os.path.join(tmp_dir, "run.vbs")
    bat_path_vbs = _path_to_vbs_chr(bat_path)
    vbs_lines = [
        'Set sh = CreateObject("WScript.Shell")',
        f'sh.Run "cmd /c """ & {bat_path_vbs} & """", 0, False',
    ]
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(vbs_lines))

    subprocess.Popen(["wscript.exe", vbs_path], close_fds=True)


def _path_to_vbs_chr(path):
    return "&".join(f"Chr({ord(c)})" for c in path)


def restart_app():
    os._exit(0)
