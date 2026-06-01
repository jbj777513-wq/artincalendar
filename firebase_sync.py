"""
firebase_sync.py
Firebase Realtime Database와 실시간 동기화를 담당합니다.
pyrebase4 라이브러리 사용 (pip install pyrebase4)
"""

import threading
import json


class FirebaseSync:
    def __init__(self, config: dict, on_update_callback):
        """
        config: {
            "url": "https://your-project.firebaseio.com",
            "group_id": "myteam2024"
        }
        on_update_callback: 원격 데이터 변경 시 호출되는 함수(events_dict)
        """
        self.config = config
        self.on_update = on_update_callback
        self.db = None
        self._stream = None
        self._path = f"calendars/{config['group_id']}/events"
        self._init_firebase()

    def _init_firebase(self):
        try:
            import pyrebase
            firebase_config = {
                "apiKey": "AIzaSyDummyKeyForAnonAccess",   # 익명 접근용
                "authDomain": "",
                "databaseURL": self.config["url"],
                "storageBucket": "",
            }
            fb = pyrebase.initialize_app(firebase_config)
            self.db = fb.database()
        except ImportError:
            raise ImportError("pyrebase4가 설치되지 않았습니다. pip install pyrebase4")
        except Exception as e:
            raise RuntimeError(f"Firebase 초기화 실패: {e}")

    def start(self):
        """실시간 리스너 시작 (백그라운드 스레드)"""
        if not self.db:
            return
        try:
            self._stream = self.db.child(self._path).stream(
                self._stream_handler
            )
        except Exception as e:
            print(f"[Firebase] 스트림 시작 실패: {e}")

    def _stream_handler(self, message):
        """Firebase 실시간 업데이트 수신"""
        if message.get("data") and message["event"] in ("put", "patch"):
            data = message["data"]
            if isinstance(data, dict):
                self.on_update(data)
            elif data is None:
                self.on_update({})

    def push_events(self, events: dict):
        """로컬 이벤트 → Firebase 업로드"""
        if not self.db:
            return
        def _push():
            try:
                self.db.child(self._path).set(events)
            except Exception as e:
                print(f"[Firebase] 업로드 실패: {e}")
        threading.Thread(target=_push, daemon=True).start()

    def stop(self):
        if self._stream:
            try:
                self._stream.close()
            except Exception:
                pass
