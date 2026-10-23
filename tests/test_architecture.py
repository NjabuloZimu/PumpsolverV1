"""Verify the package boundaries and application composition after the refactor."""

import json
import copy
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def test_core_modules_import_and_calculate_without_qt_from_another_directory(tmp_path):
    source_root = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + os.pathsep + env.get("PYTHONPATH", "")
    script = textwrap.dedent("""
        import json
        import sys
        from pumpsolver.calculations.pipe_losses import PipeLossCalculator
        import pumpsolver.calculations.pump
        from pumpsolver.models import ProjectState
        from pumpsolver.persistence import csv_io
        loss = PipeLossCalculator().darcy_loss_cal(0.02, 1.0, 10.0, 0.1)
        qt_modules = [name for name in sys.modules
                      if name.split('.')[0] in {'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}]
        print(json.dumps({'loss': loss, 'qt_modules': qt_modules}))
    """)
    completed = subprocess.run([sys.executable, "-c", script], cwd=tmp_path,
                               env=env, capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["loss"] > 0
    assert result["qt_modules"] == []


def test_pipe_designer_constructs_each_authored_control_once(qt_app, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QMessageBox, QWidget
    from pumpsolver.gui.pipe_designer import LossesCal

    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: errors.append(args[2]))
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: errors.append(self.text()))
    window = LossesCal("Inlet Pipe Fittings Losses Designer")
    try:
        window.show()
        qt_app.processEvents()
        for widget in vars(window.ui).values():
            if not isinstance(widget, QWidget) or not widget.objectName():
                continue
            matching = window.findChildren(QWidget, widget.objectName(), Qt.FindChildrenRecursively)
            assert matching == [widget], "The designer created duplicate control " + widget.objectName()
        assert not errors
    finally:
        window.close()


def test_source_launcher_runs_resources_csv_and_calculations_from_another_directory(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "launch-report.json"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    # launch.py must locate its own package; inherited source lookup would hide a defect.
    env.pop("PYTHONPATH", None)
    completed = subprocess.run([sys.executable, str(repository / "launch.py"),
                                "--smoke-test", str(report_path), "--quit-after", "50"],
                               cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["version"] == "2.1.0"
    assert report["frozen"] is False
    assert report["resources"] is True
    assert report["csv_roundtrip"] is True
    assert report["calculations"] is True
    assert report["designer_tables"] == 2
    assert report["designer_headers"] is True
    assert report["loss_reconciliation"] is True
    assert report["dialogs"] == 9
    assert report["pump_head_m"] == pytest.approx(25.25)
    assert report["pipe_loss_m"] > 0


def test_main_model_is_authoritative_and_properties_apply_updates_si(qt_app, monkeypatch, project_state):
    from PyQt5.QtTest import QTest
    from pumpsolver.gui.main_window import MainWindow
    from pumpsolver.gui.properties_dialog import Properties

    window = MainWindow()
    properties = None
    try:
        window.restore_project(project_state)
        window.show()
        qt_app.processEvents()
        window.ui.labelDiaIn.setText("999")
        assert window.datafunction()["in_dia"] == "10"
        assert window.project_state() == project_state
        monkeypatch.setattr(Properties, "exec_", lambda self: 0)
        window.ui.inletPushButton.click()
        properties = window.sub_window
        properties.show()
        qt_app.processEvents()
        assert properties.ui.lineEditDia.text() == "10"
        for name, text in (("lineEditDia", "12.5"), ("lineEditVol", "72"), ("lineEditHead", "4.25")):
            editor = getattr(properties.ui, name)
            editor.setFocus()
            editor.selectAll()
            QTest.keyClicks(editor, text)
        properties.ui.pushButtonApply.click()
        assert window.state.parameters.in_diameter_m == pytest.approx(0.125)
        assert window.state.parameters.in_flow_m3_s == pytest.approx(0.02)
        assert window.state.parameters.out_flow_m3_s == pytest.approx(0.02)
        assert window.state.parameters.in_elevation_m == pytest.approx(4.25)
        assert window.ui.labelDiaIn.text() == "12.5"
        assert window.project_state()["inlet"] == project_state["inlet"]
    finally:
        if properties is not None:
            properties.close()
        window.close()
        if window in MainWindow.windows:
            MainWindow.windows.remove(window)


def _active_inlet_state(project_state):
    state = copy.deepcopy(project_state)
    state['parameters'].update(
        in_dia='10', in_loss='0.5', in_flow='36', out_flow='36',
        in_dens='1000', out_dens='1000', designer_status_in=True,
    )
    state['inlet'] = {
        'segments': {'Line Segment 1, Segment Length (m)': '10',
                     'Line Segment 1, Segment Diameter (cm)': '10'},
        'fittings': [],
        'roughness': [{'Line Segment': 1, 'Segment Roughness': 'Smooth Pipe'}],
        'viscosity': '1', 'transition_equation': 'Moody',
    }
    return state


def _edit_designer_draft(designer, app):
    designer.ui.tableWidgetPipeSegment.selectRow(0)
    designer.ui.tableWidgetPipeSegment.item(0, 1).setText('20')
    designer.ui.lineEditDensity.setText('1200')
    designer.ui.lineEditDensity.editingFinished.emit()
    designer.ui.lineEditFlowrate.setText('72')
    designer.ui.lineEditFlowrate.editingFinished.emit()
    app.processEvents()
    assert designer.flush_calculation() is not None


@pytest.mark.parametrize('dismiss', ['close', 'reject'])
def test_abandoned_designer_does_not_leak_scalars_status_or_design(
        qt_app, monkeypatch, project_state, tmp_path, dismiss):
    from PyQt5.QtWidgets import QFileDialog
    from pumpsolver.gui.main_window import MainWindow
    from pumpsolver.gui.properties_dialog import Properties
    from pumpsolver.persistence.csv_io import read_project

    state = _active_inlet_state(project_state)
    main = MainWindow()
    properties = designer = None
    try:
        main.restore_project(state)
        monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
        main.ui.inletPushButton.click()
        properties = main.sub_window
        original_draft = properties.data()
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        _edit_designer_draft(designer, qt_app)
        designer.ui.checkBoxLossesCal.click()
        designer.flush_calculation()
        # Editing and rendering in the child must never alter the parent draft.
        assert properties.data() == original_draft
        assert main.project_state() == state
        getattr(designer, dismiss)()
        qt_app.processEvents()
        properties.ui.pushButtonApply.click()
        assert main.project_state() == state
        destination = tmp_path / 'discarded-designer.csv'
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(destination), ''))
        main.exportCSV()
        assert read_project(destination) == state
    finally:
        if designer is not None:
            designer.close()
        if properties is not None:
            properties.close()
        main.close()
        if main in MainWindow.windows:
            MainWindow.windows.remove(main)


