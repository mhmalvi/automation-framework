# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('automation_config.yaml', '.'),
    ('core',               'core'),
    ('movement_adapters',  'movement_adapters'),
    ('utils',              'utils'),
    ('vision',             'vision'),
]
binaries = []
hiddenimports = [
    # Framework internals — must be explicit so PyInstaller finds them
    'core', 'core.behavior_engine', 'core.input_controller',
    'core.movement_engine', 'core.typing_engine',
    'movement_adapters', 'movement_adapters.human_mouse_adapter',
    'movement_adapters.humancursor_adapter', 'movement_adapters.pyclick_adapter',
    'utils', 'utils.config_loader', 'utils.randomness', 'utils.timing_models',
    'utils.window_manager',
    'win32gui', 'win32con', 'win32api', 'win32process', 'pywintypes',
    'vision', 'vision.object_detection', 'vision.screen_capture', 'vision.template_matching',
    # Third-party libs
    'human_mouse', 'human_mouse.mouse',
    'pyclick', 'pyclick.humanclicker', 'pyclick.humancurve',
    'humancursor', 'humancursor.systemcursor',
    'pyautogui', 'pyperclip', 'yaml', 'cv2', 'mss', 'numpy',
    'scipy', 'scipy.spatial',
    'selenium', 'selenium.webdriver', 'selenium.webdriver.chrome',
    'selenium.webdriver.chrome.webdriver', 'selenium.webdriver.remote.webdriver',
    # Anthropic SDK
    'anthropic', 'anthropic.resources', 'anthropic.types',
    'httpx', 'httpcore', 'anyio', 'sniffio',
    'utils.ai_agent',
]
for pkg in ('human_mouse', 'pyclick', 'humancursor', 'selenium', 'anthropic'):
    tmp = collect_all(pkg)
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]


a = Analysis(
    ['gui.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AutomationFramework',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
