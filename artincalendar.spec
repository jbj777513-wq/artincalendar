# artincalendar.spec
import sys
import os
from pathlib import Path

block_cipher = None
APP_DIR = Path('.')

# Python DLL을 binaries에 직접 포함
import glob
python_dir = os.path.dirname(sys.executable)
py_ver = f"python{sys.version_info.major}{sys.version_info.minor}"

# DLL 자동 탐색
dll_binaries = []
for dll in glob.glob(os.path.join(python_dir, f"python3*.dll")):
    dll_binaries.append((dll, '.'))
# PyQt5 플러그인
for dll in glob.glob(os.path.join(python_dir, "Lib", "site-packages", "PyQt5", "Qt5", "plugins", "platforms", "*.dll")):
    dll_binaries.append((dll, 'PyQt5/Qt5/plugins/platforms'))

a = Analysis(
    ['main.py'],
    pathex=[str(APP_DIR), python_dir],
    binaries=dll_binaries,
    datas=[
        ('fonts/*.ttf',        'fonts'),
        ('logo_white.png',     '.'),
        ('firebase_sync.py',   '.'),
        ('config.py',          '.'),
        ('updater.py',         '.'),
        ('password.py',        '.'),
    ] + ([('password.txt', '.')] if __import__('os').path.exists('password.txt') else []),
    hiddenimports=[
        'PyQt5.QtWidgets',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtSvg',
        'PyQt5.sip',
        'requests',
        'urllib.request',
        'urllib.error',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='아트인캘린더',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 비활성화 (DLL 충돌 방지)
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='아트인캘린더',
)
