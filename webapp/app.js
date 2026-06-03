"use strict";

/* ────────────────────────────────────────────────────────────
 * 아트인캘린더 웹앱 — 기존 PC 앱과 동일한 Firebase 데이터 공유
 *   저장 경로:  calendars/{groupId}/events
 *   이벤트:     { "YYYY-MM-DD": [ {title,memo,time,color,end_date,important} ] }
 * ──────────────────────────────────────────────────────────── */

const DEFAULTS = {
  url: "https://artincalendar-b8963-default-rtdb.firebaseio.com",
  groupId: "ARTIN",
};

const PRESET_COLORS = ["#a099ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff922b", "#f06bce"];

const IMPORTANT_LABELS = [
  { label: "", color: "" },
  { label: "★[중요]", color: "#9c27b0" },
  { label: "★[제출]", color: "#f44336" },
  { label: "★[투찰]", color: "#ff9800" },
  { label: "★[준공]", color: "#4caf50" },
  { label: "★[착공]", color: "#1565c0" },
];

// ── 유틸 ──────────────────────────────────────────────
const pad2 = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
function parseYmd(s) {
  if (!s || typeof s !== "string") return null;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3]);
}
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ── 설정 ──────────────────────────────────────────────
function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("aic_settings") || "{}");
    return { url: s.url || DEFAULTS.url, groupId: s.groupId || DEFAULTS.groupId };
  } catch { return { ...DEFAULTS }; }
}
function saveSettings(s) { localStorage.setItem("aic_settings", JSON.stringify(s)); }

// ── 상태 ──────────────────────────────────────────────
const now = new Date();
const STATE = {
  events: {},
  year: now.getFullYear(),
  month: now.getMonth() + 1, // 1~12
  settings: loadSettings(),
};

const cacheKey = () => "aic_events_" + STATE.settings.groupId;
function cacheEvents() { try { localStorage.setItem(cacheKey(), JSON.stringify(STATE.events)); } catch {} }
function loadCache() { try { return JSON.parse(localStorage.getItem(cacheKey()) || "{}") || {}; } catch { return {}; } }

function setConn(ok) {
  const dot = $("status-dot");
  dot.classList.toggle("on", !!ok);
  dot.title = ok ? "실시간 연결됨 · " + STATE.settings.groupId : "연결 안됨";
}

// ── 동기화 (Firebase Realtime DB REST + SSE) ───────────
class Sync {
  constructor(onUpdate) { this.onUpdate = onUpdate; this.es = null; this.poll = null; }
  base() {
    const u = STATE.settings.url.replace(/\/+$/, "");
    return `${u}/calendars/${encodeURIComponent(STATE.settings.groupId)}/events`;
  }
  async load() {
    try {
      const r = await fetch(this.base() + ".json", { cache: "no-store" });
      if (!r.ok) throw 0;
      const j = await r.json();
      return j && typeof j === "object" ? j : {};
    } catch { return null; }
  }
  async save(events) {
    try {
      const r = await fetch(this.base() + ".json", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(events),
      });
      return r.ok;
    } catch { return false; }
  }
  start() {
    this.stop();
    const onMsg = (ev) => {
      try { const m = JSON.parse(ev.data); this.apply(m.path, m.data); } catch {}
      setConn(true);
    };
    try {
      this.es = new EventSource(this.base() + ".json");
      this.es.addEventListener("put", onMsg);
      this.es.addEventListener("patch", onMsg);
      this.es.onopen = () => { setConn(true); this._stopPoll(); };
      this.es.onerror = () => { setConn(false); this._startPoll(); };
    } catch { setConn(false); this._startPoll(); }
  }
  _startPoll() {
    if (this.poll) return;
    this.poll = setInterval(async () => {
      const data = await this.load();
      if (data) { STATE.events = data; cacheEvents(); setConn(true); this.onUpdate(); }
    }, 12000);
  }
  _stopPoll() { if (this.poll) { clearInterval(this.poll); this.poll = null; } }
  stop() { if (this.es) { this.es.close(); this.es = null; } this._stopPoll(); }
  apply(path, data) {
    if (!path || path === "/") {
      STATE.events = data && typeof data === "object" ? data : {};
    } else {
      const parts = path.split("/").filter(Boolean);
      let o = STATE.events;
      for (let i = 0; i < parts.length - 1; i++) {
        if (typeof o[parts[i]] !== "object" || o[parts[i]] === null) o[parts[i]] = {};
        o = o[parts[i]];
      }
      const last = parts[parts.length - 1];
      if (data === null) delete o[last]; else o[last] = data;
    }
    cacheEvents();
    this.onUpdate();
  }
}

