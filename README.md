# Process Pump and Pipe Losses Solver

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PyQt5-green.svg)](https://pypi.org/project/PyQt5/)

Process Pump and Pipe Losses Solver is a desktop engineering application for pump calculations and pipe friction loss calculations. It is designed to help process and chemical engineers estimate pump requirements, pipe losses, and related hydraulic quantities more quickly and consistently.

Video demo: [https://youtu.be/MTGeXIs2tOM](https://youtu.be/MTGeXIs2tOM)

## Features

- Interactive PyQt5 desktop interface.
- Pump, inlet pipe, and outlet pipe input dialogs.
- Pipe designer for estimating friction losses across pipe segments and fittings.
- Support for major and minor loss calculations.
- Net positive suction head available calculation support.
- Editable CSV import and export for complete projects, pipe segments, fittings, and roughness.
- Engineering calculations using NumPy, SciPy, and SymPy.

## Installation

This project is currently distributed as source code rather than as a packaged installer.

### 1. Clone the repository

```bash
git clone https://github.com/NjabuloZimu/PumpsolverV1.git
cd PumpsolverV1
```

You can also download the project as a ZIP from GitHub by selecting **Code > Download ZIP**.

### 2. Create a virtual environment

On Windows:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python callmain.py
```

The application may take a few seconds to open on first launch.

After creating `.venv`, you can launch the application from PowerShell in the project directory without activating the environment:

```powershell
.\.venv\Scripts\python.exe callmain.py
```

Alternatively, run `.\run.ps1`, which also sets the working directory so image assets load correctly.

## Resizing the interface

The main window and dialogs keep controls, fonts, tables, and images at their designed sizes. Content stays centred horizontally and vertically as the window changes size. Surrounding empty space is used first when the window shrinks; once the content no longer fits, it is clipped equally on opposite sides. There is no scaling, rearrangement, or automatic scrolling.

The main screen needs approximately **1061 × 603 logical pixels of client area** to show its complete content, plus the menu, status bar, and operating system window frame. Other dialogs have their own content size. These are Qt logical pixels, so display scaling can affect how much fits on a physical screen.

`centered_canvas.py` applies the resizing behavior at runtime. The generated GUI modules and `main.ui` retain their original control dimensions.

## Project Structure

The project contains Python source files, PyQt5-generated GUI files, and image assets used by the interface.

Important files include:

- `callmain.py` - main application entry point.
- `project.py` - alternative wrapper entry point and simple test helper functions.
- `callproperties.py` - launches and manages the pump/pipe properties dialog.
- `callmotorProp.py` - launches and manages the motor properties dialog.
- `callsolvePage.py` - solves pump-related variables and NPSH calculations.
- `callLossesCal.py` - manages the pipe designer dialog and user interactions.
- `frictionCalc.py` - performs pipe friction and fitting loss calculations.
- `main.py`, `properties.py`, `solvePage.py`, `lossesCal.py`, `motorProp.py` - PyQt5 Designer generated GUI modules.
- `test_project.py` - basic pytest tests.
- `csv_io.py` - shared CSV schemas, validation, and complete project persistence.
- `CSV_FORMAT.md` - CSV columns, units, editing instructions, and examples.
- `version.py` - application version.
- `requirements.txt` - Python package dependencies.

Image files such as `pump1.png`, `inlet2.png`, `outlet.png`, `moody.png`, and others are used by the GUI and should remain in the project folder.

## Background

Process engineers and chemical engineers often need to move fluids through piping systems at specified flow rates. Pumps are selected and evaluated by accounting for elevation changes, pressure differences, pump efficiency, and friction losses in the piping system.

Pipe friction losses include:

- Major losses caused by wall friction along straight pipe lengths.
- Minor losses caused by fittings, valves, bends, contractions, expansions, and other local flow disturbances.

This application helps automate these calculations and provides a graphical workflow for defining pump and pipe system inputs.

## Current Limitations

- The project is not currently packaged as a standalone installer.
- Users need Python installed to run the application.
- The first launch may take several seconds.
- Unit conversion support is still planned.
- The GUI currently uses PyQt5. A future version may migrate to PySide6.

## Future Development

Planned improvements include:

- Unit selection and automatic unit conversion.
- Pump performance curve plotting.
- Parametric studies.
- Moody diagram position feedback.
- Slurry and solid-fluid particle calculations.
- More flexible inlet and outlet tank loss options.

## Testing

To run the current tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The tests cover engineering calculations, CSV round trips and validation, and the GUI import/export paths. For a headless test run, set `QT_QPA_PLATFORM=offscreen` before running pytest.

## Editing and Saving Data

Use **File > Save** to export the complete project as a CSV file, and **File > Open** to restore it. A project includes the main inputs/results and the inlet and outlet designers' segments, fittings, roughness, viscosity, transition equation, and enabled state.

The three import/export button pairs in the pipe designer use separate CSV tables with fixed columns and one segment or fitting per row. You can edit these files in a spreadsheet or text editor. See [CSV_FORMAT.md](CSV_FORMAT.md) and the [examples](examples/) for the layouts and units. Imports validate the full file before replacing current data.

## Author

Developed by Njabulo Zimu as part of CS50P.

Bug reports, feedback, and feature requests can be shared through the contact details provided in the application's **About** menu.

## Version

Current version: `2.1.0`

Version 2.1.0 standardises CSV layouts and restores complete projects, including designer settings and disabled designer states.
