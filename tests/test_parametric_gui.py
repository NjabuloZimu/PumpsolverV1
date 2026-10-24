"""Exercise the menu-to-plot path, settings, loss gates and result export."""

import copy
import csv

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QFileDialog

from pumpsolver.gui.main_window import MainWindow
from pumpsolver.gui.parametric_dialog import ParametricStudyDialog
from pumpsolver.models import ProjectState


@pytest.fixture
def study_project(project_state):
    state = copy.deepcopy(project_state)
    state['parameters'].update(effi='80', power='Unspecified', designer_status_out=False)
    return ProjectState.from_legacy(state)


def _select(combo, key):
    index = combo.findData(key)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_analysis_menu_opens_separate_dialog_and_plots_stepped_curves(qt_app, study_project):
    main = MainWindow()
    dialog = None
    try:
        main.restore_project(study_project.to_legacy())
        before = main.project_state()
        menus = [action.text() for action in main.ui.menubar.actions()]
        assert menus == ['File', 'Analysis', 'About']
        assert main.ui.menuAnalysis.actions() == [main.ui.actionParametric_Study]
        main.ui.actionParametric_Study.trigger()
        dialog = main.sub_window
        qt_app.processEvents()
        assert isinstance(dialog, ParametricStudyDialog)
        assert dialog.isVisible()
        _select(dialog.independent_combo, 'flow')
        _select(dialog.dependent_combo, 'power')
        dialog.start_edit.setText('0')
        dialog.stop_edit.setText('72')
        dialog.points_spin.setValue(5)
        dialog.step_check.setChecked(True)
        _select(dialog.step_combo, 'effi')
        dialog.step_values_edit.setText('60, 70, 80')
        dialog.run_button.click()
        qt_app.processEvents()
        assert dialog.result is not None
        assert len(dialog.axes.lines) == 3
        for line, efficiency in zip(dialog.axes.lines, (60, 70, 80)):
            assert list(line.get_xdata()) == [0, 18, 36, 54, 72]
            assert f'= {efficiency} %' in line.get_label()
            # Efficiency is a fixed parameter for each whole sweep.
            assert float(line.get_ydata()[0]) == pytest.approx(24.9 / (efficiency / 100))
        assert 'flow' in dialog.axes.get_xlabel().lower() and 'm³/h' in dialog.axes.get_xlabel()
        assert 'Available Head' in dialog.axes.get_ylabel() and '(m)' in dialog.axes.get_ylabel()
        assert len(dialog.axes.get_legend().get_texts()) == 3
        assert main.project_state() == before
        assert dialog.export_button.isEnabled()
        dialog.start_edit.setText('10')
        assert dialog.result is None
        assert not dialog.axes.lines
        assert not dialog.export_button.isEnabled()
    finally:
        if dialog:
            dialog.close()
        main.close()
        MainWindow.windows.remove(main)


def test_direct_losses_require_active_calculator_and_recompute_major_minor(qt_app, study_project):
    from dataclasses import replace
    from pumpsolver.models import Fitting, PipeDesign, Segment

    inactive = ParametricStudyDialog(study_project)
    try:
        _select(inactive.dependent_combo, 'in_loss')
        assert not inactive.run_button.isEnabled()
        assert 'Activate the inlet' in inactive.ui.outputHint.text()
        assert inactive.run_study() is None
    finally:
        inactive.close()
    design = PipeDesign(segments=(Segment(1, 10, 0.1, (Fitting(1, 'Bend', 2),),
                                                   roughness_m=0, smooth=True, has_roughness=True),))
    project = replace(study_project, inlet=design, parameters=replace(
        study_project.parameters, designer_status_in=True))
    dialog = ParametricStudyDialog(project)
    try:
        _select(dialog.dependent_combo, 'in_loss')
        dialog.start_edit.setText('0')
        dialog.stop_edit.setText('72')
        dialog.points_spin.setValue(3)
        dialog.run_button.click()
        total = dialog.result.curves[0].y_values
        assert total[0] == 0 < total[1] < total[2]
        _select(dialog.dependent_combo, 'in_major_loss')
        dialog.run_button.click()
        major = dialog.result.curves[0].y_values
        _select(dialog.dependent_combo, 'in_minor_loss')
        dialog.run_button.click()
        minor = dialog.result.curves[0].y_values
        assert total == pytest.approx([a + b for a, b in zip(major, minor)])
        _select(dialog.dependent_combo, 'total_loss')
        assert not dialog.run_button.isEnabled()
        assert 'outlet' in dialog.ui.outputHint.text()
    finally:
        dialog.close()


