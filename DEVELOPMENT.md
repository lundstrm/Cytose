# Developing Cytose

Notes for working on the code, running the tests and building the desktop apps. For using Cytose, see the [README](README.md).

## Run from source

Python 3.10 or newer is required. From the repository root:

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -e ./python
cytose
```

An activated Conda environment can be used instead of `venv`. The editable install (`-e`) picks up later source changes. The only runtime dependencies are NumPy and PySide6 Essentials (Qt Core, Gui and Widgets).

## Tests

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s python/tests -v
```

The tests generate their own small FCS fixtures. Run them with a time limit when automating: a test that leaves an autosave timer running or opens a modal dialog can otherwise wait indefinitely under the offscreen platform. Locally supplied FCS files, `.cytose` projects, the `fcs_examples` folder and build outputs are ignored by Git.

## Architecture

- `cytose/core.py` – FCS parsing, gates and membership, statistics, compensation, CSV and project serialization. Event arrays are read-only and event-major; parameters and gates use channel names, not UI coordinates. Gate vertices are raw instrument values; the display transform is signed log10(1+abs(x)). Population masks are cached per sample and full gate definition (including ancestors), so edits never reuse stale masks.
- `cytose/histogram.py` – full-event 1D and 2D counts, smoothing and contour lines shared by the worksheet and overlays. Events outside a display range are counted on the nearest edge.
- `cytose/plot.py` – worksheet plots, gate drawing and editing, and input handling.
- `cytose/overlay.py` – overlay view, legend and drag-and-drop targets.
- `cytose/compensation.py` – compensation dialog and preview.
- `cytose/dialogs.py` – shared dialog footer, rename dialog, styled combo box and remembered file-dialog folders.
- `cytose/app.py` – desktop state, File Browser, worksheet, analysis tile, undo/redo and project files.

FCS 2.0/3.0/3.1 list-mode integer (8/16/32/64-bit), 32-bit float and 64-bit double encodings are supported; multiple datasets per file and packed integers are rejected. Statistics always use every event; caches store scalar results and density images, never a reduced event dataset. Compensation keeps the raw events and replaces only the area (-A) fluorescence columns with raw × inverse(spillover).

Projects store file references, not event data. Per-sample gate copies, overlays, compensation settings and control assignments are stored in the project file and reference samples by path; relinking a missing file updates these references.

## Building the apps

The **Python desktop** GitHub Actions workflow (`.github/workflows/python.yml`) runs the tests on macOS, Windows and Linux for every push and pull request, then builds:

- `Cytose-macOS-AppleSilicon.zip` on a macOS (Apple Silicon) runner, and
- `Cytose-Windows-x64.zip` on a Windows runner.

Both are uploaded as workflow artifacts. Pushing a version tag publishes them as a GitHub Release:

```sh
git tag v0.1.0
git push origin v0.1.0
```

Builds can also be made locally; build each app on its target operating system. Each build runs a bundled offscreen smoke test (FCS import, gating, PNG/PDF export, project save and load) before creating the ZIP.

### Windows

With 64-bit Python 3.10 or newer, from the repository root:

```powershell
python -m pip install ./python pyinstaller
python python/build_windows.py
```

This creates `dist/windows/Cytose/Cytose.exe` and `dist/windows/Cytose-Windows-x64.zip`. The executable depends on the libraries next to it, so the `Cytose` folder must be kept together. The build is x64 (not native Windows ARM) and unsigned.

### macOS

On Apple Silicon, with the project and `pyinstaller` installed:

```sh
sh python/build_macos.sh
```

This creates `dist/macos/Cytose.app` and `dist/macos/Cytose-macOS-AppleSilicon.zip` with an ad-hoc signature. The build removes unused Qt Quick, PDF-viewing, virtual-keyboard, network, optional image-format and translation components, and sets a minimum of macOS 15. The app is not notarized. Staging happens outside the project folder because cloud-sync Finder attributes can invalidate the bundle signature.

## Licensing of bundled components

Cytose's own code is MIT licensed. Qt for Python and Qt are used under LGPLv3, NumPy under BSD and other component licenses, and Comfortaa under the SIL Open Font License. The build scripts collect license texts and dependency versions into the application (`Legal` folder). The [Qt/LGPL audit](QT_LGPL_AUDIT.md) records a macOS modified-library test, reproduction steps and the remaining checks for source correspondence, Windows and signed releases.
