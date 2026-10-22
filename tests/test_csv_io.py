"""Regression coverage for editable CSV persistence (no Qt dependency)."""

import copy
import csv

import pytest

from pumpsolver.persistence import csv_io


SEGMENT_HEADER = ["Line Segment", "Segment Length (m)", "Segment Diameter (cm)"]
FITTING_HEADER = ["Line Segment", "Fitting", "Fitting Type", "Loss Factor"]
ROUGHNESS_HEADER = ["Line Segment", "Segment Roughness (mm)"]
PROJECT_HEADER = ["Section", "Side", "Line Segment", "Fitting", "Parameter", "Value", "Unit"]


def _read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def _write_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


@pytest.mark.parametrize("kind,header", [
    ("segments", SEGMENT_HEADER), ("fittings", FITTING_HEADER),
    ("roughness", ROUGHNESS_HEADER),
])
def test_standalone_tables_roundtrip_with_fixed_scalar_columns(tmp_path, project_state, kind, header):
    path = tmp_path / (kind + ".csv")
    value = project_state["inlet"][kind]
    getattr(csv_io, "write_" + kind)(path, value)
    assert _read_rows(path)[0] == header
    assert getattr(csv_io, "read_" + kind)(path) == value
    assert all(len(row) == len(header) for row in _read_rows(path))


@pytest.mark.parametrize("kind,empty,header", [
    ("segments", {}, SEGMENT_HEADER), ("fittings", [], FITTING_HEADER),
    ("roughness", [], ROUGHNESS_HEADER),
])
def test_empty_table_retains_schema(tmp_path, kind, empty, header):
    path = tmp_path / (kind + ".csv")
    getattr(csv_io, "write_" + kind)(path, empty)
    assert _read_rows(path) == [header]
    assert getattr(csv_io, "read_" + kind)(path) == empty


def test_project_roundtrip_includes_every_parameter_and_both_designers(tmp_path, project_state):
    path = tmp_path / "project.csv"
    before = copy.deepcopy(project_state)
    csv_io.write_project(path, project_state)
    assert csv_io.read_project(path) == before
    assert project_state == before  # Export must not rewrite caller data.
    rows = _read_rows(path)
    assert rows[0] == PROJECT_HEADER
    assert all(len(row) == len(PROJECT_HEADER) for row in rows)
    assert not any("{'" in cell or "[{'" in cell for row in rows for cell in row)
    assert csv_io.read_project(path)["parameters"]["designer_status_in"] is False


def test_project_with_all_unspecified_values_and_empty_designers(tmp_path, project_state):
    state = project_state
    state["parameters"] = {
        key: (False if key.startswith("designer_status_") else "Unspecified")
        for key in state["parameters"]
    }
    for side in ("inlet", "outlet"):
        state[side] = {"segments": {}, "fittings": [], "roughness": [],
                       "viscosity": "", "transition_equation": "Moody"}
    path = tmp_path / "empty-project.csv"
    csv_io.write_project(path, state)
    assert csv_io.read_project(path) == state


def test_ordinary_csv_edit_updates_numeric_value_and_false_boolean(tmp_path, project_state):
    path = tmp_path / "project.csv"
    csv_io.write_project(path, project_state)
    rows = _read_rows(path)
    for row in rows[1:]:
        if row[0] == "parameters" and row[4] == "out_head":
            row[5] = "25.75"
        if row[0] == "parameters" and row[4] == "designer_status_out":
            row[5] = "false"
    _write_rows(path, rows)
    result = csv_io.read_project(path)
    assert result["parameters"]["out_head"] == "25.75"
    assert result["parameters"]["designer_status_out"] is False


def test_export_is_deterministic_despite_dictionary_order(tmp_path, project_state):
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    csv_io.write_project(first, project_state)
    changed_order = copy.deepcopy(project_state)
    changed_order["parameters"] = dict(reversed(list(changed_order["parameters"].items())))
    changed_order["inlet"]["segments"] = dict(reversed(list(changed_order["inlet"]["segments"].items())))
    changed_order["inlet"]["fittings"].reverse()
    changed_order["inlet"]["roughness"].reverse()
    csv_io.write_project(second, changed_order)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("name,expected", [
    ("pump", "pump.csv"), ("pump.CSV", "pump.CSV"),
    ("pump.csv", "pump.csv"), ("pump.txt", "pump.txt.csv"),
])
def test_save_filename_has_csv_extension(name, expected):
    assert str(csv_io.ensure_csv_path(name)) == expected


@pytest.mark.parametrize("rows", [
    [["wrong", "columns"], ["1", "2"]],
    [SEGMENT_HEADER, ["1", "2"]],
    [SEGMENT_HEADER, ["1", "2", "3", "extra"]],
    [SEGMENT_HEADER, ["1", "2", "3"], ["1", "4", "5"]],
    [SEGMENT_HEADER, ["0", "2", "3"]],
    [SEGMENT_HEADER, ["1.5", "2", "3"]],
    [SEGMENT_HEADER, ["2", "2", "3"]],
    [SEGMENT_HEADER, ["1", "not a number", "3"]],
    [SEGMENT_HEADER, ["1", "nan", "3"]],
    [SEGMENT_HEADER, ["1", "2", "inf"]],
])
def test_rejects_malformed_segment_csv(tmp_path, rows):
    path = tmp_path / "bad.csv"
    _write_rows(path, rows)
    with pytest.raises(ValueError):
        csv_io.read_segments(path)


