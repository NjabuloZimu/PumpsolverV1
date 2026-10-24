"""Study physics, display-unit conversion and isolation from saved projects."""

from copy import deepcopy
from dataclasses import replace
from math import pi

import pytest

from pumpsolver.calculations.parametric import (
    MAX_STUDY_POINTS, StudyRequest, run_study,
)
from pumpsolver.calculations.pipe_losses import CalculationError, GRAVITY, PipeLossCalculator
from pumpsolver.calculations.pump import solve_pump
from pumpsolver.models import Fitting, PipeDesign, ProjectState, PumpInputs, Segment


def project():
    values = {
        'in_dia': '10', 'in_head': '2', 'in_loss': '0.5', 'in_flow': '36',
        'in_dens': '1000', 'in_press': '101325', 'out_dia': '10', 'out_head': '20',
        'out_loss': '0.7', 'out_flow': '36', 'out_dens': '1000', 'out_press': '101325',
        'effi': '80', 'power': '25.25', 'safety': '1', 'gravity': '9.81',
        'designer_status_in': False, 'designer_status_out': False,
    }
    return ProjectState(PumpInputs.from_legacy(values))


def design(side):
    return PipeDesign(
        segments=(Segment(1, 10, 0.1, (Fitting(1, 'Valve', 0.2),),
                          roughness_m=0.001, has_roughness=True),),
        viscosity_pa_s=1, entrance_enabled=side == 'inlet',
        entrance_coefficient=0.3, exit_enabled=side == 'outlet', exit_coefficient=1.2,
    )


def designed_project():
    state = project()
    return replace(state, parameters=replace(state.parameters, designer_status_in=True,
                                             designer_status_out=True,
                                             in_loss_m=999, out_loss_m=999),
                   inlet=design('inlet'), outlet=design('outlet'))


def expected_laminar(flow, density=1000, boundary_k=0.3):
    velocity = flow / 3600 / (pi * 0.1 ** 2 / 4)
    reynolds = density * velocity * 0.1 / 1.0
    major = 0 if not flow else 64 / reynolds * 10 / 0.1 * velocity ** 2 / (2 * GRAVITY)
    minor = (0.2 + boundary_k) * velocity ** 2 / (2 * GRAVITY)
    return major, minor


def test_endpoint_inclusive_sweep_uses_display_units_and_does_not_mutate_project():
    state = project()
    before = deepcopy(state.to_legacy())
    result = run_study(state, StudyRequest('flow', 0, 72, 3, 'power'))
    assert result.independent.unit == 'm³/h'
    assert result.dependent.unit == 'm'
    assert result.curves[0].x_values == (0, 36, 72)
    assert result.curves[0].y_values == pytest.approx((25.25, 25.25, 25.25))
    assert result.curves[0].step_value is None
    assert state.to_legacy() == before


def test_shared_flow_and_density_update_both_pump_boundaries():
    state = project()
    # Different saved outlet values must be replaced by the shared controls.
    state = replace(state, parameters=replace(state.parameters, out_flow_m3_s=1,
                                              out_density_kg_m3=10))
    result = run_study(state, StudyRequest('flow', 0, 72, 3, 'power', 'density', (800, 1200)))
    for curve in result.curves:
        assert curve.y_values == pytest.approx((25.25,) * 3)


def test_step_efficiency_is_held_for_a_complete_range_then_changes():
    state = replace(project(), parameters=replace(project().parameters, out_diameter_m=0.08))
    result = run_study(state, StudyRequest('flow', 0, 72, 3, 'power', 'effi', (60, 80)))
    assert [curve.step_value for curve in result.curves] == [60, 80]
    for curve in result.curves:
        expected = []
        for flow in curve.x_values:
            vin = flow / 3600 / (pi * 0.1 ** 2 / 4)
            vout = flow / 3600 / (pi * 0.08 ** 2 / 4)
            expected.append((20.2 + (vout ** 2 - vin ** 2) / (2 * 9.81)) / (curve.step_value / 100))
        assert curve.y_values == pytest.approx(expected)
    assert result.curves[0].y_values[-1] > result.curves[1].y_values[-1]


@pytest.mark.parametrize('dependent', ['power', 'effi', 'in_head', 'out_head', 'in_press', 'out_press', 'safety'])
def test_numeric_balance_matches_existing_symbolic_solver_for_each_supported_pump_output(dependent):
    state = project()
    # Any saved dependent value is replaced by the requested unknown.
    state = replace(state, parameters=replace(state.parameters, out_diameter_m=0.08))
    result = run_study(state, StudyRequest('flow', 0, 12, 3, dependent))
    for flow, actual in zip(result.curves[0].x_values, result.curves[0].y_values):
        values = state.parameters.to_legacy()
        values['in_flow'] = values['out_flow'] = str(flow)
        values[dependent] = 'Unspecified'
        assert actual == pytest.approx(solve_pump(values).solved_value, abs=1e-8)


