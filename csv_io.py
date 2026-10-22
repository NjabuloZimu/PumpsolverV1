"""Editable CSV persistence for the pump calculator and pipe designer.

Numbers retain their text representation, so opening and saving a project does
not round values. Empty designer cells are valid unfinished inputs. Main empty
numeric inputs become ``Unspecified``. All readers validate the entire file
before returning; callers can therefore restore it without partial imports.
"""

import csv
import math
import re
from collections import defaultdict


SEGMENT_FIELDS = ("Line Segment", "Segment Length (m)", "Segment Diameter (cm)")
FITTING_FIELDS = ("Line Segment", "Fitting", "Fitting Type", "Loss Factor")
ROUGHNESS_FIELDS = ("Line Segment", "Segment Roughness (mm)")
PROJECT_FIELDS = ("Section", "Side", "Line Segment", "Fitting", "Parameter", "Value", "Unit")
PARAMETER_UNITS = {
    "in_dia": "cm", "in_head": "m", "in_loss": "m", "in_flow": "m^3/h",
    "in_dens": "kg/m^3", "in_press": "Pa", "out_dia": "cm", "out_head": "m",
    "out_loss": "m", "out_flow": "m^3/h", "out_dens": "kg/m^3", "out_press": "Pa",
    "effi": "%", "power": "m", "safety": "", "gravity": "m/s^2",
    "designer_status_in": "", "designer_status_out": "",
}
BOOLEAN_FIELDS = {"designer_status_in", "designer_status_out"}
TRANSITION_EQUATIONS = ("Moody", "R.J.S Pigott")
_SEGMENT_KEY = re.compile(r"Line Segment ([1-9][0-9]*), (Segment Length \(m\)|Segment Diameter \(cm\))\Z")
_FITTING_KEY = re.compile(r"Fitting ([1-9][0-9]*), (Fitting Type|Loss Factor)\Z")


def ensure_csv_path(path):
    """Append .csv when the supplied path does not already end in .csv."""
    path = str(path)
    return path if path.lower().endswith(".csv") else path + ".csv"


def _error(context, message):
    raise ValueError(f"{context}: {message}")


def _text(value, context):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        _error(context, "expected one value per CSV cell")
    return str(value)


def _number(value, context, unspecified=False):
    value = _text(value, context).strip()
    if value == "" or (unspecified and value == "Unspecified"):
        return "Unspecified" if unspecified else ""
    try:
        numeric = float(value)
    except (ValueError, OverflowError):
        _error(context, f"expected a number, got {value!r}")
    if not math.isfinite(numeric):
        _error(context, "number must be finite")
    return value


def _boolean(value, context):
    if isinstance(value, bool):
        return value
    value = _text(value, context).strip().lower()
    if value in ("true", "false"):
        return value == "true"
    _error(context, "expected True or False")


def _index(value, context):
    value = _text(value, context).strip()
    if not re.fullmatch(r"[1-9][0-9]*", value):
        _error(context, "expected a positive whole-number index")
    try:
        return int(value)
    except ValueError:
        _error(context, "index is too large")


def _contiguous(indices, context):
    indices = sorted(indices)
    if indices and indices != list(range(1, len(indices) + 1)):
        _error(context, "indices must start at 1 and have no gaps")


def _read(path):
    reader = None
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header is None:
                _error("CSV header", "file is empty")
            header = tuple(cell.strip() for cell in header)
            if len(set(header)) != len(header):
                _error("CSV header", "duplicate column names")
            rows = []
            for cells in reader:
                line = reader.line_num
                if not cells or not any(cell.strip() for cell in cells):
                    continue
                if len(cells) != len(header):
                    _error(f"CSV line {line}", f"expected {len(header)} cells, got {len(cells)}")
                rows.append((line, dict(zip(header, cells))))
            return header, rows
    except (csv.Error, UnicodeError) as exc:
        line = reader.line_num if reader is not None else 1
        raise ValueError(f"CSV line {line}: invalid CSV: {exc}") from exc


def _header(actual, expected):
    if set(actual) != set(expected):
        _error("CSV header", "expected columns: " + ", ".join(expected))


