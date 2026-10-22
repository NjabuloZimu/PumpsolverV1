"""Existing 2.0 CSV saves can be imported and converted to editable 2.1 tables."""

import csv

import pytest

from pumpsolver.persistence import csv_io


def _write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


def test_old_key_value_project_restores_false_boolean(tmp_path, project_state):
    path = tmp_path / "old-project.csv"
    _write(path, [["Key", "Value"], *project_state["parameters"].items()])
    restored = csv_io.read_project(path)
    assert restored["parameters"] == project_state["parameters"]
    assert restored["parameters"]["designer_status_in"] is False
    for side in ("inlet", "outlet"):
        assert restored[side] == {"segments": {}, "fittings": [], "roughness": [],
                                  "viscosity": "", "transition_equation": "Moody"}
    converted = tmp_path / "converted.csv"
    csv_io.write_project(converted, restored)
    assert csv_io.read_project(converted) == restored


def test_old_key_value_segments_convert_to_fixed_columns(tmp_path, project_state):
    path = tmp_path / "old-segments.csv"
    expected = project_state["inlet"]["segments"]
    _write(path, [["Key", "Value"], *expected.items()])
    assert csv_io.read_segments(path) == expected
    converted = tmp_path / "segments.csv"
    csv_io.write_segments(converted, csv_io.read_segments(path))
    with converted.open(encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == ["Line Segment", "Segment Length (m)", "Segment Diameter (cm)"]


def test_old_roughness_header_remains_readable(tmp_path):
    path = tmp_path / "old-roughness.csv"
    _write(path, [["Line Segment", "Segment Roughness"], ["1", "Smooth Pipe"], ["2", "0.045"]])
    assert csv_io.read_roughness(path) == [
        {"Line Segment": 1, "Segment Roughness": "Smooth Pipe"},
        {"Line Segment": 2, "Segment Roughness": "0.045"},
    ]


def test_old_wide_fittings_read_arbitrary_column_order(tmp_path):
    path = tmp_path / "old-fittings.csv"
    _write(path, [
        ["Fitting 2, Loss Factor", "Line Segment", "Fitting 1, Fitting Type", "Fitting 2, Fitting Type", "Fitting 1, Loss Factor"],
        ["0.3", "1", 'Válve, "open"', "Bend", "0.15"],
        ["", "2", "Tee", "", "0.8"],
    ])
    expected = [
        {"Line Segment": 1, "Fitting 1, Fitting Type": 'Válve, "open"',
         "Fitting 1, Loss Factor": "0.15", "Fitting 2, Fitting Type": "Bend", "Fitting 2, Loss Factor": "0.3"},
        {"Line Segment": 2, "Fitting 1, Fitting Type": "Tee", "Fitting 1, Loss Factor": "0.8"},
    ]
    assert csv_io.read_fittings(path) == expected
    converted = tmp_path / "converted-fittings.csv"
    csv_io.write_fittings(converted, csv_io.read_fittings(path))
    assert csv_io.read_fittings(converted) == expected


@pytest.mark.parametrize("rows,reader", [
    ([["Key", "Value"], ["Line Segment 1, Segment Length (m)", "2"],
      ["Line Segment 1, Segment Length (m)", "3"]], "read_segments"),
    ([["Line Segment", "Fitting 1, Fitting Type"], ["1", "Valve"]], "read_fittings"),
    ([["Line Segment", "Fitting 1, Fitting Type", "Fitting 1, Loss Factor"],
      ["1", "Valve", "0.2"], ["1", "Bend", "0.3"]], "read_fittings"),
    ([["Line Segment", "Fitting 1, Fitting Type", "Fitting 1, Loss Factor"],
      ["1", "Valve", "NaN"]], "read_fittings"),
])
def test_invalid_legacy_tables_are_rejected(tmp_path, rows, reader):
    path = tmp_path / "bad-legacy.csv"
    _write(path, rows)
    with pytest.raises(ValueError):
        getattr(csv_io, reader)(path)


def test_old_boolean_garbage_is_rejected(tmp_path, project_state):
    path = tmp_path / "old-project.csv"
    parameters = dict(project_state["parameters"], designer_status_in="not boolean")
    _write(path, [["Key", "Value"], *parameters.items()])
    with pytest.raises(ValueError):
        csv_io.read_project(path)
