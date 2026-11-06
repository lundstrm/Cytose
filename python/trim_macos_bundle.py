"""Remove unused Qt components from a staged PyInstaller macOS bundle."""
import shutil
import sys
from pathlib import Path

app = Path(sys.argv[1])
if app.name != 'Cytose.app' or not (app / 'Contents' / 'Info.plist').is_file():
    raise SystemExit('Expected a staged Cytose.app bundle')
qt = app / 'Contents' / 'Frameworks' / 'PySide6' / 'Qt'
frameworks = ('QtPdf', 'QtQml', 'QtQmlMeta', 'QtQmlModels', 'QtQmlWorkerScript',
              'QtQuick', 'QtVirtualKeyboard', 'QtVirtualKeyboardQml', 'QtNetwork', 'QtSvg')
paths = [qt / 'lib' / f'{name}.framework' for name in frameworks]
paths += [qt / 'plugins' / 'platforminputcontexts' / 'libqtvirtualkeyboardplugin.dylib',
          qt / 'plugins' / 'imageformats' / 'libqpdf.dylib',
          qt / 'plugins' / 'tls', qt / 'plugins' / 'networkinformation',
          qt / 'plugins' / 'iconengines', qt / 'plugins' / 'imageformats',
          app / 'Contents' / 'Frameworks' / 'PySide6' / 'QtNetwork.abi3.so',
          app / 'Contents' / 'Resources' / 'PySide6' / 'QtNetwork.abi3.so',
          app / 'Contents' / 'Resources' / 'PySide6' / 'Qt' / 'translations',
          qt / 'translations']
for parent in ('Frameworks', 'Resources'):
    paths.extend(app / 'Contents' / parent / name for name in frameworks)
for path in paths:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
