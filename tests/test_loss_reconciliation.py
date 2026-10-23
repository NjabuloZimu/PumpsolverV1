"""The selected loss breakdown and the total saved to Properties must agree."""

import copy

import pytest

from pumpsolver.calculations.pipe_losses import PipeLossCalculator
from pumpsolver.gui.main_window import MainWindow
from pumpsolver.gui.properties_dialog import Properties
from pumpsolver.persistence.csv_io import read_project, write_project


@pytest.mark.parametrize('side,count', [('inlet', 1), ('outlet', 1), ('inlet', 3), ('outlet', 3)])
def test_visible_losses_reconcile_through_designer_properties_and_csv(
        qt_app, monkeypatch, project_state, tmp_path, side, count):
    from PyQt5.QtWidgets import QMessageBox

    state = copy.deepcopy(project_state)
    suffix = 'in' if side == 'inlet' else 'out'
    flow = '1283.64298' if count == 1 else '36'
    state['parameters'].update(in_flow=flow, out_flow=flow, in_dens='998', out_dens='998')
    state['parameters'][f'designer_status_{suffix}'] = True
    state['parameters'][f'{suffix}_dia'] = '12'
    state['parameters'][f'{suffix}_loss'] = '0'
    diameters = (12,) if count == 1 else (12, 8, 10)
    segments = {}
    for number, diameter in enumerate(diameters, 1):
        segments[f'Line Segment {number}, Segment Length (m)'] = str(number)
        segments[f'Line Segment {number}, Segment Diameter (cm)'] = str(diameter)
    design = {
        'segments': segments,
        'roughness': [{'Line Segment': number, 'Segment Roughness': 'Smooth Pipe'}
                      for number in range(1, count + 1)],
        'fittings': [] if count == 1 else [
            {'Line Segment': number, 'Fitting 1, Fitting Type': 'Valve', 'Fitting 1, Loss Factor': '0.3'}
            for number in range(1, count + 1)],
        'viscosity': '0.89', 'transition_equation': 'Moody',
        'entrance_enabled': side == 'inlet', 'entrance_coefficient': '0.5',
        'exit_enabled': side == 'outlet', 'exit_coefficient': '1.0',
    }
    state[side] = design
    expected = PipeLossCalculator(side=side).calculate(
        segments, design['fittings'], design['roughness'], '0.89', '998', flow)
    if side == 'inlet' and count == 1:
        assert expected.major_loss == pytest.approx(2.940567330)
        assert expected.minor_loss == pytest.approx(25.339502548)
        assert expected.total_loss == pytest.approx(28.280069878)

    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = designer = None
    try:
        main.restore_project(state)
        getattr(main.ui, f'{side}PushButton').click()
        properties = main.sub_window
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        total_displayed = 0.0
        for row, segment in enumerate(expected.segments):
            designer.ui.tableWidgetPipeSegment.selectRow(row)
            qt_app.processEvents()
            designer.flush_calculation()
            assert designer.ui.groupBox_6.title() == f'Segment {row + 1} Results'
            major = float(designer.ui.lineEditMajorLosses.text())
            minor = float(designer.ui.lineEditMinorLosses.text())
            assert major == pytest.approx(segment.major_loss, rel=1e-5)
            assert minor == pytest.approx(segment.minor_loss, rel=1e-5)
            assert major + minor == pytest.approx(segment.total_loss, rel=1e-5)
            total_displayed += major + minor
        assert 'all segments' in designer.ui.groupBox_7.title()
        summary = designer.ui.labelOverallSummary.text()
        for term, value in (('major', expected.major_loss), ('minor', expected.minor_loss),
                            ('total', expected.total_loss)):
            assert f'{term} {value:#.6g} m' in summary
        assert total_displayed == pytest.approx(expected.total_loss, rel=1e-5)
        assert main.project_state() == state
        designer.ui.pushButtonClose.click()
        copied = float(properties.ui.lineEditLosses.text())
        assert copied == pytest.approx(expected.total_loss, rel=1e-5)
        assert copied == pytest.approx(total_displayed, rel=1e-5)
        properties.ui.pushButtonApply.click()
        assert float(main.datafunction()[f'{suffix}_loss']) == pytest.approx(copied)
        destination = tmp_path / 'reconciled-project.csv'
        write_project(destination, main.project_state())
        assert read_project(destination) == main.project_state()
        assert not errors
    finally:
        if designer is not None:
            designer.close()
        if properties is not None:
            properties.close()
        main.close()
        if main in MainWindow.windows:
            MainWindow.windows.remove(main)