const sync = new Sync(() => render());

async function saveAll() {
  cacheEvents();
  render();
  await sync.save(STATE.events);
}

// ── 달력 데이터 가공 ───────────────────────────────────
function buildView() {
  const singles = {}; // key -> [ev]
  const spans = {};    // key -> [{color,title,isStart,important}]
  for (const [startKey, list] of Object.entries(STATE.events)) {
    if (!Array.isArray(list)) continue;
    const startD = parseYmd(startKey);
    if (!startD) continue;
    for (const ev of list) {
      const end = ev && ev.end_date;
      const endD = end ? parseYmd(end) : null;
      if (!endD || endD <= startD) {
        (singles[startKey] ||= []).push(ev);
      } else {
        for (let d = new Date(startD); d <= endD; d.setDate(d.getDate() + 1)) {
          (spans[ymd(d)] ||= []).push({
            color: ev.color || "#a099ff",
            title: ev.title || "",
            isStart: ymd(d) === startKey,
            important: !!ev.important,
          });
        }
      }
    }
  }
  const impFirst = (a, b) => (a.important ? 0 : 1) - (b.important ? 0 : 1);
  for (const k in singles) singles[k].sort(impFirst);
  for (const k in spans) spans[k].sort(impFirst);
  return { singles, spans };
}

