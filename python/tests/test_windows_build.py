import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from PySide6.QtGui import QImage


class WindowsBuildTests(unittest.TestCase):
    def test_generated_windows_icon_contains_valid_png(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('windows_builder', root / 'python' / 'build_windows.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            icon = Path(directory) / 'Cytose.ico'
            module.make_icon(root / 'Assets' / 'Cytose-icon-edited.png', icon)
            data = icon.read_bytes()
            self.assertEqual(struct.unpack('<HHH', data[:6]), (0, 1, 1))
            width, height, _, _, planes, bits, length, offset = struct.unpack('<BBBBHHII', data[6:22])
            self.assertEqual((width, height, planes, bits, offset), (0, 0, 1, 32, 22))
            image = QImage.fromData(data[offset:offset+length], 'PNG')
            self.assertEqual((image.width(), image.height()), (256, 256))

    def test_build_collects_notices_and_rejects_gpl_only_qt_modules(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('license_builder', root / 'python' / 'prepare_licenses.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); bundle = base / 'bundle'; bundle.mkdir()
            module.prepare(bundle / 'Legal', root, bundle)
            legal = bundle / 'Legal'
            self.assertEqual((legal / 'Cytose-MIT.txt').read_bytes(), (root / 'LICENSE').read_bytes())
            self.assertEqual((root / 'LICENSE').read_bytes(), (root / 'python' / 'LICENSE').read_bytes())
            for path in ('LGPL-3.0.txt', 'GPL-3.0.txt', 'Comfortaa-OFL.txt', 'numpy/licenses/LICENSE.txt', 'THIRD-PARTY-NOTICES.txt', 'QT-LGPL-AUDIT.md'):
                self.assertTrue((legal / path).is_file(), path)
            self.assertTrue((legal / 'qtbase-6.12.0' / 'src' / '3rdparty' / 'harfbuzz-ng' / 'COPYING').is_file())
            self.assertTrue((legal / 'pyside6-6.12.0' / 'sources' / 'pyside6' / 'COPYING').is_file())
            self.assertIn('PySide6-Essentials', (legal / 'THIRD-PARTY-NOTICES.txt').read_text())
            (bundle / 'Qt6VirtualKeyboard.dll').write_bytes(b'placeholder')
            with self.assertRaisesRegex(RuntimeError, 'GPL-only Qt modules'):
                module.prepare(bundle / 'Legal', root, bundle)
            bad = base / 'bad-notices'; bad.mkdir()
            (bad / 'qt_attribution.json').write_text('{"LicenseFile":"missing.txt"}')
            with self.assertRaisesRegex(RuntimeError, 'Missing upstream license reference'):
                module.check_attributions(bad)


if __name__ == '__main__':
    unittest.main()
