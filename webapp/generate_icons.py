"""
아트인캘린더 PWA 아이콘 생성기
- 기존 logo_white.png(흰색 로고)의 알파를 이용해 '남색' 로고로 재색칠
- 흰색 배경 위에 중앙 배치하여 각 플랫폼용 아이콘 PNG 출력
실행:  python generate_icons.py
"""
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # webapp/
SRC_LOGO = ROOT.parent / "logo_white.png"        # 기존 흰색 로고
OUT = ROOT / "icons"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = (26, 43, 110)        # #1a2b6e 남색
WHITE = (255, 255, 255)

def navy_logo():
    """흰색 로고를 남색으로 재색칠하고 내용에 맞게 crop."""
    im = Image.open(SRC_LOGO).convert("RGBA")
    alpha = im.split()[3]
    # 남색 단색 + 원본 알파 유지
    navy = Image.new("RGBA", im.size, NAVY + (0,))
    navy.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 20 else 0).getbbox()
    if bbox:
        navy = navy.crop(bbox)
    return navy

def make_icon(size, logo_ratio=0.66, rounded=False, bg=WHITE):
    canvas = Image.new("RGBA", (size, size), bg + (255,))
    logo = navy_logo()
    target_w = int(size * logo_ratio)
    ratio = target_w / logo.width
    target_h = int(logo.height * ratio)
    if target_h > size * logo_ratio:
        target_h = int(size * logo_ratio)
        target_w = int(logo.width * (target_h / logo.height))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    x = (size - target_w) // 2
    y = (size - target_h) // 2
    canvas.alpha_composite(logo, (x, y))
    return canvas.convert("RGB")

def main():
    # 표준 PWA 아이콘 (꽉 찬 정사각형)
    make_icon(192).save(OUT / "icon-192.png")
    make_icon(512).save(OUT / "icon-512.png")
    # maskable: 안전영역 고려해 로고를 더 작게 (가운데 60%)
    make_icon(512, logo_ratio=0.55).save(OUT / "icon-512-maskable.png")
    # iOS 홈화면 아이콘 (180px, 여백 넉넉히)
    make_icon(180, logo_ratio=0.60).save(OUT / "apple-touch-icon.png")
    # favicon
    make_icon(64, logo_ratio=0.78).save(OUT / "favicon-64.png")
    fav = make_icon(64, logo_ratio=0.78)
    fav.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("아이콘 생성 완료:", [p.name for p in sorted(OUT.iterdir())])

if __name__ == "__main__":
    main()