// ── 렌더링 ─────────────────────────────────────────────
function render() {
  $("title").textContent = `${STATE.year}년 ${STATE.month}월`;
  const grid = $("grid");
  const { singles, spans } = buildView();

  const first = new Date(STATE.year, STATE.month - 1, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(STATE.year, STATE.month, 0).getDate();

  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(0);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(0);
  const weeks = cells.length / 7;
  grid.style.gridTemplateRows = `repeat(${weeks}, 1fr)`;

  const todayKey = ymd(new Date());
  const MAX = weeks > 5 ? 2 : 3; // 한 칸에 보여줄 최대 항목 수

  let html = "";
  cells.forEach((day, idx) => {
    if (day === 0) { html += `<div class="cell empty"></div>`; return; }
    const col = idx % 7;
    const d = new Date(STATE.year, STATE.month - 1, day);
    const key = ymd(d);
    const cls = ["cell"];
    if (col === 0) cls.push("sun");
    if (col === 6) cls.push("sat");
    if (key === todayKey) cls.push("today");

    const sp = spans[key] || [];
    const sg = singles[key] || [];
    let items = "";
    let shown = 0;
    for (const s of sp) {
      if (shown >= MAX) break;
      if (s.isStart) {
        items += `<div class="chip${s.important ? " imp star" : ""}" style="background:${esc(s.color)}">${esc(s.title)}</div>`;
      } else {
        items += `<div class="bar" style="background:${esc(s.color)}"></div>`;
      }
      shown++;
    }
    for (const ev of sg) {
      if (shown >= MAX) break;
      const t = ev.time && ev.time !== "00:00" ? `[${esc(ev.time)}] ` : "";
      items += `<div class="chip${ev.important ? " imp star" : ""}" style="background:${esc(ev.color || "#a099ff")}">${t}${esc(ev.title || "")}</div>`;
      shown++;
    }
    const total = sp.length + sg.length;
    const more = total > shown ? `<div class="more">+${total - shown}</div>` : "";

    html += `<div class="${cls.join(" ")}" data-key="${key}">
      <div class="daynum">${day}</div>
      <div class="evs">${items}${more}</div>
    </div>`;
  });
  grid.innerHTML = html;
}

// ── 시트(모달) 공통 ────────────────────────────────────
function openSheet(innerHtml) {
  $("sheet").innerHTML = innerHtml;
  $("sheet-bg").classList.add("open");
}
function closeSheet() { $("sheet-bg").classList.remove("open"); }

// ── 날짜 상세 ──────────────────────────────────────────
function openDay(key) {
  const d = parseYmd(key);
  const dow = ["일", "월", "화", "수", "목", "금", "토"][d.getDay()];
  const direct = STATE.events[key] || [];

  // 다른 시작일의 다중일정 중 이 날짜를 포함하는 것(읽기전용)
  const readonly = [];
  for (const [sk, list] of Object.entries(STATE.events)) {
    if (sk === key || !Array.isArray(list)) continue;
    const sd = parseYmd(sk); if (!sd) continue;
    for (const ev of list) {
      const ed = ev.end_date ? parseYmd(ev.end_date) : null;
      if (ed && sd < d && d <= ed) readonly.push(ev);
    }
  }

  let rows = "";
  const sorted = direct
    .map((ev, i) => ({ ev, i }))
    .sort((a, b) => (a.ev.important ? 0 : 1) - (b.ev.important ? 0 : 1));
  for (const { ev, i } of sorted) rows += evRow(ev, i, false);
  for (const ev of readonly) rows += evRow(ev, -1, true);
  if (!rows) rows = `<p class="sub">등록된 일정이 없습니다.</p>`;

  openSheet(`
    <h2>📅 ${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})</h2>
    ${rows}
    <button class="btn-add" id="add-ev">＋ 새 일정 추가</button>
    <div class="btns"><button class="btn ghost" id="close-day">닫기</button></div>
  `);

  $("close-day").onclick = closeSheet;
  $("add-ev").onclick = () => openEditor(key, null);
  $("sheet").querySelectorAll("[data-edit]").forEach((b) => {
    b.onclick = () => openEditor(key, +b.dataset.edit);
  });
}

function evRow(ev, idx, readonly) {
  const meta = [];
  if (ev.time && ev.time !== "00:00") meta.push(ev.time);
  if (ev.end_date) meta.push("~" + ev.end_date);
  if (ev.memo) meta.push(ev.memo);
  const impCls = ev.important ? " imp" : "";
  const star = ev.important ? "★ " : "";
  const editBtn = readonly ? "" : `<button class="ev-edit" data-edit="${idx}">✎</button>`;
  return `<div class="ev-row${readonly ? " readonly" : ""}">
    <span class="ev-dot" style="background:${esc(ev.color || "#a099ff")}"></span>
    <div class="ev-info">
      <div class="ev-title${impCls}">${star}${esc(ev.title || "(제목 없음)")}</div>
      ${meta.length ? `<div class="ev-meta">${esc(meta.join("  ·  "))}</div>` : ""}
    </div>${editBtn}
  </div>`;
}

// ── 일정 추가/수정 ─────────────────────────────────────
function openEditor(key, idx) {
  const editing = idx != null && idx >= 0;
  const ev = editing ? { ...STATE.events[key][idx] } : { color: "#a099ff" };

  const swatches = PRESET_COLORS.map((c) =>
    `<div class="swatch${(ev.color || "#a099ff").toLowerCase() === c ? " sel" : ""}" data-color="${c}" style="background:${c}"></div>`
  ).join("");
  const impOpts = IMPORTANT_LABELS.map((o) =>
    `<option value="${esc(o.label)}"${ev.important === o.label ? " selected" : ""}>${o.label || "없음"}</option>`
  ).join("");

  openSheet(`
    <h2>${editing ? "✏️ 일정 수정" : "➕ 새 일정"}</h2>
    <label class="fld">제목</label>
    <input type="text" id="f-title" value="${esc(ev.title || "")}" placeholder="일정 제목" />
    <label class="fld">시간</label>
    <input type="time" id="f-time" value="${esc(ev.time && ev.time !== "00:00" ? ev.time : "")}" />
    <label class="fld">종료일 (여러 날 일정이면 지정)</label>
    <input type="date" id="f-end" value="${esc(ev.end_date || key)}" min="${key}" />
    <label class="fld">중요 표시</label>
    <select id="f-imp">${impOpts}</select>
    <label class="fld">색상</label>
    <div class="colors" id="f-colors">${swatches}</div>
    <label class="fld">메모</label>
    <textarea id="f-memo" placeholder="메모 (선택)">${esc(ev.memo || "")}</textarea>
    <div class="btns">
      ${editing ? `<button class="btn danger" id="f-del">삭제</button>` : ""}
      <button class="btn ghost" id="f-cancel">취소</button>
      <button class="btn primary" id="f-save">저장</button>
    </div>
  `);

  let chosen = ev.color || "#a099ff";
  $("f-colors").querySelectorAll(".swatch").forEach((sw) => {
    sw.onclick = () => {
      chosen = sw.dataset.color;
      $("f-colors").querySelectorAll(".swatch").forEach((x) => x.classList.remove("sel"));
      sw.classList.add("sel");
    };
  });

  $("f-cancel").onclick = () => openDay(key);
  $("f-save").onclick = () => {
    const title = $("f-title").value.trim();
    if (!title) { $("f-title").focus(); return; }
    const endVal = $("f-end").value;
    const out = {
      title,
      memo: $("f-memo").value.trim(),
      time: $("f-time").value || "00:00",
      color: chosen,
      end_date: endVal && endVal > key ? endVal : "",
      important: $("f-imp").value || "",
    };
    if (!Array.isArray(STATE.events[key])) STATE.events[key] = [];
    if (editing) STATE.events[key][idx] = out;
    else STATE.events[key].push(out);
    saveAll();
    closeSheet();
  };
  if (editing) {
    $("f-del").onclick = () => {
      STATE.events[key].splice(idx, 1);
      if (STATE.events[key].length === 0) delete STATE.events[key];
      saveAll();
      closeSheet();
    };
  }
}

// ── 설정 ───────────────────────────────────────────────
function openSettings() {
  const s = STATE.settings;
  openSheet(`
    <h2>⚙ 설정</h2>
    <p class="sub">같은 <b>그룹 ID</b>를 쓰는 기기끼리 일정이 실시간 공유됩니다. (PC 앱과 동일)</p>
    <label class="fld">그룹 ID</label>
    <input type="text" id="s-group" value="${esc(s.groupId)}" placeholder="예: ARTIN" />
    <label class="fld">Firebase 주소</label>
    <input type="text" id="s-url" value="${esc(s.url)}" />
    <div class="btns">
      <button class="btn ghost" id="s-cancel">취소</button>
      <button class="btn primary" id="s-save">저장</button>
    </div>
    <p class="sub" style="margin-top:16px;text-align:center">버전 ${esc(window.AIC_VERSION || "")}</p>
  `);
  $("s-cancel").onclick = closeSheet;
  $("s-save").onclick = async () => {
    const g = $("s-group").value.trim() || DEFAULTS.groupId;
    const u = $("s-url").value.trim() || DEFAULTS.url;
    STATE.settings = { groupId: g, url: u };
    saveSettings(STATE.settings);
    closeSheet();
    STATE.events = loadCache();
    render();
    sync.start();
    const data = await sync.load();
    if (data) { STATE.events = data; cacheEvents(); render(); }
  };
}

// ── 이벤트 바인딩 ──────────────────────────────────────
$("prev").onclick = () => {
  STATE.month--; if (STATE.month < 1) { STATE.month = 12; STATE.year--; } render();
};
$("next").onclick = () => {
  STATE.month++; if (STATE.month > 12) { STATE.month = 1; STATE.year++; } render();
};
$("today").onclick = () => {
  const t = new Date(); STATE.year = t.getFullYear(); STATE.month = t.getMonth() + 1; render();
};
$("settings").onclick = openSettings;
$("grid").addEventListener("click", (e) => {
  const cell = e.target.closest(".cell:not(.empty)");
  if (cell) openDay(cell.dataset.key);
});
$("sheet-bg").addEventListener("click", (e) => { if (e.target === $("sheet-bg")) closeSheet(); });

// 좌우 스와이프로 월 이동
let touchX = null;
$("grid").addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
$("grid").addEventListener("touchend", (e) => {
  if (touchX == null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) > 60) (dx < 0 ? $("next") : $("prev")).click();
  touchX = null;
});

// ── 부팅 ───────────────────────────────────────────────
(async function boot() {
  STATE.events = loadCache();
  render();
  const data = await sync.load();
  if (data) { STATE.events = data; cacheEvents(); render(); }
  sync.start();
})();

// ── 서비스워커 등록 + 자동 업데이트 ────────────────────
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    const hadController = !!navigator.serviceWorker.controller;
    let reloaded = false;
    navigator.serviceWorker.register("sw.js").then((reg) => {
      reg.update();
      setInterval(() => reg.update(), 60 * 60 * 1000);
      document.addEventListener("visibilitychange", () => { if (!document.hidden) reg.update(); });
    }).catch(() => {});
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!hadController || reloaded) return; // 첫 설치 때는 새로고침 안 함
      reloaded = true;
      $("update-toast").style.display = "block";
      setTimeout(() => location.reload(), 700);
    });
  });
}
