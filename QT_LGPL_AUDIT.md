# Qt / LGPL distribution audit

This records a technical audit, not a legal certification. Cytose's code uses MIT; Qt and PySide/Shiboken are distributed under their own LGPLv3 terms. See `Legal/THIRD-PARTY-NOTICES.txt` inside each packaged build, `LGPL-3.0.txt`, and `GPL-3.0.txt`.

## Audited macOS build

On 5 November 2026, the Apple Silicon build used PySide6-Essentials 6.12.0, shiboken6 6.12.0 and Qt 6.12.0. The package contains dynamically loaded QtCore, QtGui, QtWidgets, QtDBus and QtOpenGL frameworks and Qt platform plugins. It does not contain Qt Virtual Keyboard or other modules on the build script's list of GPL-only Qt modules. The complete native-file list is in the packaged `Legal/BUNDLED-NATIVE-FILES.txt`. Re-audit on dependency changes: the check is based on known names, not a substitute for reviewing all code and third-party components.

The packaged notice names the components and versions, links to the upstream source releases, and includes LGPL/GPL texts, Qt/PySide attribution records and their referenced license texts. The exact upstream archives checked and their SHA-256 hashes are in `python/licenses/README.md` in the source repository. Qt and PySide are pinned to that version; packaging fails if their versions differ or referenced notice files are missing.

## Library replacement check

Run `python python/audit_qt_replacement_macos.py` on macOS after building the app. It copies the app to a temporary directory, changes a diagnostic string inside its QtCore shared library, locally ad-hoc signs the copy, and executes the bundled offscreen import/gating/plot/export/project smoke test. The smoke test invokes QtCore and verifies that the modified diagnostic is observed. The original distribution is not modified.

This check passed on the Apple Silicon app with macOS 27.2: the changed QtCore library was loaded, its changed diagnostic appeared, and the bundled workflow smoke test passed. This verifies execution of a modified binary, not a clean build of Qt from modified source or every possible compatible replacement. The app currently uses an ad-hoc signature without hardened runtime. A future Developer ID / notarized build must be separately tested: signing, hardened runtime and library validation may affect replacement. Windows has not yet been built or tested.

To experiment with another compatible replacement, work on a copy of `Cytose.app`; use matching CPU architecture, Qt 6.12.0 and ABI/build configuration. QtCore is at `Contents/Frameworks/PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore`. A replacement must satisfy the bundle's Mach-O install names, rpaths and dependencies (`otool -L` and `otool -l` can inspect them); replacing a Qt framework may require compatible companion frameworks and plugins. After replacement, remove any incompatible quarantine attributes as appropriate, re-sign the copy locally with `codesign --force --deep --sign - Cytose.app`, verify with `codesign --verify --deep --strict Cytose.app`, and run it. macOS may still require explicit approval for an unnotarized app. The provided audit script demonstrates the exact tested commands; it does not build Qt from source.

## Remaining release checks

- Confirm that the linked upstream source archives and build information correspond exactly to the distributed PySide/Qt wheels, including any wheel-specific patches and configuration, and ensure corresponding source remains available to recipients as required by the applicable license. Version numbers and upstream source links alone do not establish exact correspondence.
- Review the platform-specific native dependency inventory and applicable third-party notices for each release, including components embedded in Qt or Python. The bundled upstream notices are deliberately broad but are not proof of a complete per-binary audit.
- Build and test Windows separately, including replacing a modified Qt DLL, preserving notices, and any effects of code signing or distribution channel terms.
- Review source availability, license terms, signing and redistribution obligations with an appropriately qualified person before treating a release as fully compliant. In particular, do not assume an app-store distribution satisfies library-replacement rights.
