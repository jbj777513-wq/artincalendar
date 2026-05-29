"""
updater.py
GitHub Releases 기반 자동 업데이트 모듈

동작 방식:
  1. GitHub API로 최신 릴리스 태그 확인
  2. 현재 버전(VERSION)과 비교
  3. 새 버전이 있으면 zip 다운로드 → 압축 해제 → 재시작

설정 방법:
  GITHUB_OWNER = "your-github-username"
  GITHUB_REPO  = "artincalendar"
  로 변경 후 GitHub에 릴리스를 올리면 됩니다.
  릴리스의 Assets에 artincalendar_vX.X.X.zip 파일을 첨부하세요.
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
    import urllib.error   as urlerr
except ImportError:
    urlreq = None

# ── 설정 ─────────────────────────────────────────────────────
VERSION      = "1.0.1"          # 현재 버전 (릴리스 태그와 동일하게 관리)
GITHUB_OWNER = "jbj777513-wq" # ← GitHub 사용자명으로 변경
GITHUB_REPO  = "artincalendar"  # ← GitHub 저장소 이름으로 변경
# ─────────────────────────────────────────────────────────────

API_URL      = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
APP_DIR      = Path(__file__).parent.resolve()


def _parse_version(tag: str):
    """'v1.2.3' 또는 '1.2.3' → (1,2,3) 튜플"""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except Exception:
        return (0, 0, 0)


def check_update(timeout: int = 5):
    """
    최신 버전 정보를 반환합니다.
    Returns:
        None               — 업데이트 없음 또는 확인 불가
        dict               — {"version": str, "download_url": str, "notes": str}
    """
    if urlreq is None:
        return None
    try:
        req  = urlreq.Request(API_URL, headers={"User-Agent": "ArtInCalendar-Updater"})
        with urlreq.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            return None

        if _parse_version(latest_tag) <= _parse_version(VERSION):
            return None   # 이미 최신

        # zip asset 찾기
        dl_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip"):
                dl_url = asset.get("browser_download_url")
                break

        if not dl_url:
            return None

        return {
            "version"     : latest_tag,
            "download_url": dl_url,
            "notes"       : data.get("body", "")[:300],
        }
    except Exception:
        return None


def download_and_install(download_url: str, on_progress=None):
    """
    zip을 다운로드해 현재 디렉토리에 덮어씁니다.
    on_progress(percent: int) 콜백 (0~100)
    Returns:
        True  — 성공
        False — 실패
    """
    try:
        tmp = tempfile.mkdtemp(prefix="aic_update_")
        zip_path = os.path.join(tmp, "update.zip")

        # 다운로드
        req = urlreq.Request(download_url, headers={"User-Agent": "ArtInCalendar-Updater"})
        with urlreq.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            chunk = 8192
            with open(zip_path, "wb") as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    done += len(buf)
                    if on_progress and total > 0:
                        on_progress(int(done / total * 100))

        # 압축 해제 → 현재 디렉토리에 덮어쓰기
        with zipfile.ZipFile(zip_path, "r") as z:
            members = z.namelist()
            # 최상위 폴더 접두어 제거 (artincalendar/ → ./)
            prefix = ""
            if members and members[0].endswith("/"):
                prefix = members[0]

            for member in members:
                if member == prefix:
                    continue
                rel = member[len(prefix):] if prefix else member
                if not rel:
                    continue
                target = APP_DIR / rel
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        shutil.rmtree(tmp, ignore_errors=True)
        return True
    except Exception as e:
        print(f"[Updater] 오류: {e}")
        return False


def restart_app():
    """업데이트 후 앱을 재시작합니다."""
    python = sys.executable
    main   = str(APP_DIR / "main.py")
    subprocess.Popen([python, main])
    sys.exit(0)
