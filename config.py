"""
config.py
설정 파일 로드/저장 (홈 디렉토리의 .artincalendar_config.json)
"""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".artincalendar_config.json"

DEFAULT_CONFIG = {
    "opacity": 0.70,
    "position": {"x": 50, "y": 50},
    "cal_width": 900,
    "cal_height": 750,
    "font_scale": 1.0,
    "color_theme": "black",          # "white" | "black" | "custom"
    "bg_color": "rgba(30,30,30,0.70)",
    "bg_color_hex": "#1e1e1e",
    "accent_color": "#333333",
    "text_color": "#ffffff",
    "firebase": {
        "url": "",
        "group_id": ""
    }
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            # 누락된 키 기본값 채우기
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