@pytest.mark.parametrize('enabled', [True, False])
def test_designer_close_commits_one_coherent_snapshot_then_properties_apply(
        qt_app, monkeypatch, project_state, enabled):
    from pumpsolver.gui.main_window import MainWindow
    from pumpsolver.gui.properties_dialog import Properties

    state = _active_inlet_state(project_state)
    main = MainWindow()
    properties = designer = None
    try:
        main.restore_project(state)
        monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
        main.ui.inletPushButton.click()
        properties = main.sub_window
        properties.ui.lineEditHead.setText('4.5')
        properties.ui.lineEditPressure.setText('111000')
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        _edit_designer_draft(designer, qt_app)
        if not enabled:
            designer.ui.checkBoxLossesCal.click()
        result = designer.flush_calculation()
        assert main.project_state() == state
        designer.ui.pushButtonClose.click()
        # The committed child snapshot updates the parent draft, not main state.
        assert main.project_state() == state
        assert properties.ui.lineEditHead.text() == '4.5'
        assert properties.ui.lineEditPressure.text() == '111000'
        properties.ui.pushButtonApply.click()
        updated = main.project_state()
        parameters = updated['parameters']
        assert parameters['in_flow'] == parameters['out_flow'] == '72'
        assert parameters['in_dens'] == parameters['out_dens'] == '1200'
        assert parameters['designer_status_in'] is enabled
        assert parameters['in_head'] == '4.5'
        assert parameters['in_press'] == '111000'
        assert updated['inlet']['segments']['Line Segment 1, Segment Diameter (cm)'] == '20'
        if enabled:
            assert parameters['in_dia'] == '20'
            assert float(parameters['in_loss']) == pytest.approx(result.total_loss, rel=1e-5)
        else:
            # An inactive catalogue design must retain the manual pipe values.
            assert parameters['in_dia'] == state['parameters']['in_dia']
            assert parameters['in_loss'] == state['parameters']['in_loss']
    finally:
        if designer is not None:
            designer.close()
        if properties is not None:
            properties.close()
        main.close()
        if main in MainWindow.windows:
            MainWindow.windows.remove(main)


def test_results_dialog_commits_typed_parameters_without_mutating_input(qt_app, project_state):
    from pumpsolver.gui.results_dialog import SolvePage
    from pumpsolver.models import PumpInputs

    source = copy.deepcopy(project_state['parameters'])
    before = copy.deepcopy(source)
    dialog = SolvePage(source)
    commits = []
    try:
        dialog.resultsCommitted.connect(commits.append)
        dialog.closewindow()
        assert len(commits) == 1
        assert isinstance(commits[0], PumpInputs)
        assert commits[0].available_head_m > 0
        assert source == before
    finally:
        dialog.close()


@pytest.mark.parametrize('field', ['lineEditViscosity', 'lineEditFlowrate', 'lineEditDensity'])
def test_designer_incomplete_number_keeps_dialog_and_parent_draft_intact(
        qt_app, monkeypatch, project_state, field):
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QMessageBox
    from pumpsolver.gui.main_window import MainWindow
    from pumpsolver.gui.properties_dialog import Properties

    state = _active_inlet_state(project_state)
    main = MainWindow()
    properties = designer = None
    errors, unhandled = [], []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    # Keep a regression in a Qt slot observable as an assertion, rather than
    # allowing PyQt's default unhandled-exception hook to abort the test process.
    monkeypatch.setattr(sys, 'excepthook', lambda kind, error, traceback: unhandled.append(error))
    try:
        main.restore_project(state)
        monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
        main.ui.inletPushButton.click()
        properties = main.sub_window
        before = properties.data()
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        designer.ui.tableWidgetPipeSegment.selectRow(0)
        qt_app.processEvents()
        assert designer.flush_calculation() is not None
        editor = getattr(designer.ui, field)
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, '.')
        assert designer.ui.pushButtonClose.isEnabled()
        designer.ui.pushButtonClose.click()
        assert errors and 'complete numeric values' in errors[0]
        assert not unhandled
        assert designer.isVisible()
        assert properties.data() == before
        assert main.project_state() == state
        assert designer.save() is False
        # Correcting the same draft permits the normal explicit save/close.
        editor.setText('2')
        assert designer.flush_calculation() is not None
        designer.ui.pushButtonClose.click()
        assert not designer.isVisible()
        assert not unhandled
    finally:
        if designer is not None:
            designer.close()
        if properties is not None:
            properties.close()
        main.close()
        if main in MainWindow.windows:
            MainWindow.windows.remove(main)
