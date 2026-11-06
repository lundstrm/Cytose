# Cytose

**Cytose** is a free, lightweight desktop app for everyday flow cytometry analysis. Open FCS files, gate your populations, compare conditions and export the numbers, without a licence server or a steep learning curve.

It runs on macOS and Windows (and on Linux from source), and never modifies your original FCS files.

> Cytose is at an early stage (v0.1). It is designed for routine analyses such as marker expression and population percentages across conditions. Please check results that matter against your usual software, and report anything that looks wrong.

## Features

- **Files and projects** – open or drop FCS 2.0/3.0/3.1 files and folders. Projects autosave and store references to your files, not copies of the data.
- **Gating** – rectangle, ellipse (resizable and rotatable), polygon and quadrant gates (with independently tiltable lines). Gates can be nested, renamed, coloured and edited directly on the plot, and named populations are created automatically (*Cells*, *Singlets*, …).
- **Per-sample gating** – gating normally applies to all samples. Unlock a single sample to adjust its gates, copy them to all samples in a condition, or make them the new gating for everything.
- **Statistics** – a population hierarchy with event counts and percentages for the selected sample, computed from every event.
- **Condition comparison** – assign samples to conditions and compare per-sample medians (MFI), means or percentages of parent in a bar plot. Export long tables, or wide tables that paste straight into GraphPad Prism.
- **Overlays** – compare samples in one figure as overlaid or offset histograms (counts or normalised to the peak), density overlays or contour plots.
- **Compensation** – mark single-stained and unstained controls, estimate spillover from them or enter values manually, and check the result in a live preview before applying it.
- **Backgating** – highlight gated populations in their parent plots.
- **Export** – plots as PNG, worksheets as PDF, values as CSV or straight to the clipboard.
- **Quality hints** – warnings for samples with few events in the analysed population, and for samples with their own gating.
- Undo/redo, light and dark themes, and keyboard shortcuts for every tool.

## Download

Get the latest version from the [**Releases**](https://github.com/lundstrm/Cytose/releases) page. No Python installation is needed.

**macOS** (Apple Silicon, macOS 15 or later)
1. Download `Cytose-macOS-AppleSilicon.zip` and unzip it.
2. Move `Cytose.app` to your Applications folder.
3. The first time, **right-click** the app and choose **Open**, then **Open** again. Cytose is not yet notarized by Apple, so macOS asks for this once. You can also allow it under *System Settings → Privacy & Security*.

**Windows** (64-bit)
1. Download `Cytose-Windows-x64.zip` and extract it.
2. Keep the extracted `Cytose` folder together and run `Cytose.exe` inside it.
3. If Windows SmartScreen warns about an unrecognised app, choose **More info → Run anyway**.

## Getting started

1. **Start** – in a new tab choose *New project* (pick where to save; FCS files in that folder open automatically), *Open project* or *Quick analysis*.
2. **Add samples** – click **+** next to *Samples*, or drop FCS files or folders onto the window. Scroll over the sample list to step through samples.
3. **Gate** – pick a tool in the toolbar and draw on the plot. Double-click a gate to open a plot of that population. Click a plot's axis title to change the channel.
4. **Assign conditions** – group samples by condition with *Assign conditions* (or *Auto-Assign* from the file names).
5. **Compare** – in the *Analysis* tile, click the title to choose a population and the axis title to choose a channel; switch between MFI and %. Drag bars to reorder conditions.
6. **Export** – use *Prism* to copy a Prism-ready table, or *Export* for CSV files. Right-click plots for more options.

### Keyboard shortcuts

| Key | Action | Key | Action |
|---|---|---|---|
| 1 | Select / edit | R | Reset zoom of all plots |
| 2 | Zoom (double-click to go back) | B | Backgating |
| 3 | Rectangle gate | + / − | Bigger / smaller plots |
| 4 | Ellipse gate | Z / X | Undo / redo |
| 5 | Polygon gate | L | Channel labels |
| 6 | Quadrant gate | M | Compensation |
| U | Unlock gating for this sample | C | Apply gating to the condition |
| A | Apply gating to all samples | T | Light / dark theme |

## Run from source

With Python 3.10 or newer:

```sh
python -m pip install -e ./python
cytose
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for tests, the code structure and how the apps are built.

## Limitations

- The macOS app is built for Apple Silicon; Intel Macs can run Cytose from source.
- Display scales are chosen automatically (log for fluorescence channels, linear otherwise) and axis ranges cannot yet be typed in.
- Compensation controls are not gated before spillover is estimated, so review the estimated values in the preview.
- Projects store absolute file paths. After moving files or projects between computers, use *Relink missing files*.
- Project files from early development versions may not open in later versions.

## License

Cytose is released under the [MIT License](LICENSE). It is built with [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) under the LGPLv3 and [NumPy](https://numpy.org/), and uses the [Comfortaa](https://fonts.google.com/specimen/Comfortaa) font under the SIL Open Font License. The downloadable apps include the licence texts of all bundled components.
