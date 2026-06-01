import sys
import os
import json
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QDialog, QLineEdit,
    QTextEdit, QColorDialog, QSystemTrayIcon, QMenu, QAction,
    QFrame, QScrollArea, QTimeEdit, QSlider, QDateEdit, QGroupBox,
    QCheckBox, QProgressBar, QMessageBox, QRadioButton, QButtonGroup,
    QSizePolicy, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QDate, QTime, QThread, QByteArray
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QIcon, QPixmap, QFontMetrics
from PyQt5.QtSvg import QSvgRenderer

from firebase_sync import FirebaseSync
from config import load_config, save_config
from updater import VERSION, get_current_version, check_update, download_and_install, restart_app
from password import check_password, password_required

# ── 프리텐다드 폰트 등록 ──────────────────────────────────────
def _register_pretendard():
    from PyQt5.QtGui import QFontDatabase
    base = Path(__file__).parent / "fonts"
    weights = [
        "Pretendard-Regular.ttf",
        "Pretendard-Medium.ttf",
        "Pretendard-SemiBold.ttf",
        "Pretendard-Bold.ttf",
        "Pretendard-Light.ttf",
    ]
    for w in weights:
        fp = base / w
        if fp.exists():
            QFontDatabase.addApplicationFont(str(fp))


class Signals(QObject):
    events_updated = pyqtSignal()

signals = Signals()


# ════════════════════════════════════════════════════════════
#  잠금 오버레이  ─  헤더 바 아래 전체를 덮어 클릭 차단
# ════════════════════════════════════════════════════════════
class LockOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 50))
        p.end()

    def mousePressEvent(self, e):   e.accept()
    def mouseReleaseEvent(self, e): e.accept()
    def mouseMoveEvent(self, e):    e.accept()