def test_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        csv_io.read_segments(path)


@pytest.mark.parametrize("rows", [
    [FITTING_HEADER, ["1", "1", "Bend", "0.3"], ["1", "1", "Valve", "0.5"]],
    [FITTING_HEADER, ["1", "2", "Bend", "0.3"]],
    [FITTING_HEADER, ["1", "1", "Bend", "-inf"]],
    [ROUGHNESS_HEADER, ["1", "Smooth Pipe"], ["1", "0.1"]],
    [ROUGHNESS_HEADER, ["1", "unknown material"]],
])
def test_rejects_invalid_fitting_or_roughness_data(tmp_path, rows):
    path = tmp_path / "invalid.csv"
    _write_rows(path, rows)
    reader = csv_io.read_fittings if rows[0] == FITTING_HEADER else csv_io.read_roughness
    with pytest.raises(ValueError):
        reader(path)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "boolean", "nonfinite", "reference"])
def test_rejects_invalid_project_without_silently_losing_rows(tmp_path, project_state, mutation):
    path = tmp_path / "project.csv"
    csv_io.write_project(path, project_state)
    rows = _read_rows(path)
    if mutation == "duplicate":
        rows.append(rows[1].copy())
    elif mutation == "missing":
        rows = [row for row in rows if row[4] != "in_head"]
    elif mutation == "boolean":
        for row in rows:
            if row[4] == "designer_status_in":
                row[5] = "maybe"
    elif mutation == "nonfinite":
        for row in rows:
            if row[4] == "in_head":
                row[5] = "NaN"
    else:
        for row in rows:
            if row[0] == "fittings":
                row[2] = "99"
    _write_rows(path, rows)
    with pytest.raises(ValueError):
        csv_io.read_project(path)


def test_failed_export_preserves_existing_file(tmp_path, project_state):
    path = tmp_path / "existing.csv"
    path.write_text("valuable previous export", encoding="utf-8")
    project_state["parameters"]["in_head"] = "not numeric"
    with pytest.raises(ValueError):
        csv_io.write_project(path, project_state)
    assert path.read_text(encoding="utf-8") == "valuable previous export"


def test_import_accepts_reordered_columns_and_utf8_without_bom(tmp_path):
    path = tmp_path / "edited-fittings.csv"
    path.write_text('Loss Factor,Fitting Type,Fitting,Line Segment\n0.5,"Válve, open",1,1\n', encoding="utf-8")
    assert csv_io.read_fittings(path) == [{
        "Line Segment": 1, "Fitting 1, Fitting Type": "Válve, open", "Fitting 1, Loss Factor": "0.5",
    }]


def test_project_exports_safety_as_head_in_metres(tmp_path, project_state):
    path = tmp_path / "safety-head.csv"
    csv_io.write_project(path, project_state)
    safety = next(row for row in _read_rows(path)[1:]
                  if row[0] == "parameters" and row[4] == "safety")
    assert safety[5:] == ["1.1", "m"]
    assert csv_io.read_project(path) == project_state


def test_legacy_blank_safety_unit_imports_and_resaves_with_metres(tmp_path, project_state):
    legacy, converted = tmp_path / "legacy-safety.csv", tmp_path / "converted.csv"
    csv_io.write_project(legacy, project_state)
    rows = _read_rows(legacy)
    for row in rows[1:]:
        if row[0] == "parameters" and row[4] == "safety":
            row[6] = ""
    _write_rows(legacy, rows)
    restored = csv_io.read_project(legacy)
    assert restored == project_state
    csv_io.write_project(converted, restored)
    safety = next(row for row in _read_rows(converted)[1:]
                  if row[0] == "parameters" and row[4] == "safety")
    assert safety[5:] == ["1.1", "m"]


@pytest.mark.parametrize("section,parameter,unit", [
    ("parameters", "safety", "cm"),
    ("parameters", "safety", "%"),
    ("parameters", "in_head", ""),
    ("parameters", "power", ""),
    ("parameters", "designer_status_in", "m"),
    ("settings", "viscosity", ""),
])
def test_legacy_safety_exception_does_not_allow_other_wrong_units(tmp_path, project_state, section, parameter, unit):
    path = tmp_path / "incorrect-unit.csv"
    csv_io.write_project(path, project_state)
    rows = _read_rows(path)
    for row in rows[1:]:
        if row[0] == section and row[4] == parameter:
            row[6] = unit
    _write_rows(path, rows)
    with pytest.raises(ValueError, match="expected unit"):
        csv_io.read_project(path)