@pytest.mark.parametrize('independent,step,held', [
    ('flow', 'density', '800, 1200'),
    ('density', 'flow', '0, 36, 72'),
])
@pytest.mark.parametrize('dependent', ['total_loss', 'power'])
def test_plotted_response_uses_fresh_losses_for_every_flow_and_density_point(
        qt_app, study_project, independent, step, held, dependent):
    """Compare real plotted points with closed-form laminar pipe physics."""
    from dataclasses import replace
    from math import pi
    from pumpsolver.calculations.pipe_losses import GRAVITY
    from pumpsolver.models import Fitting, PipeDesign, Segment

    inlet = PipeDesign(
        segments=(Segment(1, 10, 0.1, (Fitting(1, 'Valve', 0.2),),
                          roughness_m=0, smooth=True, has_roughness=True),),
        viscosity_pa_s=1.0, entrance_enabled=True, entrance_coefficient=0.3,
        exit_enabled=False)
    outlet = PipeDesign(
        segments=(Segment(1, 20, 0.08, (Fitting(1, 'Bend', 0.4),),
                          roughness_m=0, smooth=True, has_roughness=True),),
        viscosity_pa_s=1.0, entrance_enabled=False,
        exit_enabled=True, exit_coefficient=1.2)
    project = replace(study_project, inlet=inlet, outlet=outlet, parameters=replace(
        study_project.parameters, designer_status_in=True, designer_status_out=True,
        in_loss_m=10_000, out_loss_m=20_000,
        in_diameter_m=1.0, out_diameter_m=1.0))
    before = copy.deepcopy(project.to_legacy())
    dialog = ParametricStudyDialog(project)
    try:
        _select(dialog.independent_combo, independent)
        _select(dialog.dependent_combo, dependent)
        dialog.start_edit.setText('0' if independent == 'flow' else '800')
        dialog.stop_edit.setText('72' if independent == 'flow' else '1200')
        dialog.points_spin.setValue(3)
        dialog.step_check.setChecked(True)
        _select(dialog.step_combo, step)
        dialog.step_values_edit.setText(held)
        dialog.run_button.click()
        dialog.canvas.draw()
        assert dialog.result is not None
        assert len(dialog.axes.lines) == len(held.split(','))
        for line, curve in zip(dialog.axes.lines, dialog.result.curves):
            expected = []
            for x in line.get_xdata():
                flow = x if independent == 'flow' else curve.step_value
                density = x if independent == 'density' else curve.step_value
                q = flow / 3600
                velocities, total_loss = [], 0.0
                for diameter, length, k in ((0.1, 10, 0.5), (0.08, 20, 1.6)):
                    velocity = q / (pi * diameter ** 2 / 4)
                    assert density * velocity * diameter / 1.0 < 2100
                    # Laminar Darcy head: 128*mu*L*Q/(pi*rho*g*D^4).
                    major = 128 * 1.0 * length * q / (pi * density * GRAVITY * diameter ** 4)
                    minor = k * velocity ** 2 / (2 * GRAVITY)
                    total_loss += major + minor
                    velocities.append(velocity)
                if dependent == 'power':
                    parameters = project.parameters
                    velocity_head = (velocities[1] ** 2 - velocities[0] ** 2) / (2 * parameters.gravity_m_s2)
                    expected.append((parameters.out_elevation_m - parameters.in_elevation_m
                                     + velocity_head + total_loss + parameters.safety_head_m)
                                    / parameters.efficiency_fraction)
                else:
                    expected.append(total_loss)
            assert list(line.get_ydata()) == pytest.approx(expected, rel=1e-12)
        assert project.to_legacy() == before
    finally:
        dialog.close()


@pytest.mark.parametrize('invalid', ['', '.', 'nan', 'inf'])
def test_invalid_range_keeps_result_empty_and_error_visible(qt_app, study_project, invalid):
    dialog = ParametricStudyDialog(study_project)
    try:
        dialog.start_edit.setText(invalid)
        assert dialog.run_study() is None
        assert dialog.result is None
        assert not dialog.export_button.isEnabled()
        assert dialog.ui.statusLabel.text()
    finally:
        dialog.close()


def test_step_conflicts_errors_and_csv_export(qt_app, study_project, monkeypatch, tmp_path):
    dialog = ParametricStudyDialog(study_project)
    try:
        assert dialog.dependent_combo.findData('flow') < 0
        assert dialog.step_combo.findData('flow') < 0
        assert dialog.step_combo.findData('power') < 0
        dialog.start_edit.setText('0')
        dialog.stop_edit.setText('72')
        dialog.points_spin.setValue(3)
        dialog.step_check.setChecked(True)
        dialog.step_values_edit.setText('60, 0')
        assert dialog.run_study() is None
        assert 'Efficiency' in dialog.ui.statusLabel.text()
        dialog.step_values_edit.setText('60, 80')
        assert dialog.run_study() is not None
        destination = tmp_path / 'study'
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(destination), ''))
        dialog.export_button.click()
        with destination.with_suffix('.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
        assert len(rows) == 7
        assert rows[0] == ['Pump Efficiency (%)', 'Volumetric flow rate (m³/h)', 'Available Head (m)']
        assert [float(row[0]) for row in rows[1:]] == [60, 60, 60, 80, 80, 80]
        dialog.step_check.setChecked(False)
        assert not dialog.step_combo.isEnabled() and not dialog.step_values_edit.isEnabled()
    finally:
        dialog.close()


def test_plot_and_controls_fit_on_supported_dialog_sizes(qt_app, study_project):
    dialog = ParametricStudyDialog(study_project)
    try:
        dialog.show()
        for width, height in ((880, 660), (1120, 820), (1400, 1000)):
            dialog.resize(width, height)
            qt_app.processEvents()
            for widget in (dialog.independent_combo, dialog.dependent_combo, dialog.run_button,
                           dialog.ui.closeButton, dialog.canvas):
                origin = widget.mapTo(dialog, QPoint(0, 0))
                assert dialog.rect().contains(origin)
                assert dialog.rect().contains(origin + QPoint(widget.width() - 1, widget.height() - 1))
            assert dialog.canvas.height() >= 220
            assert dialog.step_values_edit.width() > 150
    finally:
        dialog.close()
