"""Exercise boundary settings through the real designer and project save path."""

from math import pi

import pytest
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox

from pumpsolver.calculations.pipe_losses import GRAVITY
from pumpsolver.gui.main_window import MainWindow
from pumpsolver.gui.pipe_designer import LossesCal
from pumpsolver.gui.properties_dialog import Properties
from pumpsolver.models import PipeDesign
from pumpsolver.persistence.csv_io import read_project, write_project


def _configure(designer):
    if not designer.ui.checkBoxLossesCal.isChecked():
        designer.ui.checkBoxLossesCal.click()
    designer.ui.lineEditDensity.setText('998')
    designer.ui.lineEditFlowrate.setText('36')
    designer.previously_stored_data({
        'Line Segment 1, Segment Length (m)': '2',
        'Line Segment 1, Segment Diameter (cm)': '10',
        'Line Segment 2, Segment Length (m)': '3',
        'Line Segment 2, Segment Diameter (cm)': '20',
    }, [], [{'Line Segment': number, 'Segment Roughness': 'Smooth Pipe'}
            for number in (1, 2)])
    designer.ui.tableWidgetPipeSegment.selectRow(0)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_boundary_controls_update_live_and_roundtrip_through_properties_and_csv(
        qt_app, monkeypatch, tmp_path, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = designer = reopened = None
    other = 'outlet' if side == 'inlet' else 'inlet'
    other_design = getattr(main.state, other)
    try:
        getattr(main.ui, f'{side}PushButton').click()
        properties = main.sub_window
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        _configure(designer)
        qt_app.processEvents()
        assert designer.ui.lineEditViscosity.text() == '0.89'
        assert designer.ui.checkBoxEntranceLoss.isChecked() is (side == 'inlet')
        assert designer.ui.checkBoxExitLoss.isChecked() is (side == 'outlet')
        designer.ui.checkBoxEntranceLoss.setChecked(True)
        designer.ui.checkBoxExitLoss.setChecked(True)
        for editor, text in ((designer.ui.lineEditEntranceCoefficient, '2e-1'),
                             (designer.ui.lineEditExitCoefficient, '0.75')):
            editor.setFocus()
            editor.selectAll()
            QTest.keyClicks(editor, text)
        qt_app.processEvents()
        result = designer._last_result
        # Independent reference from Q/A, using different first/last diameters.
        entry_head = (0.01 / (pi * 0.1 ** 2 / 4)) ** 2 / (2 * GRAVITY)
        exit_head = (0.01 / (pi * 0.2 ** 2 / 4)) ** 2 / (2 * GRAVITY)
        assert result.entrance_loss == pytest.approx(0.2 * entry_head)
        assert result.exit_loss == pytest.approx(0.75 * exit_head)
        assert float(designer.ui.lineEditEntranceLoss.text()) == pytest.approx(result.entrance_loss, rel=1e-5)
        assert float(designer.ui.lineEditExitLoss.text()) == pytest.approx(result.exit_loss, rel=1e-5)
        total = result.total_loss
        # Off removes only that end's contribution and retains its coefficient.
        designer.ui.checkBoxEntranceLoss.click()
        qt_app.processEvents()
        assert not designer.ui.lineEditEntranceCoefficient.isEnabled()
        assert designer.ui.lineEditEntranceCoefficient.text() == '2e-1'
        assert designer.ui.lineEditEntranceLoss.text() == '0.00000'
        assert designer._last_result.total_loss == pytest.approx(total - 0.2 * entry_head)
        assert getattr(main.state, side).segments == ()
        designer.ui.pushButtonClose.click()
        copied = float(properties.ui.lineEditLosses.text())
        assert copied == pytest.approx(total - 0.2 * entry_head, rel=1e-5)
        properties.ui.pushButtonApply.click()
        assert getattr(main.state, other) == other_design
        destination = tmp_path / 'boundary-project.csv'
        write_project(destination, main.project_state())
        saved = read_project(destination)
        assert saved == main.project_state()
        assert saved[side]['entrance_enabled'] is False
        assert saved[side]['entrance_coefficient'] == '2e-1'
        assert saved[side]['exit_enabled'] is True
        assert saved[side]['exit_coefficient'] == '0.75'
        main.restore_project(saved)
        getattr(main.ui, f'{side}PushButton').click()
        reopened = main.sub_window
        reopened.ui.pushButtonOpenDesigner.click()
        restored = reopened.sub_window_designer
        assert restored.ui.lineEditEntranceCoefficient.text() == '2e-1'
        assert not restored.ui.checkBoxEntranceLoss.isChecked()
        assert restored.ui.lineEditExitCoefficient.text() == '0.75'
        assert restored.ui.checkBoxExitLoss.isChecked()
        assert restored.flush_calculation().total_loss == pytest.approx(copied, rel=1e-5)
        restored.ui.pushButtonBoundaryInfo.click()
        assert restored.boundary_info.isVisible()
        assert restored.boundary_info.parentWidget() is restored
        restored.boundary_info.ui.pushButtonClose.click()
    finally:
        if reopened is not None:
            reopened.sub_window_designer.close()
            reopened.close()
        if designer is not None:
            designer.close()
        if properties is not None:
            properties.close()
        main.close()
        MainWindow.windows.remove(main)


@pytest.mark.parametrize('field', ['lineEditEntranceCoefficient', 'lineEditExitCoefficient'])
@pytest.mark.parametrize('value', ['', '.', '-0.1', 'nan', 'inf'])
def test_invalid_boundary_coefficient_clears_stale_results_and_cannot_commit(
        qt_app, monkeypatch, field, value):
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    designer = LossesCal('Boundary validation')
    commits = []
    designer.designCommitted.connect(commits.append)
    try:
        _configure(designer)
        assert designer.flush_calculation() is not None
        getattr(designer.ui, field).setText(value)
        qt_app.processEvents()
        assert designer._last_result is None
        assert designer.ui.lineEditEntranceLoss.text() == ''
        assert designer.ui.lineEditExitLoss.text() == ''
        assert designer.ui.labelOverallSummary.text() == ''
        assert not designer.ui.pushButtonClose.isEnabled()
        assert designer.save() is False
        assert not commits and errors
        getattr(designer.ui, field).setText('0.25')
        assert designer.flush_calculation() is not None
        assert designer.save() is True
        assert len(commits) == 1
    finally:
        designer.close()


def test_disabling_designer_preserves_boundary_draft_and_clears_results(qt_app):
    designer = LossesCal('Disabled boundary settings')
    try:
        _configure(designer)
        designer.ui.lineEditEntranceCoefficient.setText('0.12')
        assert designer.flush_calculation() is not None
        designer.ui.checkBoxLossesCal.click()
        qt_app.processEvents()
        assert not designer.ui.checkBoxEntranceLoss.isEnabled()
        assert not designer.ui.checkBoxExitLoss.isEnabled()
        assert designer.ui.pushButtonBoundaryInfo.isEnabled()
        assert designer.ui.lineEditEntranceLoss.text() == ''
        commit = designer._capture_commit()
        assert commit.enabled is False and commit.total_losses is None
        assert commit.design.entrance_coefficient == 0.12
        designer.ui.checkBoxLossesCal.click()
        assert designer.flush_calculation().entrance_loss > 0
    finally:
        designer.close()


@pytest.mark.parametrize('viscosity', ['2.5', ''])
def test_saved_viscosity_is_preserved_when_opening_designer(qt_app, viscosity):
    properties = Properties('Outlet properties', True, side='outlet')
    properties.set_design(PipeDesign.from_legacy({'viscosity': viscosity}, side='outlet'))
    try:
        properties.ui.pushButtonOpenDesigner.click()
        assert properties.sub_window_designer.ui.lineEditViscosity.text() == viscosity
        assert properties.sub_window_designer.ui.checkBoxExitLoss.isChecked()
        assert not properties.sub_window_designer.ui.checkBoxEntranceLoss.isChecked()
    finally:
        properties.sub_window_designer.close()
        properties.close()