def _write(path, fields, rows):
    with open(ensure_csv_path(path), "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _segment_rows(data):
    if not isinstance(data, dict):
        _error("Segments", "expected a dictionary")
    grouped = defaultdict(dict)
    for key, value in data.items():
        match = _SEGMENT_KEY.fullmatch(str(key))
        if not match:
            _error("Segments", f"unknown field {key!r}")
        segment, field = int(match[1]), match[2]
        grouped[segment][field] = _number(value, f"Segment {segment}, {field}")
    _contiguous(grouped, "Segments")
    rows = []
    for segment in sorted(grouped):
        if set(grouped[segment]) != set(SEGMENT_FIELDS[1:]):
            _error(f"Segment {segment}", "both length and diameter fields are required; blank values are allowed")
        rows.append({"Line Segment": segment, **grouped[segment]})
    return rows


def _segments_from_rows(rows):
    result = {}
    seen = set()
    for line, row in rows:
        context = f"CSV line {line}"
        segment = _index(row["Line Segment"], context)
        if segment in seen:
            _error(context, f"duplicate segment {segment}")
        seen.add(segment)
        for field in SEGMENT_FIELDS[1:]:
            result[f"Line Segment {segment}, {field}"] = _number(row[field], f"{context}, {field}")
    _contiguous(seen, f"CSV line {rows[-1][0]} (segments)" if rows else "Segments")
    return result


def read_segments(path):
    header, rows = _read(path)
    if set(header) == {"Key", "Value"}:
        data = _legacy_pairs(rows)
        for line, row in rows:
            context = f"CSV line {line}"
            if not _SEGMENT_KEY.fullmatch(row["Key"].strip()):
                _error(context, f"unknown segment field {row['Key']!r}")
            data[row["Key"].strip()] = _number(row["Value"], context)
        try:
            _segment_rows(data)
        except ValueError as exc:
            context = f"CSV line {rows[-1][0]}" if rows else "CSV header"
            raise ValueError(f"{context}: {exc}") from exc
        return data
    _header(header, SEGMENT_FIELDS)
    return _segments_from_rows(rows)


def write_segments(path, data):
    rows = _segment_rows(data)
    _write(path, SEGMENT_FIELDS, rows)


def _fitting_rows(data):
    if not isinstance(data, list):
        _error("Fittings", "expected a list")
    rows = []
    seen_segments = set()
    for group in data:
        if not isinstance(group, dict) or "Line Segment" not in group:
            _error("Fittings", "each group needs a Line Segment")
        segment = _index(group["Line Segment"], "Fittings")
        if segment in seen_segments:
            _error("Fittings", f"duplicate segment {segment}")
        seen_segments.add(segment)
        fittings = defaultdict(dict)
        for key, value in group.items():
            if key == "Line Segment":
                continue
            match = _FITTING_KEY.fullmatch(str(key))
            if not match:
                _error("Fittings", f"unknown field {key!r}")
            fitting, field = int(match[1]), match[2]
            fittings[fitting][field] = (_number(value, f"Segment {segment} fitting {fitting}")
                                        if field == "Loss Factor" else _text(value, "Fitting Type"))
        _contiguous(fittings, f"Segment {segment} fittings")
        if not fittings:
            rows.append({"Line Segment": segment, "Fitting": "", "Fitting Type": "", "Loss Factor": ""})
        for fitting in sorted(fittings):
            if set(fittings[fitting]) != {"Fitting Type", "Loss Factor"}:
                _error(f"Segment {segment} fitting {fitting}", "type and loss factor fields are required")
            rows.append({"Line Segment": segment, "Fitting": fitting, **fittings[fitting]})
    return sorted(rows, key=lambda row: (row["Line Segment"], row["Fitting"] or 0))


def _fittings_from_rows(rows):
    grouped = {}
    seen = set()
    empty_segments = set()
    for line, row in rows:
        context = f"CSV line {line}"
        segment = _index(row["Line Segment"], context)
        group = grouped.setdefault(segment, {"Line Segment": segment})
        if not row["Fitting"].strip():
            if row["Fitting Type"] or row["Loss Factor"] or len(group) > 1 or segment in empty_segments:
                _error(context, "empty fitting group must contain only its segment index")
            empty_segments.add(segment)
            continue
        fitting = _index(row["Fitting"], context)
        if segment in empty_segments or (segment, fitting) in seen:
            _error(context, "duplicate fitting or conflicting empty group")
        seen.add((segment, fitting))
        group[f"Fitting {fitting}, Fitting Type"] = row["Fitting Type"]
        group[f"Fitting {fitting}, Loss Factor"] = _number(row["Loss Factor"], context)
    result = [grouped[segment] for segment in sorted(grouped)]
    try:
        _fitting_rows(result)
    except ValueError as exc:
        raise ValueError(f"CSV line {rows[-1][0]}: {exc}") from exc
    return result


def read_fittings(path):
    header, rows = _read(path)
    if "Line Segment" in header and "Fitting" not in header:
        return _legacy_fittings(header, rows)
    _header(header, FITTING_FIELDS)
    return _fittings_from_rows(rows)


def _legacy_fittings(header, rows):
    """Read 2.0's wide union-of-fittings table; always write the tidy schema."""
    fields = defaultdict(set)
    for column in header:
        if column == "Line Segment":
            continue
        match = _FITTING_KEY.fullmatch(column)
        if not match:
            _error("CSV header", f"unknown legacy fitting field {column!r}")
        fields[int(match[1])].add(match[2])
    _contiguous(fields, "CSV header fittings")
    for fitting, columns in fields.items():
        if columns != {"Fitting Type", "Loss Factor"}:
            _error("CSV header", f"fitting {fitting} requires type and loss factor columns")
    result = []
    seen = set()
    for line, row in rows:
        context = f"CSV line {line}"
        segment = _index(row["Line Segment"], context)
        if segment in seen:
            _error(context, f"duplicate segment {segment}")
        seen.add(segment)
        # The old DictWriter filled missing columns with empty strings. Trim
        # only the trailing slots to retain intentionally unfinished fittings.
        populated = [fitting for fitting in fields
                     if row[f"Fitting {fitting}, Fitting Type"].strip()
                     or row[f"Fitting {fitting}, Loss Factor"].strip()]
        last = max(populated, default=0)
        group = {"Line Segment": segment}
        for fitting in sorted(fields):
            if fitting > last:
                continue
            group[f"Fitting {fitting}, Fitting Type"] = row[f"Fitting {fitting}, Fitting Type"]
            group[f"Fitting {fitting}, Loss Factor"] = _number(row[f"Fitting {fitting}, Loss Factor"], context)
        result.append(group)
    return sorted(result, key=lambda group: group["Line Segment"])


def write_fittings(path, data):
    rows = _fitting_rows(data)
    _write(path, FITTING_FIELDS, rows)


def _roughness(value, context):
    text = _text(value, context).strip()
    return text if text == "Smooth Pipe" else _number(text, context)


def _roughness_rows(data):
    if not isinstance(data, list):
        _error("Roughness", "expected a list")
    result = []
    seen = set()
    for row in data:
        if not isinstance(row, dict) or set(row) != {"Line Segment", "Segment Roughness"}:
            _error("Roughness", "expected Line Segment and Segment Roughness fields")
        segment = _index(row["Line Segment"], "Roughness")
        if segment in seen:
            _error("Roughness", f"duplicate segment {segment}")
        seen.add(segment)
        result.append({"Line Segment": segment, "Segment Roughness (mm)": _roughness(row["Segment Roughness"], f"Segment {segment} roughness")})
    return sorted(result, key=lambda row: row["Line Segment"])


def read_roughness(path):
    header, rows = _read(path)
    legacy = set(header) == {"Line Segment", "Segment Roughness"}
    if not legacy:
        _header(header, ROUGHNESS_FIELDS)
    result = []
    seen = set()
    for line, row in rows:
        context = f"CSV line {line}"
        segment = _index(row["Line Segment"], context)
        if segment in seen:
            _error(context, f"duplicate segment {segment}")
        seen.add(segment)
        field = "Segment Roughness" if legacy else "Segment Roughness (mm)"
        result.append({"Line Segment": segment, "Segment Roughness": _roughness(row[field], context)})
    return sorted(result, key=lambda row: row["Line Segment"])


def write_roughness(path, data):
    rows = _roughness_rows(data)
    _write(path, ROUGHNESS_FIELDS, rows)


def _legacy_pairs(rows):
    result = {}
    for line, row in rows:
        key = row["Key"].strip()
        if key in result:
            _error(f"CSV line {line}", f"duplicate field {key!r}")
        result[key] = row["Value"]
    return result


def _parameters(data):
    if not isinstance(data, dict) or set(data) != set(PARAMETER_UNITS):
        missing = sorted(set(PARAMETER_UNITS) - set(data)) if isinstance(data, dict) else list(PARAMETER_UNITS)
        extra = sorted(set(data) - set(PARAMETER_UNITS)) if isinstance(data, dict) else []
        _error("Project parameters", f"missing fields {missing}; unknown fields {extra}")
    return {key: (_boolean(data[key], key) if key in BOOLEAN_FIELDS else _number(data[key], key, unspecified=True))
            for key in PARAMETER_UNITS}


def validate_parameters(data):
    """Validate and normalize the complete main-window parameter dictionary."""
    return _parameters(data)


def _empty_side():
    return {"segments": {}, "fittings": [], "roughness": [], "viscosity": "", "transition_equation": "Moody"}


def _project_row(section, side="", segment="", fitting="", parameter="", value="", unit=""):
    return dict(zip(PROJECT_FIELDS, (section, side, segment, fitting, parameter, value, unit)))


def _project_rows(state):
    if not isinstance(state, dict) or set(state) != {"parameters", "inlet", "outlet"}:
        _error("Project", "expected parameters, inlet and outlet sections")
    params = _parameters(state["parameters"])
    rows = [_project_row("parameters", parameter=key, value=params[key], unit=unit)
            for key, unit in PARAMETER_UNITS.items()]
    for side in ("inlet", "outlet"):
        data = state[side]
        if not isinstance(data, dict) or set(data) - set(_empty_side()):
            _error(side, "unknown designer settings")
        data = {**_empty_side(), **data}
        viscosity = _number(data["viscosity"], f"{side} viscosity")
        transition = _text(data["transition_equation"], f"{side} transition equation")
        if transition not in TRANSITION_EQUATIONS:
            _error(side, f"unknown transition equation {transition!r}")
        rows.extend((_project_row("settings", side, parameter="viscosity", value=viscosity, unit="cP"),
                     _project_row("settings", side, parameter="transition_equation", value=transition)))
        segment_rows = _segment_rows(data["segments"])
        known_segments = {row["Line Segment"] for row in segment_rows}
        for row in segment_rows:
            for parameter, unit in ((SEGMENT_FIELDS[1], "m"), (SEGMENT_FIELDS[2], "cm")):
                rows.append(_project_row("segments", side, row["Line Segment"], parameter=parameter, value=row[parameter], unit=unit))
        for row in _fitting_rows(data["fittings"]):
            if row["Line Segment"] not in known_segments:
                _error(side, f"fittings reference unknown segment {row['Line Segment']}")
            for parameter in ("Fitting Type", "Loss Factor"):
                rows.append(_project_row("fittings", side, row["Line Segment"], row["Fitting"], parameter, row[parameter]))
        for row in _roughness_rows(data["roughness"]):
            if row["Line Segment"] not in known_segments:
                _error(side, f"roughness references unknown segment {row['Line Segment']}")
            rows.append(_project_row("roughness", side, row["Line Segment"], parameter="Segment Roughness", value=row["Segment Roughness (mm)"], unit="mm"))
    return rows


def write_project(path, state):
    rows = _project_rows(state)
    _write(path, PROJECT_FIELDS, rows)


def read_project(path):
    header, rows = _read(path)
    if set(header) == {"Key", "Value"}:
        parameters = _legacy_pairs(rows)
        for line, row in rows:
            context = f"CSV line {line}"
            key = row["Key"].strip()
            if key not in PARAMETER_UNITS:
                _error(context, f"unknown parameter {key!r}")
            parameters[key] = (_boolean(row["Value"], context) if key in BOOLEAN_FIELDS
                               else _number(row["Value"], context, unspecified=True))
        return {"parameters": _parameters(parameters), "inlet": _empty_side(), "outlet": _empty_side()}
    _header(header, PROJECT_FIELDS)
    state = {"parameters": {}, "inlet": _empty_side(), "outlet": _empty_side()}
    fitting_groups = {side: defaultdict(dict) for side in ("inlet", "outlet")}
    seen = set()
    for line, row in rows:
        context = f"CSV line {line}"
        section, side, parameter = row["Section"].strip(), row["Side"].strip(), row["Parameter"].strip()
        segment_text, fitting_text = row["Line Segment"].strip(), row["Fitting"].strip()
        value, unit = row["Value"], row["Unit"].strip()
        identity = (section, side, segment_text, fitting_text, parameter)
        if identity in seen:
            _error(context, "duplicate field")
        seen.add(identity)
        if section == "parameters":
            if side or segment_text or fitting_text or parameter not in PARAMETER_UNITS:
                _error(context, "invalid project parameter row")
            expected_unit = PARAMETER_UNITS[parameter]
            state["parameters"][parameter] = (_boolean(value, context) if parameter in BOOLEAN_FIELDS else _number(value, context, unspecified=True))
        elif section in ("settings", "segments", "fittings", "roughness"):
            if side not in ("inlet", "outlet"):
                _error(context, "side must be inlet or outlet")
            data = state[side]
            if section == "settings":
                if segment_text or fitting_text or parameter not in ("viscosity", "transition_equation"):
                    _error(context, "invalid designer setting row")
                expected_unit = "cP" if parameter == "viscosity" else ""
                if parameter == "viscosity":
                    data[parameter] = _number(value, context)
                elif value not in TRANSITION_EQUATIONS:
                    _error(context, f"unknown transition equation {value!r}")
                else:
                    data[parameter] = value
            else:
                segment = _index(segment_text, context)
                if section == "segments":
                    if fitting_text or parameter not in SEGMENT_FIELDS[1:]:
                        _error(context, "invalid segment row")
                    expected_unit = "m" if parameter == SEGMENT_FIELDS[1] else "cm"
                    data["segments"][f"Line Segment {segment}, {parameter}"] = _number(value, context)
                elif section == "roughness":
                    if fitting_text or parameter != "Segment Roughness":
                        _error(context, "invalid roughness row")
                    expected_unit = "mm"
                    data["roughness"].append({"Line Segment": segment, "Segment Roughness": _roughness(value, context)})
                else:
                    if parameter not in ("Fitting Type", "Loss Factor"):
                        _error(context, "invalid fitting row")
                    expected_unit = ""
                    group = fitting_groups[side][segment]
                    if fitting_text:
                        fitting = _index(fitting_text, context)
                        group[f"Fitting {fitting}, {parameter}"] = _number(value, context) if parameter == "Loss Factor" else value
                    elif value:
                        _error(context, "fitting value requires a fitting index")
                    else:
                        group.setdefault("_empty", set()).add(parameter)
        else:
            _error(context, f"unknown section {section!r}")
        if unit != expected_unit:
            _error(context, f"expected unit {expected_unit!r}, got {unit!r}")
    for side in ("inlet", "outlet"):
        for segment, group in sorted(fitting_groups[side].items()):
            if "_empty" in group:
                if len(group) != 1 or group["_empty"] != {"Fitting Type", "Loss Factor"}:
                    _error(f"CSV line {rows[-1][0]} ({side})", "incomplete or conflicting empty fitting group")
                group = {}
            state[side]["fittings"].append({"Line Segment": segment, **group})
        state[side]["roughness"].sort(key=lambda row: row["Line Segment"])
    try:
        _project_rows(state)
    except ValueError as exc:
        context = f"CSV line {rows[-1][0]} (project validation)" if rows else "CSV header"
        raise ValueError(f"{context}: {exc}") from exc
    return state
