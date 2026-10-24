"""Protect shared fluid inputs through the actual Properties -> designer path."""

from copy import deepcopy

import pytest
from PyQt5.QtWidgets import QMessageBox

from pumpsolver.calculations.pipe_losses import PipeLossCalculator
from pumpsolver.gui.main_window import MainWindow
from pumpsolver.gui.properties_dialog import Properties
from pumpsolver.persistence.csv_io import read_project, write_project


def _state(project_state, inlet_active=False, outlet_active=False):
    state = deepcopy(project_state)
    state['parameters']['designer_status_in'] = inlet_active
    state['parameters']['designer_status_out'] = outlet_active
    for side in ('inlet', 'outlet'):
        state[side]['segments'] = {
            'Line Segment 1, Segment Length (m)': '10',
            'Line Segment 1, Segment Diameter (cm)': '10',
        }
        state[side]['fittings'] = []
        state[side]['roughness'] = [
            {'Line Segment': 1, 'Segment Roughness': 'Smooth Pipe'}]
        state[side]['viscosity'] = '0.89'
    return state


def _open(main, side):
    getattr(main.ui, f'{side}PushButton').click()
    return main.sub_window


def _close(main, *properties):
    for window in properties:
        if window is not None:
            designer = getattr(window, 'sub_window_designer', None)
            if designer is not None:
                designer.close()
            window.close()
    main.close()
    MainWindow.windows.remove(main)


def _shared_controls(window, designer=False):
    return (window.ui.lineEditDensity,
            window.ui.lineEditFlowrate if designer else window.ui.lineEditVol)


def _both_active_state(project_state):
    state = _state(project_state, inlet_active=True, outlet_active=True)
    state['inlet'].update({
        'segments': {
            'Line Segment 1, Segment Length (m)': '10',
            'Line Segment 1, Segment Diameter (cm)': '12',
            'Line Segment 2, Segment Length (m)': '7',
            'Line Segment 2, Segment Diameter (cm)': '10',
        },
        'roughness': [
            {'Line Segment': 1, 'Segment Roughness': 'Smooth Pipe'},
            {'Line Segment': 2, 'Segment Roughness': '0.03'}],
        'fittings': [{'Line Segment': 1, 'Fitting 1, Fitting Type': 'Bend',
                      'Fitting 1, Loss Factor': '0.9'}],
        'viscosity': '0.89', 'transition_equation': 'R.J.S Pigott',
        'entrance_enabled': True, 'entrance_coefficient': '0.75',
        'exit_enabled': False, 'exit_coefficient': '0.2',
    })
    state['outlet'].update({
        'segments': {
            'Line Segment 1, Segment Length (m)': '20',
            'Line Segment 1, Segment Diameter (cm)': '8',
            'Line Segment 2, Segment Length (m)': '5',
            'Line Segment 2, Segment Diameter (cm)': '11',
        },
        'roughness': [
            {'Line Segment': 1, 'Segment Roughness': '0.045'},
            {'Line Segment': 2, 'Segment Roughness': '0.06'}],
        'fittings': [{'Line Segment': 2, 'Fitting 1, Fitting Type': 'Valve',
                      'Fitting 1, Loss Factor': '2.4'}],
        'viscosity': '1.8', 'transition_equation': 'Moody',
        'entrance_enabled': False, 'entrance_coefficient': '0.3',
        'exit_enabled': True, 'exit_coefficient': '1.25',
    })
    return state


def _expected_losses(state, side, flow, density):
    design = state[side]
    return PipeLossCalculator(side).calculate(
        design['segments'], design['fittings'], design['roughness'],
        design['viscosity'], density, flow,
        transition_equation=design['transition_equation'],
        **{key: design[key] for key in (
            'entrance_enabled', 'entrance_coefficient', 'exit_enabled', 'exit_coefficient')},
    ).total_loss


def _edit_fluid(designer, flow='72', density='995'):
    assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
    designer.ui.lineEditFlowrate.setText(flow)
    designer.ui.lineEditFlowrate.editingFinished.emit()
    designer.ui.lineEditDensity.setText(density)
    designer.ui.lineEditDensity.editingFinished.emit()
    assert designer.flush_calculation() is not None
    designer.ui.pushButtonClose.click()