# ════════════════════════════════════════════════════════════
#  메인 윈도우
# ════════════════════════════════════════════════════════════
class ArtInCalendar(QMainWindow):
    HEADER_H = 40   # 상단 바 높이 (px)

    def __init__(self):
        super().__init__()
        self.config        = load_config()
        self.events        = {}
        self.selected_date = date.today()
        self.current_year  = date.today().year
        self.current_month = date.today().month
        self._drag_pos     = None
        self.locked        = False

        self._setup_window()
        self._setup_tray()
        self._build_ui()
        self._setup_firebase()

        signals.events_updated.connect(self._refresh_calendar)
        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(60000)

    # ── 윈도우 ───────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle("아트인캘린더")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        pos = self.config.get("position", {"x": 50, "y": 50})
        w   = self.config.get("cal_width",  900)
        h   = self.config.get("cal_height", 750)
        self.setGeometry(pos["x"], pos["y"], w, h)
        self.setWindowOpacity(self.config.get("opacity", 0.70))

    # ── 트레이 ───────────────────────────────────────────────
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        # 트레이 아이콘도 로고 이미지 사용
        _logo_path = Path(__file__).parent / "logo_white.png"
        if _logo_path.exists():
            _tray_pix = QPixmap(str(_logo_path)).scaled(
                16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.tray.setIcon(QIcon(_tray_pix))
        else:
            pix = QPixmap(16, 16); pix.fill(QColor("#6C63FF"))
            self.tray.setIcon(QIcon(pix))
        self.tray.setToolTip("아트인캘린더")
        menu = QMenu()
        menu.addAction("보이기/숨기기",    self._toggle_visibility)
        menu.addAction("캘린더만 보이기",  self._show_only_calendar)
        menu.addAction("설정",             self._open_settings)
        menu.addSeparator()
        menu.addAction("종료",             self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._toggle_visibility() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    # ── UI 구성 ───────────────────────────────────────────────
    def _build_ui(self):
        theme = self.config.get("color_theme", "black")

        # 테마별 색상 결정
        if theme == "white":
            bg  = f"rgba(255,255,255,{self.config.get('opacity',0.70):.2f})"
            acc = "#cccccc"
            tc  = "#111111"   # 글씨색
        elif theme == "black":
            bg  = f"rgba(20,20,20,{self.config.get('opacity',0.70):.2f})"
            acc = "#444444"
            tc  = "#ffffff"
        else:  # custom
            bg  = self.config.get("bg_color",    "rgba(45,45,45,0.70)")
            acc = self.config.get("accent_color", "#333333")
            tc  = self.config.get("text_color",  "#ffffff")

        self._tc = tc   # 글씨색 전역 저장 (DayButton 등에서 참조)

        # ── 최상위 컨테이너 ──────────────────────────────────
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet(f"""
            #container {{
                background: {bg};
                border-radius: 20px;
                border: 1px solid {acc}55;
            }}
        """)
        self.setCentralWidget(container)
        self._container = container  # overlay 부모 참조용

        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        # ════════════════════════════════════════════════════
        #  상단 헤더 바  (항상 클릭 가능 영역)
        # ════════════════════════════════════════════════════
        self.header_bar = QWidget()
        self.header_bar.setObjectName("header_bar")
        self.header_bar.setFixedHeight(self.HEADER_H)
        self.header_bar.setStyleSheet(f"""
            #header_bar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {acc}55,
                    stop:1 {acc}22
                );
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                border-bottom: 1px solid {acc}66;
            }}
        """)

        hdr_layout = QHBoxLayout(self.header_bar)
        hdr_layout.setContentsMargins(16, 0, 12, 0)
        hdr_layout.setSpacing(6)
        hdr_layout.setAlignment(Qt.AlignBottom)   # ← 아랫 정렬

        # 날짜/시계
        self.clock_label = QLabel(self._clock_text())
        self.clock_label.setStyleSheet(
            f"color:{tc}; opacity:0.6; font-size:{self._fs(11)}px; padding-bottom:6px;")

        # 로고 + 타이틀
        title_widget = QWidget(); title_widget.setStyleSheet("background:transparent;")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)

        logo_lbl = QLabel()
        logo_lbl.setAttribute(Qt.WA_TranslucentBackground)
        logo_path = Path(__file__).parent / "logo_white.png"
        if logo_path.exists():
            logo_pix = QPixmap(str(logo_path)).scaled(
                32, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(logo_pix)
        logo_lbl.setStyleSheet("background:transparent; padding-bottom:6px;")

        title_lbl = QLabel("아트인캘린더")
        title_lbl.setStyleSheet(
            f"color:{tc}; font-size:{self._fs(16)}px; font-weight:bold;"
            f" font-family:'Pretendard'; padding-bottom:6px;")

        title_layout.addWidget(logo_lbl)
        title_layout.addWidget(title_lbl)

        # 잠금 버튼
        self.btn_lock = QPushButton("🔓")
        self.btn_lock.setFixedSize(30, 30)
        self.btn_lock.setStyleSheet(self._lock_style(False))
        self.btn_lock.clicked.connect(self._toggle_lock)
        # 아랫정렬용 마진
        self.btn_lock.setContentsMargins(0, 0, 0, 6)

        # 설정 버튼
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setStyleSheet(f"""
            QPushButton {{ background:rgba(255,255,255,0.10); color:rgba(255,255,255,0.7);
                border-radius:15px; border:1px solid rgba(255,255,255,0.2); font-size:15px; }}
            QPushButton:hover {{ background:rgba(255,255,255,0.25); color:white; }}
        """)
        self.btn_settings.clicked.connect(self._open_settings)

        # 최소화 버튼 (− 텍스트)
        self.btn_minimize = QPushButton("−")
        self.btn_minimize.setFixedSize(30, 30)
        self.btn_minimize.setStyleSheet("""
            QPushButton { background:rgba(255,255,255,0.10); color:rgba(255,255,255,0.8);
                border-radius:15px; border:1px solid rgba(255,255,255,0.2);
                font-size:18px; font-weight:bold; }
            QPushButton:hover { background:rgba(255,255,255,0.28); color:white; }
        """)
        self.btn_minimize.clicked.connect(self._minimize)

        # 닫기 버튼
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setStyleSheet("""
            QPushButton { background:rgba(255,80,80,0.3); color:#ff8080;
                border-radius:15px; font-size:17px; border:none; }
            QPushButton:hover { background:rgba(255,80,80,0.65); color:white; }
        """)
        self.btn_close.clicked.connect(self._quit_app)

        hdr_layout.addWidget(self.clock_label, 0, Qt.AlignBottom)
        hdr_layout.addStretch()
        hdr_layout.addWidget(title_widget, 0, Qt.AlignBottom)
        hdr_layout.addStretch()
        hdr_layout.addWidget(self.btn_lock,     0, Qt.AlignBottom)
        hdr_layout.addWidget(self.btn_settings, 0, Qt.AlignBottom)
        hdr_layout.addWidget(self.btn_minimize, 0, Qt.AlignBottom)
        hdr_layout.addWidget(self.btn_close,    0, Qt.AlignBottom)

        root.addWidget(self.header_bar)

        # ════════════════════════════════════════════════════
        #  본문 영역 (잠금 오버레이가 이 아래만 덮음)
        # ════════════════════════════════════════════════════
        self.body_widget = QWidget()
        self.body_widget.setObjectName("body_widget")
        self.body_widget.setStyleSheet("background:transparent;")
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(14, 8, 14, 4)
        body_layout.setSpacing(6)

        # 월 네비게이션
        nav = QHBoxLayout()
        self.btn_prev  = self._nav_btn("◀"); self.btn_prev.clicked.connect(self._prev_month)
        self.btn_next  = self._nav_btn("▶"); self.btn_next.clicked.connect(self._next_month)
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setStyleSheet(
            f"color:{tc}; font-size:{self._fs(15)}px; font-weight:bold;")

        nav.addWidget(self.btn_prev); nav.addStretch()
        nav.addWidget(self.month_label); nav.addStretch()
        nav.addWidget(self.btn_next)
        body_layout.addLayout(nav)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background:{acc}33; max-height:1px;")
        body_layout.addWidget(sep)

        # 요일 헤더
        drow = QHBoxLayout(); drow.setSpacing(3)
        for d in ["일","월","화","수","목","금","토"]:
            if d == "일":   dc = "#ff6666"
            elif d == "토": dc = "#6699ff"
            else:           dc = tc
            l = QLabel(d); l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet(f"color:{dc}; font-size:{self._fs(11)}px; font-weight:bold;")
            drow.addWidget(l)
        body_layout.addLayout(drow)

        # 날짜 그리드
        self.grid = QGridLayout()
        self.grid.setSpacing(0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        body_layout.addLayout(self.grid)

        # 하단 상태바
        bot = QHBoxLayout()
        self.status_label = QLabel("● 연결 안됨")
        self.status_label.setStyleSheet(
            f"color:rgba(255,255,255,0.28); font-size:{self._fs(9)}px;")
        self.lock_hint = QLabel("")
        self.lock_hint.setStyleSheet(
            f"color:rgba(255,200,60,0.9); font-size:{self._fs(10)}px; font-weight:bold;")
        bot.addWidget(self.status_label)
        bot.addSpacing(8)
        bot.addWidget(self.lock_hint)
        bot.addStretch()
        body_layout.addLayout(bot)

        root.addWidget(self.body_widget)

        # ── 잠금 오버레이: container 전체에서 헤더 아래 영역을 덮음 ──
        # body_widget 크기가 레이아웃에 의존하므로 container 기준으로 직접 계산
        self.overlay = LockOverlay(container)

        # 창 크기를 config 값으로 고정 (레이아웃에 의한 크기 변동 방지)
        w = self.config.get("cal_width",  900)
        h = self.config.get("cal_height", 750)
        self.setFixedSize(w, h)

        self._refresh_calendar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "overlay") and hasattr(self, "body_widget"):
            self._update_overlay_geometry()

    def _update_overlay_geometry(self):
        """헤더 아래 전체 영역(하단 포함)을 오버레이로 덮기"""
        if not hasattr(self, "overlay") or not hasattr(self, "_container"):
            return
        top    = self.HEADER_H
        rect_w = self._container.width()
        rect_h = self._container.height() - top
        self.overlay.setGeometry(0, top, rect_w, rect_h)

    # ── 잠금 토글 ─────────────────────────────────────────────
    def _toggle_lock(self):
        self.locked = not self.locked
        self.btn_lock.setText("🔒" if self.locked else "🔓")
        self.btn_lock.setStyleSheet(self._lock_style(self.locked))
        self.lock_hint.setText("🔒 잠금 중" if self.locked else "")

        if self.locked:
            self._update_overlay_geometry()
            self.overlay.raise_()
            self.overlay.show()
        else:
            self.overlay.hide()

    def _lock_style(self, locked):
        if locked:
            return ("QPushButton{background:rgba(255,200,60,0.4);color:#ffd060;"
                    "border-radius:15px;border:1px solid rgba(255,200,60,0.7);font-size:15px;}"
                    "QPushButton:hover{background:rgba(255,200,60,0.6);}")
        return ("QPushButton{background:rgba(255,255,255,0.10);color:rgba(255,255,255,0.6);"
                "border-radius:15px;border:1px solid rgba(255,255,255,0.2);font-size:15px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.22);}")

    # ── 캘린더 그리드 갱신 ───────────────────────────────────
    def _refresh_calendar(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.month_label.setText(f"{self.current_year}년 {self.current_month}월")
        calendar.setfirstweekday(6)   # 일요일 시작 (한국 기준)
        cal   = calendar.monthcalendar(self.current_year, self.current_month)
        today = date.today()

        # 창의 실제 고정 크기를 우선 사용
        W = self.width()  if self.width()  > 100 else self.config.get("cal_width",  900)
        H = self.height() if self.height() > 100 else self.config.get("cal_height", 750)

        # 그리드 간격 완전 0 고정
        self.grid.setSpacing(0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)

        # body_layout 좌우 마진(각 14px) 제외 후 7등분
        BODY_MARGIN = 14
        grid_w = W - BODY_MARGIN * 2
        cell_w = grid_w // 7

        # ── 수직 공간 정밀 계산 ──────────────────────────────
        # 그리드 외부 고정 높이 요소들을 모두 명시적으로 빼야 겹침 방지
        HEADER_H    = self.HEADER_H   # 40px  헤더 바
        BODY_TOP    = 8               # body_layout 상단 margin
        BODY_BOT    = 4               # body_layout 하단 margin
        SPACING     = 6               # body_layout spacing
        NAV_H       = 28              # 월 네비게이션
        SEP_H       = 1               # 구분선
        DOW_H       = 20              # 요일 헤더
        STATUS_H    = 18              # 하단 상태바
        # body_layout에는 요소가 4개(nav, sep, dow, grid, bot) → spacing 4칸
        SPACINGS    = SPACING * 4

        NON_GRID_H = (HEADER_H + BODY_TOP + BODY_BOT +
                      NAV_H + SEP_H + DOW_H + STATUS_H + SPACINGS)

        avail_h    = H - NON_GRID_H
        rows_in_cal = max(len(cal), 5)
        # 셀 높이: 사용 가능 높이를 행 수로 나눔, 최솟값 보장
        cell_h = max(80, avail_h // rows_in_cal)

        span_rows = self._compute_spans(cal)

        for row, week in enumerate(cal):
            for col, day in enumerate(week):
                if day == 0:
                    ph = QWidget()
                    ph.setFixedHeight(cell_h)
                    ph.setMinimumWidth(1)
                    self.grid.addWidget(ph, row, col)
                    continue

                d   = date(self.current_year, self.current_month, day)
                key = d.strftime("%Y-%m-%d")

                single_evs_raw = [
                    ev for ev in self.events.get(key, [])
                    if not ev.get("end_date") or ev["end_date"] == key
                ]
                # 중요 일정을 위로 정렬
                single_evs = sorted(single_evs_raw,
                                    key=lambda e: 0 if e.get("important") else 1)

                spans_raw = span_rows[row][col]
                # 스팬도 중요 일정 위로
                spans = sorted(spans_raw,
                               key=lambda s: 0 if (s[6] if len(s) > 6 else False) else 1)

                btn = DayButton(
                    day=day, is_today=(d == today),
                    single_events=single_evs,
                    spans=spans,
                    is_sun=(col == 0), is_sat=(col == 6),
                    w=cell_w, h=cell_h,
                    font_scale=self.config.get("font_scale", 1.0),
                    col=col, total_cols=7,
                    text_color=getattr(self, "_tc", "#ffffff"),
                )
                btn.setFixedHeight(cell_h)
                btn.setMinimumWidth(1)
                btn.clicked.connect(lambda _, dd=d: self._on_day_click(dd))
                self.grid.addWidget(btn, row, col)

        if self.locked:
            self._update_overlay_geometry()
            self.overlay.raise_()
            self.overlay.show()

    def _compute_spans(self, cal):
        span_rows = [[[] for _ in range(7)] for _ in range(len(cal))]
        year, month = self.current_year, self.current_month

        for start_key, ev_list in self.events.items():
            try:
                start_d = date.fromisoformat(start_key)
            except Exception:
                continue
            for ev in ev_list:
                end_str = ev.get("end_date", "")
                if not end_str or end_str == start_key:
                    continue
                try:
                    end_d = date.fromisoformat(end_str)
                except Exception:
                    continue
                if end_d <= start_d:
                    continue

                color     = ev.get("color", "#a099ff")
                title     = ev.get("title", "")
                important = ev.get("important", False)

                for row, week in enumerate(cal):
                    for col, day in enumerate(week):
                        if day == 0:
                            continue
                        d = date(year, month, day)
                        if start_d <= d <= end_d:
                            is_start = (d == start_d)
                            is_end   = (d == end_d)
                            # 행 경계는 col 번호로만 판정 (가장 단순하고 정확함)
                            is_row_start = (col == 0)
                            is_row_end   = (col == 6)
                            span_rows[row][col].append(
                                (color, is_start, is_end, title, is_row_start, is_row_end, important)
                            )
        return span_rows

    # ── 날짜 클릭 ────────────────────────────────────────────
    def _on_day_click(self, d: date):

        # 해당 날짜에 등록된 단일/시작 이벤트
        key = d.strftime("%Y-%m-%d")
        direct_events = list(self.events.get(key, []))

        # 다중일정 중 이 날짜가 중간/종료일인 이벤트를 읽기 전용으로 수집
        span_readonly = []
        for start_key, ev_list in self.events.items():
            try:
                start_d = date.fromisoformat(start_key)
            except Exception:
                continue
            if start_d == d:
                continue   # 이미 direct_events에 포함
            for ev in ev_list:
                end_str = ev.get("end_date", "")
                if not end_str:
                    continue
                try:
                    end_d = date.fromisoformat(end_str)
                except Exception:
                    continue
                if start_d < d <= end_d:
                    # 읽기 전용 표시용 — 원본 시작일 정보 첨부
                    ev_copy = dict(ev)
                    ev_copy["_span_start"] = start_key   # 내부 표시용 메타
                    span_readonly.append((start_key, ev_copy))

        dlg = EventDialog(d, direct_events, span_readonly, self)
        if dlg.exec_():
            self.events[key] = dlg.result_events
            self._save_local()
            if hasattr(self, "firebase") and self.firebase:
                self.firebase.push_events(self.events)
            self._refresh_calendar()

    # ── Firebase / 로컬 저장 ─────────────────────────────────
    def _setup_firebase(self):
        self.firebase = None
        cfg = self.config.get("firebase", {})
        if cfg.get("url") and cfg.get("group_id"):
            try:
                self.firebase = FirebaseSync(cfg, self._on_remote_update)
                self.firebase.start()
                self._set_status(True, cfg["group_id"])
            except Exception as e:
                self._set_status(False, str(e)[:30])
        self._load_local()

    def _on_remote_update(self, data):
        self.events = data; self._save_local(); signals.events_updated.emit()

    def _set_status(self, ok, text):
        if ok:
            self.status_label.setText(f"● {text}")
            self.status_label.setStyleSheet("color:rgba(85,255,136,0.8);font-size:9px;")
        else:
            self.status_label.setText("● 연결 안됨")
            self.status_label.setStyleSheet("color:rgba(255,255,255,0.28);font-size:9px;")

    def _save_local(self):
        p = Path.home() / ".artincalendar_events.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)

    def _load_local(self):
        p = Path.home() / ".artincalendar_events.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                self.events = json.load(f)
        self._refresh_calendar()

    # ── 네비게이션 ────────────────────────────────────────────
    def _prev_month(self):
        self.current_month -= 1
        if self.current_month == 0: self.current_month = 12; self.current_year -= 1
        self._refresh_calendar()

    def _next_month(self):
        self.current_month += 1
        if self.current_month == 13: self.current_month = 1; self.current_year += 1
        self._refresh_calendar()

    def _go_today(self):
        t = date.today()
        self.current_year = t.year; self.current_month = t.month; self.selected_date = t
        self._refresh_calendar()

    def _clock_text(self): return datetime.now().strftime("%Y.%m.%d  %H:%M")
    def _update_clock(self): self.clock_label.setText(self._clock_text())
    def _fs(self, base): return max(8, int(base * self.config.get("font_scale", 1.0)))

    def _nav_btn(self, text):
        btn = QPushButton(text); btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.10);color:white;"
            "border-radius:14px;border:none;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:rgba(255,255,255,0.25);}")
        return btn

    # ── 드래그 (헤더 바에서만) ────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPos() - self._drag_pos)
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = None
            pos = self.pos()
            self.config["position"] = {"x": pos.x(), "y": pos.y()}
            save_config(self.config)

    def _toggle_visibility(self):
        self.hide() if self.isVisible() else (self.show(), self.raise_())

    def _minimize(self):
        self.showMinimized()

    def _quit_app(self):
        """Firebase 스레드 등 정리 후 완전 종료"""
        try:
            # Firebase 동기화 중지
            if hasattr(self, "firebase") and self.firebase:
                self.firebase.stop()
        except Exception:
            pass
        try:
            # 트레이 아이콘 제거
            if hasattr(self, "tray"):
                self.tray.hide()
        except Exception:
            pass
        QApplication.instance().quit()

    def _show_only_calendar(self):
        """모든 창을 최소화하고 캘린더만 표시"""
        import ctypes
        # EnumWindows로 모든 최상위 윈도우를 최소화
        SW_MINIMIZE = 6
        GW_OWNER = 4

        def _enum_callback(hwnd, _):
            try:
                # 현재 앱 윈도우는 건너뜀
                if hwnd == int(self.winId()):
                    return True
                # 보이는 창만 처리
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    # 작업표시줄·트레이 등 시스템 창 제외
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
                    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                    # WS_VISIBLE=0x10000000, WS_EX_TOOLWINDOW=0x80
                    if (style & 0x10000000) and not (ex_style & 0x80):
                        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)

        # 캘린더 창 표시 및 최상위로 올리기
        self.show()
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        self.raise_()
        self.activateWindow()

        # 2초 후 다시 최하단으로 복귀
        QTimer.singleShot(2000, self._restore_bottom)

    def _restore_bottom(self):
        """캘린더만 보이기 후 다시 최하단으로 복귀"""
        flags = self.windowFlags()
        flags &= ~Qt.WindowStaysOnTopHint
        flags |= Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags | Qt.FramelessWindowHint | Qt.Tool)
        self.show()

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec_():
            self.config = dlg.new_config
            save_config(self.config)
            new_w = self.config.get("cal_width",  900)
            new_h = self.config.get("cal_height", 750)
            self.setWindowOpacity(self.config.get("opacity", 0.70))
            pos = self.pos()
            # setFixedSize를 먼저 풀어야 새 크기 적용 가능
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setGeometry(pos.x(), pos.y(), new_w, new_h)
            self._setup_firebase()
            self._build_ui()


