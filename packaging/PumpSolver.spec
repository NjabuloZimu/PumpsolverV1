# -*- mode: python ; coding: utf-8 -*-
"""One Windows build definition for folder and single-file distributions."""

import os
from pathlib import Path
import runpy

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

root = Path(SPECPATH).parent
version = runpy.run_path(str(root / 'src/pumpsolver/version.py'))['__version__']
version_numbers = tuple(int(part) for part in version.split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_numbers, prodvers=version_numbers,
                      mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904b0', [
            StringStruct('CompanyName', 'Njabulo Zimu'),
            StringStruct('FileDescription', 'Process Pump and Pipe Losses Solver'),
            StringStruct('FileVersion', version),
            StringStruct('InternalName', 'PumpSolver'),
            StringStruct('OriginalFilename', 'PumpSolver.exe'),
            StringStruct('ProductName', 'PumpSolver'),
            StringStruct('ProductVersion', version),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x409, 1200])]),
    ],
)

a = Analysis(
    [str(root / 'launch.py')],
    pathex=[str(root / 'src')],
    binaries=[], datas=[], hiddenimports=[], hookspath=[],
    # The plot is embedded in the existing PyQt5 application. Restrict backend
    # collection so other GUI frameworks and their plugins are not bundled.
    hooksconfig={'matplotlib': {'backends': ['QtAgg']}}, runtime_hooks=[],
    # SymPy has optional integrations; the application's solver needs none of these.
    excludes=['scipy', 'IPython', 'pytest', '_pytest', 'pygments',
              'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
options = dict(
    name='PumpSolver', console=False, debug=False, strip=False, upx=False,
    icon=str(root / 'src/pumpsolver/gui/assets/pumpsolver.ico'), version=version_info,
)
if os.environ.get('PUMPSOLVER_ONEFILE') == '1':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PumpSolver')
