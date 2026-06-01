# 아트인캘린더 — EXE 빌드 & 배포 가이드

---

## ✅ EXE 빌드 방법 (Windows에서 실행)

### 1단계: 필요 라이브러리 설치
```
pip install pyinstaller PyQt5 requests
```

### 2단계: 빌드 실행
artincalendar 폴더 안에서 실행:
```
cd artincalendar
pyinstaller artincalendar.spec
```

### 3단계: EXE 파일 위치 확인
빌드 완료 후 아래 경로에 생성됩니다:

```
artincalendar/
└── dist/
    └── 아트인캘린더/          ← 이 폴더 전체를 배포
        ├── 아트인캘린더.exe   ← 실행 파일 (더블클릭으로 실행)
        ├── _internal/         ← 필수 라이브러리 (건드리지 말 것)
        └── ...
```

> ⚠️ **주의:** `아트인캘린더.exe` 파일만 따로 보내면 안 됩니다.
> `dist/아트인캘린더/` 폴더 전체를 zip으로 묶어서 배포하세요.
> 받는 사람은 압축 해제 후 `아트인캘린더.exe`를 실행하면 됩니다.

---

## 🔄 자동 업데이트 설정 (GitHub 사용)

### 1단계: GitHub 저장소 만들기
1. https://github.com 에서 새 저장소 생성 (예: `artincalendar`)
2. `updater.py` 파일을 열어서 아래 두 줄 수정:
   ```python
   GITHUB_OWNER = "your-github-id"   # ← 본인의 GitHub 사용자명
   GITHUB_REPO  = "artincalendar"    # ← 저장소 이름
   ```

### 2단계: 새 버전 배포하기
1. `updater.py`의 `VERSION`을 올린다 (예: `"1.0.0"` → `"1.1.0"`)
2. EXE 빌드 → `dist/아트인캘린더/` 폴더를 zip으로 압축
3. GitHub → 저장소 → **Releases** → **Draft a new release**
4. 태그명: 버전과 동일하게 (예: `v1.1.0`)
5. zip 파일을 **Assets에 첨부** → **Publish release**

### 앱 동작 방식
- 실행 2초 후 자동으로 GitHub에서 최신 버전 확인
- 새 버전이 있으면 업데이트 팝업 표시
- "지금 업데이트" 클릭 → 자동 다운로드 → 앱 재시작

---

## 🔥 Firebase 공유 설정 방법

1. https://console.firebase.google.com 접속 (구글 계정 로그인)
2. **프로젝트 만들기** → 이름 입력 → 생성
3. 왼쪽 메뉴: **빌드 → Realtime Database → 데이터베이스 만들기**
4. **테스트 모드로 시작** 선택 → 완료
5. DB URL 복사: `https://프로젝트명-default-rtdb.firebaseio.com`
6. 캘린더 **⚙ 설정** 열기 → Firebase URL + 그룹ID 입력 → 저장
7. 팀원 모두 **동일한 그룹ID** 입력 → 실시간 공유 시작

### ⚠️ 30일 후 보안 규칙 갱신 필요
Firebase 콘솔 → Realtime Database → **규칙** 탭에 아래 내용 붙여넣고 게시:
```json
{
  "rules": {
    "calendars": {
      "$group_id": {
        ".read": true,
        ".write": true
      }
    }
  }
}
```