@pytest.mark.parametrize('dependent,side,boundary,component', [
    ('in_loss', 'inlet', 0.3, 'total'),
    ('in_major_loss', 'inlet', 0.3, 'major'),
    ('in_minor_loss', 'inlet', 0.3, 'minor'),
    ('out_loss', 'outlet', 1.2, 'total'),
    ('out_major_loss', 'outlet', 1.2, 'major'),
    ('out_minor_loss', 'outlet', 1.2, 'minor'),
])
def test_flow_sweep_recalculates_major_and_minor_losses_at_every_point(dependent, side, boundary, component):
    state = designed_project()
    result = run_study(state, StudyRequest('flow', 0, 72, 3, dependent))
    expected = []
    for flow in result.curves[0].x_values:
        major, minor = expected_laminar(flow, boundary_k=boundary)
        expected.append(major if component == 'major' else minor if component == 'minor' else major + minor)
    assert result.curves[0].y_values == pytest.approx(expected)
    assert result.curves[0].y_values[-1] != 999


def test_density_step_changes_laminar_major_losses_but_not_minor_losses():
    result = run_study(designed_project(), StudyRequest('flow', 0, 72, 3, 'in_loss', 'density', (800, 1200)))
    for curve in result.curves:
        assert curve.y_values == pytest.approx([
            sum(expected_laminar(flow, curve.step_value)) for flow in curve.x_values])
    assert result.curves[0].y_values[-1] > result.curves[1].y_values[-1]


@pytest.mark.parametrize('dependent,component', [('total_loss', 'total'),
                                               ('total_major_loss', 'major'),
                                               ('total_minor_loss', 'minor')])
def test_combined_losses_reconcile_both_designed_sides(dependent, component):
    result = run_study(designed_project(), StudyRequest('flow', 0, 72, 3, dependent))
    expected = []
    for flow in result.curves[0].x_values:
        major_in, minor_in = expected_laminar(flow, boundary_k=0.3)
        major_out, minor_out = expected_laminar(flow, boundary_k=1.2)
        expected.append(major_in + major_out if component == 'major' else minor_in + minor_out
                        if component == 'minor' else major_in + minor_in + major_out + minor_out)
    assert result.curves[0].y_values == pytest.approx(expected)


def test_active_designs_update_losses_and_pump_attached_boundary_diameters():
    state = designed_project()
    inlet = replace(state.inlet, viscosity_pa_s=0.00089, transition_equation='R.J.S Pigott',
                    segments=(Segment(1, 2, 0.12, roughness_m=0.001, has_roughness=True),
                              Segment(2, 3, 0.1, (Fitting(1, 'Elbow', 0.7),),
                                      roughness_m=0.001, has_roughness=True)),
                    entrance_enabled=False, exit_enabled=True, exit_coefficient=0.6)
    outlet = replace(state.outlet, segments=(Segment(1, 4, 0.08, roughness_m=0.001, has_roughness=True),
                                            Segment(2, 5, 0.15, roughness_m=0, has_roughness=True)),
                     entrance_enabled=True, entrance_coefficient=0.4,
                     exit_enabled=False)
    state = replace(state, inlet=inlet, outlet=outlet,
                    parameters=replace(state.parameters, in_diameter_m=1, out_diameter_m=1))
    before = deepcopy(state.to_legacy())
    result = run_study(state, StudyRequest('flow', 0, 72, 3, 'power'))
    for flow, actual in zip(result.curves[0].x_values, result.curves[0].y_values):
        values = state.parameters.to_legacy()
        values['in_flow'] = values['out_flow'] = str(flow)
        for side, prefix, design_model, boundary in [('inlet', 'in', inlet, 0.1),
                                                     ('outlet', 'out', outlet, 0.08)]:
            saved = design_model.to_legacy()
            pipe = PipeLossCalculator(side, saved['transition_equation']).calculate(
                saved['segments'], saved['fittings'], saved['roughness'], saved['viscosity'], 1000, flow,
                entrance_enabled=saved['entrance_enabled'], entrance_coefficient=saved['entrance_coefficient'],
                exit_enabled=saved['exit_enabled'], exit_coefficient=saved['exit_coefficient'])
            values[f'{prefix}_loss'] = pipe.total_loss
            values[f'{prefix}_dia'] = boundary * 100
        values['power'] = 'Unspecified'
        assert actual == pytest.approx(solve_pump(values).solved_value, abs=1e-8)
    assert state.to_legacy() == before


