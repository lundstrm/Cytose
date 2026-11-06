"""Collect license texts and dependency versions into an application bundle."""
from __future__ import annotations

import importlib.metadata as metadata
import json
import platform
from pathlib import Path
import shutil
import sys
import sysconfig


def check_attributions(directory: Path) -> None:
    """Check every upstream attribution's local license-file references."""
    base = directory.resolve()
    for attribution in base.rglob('qt_attribution.json'):
        value = json.loads(attribution.read_text(encoding='utf-8'), strict=False)
        for item in value if isinstance(value, list) else [value]:
            references = item.get('LicenseFile', [])
            if isinstance(references, str): references = [references]
            for reference in references:
                target = (attribution.parent / reference).resolve()
                if not target.is_relative_to(base) or not target.is_file():
                    raise RuntimeError(f'Missing upstream license reference: {attribution}: {reference}')


def prepare(destination: Path, root: Path | None = None, bundle: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parent.parent
    destination.mkdir(parents=True, exist_ok=True)
    if bundle:
        # Qt publishes some modules only under GPL/commercial terms. Fail the
        # LGPL build if any are packaged; revisit this list for each Qt release.
        gpl_only = ('qt6canvaspainter', 'qt6coap', 'qt6graphs', 'qt6grpc', 'qt6httpserver',
                    'qt6lottie', 'qt6mqtt', 'qt6networkauth', 'qt6qmlcompiler', 'qt6quick3d',
                    'qt6quicktimeline', 'qt6virtualkeyboard', 'qt6waylandcompositor',
                    'qtcanvaspainter', 'qtcoap', 'qtgraphs', 'qtgrpc', 'qthttpserver',
                    'qtlottie', 'qtmqtt', 'qtnetworkauth', 'qtqmlcompiler', 'qtquick3d',
                    'qtquicktimeline', 'qtvirtualkeyboard', 'qtwaylandcompositor')
        native = sorted(str(path.relative_to(bundle)) for path in bundle.rglob('*')
                        if path.is_file() and not path.is_symlink() and (path.suffix.lower() in ('.dll', '.dylib', '.so') or '.framework/Versions/' in path.as_posix() and path.parent.name == 'A' and path.suffix == ''))
        flagged = [name for name in native if any(token in Path(name).name.lower() for token in gpl_only)]
        if flagged: raise RuntimeError('GPL-only Qt modules need a separate license review: ' + ', '.join(flagged))
        (destination / 'BUNDLED-NATIVE-FILES.txt').write_text('\n'.join(native)+'\n', encoding='utf-8')
    for source, name in ((root / 'LICENSE', 'Cytose-MIT.txt'),
                         (root / 'python/licenses/LGPL-3.0.txt', 'LGPL-3.0.txt'),
                         (root / 'python/licenses/GPL-3.0.txt', 'GPL-3.0.txt'),
                         (root / 'QT_LGPL_AUDIT.md', 'QT-LGPL-AUDIT.md'),
                         (root / 'python/cytose/fonts/OFL.txt', 'Comfortaa-OFL.txt')):
        shutil.copy2(source, destination / name)
    versions = {}
    for package in ('PySide6-Essentials', 'shiboken6', 'numpy', 'pyinstaller'):
        dist = metadata.distribution(package)
        versions[package] = dist.version
        package_dir = destination / package
        for entry in dist.files or ():
            path = str(entry).replace('\\', '/')
            if '.dist-info/licenses/' in path or (path.endswith('.dist-info/METADATA') and package in ('PySide6-Essentials', 'shiboken6')):
                source = Path(dist.locate_file(entry))
                relative = path.split('.dist-info/', 1)[-1]
                target = package_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    candidates = (Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE')
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license:
        shutil.copy2(python_license, destination / 'Python-license.txt')
    # On Homebrew macOS these are bundled by Python's shared library. Their
    # presence varies by Python distribution and platform; audit each build.
    if sys.platform == 'darwin':
        for source, name in ((Path('/opt/homebrew/opt/openssl@3/LICENSE.txt'), 'OpenSSL-license.txt'),
                             (Path('/opt/homebrew/opt/xz/share/doc/xz/COPYING'), 'XZ-COPYING.txt'),
                             (Path('/opt/homebrew/opt/xz/share/doc/xz/COPYING.0BSD'), 'XZ-0BSD.txt'),
                             (Path('/opt/homebrew/opt/mpdecimal/share/doc/mpdecimal/COPYRIGHT.txt'), 'mpdecimal-COPYRIGHT.txt')):
            if source.is_file(): shutil.copy2(source, destination / name)
    from PySide6.QtCore import qVersion
    qt = qVersion(); series = '.'.join(qt.split('.')[:2])
    if qt != '6.12.0' or versions['PySide6-Essentials'] != '6.12.0' or versions['shiboken6'] != '6.12.0':
        raise RuntimeError('Qt or PySide version changed; obtain and audit matching third-party notices before packaging')
    for name in ('qtbase-6.12.0', 'pyside6-6.12.0'):
        source=root / 'python/licenses' / name; check_attributions(source)
        shutil.copytree(source, destination / name, dirs_exist_ok=True)
    text = f'''Cytose includes independently licensed third-party software.

Cytose: MIT; see Cytose-MIT.txt. Comfortaa: SIL OFL 1.1; see Comfortaa-OFL.txt.
Qt for Python (PySide6-Essentials {versions['PySide6-Essentials']}, shiboken6 {versions['shiboken6']}) and Qt {qt} are used under the LGPL version 3. See LGPL-3.0.txt and GPL-3.0.txt. You may modify these libraries and reverse engineer the application for debugging those modifications, as permitted by the LGPL.
Qt is copyright The Qt Company Ltd. and other contributors; see https://www.qt.io/licensing/.

Upstream source releases:
  PySide6/Shiboken: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{versions['PySide6-Essentials']}-src/
  Qt: https://download.qt.io/archive/qt/{series}/{qt}/submodules/
Qt contains additional third-party code: https://doc.qt.io/qt-{series}/licenses-used-in-qt.html
Qt for Python additional notices: https://doc.qt.io/qtforpython-6/licenses.html
Upstream attribution and license files for Qt 6.12.0 and PySide 6.12.0 are in the qtbase-6.12.0 and pyside6-6.12.0 folders.

NumPy {versions['numpy']}: see the NumPy license files in numpy/licenses/.
Python {platform.python_version()}: see Python-license.txt if present.
PyInstaller {versions['pyinstaller']}: see pyinstaller/licenses/ for its license and bundling exception.

See QT-LGPL-AUDIT.md for the replacement test, reproduction steps, and remaining
platform-specific source and distribution checks.
'''
    (destination / 'THIRD-PARTY-NOTICES.txt').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]), bundle=Path(sys.argv[2]) if len(sys.argv)>2 else None)
