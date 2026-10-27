from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'packaging' / 'windows_entry.py')],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=[],
    # PyInstaller 6.16 gates this helper on the optional PySide6 meta-package.
    # Essentials supplies the namespace but not that distribution metadata.
    hiddenimports=collect_submodules('digital_child') + ['PySide6.support.deprecated'],
    hookspath=[],
    excludes=['pytest', 'mypy', 'ruff', 'PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='DigitalChild',
    debug=False, strip=False, upx=False, console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DigitalChild')