# ════════════════════════════════════════════════════════════
#  날짜 버튼
# ════════════════════════════════════════════════════════════
class DayButton(QPushButton):
    BAR_H   = 11   # 이벤트 바 높이
    BAR_GAP = 2    # 바 간격
    MAX_EV  = 8    # 최대 표시 개수

    def __init__(self, day, is_today,
                 single_events, spans,
                 is_sun, is_sat, w, h, font_scale,
                 col, total_cols, text_color="#ffffff"):
        super().__init__()
        self.day_num     = day
        self.single_evs  = single_events
        self.spans       = spans
        self.font_scale  = font_scale
        self._is_today   = is_today
        self._col        = col
        self._total_cols = total_cols
        self._cell_w     = w
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if is_today:
            bg, border = "rgba(108,99,255,0.20)", "1px solid rgba(160,153,255,0.40)"
        else:
            bg, border = "rgba(255,255,255,0.03)", "1px solid rgba(255,255,255,0.06)"

        self.setStyleSheet(f"""
            QPushButton {{
                background:{bg}; border-radius:10px; border:{border};
                text-align:left; padding:0;
            }}
            QPushButton:hover {{
                background:rgba(108,99,255,0.35);
                border:1px solid rgba(108,99,255,0.65);
            }}
        """)

        if is_today:   self._num_color = text_color
        elif is_sun:   self._num_color = "#ff6666"
        elif is_sat:   self._num_color = "#6699ff"
        else:          self._num_color = text_color

        self.setToolTip("")

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # 셀 영역 바깥으로 그려지지 않도록 클리핑
        p.setClipRect(self.rect())

        fs     = self.font_scale
        num_sz = max(8, int(12 * fs))
        ev_sz  = max(7, int(8  * fs))
        num_y  = int(14 * fs) + 1

        # 날짜 숫자
        nf = QFont("Pretendard"); nf.setPointSize(num_sz); nf.setBold(True)
        ef = QFont("Pretendard"); ef.setPointSize(ev_sz)   # ← ef를 먼저 정의
        p.setFont(nf); p.setPen(QColor(self._num_color))
        p.drawText(5, num_y, str(self.day_num))

        # 오늘 표시
        if self._is_today:
            tf = QFont("Pretendard"); tf.setPointSize(max(6, int(8 * fs))); tf.setBold(False)
            p.setFont(tf)
            p.setPen(QColor(160, 153, 255, 200))
            num_fm  = QFontMetrics(nf)
            today_x = 5 + num_fm.horizontalAdvance(str(self.day_num)) + 4
            p.drawText(today_x, num_y, "오늘")
            p.setFont(ef)

        p.setFont(ef)
        fm = p.fontMetrics()

        y         = num_y + 6
        BH        = self.BAR_H
        BG        = self.BAR_GAP
        W         = self.width()
        H         = self.height()
        PAD       = 2
        shown     = 0
        y_max     = H - 4

        # 바 그리기 전 안티앨리어싱 OFF (경계 번짐이 겹침처럼 보이는 문제 방지)
        p.setRenderHint(QPainter.Antialiasing, False)

        # ── 다일 스팬 바 ─────────────────────────────────────
        from PyQt5.QtGui import QPainterPath as _QPP
        for sp in self.spans:
            if shown >= self.MAX_EV: break
            color, is_start, is_end, title, is_row_start, is_row_end = sp[:6]
            important = sp[6] if len(sp) > 6 else False

            qc  = QColor(color)
            bar = QColor(qc.red(), qc.green(), qc.blue(), 175)
            bh_cur = int(BH * 1.3) if important else BH

            if y + bh_cur > y_max: break

            round_left  = is_start or is_row_start
            round_right = is_end   or is_row_end

            # x 경계: 셀 안쪽에 확실히 들어오도록 여백 설정
            # 중간 셀(양쪽 직각)은 2px 여백으로 인접 셀과 확실히 분리
            x0 = PAD + 2 if round_left  else 2
            x1 = W - PAD - 2 if round_right else W - 2
            bw = max(4, x1 - x0)
            r  = min(bh_cur // 2, bw // 2) if (round_left or round_right) else 0

            path = _QPP()
            if round_left and round_right:
                p.setRenderHint(QPainter.Antialiasing, True)
                path.addRoundedRect(x0, y, bw, bh_cur, r, r)
            elif round_left:
                p.setRenderHint(QPainter.Antialiasing, True)
                path.moveTo(x0 + r, y)
                path.lineTo(x1, y)
                path.lineTo(x1, y + bh_cur)
                path.lineTo(x0 + r, y + bh_cur)
                path.quadTo(x0, y + bh_cur, x0, y + bh_cur - r)
                path.lineTo(x0, y + r)
                path.quadTo(x0, y, x0 + r, y)
                path.closeSubpath()
            elif round_right:
                p.setRenderHint(QPainter.Antialiasing, True)
                path.moveTo(x0, y)
                path.lineTo(x1 - r, y)
                path.quadTo(x1, y, x1, y + r)
                path.lineTo(x1, y + bh_cur - r)
                path.quadTo(x1, y + bh_cur, x1 - r, y + bh_cur)
                path.lineTo(x0, y + bh_cur)
                path.closeSubpath()
            else:
                # 중간 셀: 안티앨리어싱 OFF 유지, 단순 사각형
                p.setRenderHint(QPainter.Antialiasing, False)
                path.addRect(x0, y, bw, bh_cur)

            p.setBrush(QBrush(bar)); p.setPen(Qt.NoPen)
            p.drawPath(path)
            # 다음 바를 위해 안티앨리어싱 다시 OFF
            p.setRenderHint(QPainter.Antialiasing, False)

            if is_start:
                p.setRenderHint(QPainter.TextAntialiasing, True)
                if important:
                    imp_f = QFont("Pretendard"); imp_f.setPointSize(max(7, int(ev_sz * 1.3))); imp_f.setBold(True)
                    p.setFont(imp_f); fm = p.fontMetrics()
                p.setPen(QColor(255, 255, 255, 230))
                txt_x = x0 + 4
                max_w = W - txt_x - 4
                star  = (important + " ") if isinstance(important, str) and important else ("★ " if important else "")
                txt   = fm.elidedText(star + title, Qt.ElideRight, max_w)
                p.drawText(txt_x, y + bh_cur - 1, txt)
                if important:
                    p.setFont(ef); fm = p.fontMetrics()

            y     += bh_cur + BG
            shown += 1

        # ── 단일 이벤트 바 ────────────────────────────────────
        p.setRenderHint(QPainter.Antialiasing, True)  # 단일 바는 양쪽 둥글게
        for ev in self.single_evs:
            if shown >= self.MAX_EV: break
            color     = ev.get("color", "#a099ff")
            title     = ev.get("title", "")
            important = ev.get("important", False)
            qc        = QColor(color)
            bar       = QColor(qc.red(), qc.green(), qc.blue(), 175)

            bh_cur = int(BH * 1.3) if important else BH

            if y + bh_cur > y_max: break

            r  = bh_cur // 2
            x0 = PAD + 3
            x1 = W - PAD - 3
            bw = max(4, x1 - x0)
            path2 = _QPP()
            path2.addRoundedRect(x0, y, bw, bh_cur, r, r)
            p.setBrush(QBrush(bar)); p.setPen(Qt.NoPen)
            p.drawPath(path2)

            p.setRenderHint(QPainter.TextAntialiasing, True)
            if important:
                imp_f = QFont("Pretendard"); imp_f.setPointSize(max(7, int(ev_sz * 1.3))); imp_f.setBold(True)
                p.setFont(imp_f); fm = p.fontMetrics()
            p.setPen(QColor(255, 255, 255, 230))
            max_w = bw - 8
            star  = "★ " if important else ""
            txt   = fm.elidedText(star + title, Qt.ElideRight, max_w)
            p.drawText(x0 + 4, y + bh_cur - 1, txt)
            if important:
                p.setFont(ef); fm = p.fontMetrics()

            y     += bh_cur + BG
            shown += 1

        # 초과 표시
        total = len(self.spans) + len(self.single_evs)
        if total > shown:
            p.setPen(QColor(255, 255, 255, 100))
            sf = QFont("Pretendard"); sf.setPointSize(max(6, int(7 * fs))); p.setFont(sf)
            p.drawText(5, self.height() - 3, f"+{total - shown}개 더")

        p.end()


# ════════════════════════════════════════════════════════════
#  일정 수정 다이얼로그
# ════════════════════════════════════════════════════════════
PRESET_COLORS = ["#a099ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff922b", "#f06bce"]

class EditEventDialog(QDialog):
    """기존 일정 한 개를 수정하는 다이얼로그"""
    def __init__(self, day: date, ev: dict, parent=None):
        super().__init__(parent)
        self.day = day
        self.ev  = dict(ev)
        self.setWindowTitle("일정 수정")
        self.setFixedSize(460, 380)
        self.setStyleSheet("""
            QDialog { background:#0f0c1e; color:white; }
            QLabel  { color:white; }
            QLineEdit, QTextEdit {
                background:rgba(255,255,255,0.07); color:white;
                border:1px solid rgba(108,99,255,0.4); border-radius:8px; padding:6px; }
            QDateEdit, QTimeEdit {
                background:rgba(255,255,255,0.07); color:white;
                border:1px solid rgba(108,99,255,0.4); border-radius:8px; padding:4px; }
            QPushButton {
                background:rgba(108,99,255,0.5); color:white;
                border-radius:8px; border:none; padding:6px 14px; }
            QPushButton:hover { background:rgba(108,99,255,0.8); }
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self); layout.setSpacing(10)
        layout.addWidget(self._lbl("✏️  일정 수정", "#a099ff", 14, bold=True))

        self.inp_title = QLineEdit(self.ev.get("title", ""))
        self.inp_title.setPlaceholderText("일정 제목")
        layout.addWidget(self.inp_title)

        self.inp_memo = QTextEdit()
        self.inp_memo.setPlainText(self.ev.get("memo", ""))
        self.inp_memo.setPlaceholderText("메모 (선택)")
        self.inp_memo.setFixedHeight(55)
        layout.addWidget(self.inp_memo)

        # 시간 + 색상
        r1 = QHBoxLayout()
        r1.addWidget(self._lbl("시작 시간:", size=10))
        self.inp_time = QTimeEdit(); self.inp_time.setDisplayFormat("HH:mm")
        t = self.ev.get("time", "00:00")
        try:
            h, m = map(int, t.split(":"))
        except Exception:
            h, m = 0, 0
        self.inp_time.setTime(QTime(h, m))
        r1.addWidget(self.inp_time); r1.addStretch()
        layout.addLayout(r1)

        # 색상 행
        color_row = QHBoxLayout(); color_row.setSpacing(6)
        color_row.addWidget(self._lbl("색상:", size=10))
        self.chosen_color = self.ev.get("color", "#a099ff")
        self._preset_btns = []
        for pc in PRESET_COLORS:
            pb = QPushButton(); pb.setFixedSize(22, 22)
            is_sel = (pc.lower() == self.chosen_color.lower())
            self._style_preset_btn(pb, pc, is_sel)
            pb.clicked.connect(lambda _, c=pc: self._apply_preset(c))
            color_row.addWidget(pb)
            self._preset_btns.append((pb, pc))
        self.btn_color = QPushButton("🎨")
        self.btn_color.setFixedSize(34, 26)
        self.btn_color.setStyleSheet(
            f"background:{self.chosen_color};color:white;"
            "border-radius:8px;border:2px solid rgba(255,255,255,0.3);font-size:13px;")
        self.btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.btn_color)
        color_row.addStretch()
        layout.addLayout(color_row)

        # 종료 날짜
        r2 = QHBoxLayout()
        r2.addWidget(self._lbl("종료 날짜:", size=10))
        self.inp_end = QDateEdit(); self.inp_end.setCalendarPopup(True)
        end_str = self.ev.get("end_date", "")
        if end_str:
            try:
                ed = date.fromisoformat(end_str)
                self.inp_end.setDate(QDate(ed.year, ed.month, ed.day))
            except Exception:
                self.inp_end.setDate(QDate(self.day.year, self.day.month, self.day.day))
        else:
            self.inp_end.setDate(QDate(self.day.year, self.day.month, self.day.day))
        self.inp_end.setMinimumDate(QDate(self.day.year, self.day.month, self.day.day))
        r2.addWidget(self.inp_end); r2.addStretch()
        layout.addLayout(r2)

        # 중요일정 콤보박스
        _IMPORTANT_CATS = ["없음", "★[중요일정]", "★[제출]", "★[투찰]", "★[준공]", "★[착공]"]
        imp_row = QHBoxLayout()
        imp_row.addWidget(self._lbl("중요도:", size=10))
        self.cmb_important = QComboBox()
        self.cmb_important.addItems(_IMPORTANT_CATS)
        cur_imp = self.ev.get("important", "")
        if cur_imp is True:
            self.cmb_important.setCurrentIndex(1)
        elif isinstance(cur_imp, str) and cur_imp in _IMPORTANT_CATS:
            self.cmb_important.setCurrentIndex(_IMPORTANT_CATS.index(cur_imp))
        self.cmb_important.setStyleSheet(
            "QComboBox{background:rgba(255,255,255,0.07);color:rgba(255,220,80,0.9);"
            "border:1px solid rgba(255,220,80,0.4);border-radius:8px;padding:4px 8px;}"
            "QComboBox::drop-down{border:none;width:18px;}"
            "QComboBox QAbstractItemView{background:#1a1530;color:white;"
            "border:1px solid rgba(108,99,255,0.4);selection-background-color:rgba(108,99,255,0.5);}")
        imp_row.addWidget(self.cmb_important)
        imp_row.addStretch()
        layout.addLayout(imp_row)

        layout.addStretch()
        br = QHBoxLayout()
        btn_save = QPushButton("💾 저장"); btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background:rgba(255,255,255,0.1);")
        btn_cancel.clicked.connect(self.reject)
        br.addWidget(btn_save); br.addWidget(btn_cancel)
        layout.addLayout(br)

    def _style_preset_btn(self, btn, color, selected):
        border = "2px solid white" if selected else "2px solid rgba(255,255,255,0.2)"
        btn.setStyleSheet(
            f"QPushButton{{background:{color};border-radius:11px;border:{border};}}"
            f"QPushButton:hover{{border:2px solid white;}}")

    def _apply_preset(self, color):
        self.chosen_color = color
        for pb, pc in self._preset_btns:
            self._style_preset_btn(pb, pc, pc.lower() == color.lower())
        self.btn_color.setStyleSheet(
            f"background:{color};color:white;"
            "border-radius:8px;border:2px solid rgba(255,255,255,0.3);font-size:13px;")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.chosen_color), self)
        if c.isValid():
            self._apply_preset(c.name())

    def _save(self):
        title = self.inp_title.text().strip()
        if not title: return
        qd    = self.inp_end.date()
        end_d = date(qd.year(), qd.month(), qd.day())
        self.ev.update({
            "title"    : title,
            "memo"     : self.inp_memo.toPlainText().strip(),
            "time"     : self.inp_time.time().toString("HH:mm"),
            "color"    : self.chosen_color,
            "end_date" : end_d.strftime("%Y-%m-%d") if end_d > self.day else "",
            "important": self.cmb_important.currentText() if self.cmb_important.currentIndex() > 0 else "",
        })
        self.accept()

    def _lbl(self, text, color="white", size=11, bold=False):
        l = QLabel(text)
        l.setStyleSheet(
            f"color:{color};font-size:{size}px;"
            f"font-weight:{'bold' if bold else 'normal'};")
        return l


# ════════════════════════════════════════════════════════════
#  일정 추가/편집 다이얼로그
# ════════════════════════════════════════════════════════════
class EventDialog(QDialog):
    def __init__(self, day: date, events: list, span_readonly: list = None, parent=None):
        super().__init__(parent)
        self.day           = day
        self.result_events = list(events)
        self.span_readonly = span_readonly or []   # [(start_key, ev_dict), ...]
        self.setWindowTitle(f"{day.strftime('%Y년 %m월 %d일')} 일정")
        self.setFixedSize(460, 620)
        self.setStyleSheet("""
            QDialog { background:#0f0c1e; color:white; }
            QLabel  { color:white; }
            QLineEdit, QTextEdit {
                background:rgba(255,255,255,0.07); color:white;
                border:1px solid rgba(108,99,255,0.4); border-radius:8px; padding:6px; }
            QDateEdit {
                background:rgba(255,255,255,0.07); color:white;
                border:1px solid rgba(108,99,255,0.4); border-radius:8px; padding:4px; }
            QPushButton {
                background:rgba(108,99,255,0.5); color:white;
                border-radius:8px; border:none; padding:6px 14px; }
            QPushButton:hover { background:rgba(108,99,255,0.8); }
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self); layout.setSpacing(10)
        layout.addWidget(self._lbl(f"📅  {self.day.strftime('%Y년 %m월 %d일')}", "#a099ff", 14, bold=True))

        self.ev_layout = QVBoxLayout()
        sa = QScrollArea(); sa.setWidgetResizable(True)
        sa.setStyleSheet("border:none;background:transparent;")
        inner = QWidget(); inner.setLayout(self.ev_layout)
        sa.setWidget(inner); sa.setFixedHeight(195)
        layout.addWidget(sa)
        self._render_events()

        layout.addWidget(self._hsep())
        layout.addWidget(self._lbl("➕  새 일정 추가", "#a099ff", 11))

        self.inp_title = QLineEdit()
        self.inp_title.setPlaceholderText("일정 제목 (한글 가능)")
        layout.addWidget(self.inp_title)

        self.inp_memo = QTextEdit()
        self.inp_memo.setPlaceholderText("메모 (선택)")
        self.inp_memo.setFixedHeight(50)
        layout.addWidget(self.inp_memo)

        r1 = QHBoxLayout()
        r1.addWidget(self._lbl("시작 시간:", size=10))
        self.inp_time = QTimeEdit(); self.inp_time.setDisplayFormat("HH:mm")
        self.inp_time.setStyleSheet(
            "QTimeEdit{background:rgba(255,255,255,0.07);color:white;"
            "border:1px solid rgba(108,99,255,0.4);border-radius:8px;padding:4px;}")
        r1.addWidget(self.inp_time); r1.addStretch()
        layout.addLayout(r1)

        # 색상 행: 프리셋 7개 + 색상 선택기
        color_row = QHBoxLayout(); color_row.setSpacing(6)
        color_row.addWidget(self._lbl("색상:", size=10))
        self.chosen_color = "#a099ff"
        self._preset_btns = []
        for pc in PRESET_COLORS:
            pb = QPushButton(); pb.setFixedSize(22, 22)
            is_sel = (pc.lower() == self.chosen_color.lower())
            self._style_preset_btn(pb, pc, is_sel)
            pb.clicked.connect(lambda _, c=pc: self._apply_preset(c))
            color_row.addWidget(pb)
            self._preset_btns.append((pb, pc))
        self.btn_color = QPushButton("🎨")
        self.btn_color.setFixedSize(34, 26)
        self.btn_color.setStyleSheet(
            f"background:{self.chosen_color};color:white;"
            "border-radius:8px;border:2px solid rgba(255,255,255,0.3);font-size:13px;")
        self.btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.btn_color)
        color_row.addStretch()
        layout.addLayout(color_row)

        r2 = QHBoxLayout()
        r2.addWidget(self._lbl("종료 날짜 (다일이면 변경):", size=10))
        self.inp_end = QDateEdit(); self.inp_end.setCalendarPopup(True)
        self.inp_end.setDate(QDate(self.day.year, self.day.month, self.day.day))
        self.inp_end.setMinimumDate(QDate(self.day.year, self.day.month, self.day.day))
        self.inp_end.setStyleSheet(
            "QDateEdit{background:rgba(255,255,255,0.07);color:white;"
            "border:1px solid rgba(108,99,255,0.4);border-radius:8px;padding:4px;}")
        r2.addWidget(self.inp_end); r2.addStretch()
        layout.addLayout(r2)

        # 중요일정 콤보박스
        _IMPORTANT_CATS = ["없음", "★[중요일정]", "★[제출]", "★[투찰]", "★[준공]", "★[착공]"]
        imp_row = QHBoxLayout()
        imp_row.addWidget(self._lbl("중요도:", size=10))
        self.cmb_important = QComboBox()
        self.cmb_important.addItems(_IMPORTANT_CATS)
        self.cmb_important.setStyleSheet(
            "QComboBox{background:rgba(255,255,255,0.07);color:rgba(255,220,80,0.9);"
            "border:1px solid rgba(255,220,80,0.4);border-radius:8px;padding:4px 8px;}"
            "QComboBox::drop-down{border:none;width:18px;}"
            "QComboBox QAbstractItemView{background:#1a1530;color:white;"
            "border:1px solid rgba(108,99,255,0.4);selection-background-color:rgba(108,99,255,0.5);}")
        imp_row.addWidget(self.cmb_important)
        imp_row.addStretch()
        layout.addLayout(imp_row)

        br = QHBoxLayout()
        btn_add = QPushButton("➕ 일정 추가"); btn_add.clicked.connect(self._add_event)
        btn_cls = QPushButton("닫기")
        btn_cls.setStyleSheet("background:rgba(255,255,255,0.1);")
        btn_cls.clicked.connect(self.accept)
        br.addWidget(btn_add); br.addWidget(btn_cls)
        layout.addLayout(br)

    def _style_preset_btn(self, btn, color, selected):
        border = "2px solid white" if selected else "2px solid rgba(255,255,255,0.2)"
        btn.setStyleSheet(
            f"QPushButton{{background:{color};border-radius:11px;border:{border};}}"
            f"QPushButton:hover{{border:2px solid white;}}")

    def _apply_preset(self, color):
        self.chosen_color = color
        for pb, pc in self._preset_btns:
            self._style_preset_btn(pb, pc, pc.lower() == color.lower())
        self.btn_color.setStyleSheet(
            f"background:{color};color:white;"
            "border-radius:8px;border:2px solid rgba(255,255,255,0.3);font-size:13px;")

    def _render_events(self):
        while self.ev_layout.count():
            item = self.ev_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        has_any = bool(self.result_events) or bool(self.span_readonly)

        if not has_any:
            self.ev_layout.addWidget(
                self._lbl("등록된 일정이 없습니다", "rgba(255,255,255,0.3)", 11))
            return

        # ── 직접 등록 이벤트 (수정/삭제 가능)
        for i, ev in enumerate(self.result_events):
            color     = ev.get("color", "#a099ff")
            important = ev.get("important", False)
            row       = QHBoxLayout()
            dot       = QLabel("●"); dot.setStyleSheet(f"color:{color};font-size:11px;"); dot.setFixedWidth(18)
            end       = ev.get("end_date","")
            range_txt = f"  📅~{end}" if end and end != self.day.strftime("%Y-%m-%d") else ""
            time_txt  = f"[{ev['time']}] " if ev.get("time") else ""
            star      = (important + " ") if isinstance(important, str) and important else ("★ " if important else "")
            body      = f"{star}{time_txt}{ev.get('title','')}{range_txt}"
            if ev.get("memo"): body += f"\n📝 {ev['memo']}"
            font_size  = 14 if important else 11
            lbl = QLabel(body); lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"font-size:{font_size}px; font-weight:{'bold' if important else 'normal'};"
                f" color:{'#ffe04a' if important else 'white'};")

            # 수정 버튼 - 기울어진 연필 SVG 아이콘
            btn_edit = QPushButton(); btn_edit.setFixedSize(24, 24)
            btn_edit.setStyleSheet(
                "QPushButton{background:rgba(108,99,255,0.3);"
                "border-radius:12px;border:none;}"
                "QPushButton:hover{background:rgba(108,99,255,0.6);}")
            # SVG 연필 아이콘 생성
            _pencil_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <g transform="rotate(-45,10,10)">
    <rect x="7" y="2" width="6" height="11" rx="1.5" fill="#c0bbff"/>
    <polygon points="7,13 10,18 13,13" fill="#c0bbff"/>
    <rect x="7" y="2" width="6" height="3" rx="1.5" fill="#8880dd"/>
  </g>
