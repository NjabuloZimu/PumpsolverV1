"""Exercise CSV persistence through the application's existing GUI actions."""

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from pumpsolver.persistence import csv_io


@pytest.fixture
def message_errors(monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: messages.append(args[2]))
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: messages.append(self.text()))
    return messages


@pytest.fixture
def main_window(qt_app, message_errors):
    from pumpsolver.gui.main_window import MyForm
    window = MyForm()
    window.show()
    qt_app.processEvents()
    yield window
    window.close()
    MyForm.windows.remove(window)


@pytest.fixture
def designer(qt_app, message_errors):
    from pumpsolver.gui.pipe_designer import LossesCal
    window = LossesCal("Inlet Pipe Fittings Losses Designer")
    yield window
    window.close()


def _open_path(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), "CSV Files (*.csv)"))


def _save_path(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), "CSV Files (*.csv)"))


def test_main_open_and_save_actions_preserve_full_project(tmp_path, monkeypatch, main_window, project_state, message_errors):
    source, target = tmp_path / "source.csv", tmp_path / "saved.csv"
    csv_io.write_project(source, project_state)
    _open_path(monkeypatch, source)
    main_window.ui.actionOpen.trigger()
    assert main_window.ui.radioButtonInDesigner.isChecked() is False
    assert main_window.ui.labelDesignerStateIn.text() == "Inactive"
    assert main_window.ui.radioButtonOutDesigner.isChecked() is True
    assert main_window.ui.labelDesignerStateOut.text() == "Active"
    assert main_window.ui.labelDensityOut.text() == project_state["parameters"]["out_dens"]
    _save_path(monkeypatch, target.with_suffix(""))
    main_window.ui.actionSave.trigger()
    assert not message_errors
    assert csv_io.read_project(target) == project_state


def test_failed_main_import_keeps_existing_project(tmp_path, monkeypatch, main_window, project_state, message_errors):
    source, before, after = (tmp_path / name for name in ("source.csv", "before.csv", "after.csv"))
    csv_io.write_project(source, project_state)
    _open_path(monkeypatch, source)
    main_window.importCSV()
    _save_path(monkeypatch, before)
    main_window.exportCSV()
    broken = tmp_path / "bad.csv"
    broken.write_text("Section,Side\nparameters,inlet\n", encoding="utf-8")
    _open_path(monkeypatch, broken)
    main_window.importCSV()
    _save_path(monkeypatch, after)
    main_window.exportCSV()
    assert message_errors
    assert csv_io.read_project(before) == csv_io.read_project(after)


