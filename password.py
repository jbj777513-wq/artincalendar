"""
password.py  -  아트인캘린더 비밀번호 관리

[관리자 사용법]
  1. artincalendar 폴더 안에 password.txt 파일 생성
  2. 첫 번째 줄에 비밀번호를 평문으로 입력 (예: mypassword123)
  3. 저장 후 pyinstaller로 재빌드
  4. GitHub에 새 버전 릴리스 → 사용자 자동 업데이트 시 적용

[동작 방식]
  - password.txt의 평문 비밀번호를 SHA-256 해시로 변환해서 비교
  - 평문이 그대로 EXE에 포함되지 않아 보안 향상
  - password.txt가 없으면 비밀번호 없이 실행 가능
"""

import hashlib
from pathlib import Path


def _pw_file():
    return Path(__file__).parent / "password.txt"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_password_hash() -> str:
    """
    password.txt의 비밀번호를 SHA-256 해시로 반환.
    파일이 없으면 빈 문자열 반환 (비밀번호 없음).
    """
    pf = _pw_file()
    if not pf.exists():
        return ""
    try:
        pw = pf.read_text(encoding="utf-8").strip()
        if not pw:
            return ""
        return _hash(pw)
    except Exception:
        return ""


def check_password(input_text: str) -> bool:
    """입력한 비밀번호가 맞는지 확인"""
    stored = get_password_hash()
    if not stored:
        return True   # 비밀번호 없으면 항상 통과
    return _hash(input_text) == stored


def password_required() -> bool:
    """비밀번호 설정 여부"""
    return bool(get_password_hash())
