# Process Pump and Pipe Losses Solver

**Version 2.1.0** is a PyQt5 desktop application for pump-head, pipe-friction and net positive suction head available (NPSHa) calculations. It includes inlet and outlet pipe designers and editable CSV import/export for complete projects and individual design tables.

Developed by Njabulo Zimu as part of CS50P. [Video demonstration](https://youtu.be/MTGeXIs2tOM).

## Install and run from source

Use **Python 3.11 or later**. From the project root, create a virtual environment and install the package. These commands are for PowerShell on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
python launch.py
```

The `dev` extra installs pytest; `build` installs PyInstaller. For application use alone, install with `python -m pip install -e .`. Runtime dependencies are **PyQt5 and SymPy**. Pipe calculations and the Colebrook solver use Python's standard library; NumPy and SciPy are no longer required.

All startup routes use the same `pumpsolver.app.main` function:

```powershell
python launch.py
python -m pumpsolver
.\run.ps1
```

`launch.py` locates the source package relative to its own file. `python -m pumpsolver` uses the installed package. `run.ps1` uses the project's `.venv` interpreter and the source launcher. Resource lookup is independent of the current working directory; images no longer need to be loose files beside the launch command.

## Architecture and data ownership

Application code lives under `src/pumpsolver`. The main window owns one typed `ProjectState`; dialogs edit drafts and commit structured updates. Widgets display that state. The inlet and outlet each retain their own pipe design, viscosity, transition equation and enabled state.

| Location | Responsibility |
| --- | --- |
| `launch.py` | Thin bootstrap for source and frozen startup. |
| `src/pumpsolver/app.py` | Argument handling, QApplication startup, application metadata and smoke checks. |
| `src/pumpsolver/__main__.py` | The `python -m pumpsolver` entry point. |
| `src/pumpsolver/models.py` | Immutable `ProjectState`, `PumpInputs`, `PipeDesign`, `Segment` and `Fitting` data models, with display/CSV adapters. |
| `src/pumpsolver/calculations/pipe_losses.py` | Qt-free pipe losses, friction factors and per-segment results. |
| `src/pumpsolver/calculations/pump.py` | Qt-free pump balance, NPSHa and NPSH comparison calculations. |
| `src/pumpsolver/gui/*.py` | Handwritten window/dialog controllers and the centred-canvas resize helper. |
| `src/pumpsolver/gui/forms/*.ui` | Editable Qt Designer source forms, including recovered forms retained for future editing. |
| `src/pumpsolver/gui/generated/` | Generated UI classes and compiled Qt resources. Regenerate these files from their sources. |
| `src/pumpsolver/gui/assets/` | Source images, icons and the Qt resource collection. |
| `src/pumpsolver/persistence/csv_io.py` | CSV schemas, complete-file validation, import/export and legacy CSV compatibility. |
| `tests/` | Calculation, state-model, CSV, GUI, resource, startup and resize regression tests. |
| `tools/` | Reproducible UI generation and executable-build commands. |
| `examples/` and `CSV_FORMAT.md` | Editable example data and CSV schema documentation. |

Physical values in the typed models use **SI units**. The GUI and CSV files keep their established display units: for example, centimetres for pipe diameter, cubic metres per hour for flow, centipoise for viscosity and percent for efficiency. Adapters perform the conversion at the boundary and preserve the original text of unchanged values, including unfinished designer cells. The GUI and CSV units remain fixed; there is no unit-selection interface.

The `safety` CSV key represents an additive safety-head allowance in metres in the pump and NPSH equations. Older CSV files with its unit left blank remain readable; new exports label it `m`.

The calculation modules import without Qt and can be exercised independently of the desktop application. Pipe calculations return structured results; the pipe designer owns its UI once and displays those results.

The designer shows the selected segment's major pipe-friction loss and complete minor loss (fittings, diameter changes, and the assumed tank entrance or exit). The overall panel sums every segment and shows major + minor = total; **Close** copies that total to Properties. This classification follows the [Hydraulic Institute's loss definitions](https://datatool.pumps.org/pump-fundamentals/sys-curves).

## Editing and saving data

Use **File > Save** to export a complete project as CSV and **File > Open** to restore it. A project includes main inputs/results plus both designers' segments, fittings, roughness, viscosity, transition equation and enabled state. A disabled designer's data is preserved.

The pipe designer's three import/export button pairs use separate segment, fitting and roughness CSV tables. Columns have a fixed order and each cell contains one editable value. Text containing commas or quotes is quoted normally. Files are UTF-8 CSV with a header and a BOM for spreadsheet compatibility.

Save spreadsheet edits as **CSV UTF-8 (comma delimited)**, keeping the documented headers and units. Imports validate the entire file before replacing the selected data. A header-only designer CSV clears that dataset. Legacy version 2.0 CSV layouts remain readable; new exports use the standardised layouts.

See [CSV_FORMAT.md](CSV_FORMAT.md) for columns, units, validation rules and legacy behaviour, and [examples/](examples/) for complete editable files.

## Resizing the interface

The main window and dialogs keep controls, fonts, tables, icons and images at their designed sizes. Content stays centred horizontally and vertically while the window changes size. Empty space is used first when shrinking; once the content no longer fits, it is clipped equally on opposite sides. There is no scaling, rearrangement or automatic scrolling.

The main screen needs approximately **1061 × 603 Qt logical pixels of content area**, plus the menu, status bar and operating-system frame, to show all its controls. Dialogs have their own content sizes. Display scaling changes how these logical dimensions fit on a physical screen.

`src/pumpsolver/gui/centered_canvas.py` implements this behaviour around the authored forms. It preserves control dimensions and tab order, and lets the outer window shrink below the fixed content size.

## Editing forms and resources

Keep behaviour in the handwritten controllers. Edit the `.ui` files in `src/pumpsolver/gui/forms/` and source resources in `src/pumpsolver/gui/assets/`, then regenerate:

```powershell
python tools/generate_ui.py
python tools/generate_ui.py --check
```

The first command generates the UI modules and compiled Qt resource module. `--check` regenerates in memory/temporary storage and fails if the checked-in generated files are stale. The recovered forms remain the editable source of the interface; changes made directly to generated Python files will be overwritten.

## Tests

With the `dev` extra installed:

```powershell
python -m pytest
python tools/generate_ui.py --check
```

For a headless PowerShell test run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest
Remove-Item Env:QT_QPA_PLATFORM
```

The suite covers reference engineering results, SI/display conversion, independent state snapshots, editable and legacy CSV round trips, rejected imports, real dialog Apply/Save paths, a single pipe-designer UI tree, bundled resources, source startup from another directory, and resize/visibility/tab-order invariants. Native desktop rendering is also worth checking when changing forms, fonts or icons.

The launcher exposes the same automated smoke path used by executable verification:

```powershell
python launch.py --smoke-test .artifacts/source-smoke.json
```

It opens the application components, checks resources, a CSV round trip and reference calculations, writes a JSON result and exits.

## Build a Windows executable

Install the `build` extra in the environment used to build the application. Build and verify the default folder distribution with:

```powershell
python tools/build_executable.py --verify
```

The executable is `dist/PumpSolver/PumpSolver.exe`. Distribute the **entire `dist/PumpSolver` folder**, including its bundled dependencies and resources.

For a single executable:

```powershell
python tools/build_executable.py --onefile --verify
```

This produces `dist/PumpSolver.exe`. The single-file build extracts its bundled runtime when it starts.

`--verify` launches the built application using the native Windows platform from an unrelated working directory and runs its resource, dialog, CSV and calculation smoke checks. A successful local build check should be followed by testing the copied distribution on a clean Windows machine before sharing it with users.

## Engineering behaviour and assumptions

The calculation extraction includes targeted corrections to the existing implementation:

- Colebrook calls pass Reynolds number and relative roughness in the correct order. A pure-Python bracketed solver keeps the friction factor positive.
- Segment indexing no longer wraps an outlet's first segment back to its last segment.
- Equal diameters do not count as a contraction or add a transition loss.
- Laminar flow uses `64/Re` for rough as well as smooth pipes, and zero flow produces zero loss.
- Complete calculations reject invalid geometry, viscosity or density with a clear input error; units are converted locally without modifying saved inputs.

The existing Moody/R.J.S. Pigott correlation choices, contraction/expansion coefficient formulas and tank-boundary assumptions are retained. The inlet includes an entrance loss (`K = 0.1` for laminar flow, otherwise `0.4`); the outlet includes a final exit loss (`K = 1`). These assumptions should match the system being analysed. The designer does not yet offer selectable tank-boundary models, slurry/particle models or a general unit-conversion interface.

## Version and author

The application remains **2.1.0**. Its version is defined in `src/pumpsolver/version.py` and used by package metadata and startup. Version 2.1.0 standardises editable CSV persistence and preserves complete project/design settings; the package structure separates data, calculations, persistence and the desktop interface.

Developed by **Njabulo Zimu**. Contact details are available through the application's **About** dialog.
