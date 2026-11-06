"""Exercise a modified QtCore in an isolated copy of the packaged macOS app.

This is a binary patch to a diagnostic string, not a source rebuild. It proves
the app can load and execute a changed Qt library after local ad-hoc signing.
"""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import tempfile


def main():
    if sys.platform != 'darwin': raise SystemExit('This audit requires macOS.')
    root=Path(__file__).resolve().parent.parent
    original=Path(sys.argv[1]) if len(sys.argv)>1 else root/'dist/macos/Cytose.app'
    with tempfile.TemporaryDirectory(prefix='cytose-qt-audit-') as directory:
        app=Path(directory)/'Cytose.app'
        subprocess.run(['ditto','--noextattr','--norsrc',str(original),str(app)],check=True)
        library=app/'Contents/Frameworks/PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore'
        before=library.read_bytes(); needle=b'device not open'; marker=b'CYTOSE QT PROBE'
        if len(needle)!=len(marker) or before.count(needle)!=1:
            raise RuntimeError('Expected QtCore diagnostic string not found exactly once')
        after=before.replace(needle,marker); library.write_bytes(after)
        subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
        subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
        env=os.environ.copy(); env['QT_QPA_PLATFORM']='offscreen'; env['CYTOSE_QT_REPLACEMENT_PROBE']='1'
        subprocess.run([str(app/'Contents/MacOS/Cytose'),'--bundle-smoke-test'],env=env,check=True,timeout=120)
        print('Original QtCore SHA-256:',hashlib.sha256(before).hexdigest())
        print('Modified QtCore SHA-256:',hashlib.sha256(after).hexdigest())
        print('The modified library was loaded and its changed diagnostic was observed.')


if __name__ == '__main__': main()