def test_loss_only_study_allows_unrelated_pump_unknowns():
    state = designed_project()
    state = replace(state, parameters=replace(state.parameters, available_head_m=None,
                                              in_pressure_pa=None, efficiency_fraction=None))
    result = run_study(state, StudyRequest('flow', 0, 72, 3, 'in_loss'))
    assert result.curves[0].y_values[-1] == pytest.approx(sum(expected_laminar(72)))


@pytest.mark.parametrize('dependent', ['in_loss', 'out_loss', 'total_loss', 'total_major_loss', 'total_minor_loss'])
def test_loss_outputs_require_enabled_calculators(dependent):
    with pytest.raises(CalculationError, match='Activate the .* losses calculator'):
        run_study(project(), StudyRequest('flow', 0, 72, 3, dependent))


def test_total_losses_require_both_designers():
    state = designed_project()
    state = replace(state, parameters=replace(state.parameters, designer_status_out=False))
    with pytest.raises(CalculationError, match='outlet losses calculator'):
        run_study(state, StudyRequest('flow', 0, 72, 3, 'total_loss'))


@pytest.mark.parametrize('change,match', [
    ({'points': 1}, 'at least two'), ({'points': 2.5}, 'integer'),
    ({'points': True}, 'integer'), ({'points': MAX_STUDY_POINTS + 1}, 'at most'),
    ({'start': float('nan')}, 'finite'), ({'stop': float('inf')}, 'finite'),
    ({'start': -1}, 'negative'), ({'stop': 0}, 'different'),
    ({'independent_key': 'effi', 'start': 0, 'stop': 100}, 'greater than zero'),
    ({'independent_key': 'effi', 'start': 50, 'stop': 101}, 'at most 100'),
    ({'independent_key': 'density', 'start': 0}, 'greater than zero'),
    ({'independent_key': 'bad'}, 'independent variable'),
    ({'independent_key': 'gravity'}, 'independent variable'),
    ({'dependent_key': 'flow'}, 'dependent variable'),
    ({'dependent_key': 'gravity'}, 'dependent variable'),
    ({'independent_key': 'power'}, 'must be different'),
    ({'step_key': 'flow', 'step_values': (36,)}, 'must be different'),
    ({'step_key': 'power', 'step_values': (20,)}, 'must be different'),
    ({'step_key': 'bad'}, 'step variable'),
    ({'step_key': 'gravity', 'step_values': (9.7, 9.9)}, 'step variable'),
    ({'step_key': 'effi'}, 'at least one'),
    ({'step_values': (80,)}, 'Choose a step variable'),
    ({'step_key': 'effi', 'step_values': (80, float('nan'))}, 'finite'),
    ({'step_key': 'effi', 'step_values': (80, 101)}, 'at most 100'),
    ({'points': MAX_STUDY_POINTS, 'step_key': 'effi', 'step_values': (60, 80)}, 'at most'),
])
def test_invalid_requests_rejected_before_calculating(change, match):
    request = replace(StudyRequest('flow', 0, 72, 3, 'power'), **change)
    with pytest.raises(CalculationError, match=match):
        run_study(project(), request)


def test_descending_ranges_are_supported():
    result = run_study(project(), StudyRequest('flow', 72, 0, 3, 'power'))
    assert result.curves[0].x_values == (72, 36, 0)


def test_missing_pump_input_has_point_context_and_preserves_project():
    state = project()
    state = replace(state, parameters=replace(state.parameters, out_pressure_pa=None))
    before = deepcopy(state.to_legacy())
    with pytest.raises(CalculationError, match='Point 1 .*Outlet Pressure must be a number'):
        run_study(state, StudyRequest('flow', 0, 72, 3, 'power'))
    assert state.to_legacy() == before


def test_late_failure_has_step_and_point_context_without_mutating_project():
    state = project()
    before = deepcopy(state.to_legacy())
    with pytest.raises(CalculationError, match='Point 1 .*step 2 .*Available Head cannot be negative'):
        run_study(state, StudyRequest('flow', 0, 72, 3, 'power', 'in_head', (2, 40)))
    assert state.to_legacy() == before


def test_incomplete_active_design_is_not_silently_replaced_by_stale_saved_loss():
    state = designed_project()
    state = replace(state, inlet=replace(state.inlet, segments=()))
    with pytest.raises(CalculationError, match='Point 1 .*at least one pipe segment'):
        run_study(state, StudyRequest('flow', 0, 72, 3, 'power'))


def test_zero_available_head_cannot_solve_efficiency():
    state = project()
    state = replace(state, parameters=replace(state.parameters, available_head_m=0))
    with pytest.raises(CalculationError, match='no unique solution'):
        run_study(state, StudyRequest('flow', 0, 72, 3, 'effi'))
