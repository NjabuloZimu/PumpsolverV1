# Editable CSV files — version 2.1.0

All exports are comma-separated UTF-8 CSV files with a header row and a UTF-8 BOM for spreadsheet compatibility. Text containing commas, quotes, or line breaks is quoted automatically. Columns are written in a fixed order; imports also accept reordered columns. Save edited files as **CSV UTF-8 (comma delimited)**, retaining the header names. Numbers use a decimal point without thousands separators; scientific notation is accepted. Units are fixed, with no automatic conversion.

Exports add `.csv` when the selected filename does not already end in `.csv`. Cancelling a dialog does nothing. Invalid imports display an error and leave the current data intact. A successful import replaces the selected dataset, including removing rows absent from the imported file. A header-only designer CSV clears that dataset.

## Complete project

**File > Save** and **File > Open** use a single file with these columns:

```csv
Section,Side,Line Segment,Fitting,Parameter,Value,Unit
parameters,,,,in_dia,10,cm
parameters,,,,designer_status_in,False,
settings,inlet,,,viscosity,1.005,cP
settings,inlet,,,transition_equation,Moody,
settings,inlet,,,entrance_enabled,True,
settings,inlet,,,entrance_coefficient,0.5,
settings,inlet,,,exit_enabled,False,
settings,inlet,,,exit_coefficient,1.0,
segments,inlet,1,,Segment Length (m),2.5,m
segments,inlet,1,,Segment Diameter (cm),10,cm
fittings,inlet,1,1,Fitting Type,"Valve, open",
fittings,inlet,1,1,Loss Factor,0.15,
roughness,inlet,1,,Segment Roughness,Smooth Pipe,mm
```

This is a layout excerpt. [examples/project.csv](examples/project.csv) is a complete importable file containing all required main parameters. Each cell contains a single value; indexed dictionaries and lists are never embedded in cells. `Side` is `inlet` or `outlet` for designer data and empty for main parameters. Do not change the `Unit` column to convert values.

The `parameters` section requires these fields:

| Parameter | Meaning | Unit |
| --- | --- | --- |
| `in_dia`, `out_dia` | Pipe diameter at pump inlet/outlet | cm |
| `in_head`, `out_head` | Inlet/outlet elevation | m |
| `in_loss`, `out_loss` | Inlet/outlet friction head loss | m |
| `in_flow`, `out_flow` | Volumetric flow | m^3/h |
| `in_dens`, `out_dens` | Fluid density | kg/m^3 |
| `in_press`, `out_press` | Inlet/outlet pressure | Pa |
| `effi` | Pump efficiency | % |
| `power` | Total available pump head (existing internal field name) | m |
| `safety` | Safety head allowance | m |
| `gravity` | Gravitational acceleration | m/s^2 |
| `designer_status_in`, `designer_status_out` | Designer enabled state | `True` or `False`, empty unit |

Main numeric values may be `Unspecified` or blank; blanks restore as `Unspecified`. Designer geometry and fluid values may be blank for an unfinished design. Numbers must be finite. Boolean text accepts `True`/`False` in any letter case. Empty designs are represented by the absence of their segment, fitting, and roughness rows.

Each side retains these independent `settings` rows:

| Parameter | Value | Unit | Default when omitted |
| --- | --- | --- | --- |
| `viscosity` | Dynamic viscosity | `cP` | `0.89` |
| `transition_equation` | `Moody` or `R.J.S Pigott` | empty | `Moody` |
| `entrance_enabled` | `True` or `False` | empty | inlet `True`, outlet `False` |
| `entrance_coefficient` | Finite number, zero or greater | empty (dimensionless) | `0.5` |
| `exit_enabled` | `True` or `False` | empty | inlet `False`, outlet `True` |
| `exit_coefficient` | Finite number, zero or greater | empty (dimensionless) | `1.0` |

Coefficients are required numbers when their rows are present, even when switched off; their values remain saved for later use. An explicitly blank saved viscosity stays blank. Older projects without the new settings receive the defaults above. Opening a file preserves saved main loss values; recalculating in the designer uses the restored settings and may change losses from older calculations. Earlier versions assumed inlet K = 0.1 for laminar flow or 0.4 otherwise. Enter that coefficient explicitly to reproduce those earlier boundary losses.

The `safety` value is an additive head allowance in metres in the pump and NPSH equations. Earlier project CSV files with an empty `Unit` cell for `safety` remain readable; new exports write `m` without changing the value. All other unit requirements remain strict.

## Pipe segments

```csv
Line Segment,Segment Length (m),Segment Diameter (cm)
1,2.5,10
2,3,8
```

One row per segment. Segment numbers start at 1 and have no gaps. Replacing segments removes fittings and roughness associated with segment numbers that no longer exist. Import segments before their fittings and roughness.

## Fittings

```csv
Line Segment,Fitting,Fitting Type,Loss Factor
1,1,"Valve, open",0.15
1,2,Bend,0.3
2,1,Elbow,0.5
```

One row per fitting. Fitting numbers start at 1 within each segment and have no gaps. Fitting type is free text; loss factor is dimensionless. An empty fitting group may be represented by a segment number with the other three cells blank. Segments without fittings can simply be omitted.

## Roughness

```csv
Line Segment,Segment Roughness (mm)
1,Smooth Pipe
2,0.045
```

One row per segment whose roughness is specified or being edited. Roughness may be a number in millimetres, `Smooth Pipe`, or blank.

## Existing version 2.0 files

The old main and segment `Key,Value` CSV files, wide fitting tables with indexed `Fitting N` columns, and the old `Line Segment,Segment Roughness` layout remain readable. A legacy main file has no saved designer geometry or settings, so opening it restores empty designs. New saves always use the layouts above.

The examples contain illustrative inputs. Edit them for your own system before calculating.
