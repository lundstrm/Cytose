"""Exercise bundled Qt, NumPy, FCS import, plotting, PDF export and project loading."""
import os
import struct
import sys
import tempfile
from pathlib import Path


def run():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QFontDatabase, QFontInfo
    from PySide6.QtWidgets import QApplication
    from .app import Workspace, configure_font
    app = QApplication([])
    if os.environ.get('CYTOSE_QT_REPLACEMENT_PROBE') == '1':
        from PySide6.QtCore import QFile, qInstallMessageHandler
        messages = []
        previous = qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
        try:
            QFile().read(1)
        finally:
            qInstallMessageHandler(previous)
        assert any('CYTOSE QT PROBE' in message for message in messages), 'Modified QtCore was not used'
    assert configure_font(app), 'Bundled Comfortaa font could not be loaded'
    assert {'Regular', 'Bold'}.issubset(QFontDatabase.styles('Comfortaa'))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = b''.join(struct.pack('<ff', *values) for values in [(1, 2), (3, 4), (5, 6)])
        text = b'|$MODE|L|$PAR|2|$TOT|3|$DATATYPE|F|$BYTEORD|1,2,3,4|$P1N|FSC-A|$P1B|32|$P2N|SSC-A|$P2B|32|$NEXTDATA|0|'
        start, end = 58, 58 + len(text) - 1
        first, last = end + 1, end + len(data)
        header = b'FCS3.1    ' + b''.join(f'{n:8d}'.encode() for n in (start, end, first, last, 0, 0))
        source = root / 'smoke.fcs'
        source.write_bytes(header + text + data)
        workspace = Workspace()
        workspace.import_paths([str(source)])
        workspace.show()
        app.processEvents()
        assert QFontInfo(workspace.active.font()).family() == 'Comfortaa'
        workspace.add_gate(workspace.active, [[0, 0], [4, 0], [4, 5], [0, 5]])
        assert len(workspace.samples) == 1 and workspace.comparison_rows()[0][2] == 3
        workspace.copy_plot(workspace.active)
        assert not app.clipboard().pixmap().isNull()
        image = root / 'plot.png'
        assert workspace.active.grab().save(str(image), 'PNG')
        assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        pdf = root / 'worksheet.pdf'
        workspace.write_worksheet(str(pdf))
        assert pdf.read_bytes().startswith(b'%PDF')
        project = root / 'smoke.cytose'
        workspace.project_path = str(project)
        assert workspace.autosave()
        restored = Workspace()
        restored.load_project(project)
        assert len(restored.gates) == 1 and len(restored.samples) == 1
        workspace.timer.stop()
        restored.timer.stop()
        workspace.close()
        restored.close()
    if sys.stdout is not None:
        print('Bundled workflow smoke test passed', flush=True)
    return 0
