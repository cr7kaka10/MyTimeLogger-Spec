# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 获取 qfluentwidgets 资源路径
import os
import qfluentwidgets
_fluent_pkg_dir = os.path.dirname(qfluentwidgets.__file__)

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../assets', 'assets'),
        ('../config', 'config'),
        ('../server', 'server'),
        # PyQt-Fluent-Widgets 资源文件（图标、字体、i18n）
        (os.path.join(_fluent_pkg_dir, 'resource'), 'qfluentwidgets/resource'),
    ],
    hiddenimports=[
        'app.ui.gui',
        'app.ui.fluent_theme',
        'app.ui.activity_panel',
        'app.ui.daily_checklist',
        'app.ui.habit_tracker',
        'app.ui.goals_panel',
        'app.ui.reward_shop',
        'app.ui.reward',
        'app.ui.reward.reward_card',
        'app.ui.reward.timeline_widgets',
        'app.ui.reward.ledger_dialog',
        'app.ui.reward.backpack_dialog',
        'app.ui.reward.reward_shop_window',
        'app.ui.sleep_statistics',
        'app.ui.sleep',
        'app.ui.sleep.sleep_statistics_window',
        'app.ui.sleep.sleep_trend_chart',
        'app.ui.sleep.ai_config_widget',
        'app.core.logic',
        'app.core.hotkeys',
        'app.core.ticktick_sync',
        'app.core.ai_worker',
        'app.core.signal_bus',
        'app.core.simple_timer',
        'app.models.database',
        'app.models.category_manager',
        'app.models.habit_store',
        'app.models.reward_store',
        'app.models.goal_store',
        'app.models.schema',
        'app.utils.utils',
        'app.utils.config',
        'app.utils.report_builder',
        'app.utils.template_loader',
        'qfluentwidgets',
    ],
    hookspath=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MyTimeLogger',
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
    icon='../assets/icons/icon.ico',
)