def test_designer_smaller_then_empty_segment_import_removes_stale_rows(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    assert designer.ui.tableWidgetPipeSegment.rowCount() == 2
    one_segment = {key: value for key, value in design["segments"].items() if key.startswith("Line Segment 1,")}
    smaller, empty = tmp_path / "smaller.csv", tmp_path / "empty.csv"
    csv_io.write_segments(smaller, one_segment)
    _open_path(monkeypatch, smaller)
    designer.import_data("segment")
    assert designer.ui.tableWidgetPipeSegment.rowCount() == 1
    assert designer.stored_segments == one_segment
    assert all(item["Line Segment"] == 1 for item in designer.list_fittings_by_segment)
    assert all(item["Line Segment"] == 1 for item in designer.lineRoughnessList)
    csv_io.write_segments(empty, {})
    _open_path(monkeypatch, empty)
    designer.import_data("segment")
    assert not message_errors
    assert designer.ui.tableWidgetPipeSegment.rowCount() == 0
    assert designer.stored_segments == {}
    assert designer.list_fittings_by_segment == []
    assert designer.lineRoughnessList == []


def test_designer_invalid_import_preserves_original_data(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    broken = tmp_path / "invalid.csv"
    broken.write_text("Line Segment,Segment Length (m),Segment Diameter (cm)\n1,2.5,10\n2,invalid,8\n", encoding="utf-8")
    _open_path(monkeypatch, broken)
    designer.import_data("segment")
    assert message_errors
    assert designer.stored_segments == design["segments"]
    assert designer.list_fittings_by_segment == design["fittings"]
    assert designer.lineRoughnessList == design["roughness"]


def test_designer_fitting_import_replaces_visible_rows_without_overwriting_data(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    designer.ui.tableWidgetPipeSegment.selectRow(0)
    replacement = [{"Line Segment": 1, "Fitting 1, Fitting Type": "New valve, brass",
                    "Fitting 1, Loss Factor": "0.75"}]
    path = tmp_path / "fittings.csv"
    csv_io.write_fittings(path, replacement)
    _open_path(monkeypatch, path)
    designer.import_data("fittings")
    assert not message_errors
    assert designer.list_fittings_by_segment == replacement
    assert designer.ui.tableWidgetFittings.rowCount() == 1
    assert designer.ui.tableWidgetFittings.item(0, 0).text() == "New valve, brass"
    assert designer.ui.tableWidgetFittings.item(0, 1).text() == "0.75"


def test_designer_roughness_import_preserves_new_selected_value(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    designer.ui.tableWidgetPipeSegment.selectRow(0)
    replacement = [{"Line Segment": 1, "Segment Roughness": "0.125"}]
    path = tmp_path / "roughness.csv"
    csv_io.write_roughness(path, replacement)
    _open_path(monkeypatch, path)
    designer.import_data("roughness")
    assert not message_errors
    assert designer.lineRoughnessList == replacement
    assert designer.ui.comboBoxRoughness.currentText() == "0.125"


def test_designer_rejects_unknown_segment_reference(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    bad = [{"Line Segment": 9, "Fitting 1, Fitting Type": "Valve", "Fitting 1, Loss Factor": "0.5"}]
    path = tmp_path / "unknown-segment.csv"
    csv_io.write_fittings(path, bad)
    _open_path(monkeypatch, path)
    designer.import_data("fittings")
    assert message_errors
    assert designer.list_fittings_by_segment == design["fittings"]


def test_imported_settings_survive_properties_designer_edit_and_save(tmp_path, monkeypatch, main_window, project_state, message_errors):
    from pumpsolver.gui.properties_dialog import Properties
    state = copy.deepcopy(project_state)
    state["parameters"]["designer_status_in"] = True
    main_window.restore_project(state)
    monkeypatch.setattr(Properties, "exec_", lambda self: 0)
    main_window.ui.inletPushButton.click()
    properties = main_window.sub_window
    properties.ui.pushButtonOpenDesigner.click()
    pipe_designer = properties.sub_window_designer
    try:
        assert pipe_designer.ui.lineEditViscosity.text() == state["inlet"]["viscosity"]
        assert pipe_designer.ui.comboBoxTransitionEquation.currentText() == "R.J.S Pigott"
        assert pipe_designer.stored_segments == state["inlet"]["segments"]
        assert pipe_designer.list_fittings_by_segment == state["inlet"]["fittings"]
        assert pipe_designer.lineRoughnessList == state["inlet"]["roughness"]
        pipe_designer.ui.lineEditViscosity.setText("2.75")
        pipe_designer.ui.comboBoxTransitionEquation.setCurrentText("Moody")
        pipe_designer.save()
        properties.save()
        updated = main_window.project_state()
        assert updated["inlet"]["viscosity"] == "2.75"
        assert updated["inlet"]["transition_equation"] == "Moody"
        assert updated["outlet"] == state["outlet"]
        assert updated["inlet"]["segments"] == state["inlet"]["segments"]
        assert updated["inlet"]["fittings"] == state["inlet"]["fittings"]
        assert updated["inlet"]["roughness"] == state["inlet"]["roughness"]
        path = tmp_path / "edited-project.csv"
        _save_path(monkeypatch, path)
        main_window.exportCSV()
        assert csv_io.read_project(path) == updated
        assert not message_errors
    finally:
        pipe_designer.close()
        properties.close()


def test_designer_export_captures_latest_fitting_cell_edit(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
    designer.ui.tableWidgetPipeSegment.selectRow(0)
    designer.ui.tableWidgetFittings.item(0, 1).setText("0.95")
    path = tmp_path / "latest-fittings.csv"
    _save_path(monkeypatch, path)
    designer.export_data("fittings")
    restored = csv_io.read_fittings(path)
    assert restored[0]["Fitting 1, Loss Factor"] == "0.95"
    assert not message_errors


def test_cancelled_main_dialogs_preserve_state(tmp_path, monkeypatch, main_window, project_state, message_errors):
    main_window.restore_project(project_state)
    before = copy.deepcopy(main_window.project_state())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    main_window.importCSV()
    main_window.exportCSV()
    assert main_window.project_state() == before
    assert not message_errors


def test_inactive_manual_loss_survives_repeated_properties_apply(tmp_path, monkeypatch, main_window, project_state, message_errors):
    from pumpsolver.gui.properties_dialog import Properties
    from PyQt5.QtTest import QTest
    main_window.restore_project(project_state)
    monkeypatch.setattr(Properties, "exec_", lambda self: 0)
    main_window.ui.inletPushButton.click()
    properties = main_window.sub_window
    try:
        assert properties.designerStatus is False
        assert properties.ui.lineEditLosses.text() == "0.1"
        properties.enablesave()
        properties.ui.pushButtonApply.click()
        assert properties.ui.lineEditLosses.text() == "0.1"
        properties.ui.lineEditHead.selectAll()
        QTest.keyClicks(properties.ui.lineEditHead, "4.25")
        properties.ui.pushButtonApply.click()
        assert main_window.ui.labelHeadIn.text() == "4.25"
        assert properties.ui.lineEditLosses.text() == "0.1"
        assert main_window.ui.labelLossesIn.text() == "0.1"
        path = tmp_path / "manual-loss-preserved.csv"
        _save_path(monkeypatch, path)
        main_window.exportCSV()
        assert csv_io.read_project(path)["parameters"]["in_loss"] == "0.1"
        assert not message_errors
    finally:
        properties.close()


def test_segment_insert_delete_preserves_associated_data_and_csv(tmp_path, monkeypatch, designer, project_state, message_errors):
    design = copy.deepcopy(project_state["inlet"])
    designer.previously_stored_data(copy.deepcopy(design["segments"]), copy.deepcopy(design["fittings"]), copy.deepcopy(design["roughness"]))
    designer.ui.tableWidgetPipeSegment.selectRow(1)
    designer.ui.pushButtonAddSegment.click()
    assert designer.ui.tableWidgetPipeSegment.rowCount() == 3
    assert designer.stored_segments["Line Segment 2, Segment Length (m)"] == ""
    assert designer.stored_segments["Line Segment 3, Segment Diameter (cm)"] == "8"
    assert designer.list_fittings_by_segment == [
        design["fittings"][0], dict(design["fittings"][1], **{"Line Segment": 3}),
    ]
    assert designer.lineRoughnessList == [
        design["roughness"][0], {"Line Segment": 2, "Segment Roughness": ""},
        dict(design["roughness"][1], **{"Line Segment": 3}),
    ]
    designer.ui.pushButtonDeleteSegment.click()
    assert designer.ui.tableWidgetPipeSegment.rowCount() == 2
    assert designer.stored_segments == design["segments"]
    assert designer.list_fittings_by_segment == design["fittings"]
    assert designer.lineRoughnessList == design["roughness"]
    for identifier, key in (("segment", "segments"), ("fittings", "fittings"), ("roughness", "roughness")):
        path = tmp_path / (key + ".csv")
        _save_path(monkeypatch, path)
        designer.export_data(identifier)
        assert getattr(csv_io, "read_" + key)(path) == design[key]
    assert not message_errors


def test_closing_unsaved_designer_keeps_parent_collections_consistent(tmp_path, monkeypatch, main_window, project_state, message_errors):
    from pumpsolver.gui.properties_dialog import Properties
    state = copy.deepcopy(project_state)
    state["parameters"]["designer_status_in"] = True
    main_window.restore_project(state)
    monkeypatch.setattr(Properties, "exec_", lambda self: 0)
    main_window.ui.inletPushButton.click()
    properties = main_window.sub_window
    properties.ui.pushButtonOpenDesigner.click()
    pipe_designer = properties.sub_window_designer
    try:
        pipe_designer.ui.tableWidgetPipeSegment.selectRow(0)
        pipe_designer.ui.pushButtonAddSegment.click()
        assert pipe_designer.ui.tableWidgetPipeSegment.rowCount() == 3
        pipe_designer.close()
        assert properties.stored_segments == state["inlet"]["segments"]
        assert properties.list_fittings_by_segment == state["inlet"]["fittings"]
        assert properties.lineRoughnessList == state["inlet"]["roughness"]
        properties.ui.pushButtonApply.click()
        assert main_window.project_state()["inlet"] == state["inlet"]
        path = tmp_path / "unsaved-child-closed.csv"
        _save_path(monkeypatch, path)
        main_window.exportCSV()
        assert not message_errors
        assert csv_io.read_project(path)["inlet"] == state["inlet"]
    finally:
        pipe_designer.close()
        properties.close()
