# Cytose

Cytose is a cross-platform desktop application for basic flow cytometry analysis. It uses Python, NumPy and Qt and runs on macOS, Windows and Linux.

## License

Cytose's own code is licensed under the [MIT License](LICENSE). Third-party components retain their own licenses: in particular, Qt for Python and Qt are used under LGPLv3, NumPy under BSD and other component licenses, and Comfortaa under the SIL Open Font License. The build scripts collect license texts and dependency versions into the application. The [Qt/LGPL audit](QT_LGPL_AUDIT.md) records a macOS modified-library test, reproduction steps and the remaining checks for source correspondence, Windows and signed releases.

## Run

Python 3.10 or newer is required. From the repository root:

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -e ./python
cytose
```

An activated Conda environment can be used instead of `venv`. The editable install picks up later source changes. If you previously installed without `-e`, run the install command above again in the same environment.

Run tests with `python -m unittest discover -s python/tests -v`. The only runtime dependencies are NumPy and PySide6 Essentials (Qt Core, Gui and Widgets). Qt renders density from all visible events, and population statistics use the original values. FCS source files are never changed.

The tests generate their own small FCS fixtures. Locally supplied FCS files, `.cytose` projects, the `fcs_examples` folder and build outputs are ignored by Git; review any data you choose to share separately.

## Available

Start each tab with an existing `.cytose` project, a new autosaved project, or a quick analysis. New projects automatically open FCS files in the chosen folder. New analyses use a dark worksheet by default; saved projects retain their chosen appearance. Open or drop FCS files and folders; use the sample list or wheel to browse; change axes and annotate channels; draw rectangular, elliptical, polygon and quadrant gates (resize an ellipse with its four handles and rotate it with the round handle; drag a quadrant's centre to move it, or any of its four outer handles to tilt that line on its own); drag a gate's name to move its label; move polygon gates and vertices or resize rectangle edges, including beyond the visible plot (gate drawing is clipped to the plot); double-click a gate to open its child population; calculate nested population statistics; and assign and rename conditions. In the analysis plot, click the population title or Y-axis title to choose a population or parameter, and use the MFI/% switch to compare per-sample medians or percentages of parent. Drag condition bars to reorder them; use Export in the Analysis tile to save or copy the per-sample values as a long table (one row per sample, with population and counts) or a wide table (one column per condition in plot order, ready for Prism). In a saved project, CSV files are written next to the project as YYYY-MM-DD_parameter_population_long.csv or _wide.csv. Export a worksheet plot as PNG or a worksheet as PDF, or copy a plot. The worksheet toolbar groups gating tools (1 select, 2 zoom, 3 rectangle, 4 ellipse, 5 polygon, 6 quadrant), view controls (R reset zoom of all plots, B backgating, + and − for bigger or smaller plots, including overlay plots) and editing (Z undo, X redo, L annotate labels). In zoom mode, double-click a plot to go back one zoom level, with Options and T for light/dark on the right; unavailable controls are greyed out. Gating normally applies to every sample. The lock button (U) unlocks the current sample so its gates can be edited on their own, and locking it again returns it to the main gating; C copies its gates to all samples in its condition (available once the sample has a condition) and A makes them the new main gating for all samples; samples with unique gating are marked in blue in the sample list. Compensation (M): choose compensation controls in the dialog (or right-click samples and choose "Use as compensation control"); controls are listed separately and excluded from analysis. The dialog assigns each control's stained detector, estimates spillover from the controls (brightest 10% of events, background from the unstained control; controls are not gated first) or accepts manual values, and previews every channel pair after compensation for a chosen sample and population. Only area (-A) fluorescence channels are compensated, as raw × inverse(spillover); raw values are kept and return when compensation is switched off. Undo is available in the worksheet and with the standard keyboard shortcut; history lasts for the current session. Gate outlines update during a drag, and statistics and backgating refresh on release. Projects store file references, not event data, and missing files can be relinked by matching their original checksum. Right-click a plot for additional actions; choose Histogram (count) as the Y axis for a single-channel histogram. Double-click a condition in the assignment dialog to start an independent tab for its samples.

Overlays compare samples in one figure without changing them. Drag a sample onto another sample to create an overlay, drag more samples onto an overlay to add them, or use New… in the Overlays section (or right-click selected samples) to pick several at once. Selecting an overlay replaces the gated plots with the overlay view; click a sample to return. Overlay plots are square and work like the analysis plot: click the title to choose the population, click an axis title to choose its channel, and use the switches and bars beside the plot (controls that do not apply to the current plot are greyed out) to change between histogram and scatter and adjust the display. Opacity applies to histogram fills, density layers and contour lines. Histograms show event counts, or with Modal each sample scaled to its own highest peak. They share one X range and display scale; the Offset slider moves them from fully overlaid into separated lanes that share one height scale. Scatter overlays draw each sample as a colored density layer with adjustable opacity, or as smoothed equal-probability contours (smoothing widens when fewer events are in view, such as when zoomed) with an adjustable number of levels (the outermost encloses 95% of events), and their axes span the central 99.8% of pooled events. Drag in an overlay plot to zoom (along X for histograms), and double-click or use Reset zoom to return. The legend sets colors, visibility and draw order (the first sample is drawn at the back), lists each sample's event count and median, and double-clicking a sample opens it. Overlays can be renamed, duplicated and deleted, and are saved in projects with their sample references and settings. Copy the plot or per-sample statistics from its context menu.

## Known gaps

Density-gate selection, plot rearrangement, manual axis ranges and configurable display scales are not currently available. Project paths are absolute, so moving projects between computers can require relinking FCS files. Project files from earlier versions of Cytose are not necessarily compatible.

## Architecture

`cytose/core.py` holds FCS parsing, gates, membership, statistics, CSV and project serialization. Event arrays are read-only and event-major; parameters and gates use channel names, not UI coordinates. Gate vertices are raw instrument values; the display transform is signed log10(1+abs(x)). `cytose/histogram.py` computes full-event 1D and 2D counts shared by the worksheet and overlays. `cytose/plot.py` handles plotting and input; `cytose/overlay.py` holds the overlay view, legend and drag-and-drop targets; `cytose/app.py` owns desktop state and widgets. Overlays are stored in the project as plain records that reference sample paths, so relinking a missing file also updates its overlays. FCS 2.0/3.0/3.1 list-mode integer (8/16/32/64-bit), 32-bit float and 64-bit double encodings are supported; multiple datasets per file and packed integers are rejected.

Sample navigation reuses bounded caches of scalar population statistics and up to eight density images per plot. Cache keys include the sample data and the relevant gate hierarchy, so changes to gates or analysis choices trigger fresh calculations. Statistics still use every event; the caches do not store a reduced event dataset.

## Download and run

Ready-to-run apps are attached to each GitHub Release (and to every workflow run under Actions → run → Artifacts):

- **macOS (Apple Silicon):** download `Cytose-macOS-AppleSilicon.zip`, unzip, and move `Cytose.app` to Applications. The app is not notarized, so the first time, right-click it and choose **Open**, then **Open** again (or allow it in System Settings → Privacy & Security). Requires macOS 15 or later.
- **Windows (64-bit):** download `Cytose-Windows-x64.zip`, extract the whole `Cytose` folder, and run `Cytose.exe` inside it. The app is unsigned, so Windows SmartScreen may warn: choose **More info → Run anyway**.

No Python installation is needed for either.

## Distribution

To publish a release, push a version tag (for example `git tag v0.1.0` and `git push origin v0.1.0`). The **Python desktop** workflow runs the tests on macOS, Windows and Linux, builds both apps, and attaches them to a GitHub Release for that tag. Every other push builds the apps as downloadable workflow artifacts.

Builds can also be made locally; build distributable binaries on their target operating system. Signing and notarization must be configured separately.

### Build a Windows app

Run the build on Windows with 64-bit Python 3.10 or newer. From the repository root, using a virtual environment or an activated Conda environment:

```powershell
python -m pip install ./python pyinstaller
python python/build_windows.py
```

The build creates `dist/windows/Cytose/Cytose.exe` and `dist/windows/Cytose-Windows-x64.zip`. Extract the ZIP and keep the `Cytose` folder together; the executable depends on the included libraries. The app does not require Python to be installed on the recipient's machine. The build runs an offscreen bundled workflow smoke test before creating the ZIP. The executable is unsigned and Windows may display a security warning.

The GitHub Actions **Python desktop** workflow also builds and tests the Windows version on a Windows runner and uploads the `Cytose-Windows-x64` artifact. After the repository is pushed to GitHub, run the workflow from the Actions tab or wait for a push; download the artifact from the completed run. This produces an x64 build, not a native Windows ARM build.

### Build a macOS app

On Apple Silicon macOS, install the project and `pyinstaller` in your Python environment, then run `python/build_macos.sh` from the repository root. The resulting `dist/macos/Cytose.app` and `dist/macos/Cytose-macOS-AppleSilicon.zip` contain an ad-hoc signed app. The build removes unused Qt Quick, PDF-viewing, virtual-keyboard, network, optional image-format and translation components, and runs a bundled FCS, gating, project, PNG and PDF-export smoke test. PNG support remains built into Qt. The build must be rerun after source changes to update the distributable app. This build uses a Python runtime requiring macOS 15 or later. Build and test separately on each target architecture; the ZIP is not notarized and macOS may require approval in Privacy & Security. The staging step avoids cloud-sync Finder attributes that can invalidate the bundle signature.