@pytest.mark.parametrize('owner', ['inlet', 'outlet'])
def test_opposite_calculator_locks_properties_but_active_designer_is_editable(
        qt_app, monkeypatch, tmp_path, project_state, owner):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = reopened = None
    other = 'outlet' if owner == 'inlet' else 'inlet'
    state = _state(project_state, inlet_active=owner == 'inlet', outlet_active=owner == 'outlet')
    main.restore_project(state)
    try:
        properties = _open(main, other)
        assert all(not editor.isEnabled() for editor in _shared_controls(properties))
        assert all(owner in editor.toolTip() for editor in _shared_controls(properties))
        # Ordinary pipe fields remain editable when this pipe's calculator is off.
        assert properties.ui.lineEditLosses.isEnabled()
        assert properties.ui.lineEditDia.isEnabled()
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        assert not designer.ui.tableWidgetPipeSegment.selectedIndexes()
        assert all(not editor.isEnabled() for editor in _shared_controls(designer, True))
        for _ in range(3):
            designer.ui.checkBoxLossesCal.click()
            qt_app.processEvents()
            assert all(editor.isEnabled() == designer.ui.checkBoxLossesCal.isChecked()
                       for editor in _shared_controls(designer, True))
        assert designer.ui.checkBoxLossesCal.isChecked()
        designer.ui.tableWidgetPipeSegment.selectRow(0)
        assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
        designer.ui.tableWidgetPipeSegment.clearSelection()
        assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
        designer.previously_stored_data(
            state[other]['segments'], state[other]['fittings'], state[other]['roughness'])
        assert not designer.ui.tableWidgetPipeSegment.selectedIndexes()
        assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
        assert designer.flush_calculation() is not None
        designer.ui.pushButtonClose.click()
        properties.ui.pushButtonApply.click()
        destination = tmp_path / 'both-calculators-active.csv'
        write_project(destination, main.project_state())
        main.restore_project(read_project(destination))
        reopened = _open(main, other)
        assert all(not editor.isEnabled() for editor in _shared_controls(reopened))
        reopened.ui.pushButtonOpenDesigner.click()
        restored = reopened.sub_window_designer
        assert all(editor.isEnabled() for editor in _shared_controls(restored, True))
    finally:
        _close(main, properties, reopened)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_either_active_designer_changes_shared_fluid_and_recalculates_both_sides(
        qt_app, monkeypatch, tmp_path, project_state, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = reopened = None
    state = _both_active_state(project_state)
    main.restore_project(state)
    try:
        properties = _open(main, side)
        assert all(not editor.isEnabled() for editor in _shared_controls(properties))
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        assert not designer.ui.tableWidgetPipeSegment.selectedIndexes()
        _edit_fluid(designer)
        assert main.project_state() == state
        assert properties.ui.lineEditVol.text() == '72'
        assert properties.ui.lineEditDensity.text() == '995'
        properties.ui.pushButtonApply.click()
        updated = main.project_state()
        parameters = updated['parameters']
        assert parameters['in_flow'] == parameters['out_flow'] == '72'
        assert parameters['in_dens'] == parameters['out_dens'] == '995'
        for current, suffix in (('inlet', 'in'), ('outlet', 'out')):
            expected = _expected_losses(state, current, '72', '995')
            assert float(parameters[f'{suffix}_loss']) == pytest.approx(expected, rel=1e-12)
            assert updated[current] == state[current]
        assert parameters['in_loss'] != parameters['out_loss']
        destination = tmp_path / f'shared-fluid-from-{side}.csv'
        write_project(destination, updated)
        main.restore_project(read_project(destination))
        assert main.project_state() == updated
        other = 'outlet' if side == 'inlet' else 'inlet'
        reopened = _open(main, other)
        reopened.ui.pushButtonOpenDesigner.click()
        restored = reopened.sub_window_designer
        assert all(editor.isEnabled() for editor in _shared_controls(restored, True))
        assert restored.ui.lineEditFlowrate.text() == '72'
        assert restored.ui.lineEditDensity.text() == '995'
        assert restored.flush_calculation().total_loss == pytest.approx(
            _expected_losses(state, other, '72', '995'))
    finally:
        _close(main, properties, reopened)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_discard_properties_after_designer_save_keeps_both_pipes_unchanged(
        qt_app, monkeypatch, project_state, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.Discard)
    main = MainWindow()
    properties = None
    state = _both_active_state(project_state)
    main.restore_project(state)
    try:
        properties = _open(main, side)
        properties.ui.pushButtonOpenDesigner.click()
        _edit_fluid(properties.sub_window_designer)
        assert properties.ui.pushButtonApply.isEnabled()
        properties.ui.pushButtonCancel.click()
        assert main.project_state() == state
    finally:
        _close(main, properties)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_incomplete_opposite_design_rejects_apply_atomically_and_can_be_repaired(
        qt_app, monkeypatch, project_state, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args[2]))
    main = MainWindow()
    properties = repair = None
    other = 'outlet' if side == 'inlet' else 'inlet'
    state = _both_active_state(project_state)
    state[other]['roughness'] = []
    main.restore_project(state)
    try:
        properties = _open(main, side)
        properties.ui.pushButtonOpenDesigner.click()
        _edit_fluid(properties.sub_window_designer)
        assert properties.save() is False
        assert main.project_state() == state
        assert errors and f'{other.title()} losses:' in errors[-1]
        assert properties.ui.pushButtonApply.isEnabled()
        assert properties.ui.pushButtonSubmit.isEnabled()
        # Repair the opposite design, then retry the still-open original draft.
        repair = _open(main, other)
        repair.ui.pushButtonOpenDesigner.click()
        designer = repair.sub_window_designer
        designer.lineRoughnessList = _both_active_state(project_state)[other]['roughness']
        assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
        assert designer.flush_calculation() is not None
        designer.ui.pushButtonClose.click()
        assert repair.save()
        assert properties.save()
        parameters = main.project_state()['parameters']
        assert parameters['in_flow'] == parameters['out_flow'] == '72'
        assert parameters['in_dens'] == parameters['out_dens'] == '995'
        expected_state = _both_active_state(project_state)
        for current, suffix in (('inlet', 'in'), ('outlet', 'out')):
            assert float(parameters[f'{suffix}_loss']) == pytest.approx(
                _expected_losses(expected_state, current, '72', '995'), rel=1e-12)
    finally:
        _close(main, properties, repair)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_only_active_calculator_can_edit_shared_values_and_recalculate_its_losses(
        qt_app, monkeypatch, project_state, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = None
    main.restore_project(_state(project_state, inlet_active=side == 'inlet', outlet_active=side == 'outlet'))
    try:
        properties = _open(main, side)
        assert all(not editor.isEnabled() for editor in _shared_controls(properties))
        properties.ui.pushButtonOpenDesigner.click()
        designer = properties.sub_window_designer
        designer.ui.tableWidgetPipeSegment.selectRow(0)
        assert all(editor.isEnabled() for editor in _shared_controls(designer, True))
        before = designer.flush_calculation().total_loss
        designer.ui.lineEditFlowrate.setText('72')
        designer.ui.lineEditDensity.setText('995')
        after = designer.flush_calculation().total_loss
        assert after > before
        designer.ui.pushButtonClose.click()
        properties.ui.pushButtonApply.click()
        parameters = main.project_state()['parameters']
        assert parameters['in_flow'] == parameters['out_flow'] == '72'
        assert parameters['in_dens'] == parameters['out_dens'] == '995'
        suffix = 'in' if side == 'inlet' else 'out'
        assert float(parameters[f'{suffix}_loss']) == pytest.approx(after, rel=1e-5)
    finally:
        _close(main, properties)


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
def test_both_inactive_properties_are_unlocked_and_main_rejects_locked_shared_edits(
        qt_app, monkeypatch, project_state, side):
    monkeypatch.setattr(Properties, 'exec_', lambda self: 0)
    main = MainWindow()
    properties = locked = None
    main.restore_project(_state(project_state))
    try:
        properties = _open(main, side)
        assert all(editor.isEnabled() for editor in _shared_controls(properties))
        other = 'outlet' if side == 'inlet' else 'inlet'
        main.restore_project(_state(project_state, inlet_active=other == 'inlet', outlet_active=other == 'outlet'))
        locked = _open(main, side)
        # Programmatic changes can bypass disabled Qt editors; the state commit must guard them too.
        locked.ui.lineEditVol.setText('99')
        locked.ui.lineEditDensity.setText('500')
        assert locked.save()
        parameters = main.project_state()['parameters']
        assert parameters['in_flow'] == parameters['out_flow'] == '36'
        assert parameters['in_dens'] == parameters['out_dens'] == '1000'
    finally:
        _close(main, properties, locked)