</svg>"""
            _renderer = QSvgRenderer(QByteArray(_pencil_svg))
            _pix = QPixmap(18, 18); _pix.fill(Qt.transparent)
            _painter = QPainter(_pix)
            _renderer.render(_painter); _painter.end()
            btn_edit.setIcon(QIcon(_pix)); btn_edit.setIconSize(_pix.size())
            btn_edit.clicked.connect(lambda _, idx=i: self._edit(idx))

            btn_del = QPushButton("✕"); btn_del.setFixedSize(22, 22)
            btn_del.setStyleSheet(
                "QPushButton{background:rgba(255,80,80,0.2);color:#ff8080;"
                "border-radius:11px;border:none;font-size:11px;}"
                "QPushButton:hover{background:rgba(255,80,80,0.5);}")
            btn_del.clicked.connect(lambda _, idx=i: self._del(idx))

            row.addWidget(dot); row.addWidget(lbl, 1)
            row.addWidget(btn_edit); row.addWidget(btn_del)
            card = QWidget(); card.setLayout(row)
            card.setStyleSheet(
                "background:rgba(255,255,255,0.05);border-radius:8px;padding:2px;")
            self.ev_layout.addWidget(card)

        # ── 다중일정 연장 표시 (읽기 전용 — 시작일에서 수정)
        for start_key, ev in self.span_readonly:
            color = ev.get("color", "#a099ff")
            row   = QHBoxLayout()
            dot   = QLabel("↔"); dot.setStyleSheet(f"color:{color};font-size:11px;"); dot.setFixedWidth(18)
            end   = ev.get("end_date", "")
            body  = f"{ev.get('title','')}  📅 {start_key} ~ {end}"
            if ev.get("memo"): body += f"\n📝 {ev['memo']}"
            lbl = QLabel(body); lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.7);")
            hint = QLabel("시작일에서 수정")
            hint.setStyleSheet(
                "font-size:9px; color:rgba(255,200,100,0.6); padding-right:2px;")
            row.addWidget(dot); row.addWidget(lbl, 1); row.addWidget(hint)
            card = QWidget(); card.setLayout(row)
            card.setStyleSheet(
                "background:rgba(255,255,255,0.03);border-radius:8px;padding:2px;"
                "border:1px dashed rgba(255,200,100,0.25);")
            self.ev_layout.addWidget(card)

    def _edit(self, idx):
        ev  = self.result_events[idx]
        dlg = EditEventDialog(self.day, ev, self)
        if dlg.exec_():
            self.result_events[idx] = dlg.ev
            self._render_events()

    def _del(self, idx):
        self.result_events.pop(idx); self._render_events()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.chosen_color), self)
        if c.isValid():
            self._apply_preset(c.name())

    def _add_event(self):
        title = self.inp_title.text().strip()
        if not title: return
        qd    = self.inp_end.date()
        end_d = date(qd.year(), qd.month(), qd.day())
        ev = {
            "title"    : title,
            "memo"     : self.inp_memo.toPlainText().strip(),
            "time"     : self.inp_time.time().toString("HH:mm"),
            "color"    : self.chosen_color,
            "end_date" : end_d.strftime("%Y-%m-%d") if end_d > self.day else "",
            "important": self.cmb_important.currentText() if self.cmb_important.currentIndex() > 0 else "",
        }
        self.result_events.append(ev)
        self.inp_title.clear(); self.inp_memo.clear()
        self.cmb_important.setCurrentIndex(0)
        self._render_events()

    def _lbl(self, text, color="white", size=11, bold=False):
        l = QLabel(text)
        l.setStyleSheet(
            f"color:{color};font-size:{size}px;"
            f"font-weight:{'bold' if bold else 'normal'};")
        return l

    def _hsep(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("background:rgba(108,99,255,0.25);"); return f


# ════════════════════════════════════════════════════════════
#  설정 다이얼로그
# ════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.new_config = dict(config)
        self.setWindowTitle("아트인캘린더 설정")
        self.setFixedSize(460, 640)
        self.setStyleSheet("""
            QDialog  { background:#141414; color:white; }
            QLabel   { color:white; }
            QGroupBox{ color:#a099ff; border:1px solid rgba(108,99,255,0.35);
                       border-radius:10px; margin-top:6px; padding:10px; font-size:11px; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; }
            QLineEdit{ background:rgba(255,255,255,0.07); color:white;
                       border:1px solid rgba(108,99,255,0.4); border-radius:8px; padding:6px; }
            QPushButton { background:rgba(108,99,255,0.5); color:white;
                border-radius:8px; border:none; padding:6px 14px; }
            QPushButton:hover { background:rgba(108,99,255,0.8); }
            QRadioButton { color:white; font-size:11px; spacing:6px; }
            QRadioButton::indicator { width:15px; height:15px; border-radius:8px;
                border:2px solid rgba(255,255,255,0.35); background:transparent; }
            QRadioButton::indicator:checked { background:#6C63FF;
                border:2px solid #a099ff; }
            QSlider::groove:horizontal {
                background:rgba(255,255,255,0.12);height:4px;border-radius:2px; }
            QSlider::handle:horizontal {
                background:#a099ff;width:14px;height:14px;margin:-5px 0;border-radius:7px; }
            QSlider::sub-page:horizontal { background:#6C63FF;border-radius:2px; }
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10); layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(self._lbl("⚙  설정", "#a099ff", 15, bold=True))

        # ── Firebase ──────────────────────────────────────────
        fb = QGroupBox("🔗  Firebase 공유 설정"); fl = QVBoxLayout(fb)
        fl.addWidget(QLabel("Realtime DB URL:"))
        self.fb_url = QLineEdit(self.new_config.get("firebase", {}).get("url", ""))
        self.fb_url.setPlaceholderText("https://your-project.firebaseio.com")
        fl.addWidget(self.fb_url)
        fl.addWidget(QLabel("그룹 ID:"))
        self.group_id = QLineEdit(self.new_config.get("firebase", {}).get("group_id", ""))
        self.group_id.setPlaceholderText("예: myteam2024")
        fl.addWidget(self.group_id)
        layout.addWidget(fb)

        # ── 외관 ──────────────────────────────────────────────
        ap = QGroupBox("🎨  외관 설정"); al = QVBoxLayout(ap); al.setSpacing(10)

        # 전체 컬러 테마 라디오 버튼
        theme_row = QHBoxLayout(); theme_row.setSpacing(18)
        theme_row.addWidget(self._lbl("전체 컬러:", size=11))
        self._rbg = QButtonGroup(self)
        current_theme = self.new_config.get("color_theme", "black")
        for val, label in [("white","⬜ 화이트"), ("black","⬛ 블랙"), ("custom","⚙ 사용자지정")]:
            rb = QRadioButton(label)
            if val == current_theme:
                rb.setChecked(True)
            rb.setProperty("theme_val", val)
            self._rbg.addButton(rb)
            theme_row.addWidget(rb)
        theme_row.addStretch()
        al.addLayout(theme_row)

        # 사용자지정 색상 패널 (custom 선택 시에만 활성화)
        self._custom_panel = QWidget()
        cp_layout = QVBoxLayout(self._custom_panel)
        cp_layout.setContentsMargins(0, 4, 0, 0); cp_layout.setSpacing(8)

        r1 = QHBoxLayout(); r1.addWidget(self._lbl("배경색:", size=10))
        self._bg = self.new_config.get("bg_color_hex", "#1e1e1e")
        self.btn_bg = QPushButton(); self.btn_bg.setFixedSize(36, 24)
        self.btn_bg.setStyleSheet(f"background:{self._bg};border-radius:6px;border:1px solid #555;")
        self.btn_bg.clicked.connect(self._pick_bg)
        r1.addWidget(self.btn_bg); r1.addStretch()
        cp_layout.addLayout(r1)

        r2 = QHBoxLayout(); r2.addWidget(self._lbl("강조색:", size=10))
        self._ac = self.new_config.get("accent_color", "#333333")
        self.btn_ac = QPushButton(); self.btn_ac.setFixedSize(36, 24)
        self.btn_ac.setStyleSheet(f"background:{self._ac};border-radius:6px;border:1px solid #555;")
        self.btn_ac.clicked.connect(self._pick_ac)
        r2.addWidget(self.btn_ac); r2.addStretch()
        cp_layout.addLayout(r2)

        r3 = QHBoxLayout(); r3.addWidget(self._lbl("글씨색:", size=10))
        self._tc = self.new_config.get("text_color", "#ffffff")
        self.btn_tc = QPushButton(); self.btn_tc.setFixedSize(36, 24)
        self.btn_tc.setStyleSheet(f"background:{self._tc};border-radius:6px;border:1px solid #555;")
        self.btn_tc.clicked.connect(self._pick_tc)
        r3.addWidget(self.btn_tc); r3.addStretch()
        cp_layout.addLayout(r3)

        al.addWidget(self._custom_panel)

        # 투명도
        al.addWidget(self._lbl("투명도:", size=10))
        ro = QHBoxLayout()
        self.sld_op = QSlider(Qt.Horizontal)
        self.sld_op.setRange(10, 100)
        self.sld_op.setValue(max(10, int(self.new_config.get("opacity", 0.70) * 100)))
        self.lbl_op = QLabel(f"{self.sld_op.value()}%")
        self.sld_op.valueChanged.connect(lambda v: self.lbl_op.setText(f"{v}%"))
        ro.addWidget(self.sld_op); ro.addWidget(self.lbl_op)
        al.addLayout(ro)
        layout.addWidget(ap)

        # 라디오 버튼 변경 시 custom_panel 활성화 토글
        self._rbg.buttonClicked.connect(self._on_theme_change)
        self._update_custom_panel(current_theme)

        # ── 크기 ──────────────────────────────────────────────
        sz = QGroupBox("📐  크기 설정"); sl = QVBoxLayout(sz)
        sl.addWidget(self._lbl("캘린더 가로 (px):", size=10))
        rw = QHBoxLayout()
        self.sld_w = QSlider(Qt.Horizontal)
        self.sld_w.setRange(400, 1400); self.sld_w.setValue(self.new_config.get("cal_width", 900))
        self.lbl_w = QLabel(f"{self.sld_w.value()}px")
        self.sld_w.valueChanged.connect(lambda v: self.lbl_w.setText(f"{v}px"))
        rw.addWidget(self.sld_w); rw.addWidget(self.lbl_w); sl.addLayout(rw)

        sl.addWidget(self._lbl("캘린더 세로 (px):", size=10))
        rh = QHBoxLayout()
        self.sld_h = QSlider(Qt.Horizontal)
        self.sld_h.setRange(400, 1100); self.sld_h.setValue(self.new_config.get("cal_height", 750))
        self.lbl_h = QLabel(f"{self.sld_h.value()}px")
        self.sld_h.valueChanged.connect(lambda v: self.lbl_h.setText(f"{v}px"))
        rh.addWidget(self.sld_h); rh.addWidget(self.lbl_h); sl.addLayout(rh)

        sl.addWidget(self._lbl("폰트 배율:", size=10))
        rf = QHBoxLayout()
        self.sld_f = QSlider(Qt.Horizontal)
        self.sld_f.setRange(70, 160)
        self.sld_f.setValue(int(self.new_config.get("font_scale", 1.0) * 100))
        self.lbl_f = QLabel(f"{self.sld_f.value()}%")
        self.sld_f.valueChanged.connect(lambda v: self.lbl_f.setText(f"{v}%"))
        rf.addWidget(self.sld_f); rf.addWidget(self.lbl_f); sl.addLayout(rf)
        layout.addWidget(sz)

        layout.addStretch()

        br = QHBoxLayout()
        bs = QPushButton("저장"); bs.clicked.connect(self._save)
        bc = QPushButton("취소")
        bc.setStyleSheet("background:rgba(255,255,255,0.1);"); bc.clicked.connect(self.reject)
        br.addWidget(bs); br.addWidget(bc)
        layout.addLayout(br)

        bottom_row = QHBoxLayout()
        ver_lbl = QLabel(f"v{get_current_version()}")
        ver_lbl.setStyleSheet("color:rgba(255,255,255,0.35);font-size:11px;")
        cr = QLabel("제작자 : 조범진")
        cr.setAlignment(Qt.AlignRight)
        cr.setStyleSheet("color:rgba(255,255,255,0.45);font-size:11px;")
        bottom_row.addWidget(ver_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(cr)
        layout.addLayout(bottom_row)

    def _on_theme_change(self, btn):
        self._update_custom_panel(btn.property("theme_val"))

    def _update_custom_panel(self, theme):
        is_custom = (theme == "custom")
        self._custom_panel.setEnabled(is_custom)
        self._custom_panel.setVisible(is_custom)
        # 다이얼로그 높이 동적 조정
        self.setFixedSize(460, 680 if is_custom else 580)

    def _pick_bg(self):
        c = QColorDialog.getColor(QColor(self._bg), self)
        if c.isValid():
            self._bg = c.name()
            self.btn_bg.setStyleSheet(f"background:{self._bg};border-radius:6px;border:1px solid #555;")

    def _pick_ac(self):
        c = QColorDialog.getColor(QColor(self._ac), self)
        if c.isValid():
            self._ac = c.name()
            self.btn_ac.setStyleSheet(f"background:{self._ac};border-radius:6px;border:1px solid #555;")

    def _pick_tc(self):
        c = QColorDialog.getColor(QColor(self._tc), self)
        if c.isValid():
            self._tc = c.name()
            self.btn_tc.setStyleSheet(f"background:{self._tc};border-radius:6px;border:1px solid #555;")

    def _save(self):
        # 선택된 테마 읽기
        theme = "black"
        for btn in self._rbg.buttons():
            if btn.isChecked():
                theme = btn.property("theme_val")
                break

        op = self.sld_op.value() / 100.0
        qc = QColor(self._bg)

        # 테마에 따라 bg/accent/text 결정
        if theme == "white":
            bg_hex  = "#ffffff"
            bg_rgba = f"rgba(255,255,255,{op:.2f})"
            acc     = "#cccccc"
            tc      = "#111111"
        elif theme == "black":
            bg_hex  = "#141414"
            bg_rgba = f"rgba(20,20,20,{op:.2f})"
            acc     = "#444444"
            tc      = "#ffffff"
        else:  # custom
            bg_hex  = self._bg
            bg_rgba = f"rgba({qc.red()},{qc.green()},{qc.blue()},{op:.2f})"
            acc     = self._ac
            tc      = self._tc

        self.new_config.update({
            "firebase"    : {"url": self.fb_url.text().strip(),
                             "group_id": self.group_id.text().strip()},
            "color_theme" : theme,
            "opacity"     : op,
            "bg_color"    : bg_rgba,
            "bg_color_hex": bg_hex,
            "accent_color": acc,
            "text_color"  : tc,
            "cal_width"   : self.sld_w.value(),
            "cal_height"  : self.sld_h.value(),
            "font_scale"  : self.sld_f.value() / 100.0,
        })
        self.accept()

    def _lbl(self, text, color="white", size=11, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;"
                        f"font-weight:{'bold' if bold else 'normal'};")
        return l


# ════════════════════════════════════════════════════════════
#  비밀번호 입력 다이얼로그
# ════════════════════════════════════════════════════════════
class PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("아트인캘린더")
        self.setFixedSize(320, 200)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        self.setStyleSheet("""
            QDialog  { background:#141414; color:white; }
            QLabel   { color:white; }
            QLineEdit {
                background:rgba(255,255,255,0.08); color:white;
                border:1px solid rgba(108,99,255,0.5); border-radius:8px;
                padding:8px; font-size:13px; }
            QPushButton {
                background:rgba(108,99,255,0.55); color:white;
                border-radius:8px; border:none; padding:8px 20px; font-size:12px; }
            QPushButton:hover { background:rgba(108,99,255,0.85); }
        """)
        self._attempts = 0
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12); layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("🎨 아트인캘린더")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:white; font-size:15px; font-weight:bold;")
        layout.addWidget(title)

        sub = QLabel("비밀번호를 입력하세요")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:rgba(255,255,255,0.5); font-size:11px;")
        layout.addWidget(sub)

        self.inp = QLineEdit()
        self.inp.setPlaceholderText("비밀번호")
        self.inp.setEchoMode(QLineEdit.Password)
        self.inp.returnPressed.connect(self._confirm)
        layout.addWidget(self.inp)

        self.err_lbl = QLabel("")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        self.err_lbl.setStyleSheet("color:#ff6b6b; font-size:10px;")
        layout.addWidget(self.err_lbl)

        btn = QPushButton("확인")
        btn.clicked.connect(self._confirm)
        layout.addWidget(btn)

    def _confirm(self):
        pw = self.inp.text()
        if check_password(pw):
            self.accept()
        else:
            self._attempts += 1
            self.inp.clear()
            self.err_lbl.setText(f"비밀번호가 틀렸습니다. ({self._attempts}회 시도)")
            if self._attempts >= 5:
                self.reject()


# ════════════════════════════════════════════════════════════
#  업데이트 워커 (백그라운드 스레드)
# ════════════════════════════════════════════════════════════
class UpdateWorker(QThread):
    checked    = pyqtSignal(object)   # None or dict
    progress   = pyqtSignal(int)
    finished_dl = pyqtSignal(bool)

    def __init__(self, mode="check", download_url=None, target_version=""):
        super().__init__()
        self.mode           = mode
        self.download_url   = download_url
        self.target_version = target_version

    def run(self):
        if self.mode == "check":
            result = check_update()
            self.checked.emit(result)
        elif self.mode == "download":
            ok = download_and_install(
                self.download_url,
                on_progress=lambda p: self.progress.emit(p),
                target_version=self.target_version,
            )
            self.finished_dl.emit(ok)


# ════════════════════════════════════════════════════════════
#  업데이트 다이얼로그
# ════════════════════════════════════════════════════════════
class UpdateDialog(QDialog):
    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setWindowTitle("업데이트 알림")
        self.setFixedSize(400, 260)
        self.setStyleSheet("""
            QDialog  { background:#0f0c1e; color:white; }
            QLabel   { color:white; }
            QPushButton { background:rgba(108,99,255,0.55); color:white;
                border-radius:8px; border:none; padding:8px 18px; font-size:12px; }
            QPushButton:hover { background:rgba(108,99,255,0.85); }
            QProgressBar { background:rgba(255,255,255,0.1); border-radius:5px;
                border:none; height:10px; }
            QProgressBar::chunk { background:#6C63FF; border-radius:5px; }
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self); layout.setSpacing(12); layout.setContentsMargins(20,18,20,18)

        layout.addWidget(self._lbl("🔄  새 버전이 있습니다!", "#a099ff", 15, bold=True))

        ver_row = QHBoxLayout()
        ver_row.addWidget(self._lbl(f"현재 버전:  v{get_current_version()}", size=11))
        ver_row.addStretch()
        ver_row.addWidget(self._lbl(f"최신 버전:  {self.update_info['version']}", "#6bcb77", 11))
        layout.addLayout(ver_row)

        if self.update_info.get("notes"):
            notes = QLabel(self.update_info["notes"][:200])
            notes.setWordWrap(True)
            notes.setStyleSheet("color:rgba(255,255,255,0.6);font-size:10px;"
                                "background:rgba(255,255,255,0.05);border-radius:6px;padding:6px;")
            layout.addWidget(notes)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color:rgba(255,255,255,0.5);font-size:10px;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()
        btn_row = QHBoxLayout()
        self.btn_update = QPushButton("⬇  지금 업데이트")
        self.btn_update.clicked.connect(self._do_update)
        btn_skip = QPushButton("나중에")
        btn_skip.setStyleSheet("background:rgba(255,255,255,0.1);")
        btn_skip.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_update); btn_row.addWidget(btn_skip)
        layout.addLayout(btn_row)

    def _do_update(self):
        self.btn_update.setEnabled(False)
        self.progress_bar.show()
        self.status_lbl.setText("다운로드 중...")
        self._worker = UpdateWorker("download", self.update_info["download_url"],
                                    self.update_info["version"])
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.finished_dl.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool):
        if ok:
            self.status_lbl.setText("완료! 잠시 후 재시작됩니다...")
            # 트레이 아이콘 먼저 숨기고 앱 완전 종료
            # (배치 스크립트가 파일 교체 후 새 EXE를 실행함)
            def _do_quit():
                try:
                    parent = self.parent()
                    if parent and hasattr(parent, "tray"):
                        parent.tray.hide()
                except Exception:
                    pass
                restart_app()   # os._exit(0) 호출
            QTimer.singleShot(1200, _do_quit)
        else:
            self.status_lbl.setText("❌ 다운로드 실패. 나중에 다시 시도해주세요.")
            self.btn_update.setEnabled(True)

    def _lbl(self, text, color="white", size=11, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;"
                        f"font-weight:{'bold' if bold else 'normal'};")
        return l


# ── 진입점 ───────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(lambda: os._exit(0))
    _register_pretendard()
    from PyQt5.QtGui import QFont as _QFont
    default_font = _QFont("Pretendard", 10)
    app.setFont(default_font)

    # 비밀번호 확인 (password.txt가 있을 때만)
    if password_required():
        pw_dlg = PasswordDialog()
        if pw_dlg.exec_() != QDialog.Accepted:
            os._exit(0)

    win = ArtInCalendar()
    win.show()

    # 백그라운드 업데이트 체크 (시작 2초 후)
    def _check_update_bg():
        _uw = UpdateWorker("check")
        def _on_result(info):
            if info:
                dlg = UpdateDialog(info, win)
                dlg.exec_()
        _uw.checked.connect(_on_result)
        _uw.start()
        win._update_worker = _uw   # GC 방지

    QTimer.singleShot(2000, _check_update_bg)

    sys.exit(app.exec_())
