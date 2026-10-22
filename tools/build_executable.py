"""Build a Windows executable and optionally verify it outside the source tree."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import stat
from tempfile import TemporaryDirectory
from types import CodeType


ROOT = Path(__file__).resolve().parents[1]


def prepare_output(path):
    """Allow PyInstaller to replace its own outputs in OneDrive folders."""
    if not path.exists():
        return
    entries = [path, *path.rglob('*')] if path.is_dir() else [path]
    if any(not entry.resolve().is_relative_to(ROOT) for entry in entries):
        raise RuntimeError(f'Build output is outside this project: {path}')
    # OneDrive can mark generated directories read-only. Windows rmdir then
    # fails even when all files were removed successfully during --clean.
    for entry in entries:
        entry.chmod(stat.S_IREAD | stat.S_IWRITE)


def check_bundled_sources(executable):
    """Catch stale modules and accidental development dependencies in a build."""
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(executable)).open_embedded_archive('PYZ.pyz')
    unwanted = {name.split('.')[0] for name in archive.toc} & {'numpy', 'scipy', 'pytest', '_pytest'}
    if unwanted:
        raise RuntimeError(f'Unexpected bundled dependencies: {sorted(unwanted)}')

    def normalized(code):
        # PyInstaller rewrites filenames for tracebacks. Compare code/constants
        # recursively, independent of the machine's checkout path.
        return code.replace(co_filename='', co_consts=tuple(
            normalized(value) if isinstance(value, CodeType) else value for value in code.co_consts))

    checked = 0
    for name in archive.toc:
        if name != 'pumpsolver' and not name.startswith('pumpsolver.'):
            continue
        path = ROOT / 'src' / Path(*name.split('.'))
        path = path / '__init__.py' if path.is_dir() else path.with_suffix('.py')
        expected = compile(path.read_bytes(), str(path), 'exec', dont_inherit=True, optimize=0)
        if normalized(archive.extract(name)) != normalized(expected):
            raise RuntimeError(f'Bundled module differs from the current source: {name}')
        checked += 1
    if checked < 20:
        raise RuntimeError('Application modules are missing from the executable.')
    print(f'Bundled sources match the checkout ({checked} modules).')


def verify(executable, kind):
    """A GUI build writes a report because a windowed executable has no stdout."""
    check_bundled_sources(executable)
    output = ROOT / '.artifacts' / 'executable-review' / kind
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'smoke-test.json'
    report.unlink(missing_ok=True)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env['QT_QPA_PLATFORM'] = 'windows'
    with TemporaryDirectory(prefix='pumpsolver-frozen-test-') as folder:
        completed = subprocess.run(
            [str(executable), '--smoke-test', str(report),
             '--screenshot', str(output / 'main-window.png')],
            cwd=folder, env=env, timeout=120,
        )
    if completed.returncode or not report.is_file():
        raise RuntimeError(f'Executable smoke test failed (exit {completed.returncode}).')
    result = json.loads(report.read_text(encoding='utf-8'))
    if not result.get('success') or not result.get('frozen'):
        raise RuntimeError(f'Executable smoke test failed: {result}')
    print(f'Executable verified: {report}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onefile', action='store_true', help='produce one self-extracting .exe')
    parser.add_argument('--verify', action='store_true', help='run the built GUI, CSV and calculation checks')
    options = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Build Windows executables on Windows.')
    subprocess.run([sys.executable, str(ROOT / 'tools/generate_ui.py'), '--check'], check=True, cwd=ROOT)
    env = dict(os.environ)
    env['PUMPSOLVER_ONEFILE'] = '1' if options.onefile else '0'
    env['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.artifacts' / 'pyinstaller-cache')
    kind = 'onefile' if options.onefile else 'onedir'
    executable = ROOT / 'dist' / ('PumpSolver.exe' if options.onefile else 'PumpSolver/PumpSolver.exe')
    for output in (ROOT / 'build' / kind, executable if options.onefile else executable.parent,
                   Path(env['PYINSTALLER_CONFIG_DIR'])):
        prepare_output(output)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
        '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / kind),
        str(ROOT / 'packaging/PumpSolver.spec'),
    ], check=True, cwd=ROOT, env=env)
    if options.verify:
        verify(executable, kind)
    print(f'Built: {executable}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
