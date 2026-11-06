"""Build a self-contained Cytose folder and ZIP on 64-bit Windows.

Run from the repository root in an environment containing Cytose and PyInstaller.
The application and its Qt/Python dependencies must be kept together.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile


def make_icon(source: Path, destination: Path) -> None:
    """Store a Qt-resized PNG in an ICO container without a Pillow dependency."""
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
    from PySide6.QtGui import QImage

    image = QImage(str(source))
    if image.isNull():
        raise RuntimeError(f'Cannot read app icon: {source}')
    image = image.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, 'PNG'):
        raise RuntimeError('Could not create the Windows app icon')
    png = bytes(data)
    # ICO width/height 0 means 256; the embedded PNG supplies its alpha channel.
    destination.write_bytes(struct.pack('<HHH', 0, 1, 1) +
                            struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png)


def main() -> None:
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise SystemExit('Build this app using 64-bit Python on Windows.')
    from prepare_licenses import prepare
    root = Path(__file__).resolve().parent.parent
    output = root / 'dist' / 'windows'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cytose-windows-') as temporary:
        staging = Path(temporary)
        icon = staging / 'Cytose.ico'
        make_icon(root / 'Assets' / 'Cytose-icon-edited.png', icon)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                   '--windowed', '--onedir', '--name', 'Cytose', '--icon', str(icon),
                   '--add-data', f'{root / "python" / "cytose" / "fonts"}{os.pathsep}cytose/fonts',
                   '--exclude-module', 'PySide6.QtNetwork', '--exclude-module', 'ssl',
                   '--exclude-module', '_ssl', '--paths', str(root / 'python'),
                   '--distpath', str(staging / 'dist'), '--workpath', str(staging / 'work'),
                   '--specpath', str(staging), str(root / 'python' / 'launch.py')]
        subprocess.run(command, check=True, cwd=root)
        bundle = staging / 'dist' / 'Cytose'
        prepare(bundle / 'Legal', root, bundle)
        environment = os.environ.copy()
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        subprocess.run([str(bundle / 'Cytose.exe'), '--bundle-smoke-test'],
                       check=True, cwd=root, env=environment, timeout=120)
        archive = staging / 'Cytose-Windows-x64.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as result:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():
                    result.write(path, Path('Cytose') / path.relative_to(bundle))
        with zipfile.ZipFile(archive) as result:
            if result.testzip() or 'Cytose/Cytose.exe' not in result.namelist():
                raise RuntimeError('Windows ZIP validation failed')
        current = output / 'Cytose'
        if current.exists():
            shutil.move(str(current), str(staging / 'previous'))
        shutil.copytree(bundle, current)
        os.replace(archive, output / archive.name)
    print(f'Windows application: {output / "Cytose" / "Cytose.exe"}')
    print(f'Windows archive: {output / "Cytose-Windows-x64.zip"}')


if __name__ == '__main__':
    main()
