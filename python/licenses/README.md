# Qt and PySide source notice provenance

The `qtbase-6.12.0` and `pyside6-6.12.0` folders contain upstream attribution metadata and license/copyright files, preserved at their source-tree paths. They are included in packaged applications; their presence does not imply that every listed optional component is included in the app. License terms for those third-party components remain their own.

- Qt base source: `qtbase-everywhere-src-6.12.0.tar.xz`, from <https://download.qt.io/archive/qt/6.12/6.12.0/submodules/>. SHA-256: `a951bd163c7b80fc6b8c88d7668fb56abf91c152373e13c10666763238131307`.
- Qt for Python source: `pyside-setup-everywhere-src-6.12.0.tar.xz`, from <https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/>. SHA-256: `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751`.

For Qt base, the copies include all `qt_attribution.json` files, the upstream `LICENSES` texts, files starting with `LICENSE`, `LICENCE`, `COPYING` or `COPYRIGHT` beneath third-party directories, and every file referenced by the attribution records. For Qt for Python, they include the upstream `LICENSES` texts, attribution/copyright/license files under `sources/`, and files referenced by those attribution records. These files do not contain the full library source. The full upstream source releases are linked above and in each bundled `Legal/THIRD-PARTY-NOTICES.txt`.

The Qt/PySide version is intentionally pinned to 6.12.0 and packaging rejects other versions until their notices have been audited. Revisit the notices, source correspondence and GPL-only module check when upgrading. The version-specific upstream archives have been checked for availability and these hashes; correspondence to the wheel's exact build configuration and any upstream patches still needs independent verification.
