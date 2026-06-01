# 🎨 아트인캘린더 (ArtInCalendar)

Windows 바탕화면 위에 떠 있는 반투명 일정 공유 캘린더입니다.

---

## 📦 설치 방법

### 1. Python 설치 (없는 경우)
https://www.python.org/downloads/ 에서 Python 3.9 이상 설치

### 2. 라이브러리 설치
```
pip install -r requirements.txt
```

### 3. 실행
```
python main.py
```

---

## 🖥️ 기능

| 기능 | 설명 |
|------|------|
| 바탕화면 오버레이 | 항상 최상위에 표시, 반투명 |
| 드래그 이동 | 원하는 위치로 자유롭게 이동 |
| 일정 추가/삭제 | 날짜 클릭 → 일정 관리 |
| 색상 지정 | 일정마다 다른 색상 지정 가능 |
| 실시간 공유 | Firebase 연동 시 팀원과 실시간 공유 |
| 로컬 저장 | Firebase 없이도 내 PC에 저장 |
| 투명도 조절 | 설정에서 투명도 조절 가능 |
| 시스템 트레이 | 트레이 아이콘으로 숨기기/보이기 |

---

## 🔗 팀 공유 설정 (Firebase)

### 1. Firebase 프로젝트 생성 (무료)
1. https://console.firebase.google.com 접속
2. "프로젝트 추가" 클릭
3. 프로젝트 이름 입력 후 생성

### 2. Realtime Database 활성화
1. 좌측 메뉴 → "Realtime Database"
2. "데이터베이스 만들기" 클릭
3. **테스트 모드**로 시작 (30일 무료 공개 읽기/쓰기)
4. 데이터베이스 URL 복사: `https://your-project-default-rtdb.firebaseio.com`

### 3. 아트인캘린더 설정
- 캘린더 우측 하단 ⚙ 버튼 클릭
- Firebase URL 입력
- **그룹 ID** 입력 (팀원 모두 동일하게!)
- 저장

### 4. 팀원 PC에도 동일하게 설치 후
- 같은 **그룹 ID** 입력하면 자동 공유됩니다! ✅

---

## 💡 사용 팁

- **드래그**: 캘린더 빈 공간을 드래그해서 이동
- **숨기기**: 우측 상단 × 버튼 또는 트레이 아이콘 더블클릭
- **완전 종료**: 트레이 아이콘 우클릭 → 종료

---

## 🔒 보안 참고사항

Firebase 테스트 모드는 30일 후 읽기/쓰기가 제한됩니다.
이후 계속 사용하려면 Firebase 콘솔에서 규칙을 업데이트하세요:

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
