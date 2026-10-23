"""Numerical reference cases for the extracted, GUI-independent domain layer."""

from copy import deepcopy
from math import pi

import pytest

from pumpsolver.calculations.pipe_losses import (
    CalculationError, GRAVITY, PipeLossCalculator,
)
from pumpsolver.calculations.pump import calculate_npsha, compare_npsh, solve_pump


def pipe_inputs(diameters=(10,), lengths=None, roughness='Smooth Pipe'):
    lengths = lengths or [10] * len(diameters)
    segments = {}
    for index, (diameter, length) in enumerate(zip(diameters, lengths), 1):
        segments[f'Line Segment {index}, Segment Length (m)'] = str(length)
        segments[f'Line Segment {index}, Segment Diameter (cm)'] = str(diameter)
    return segments, [], [{'Line Segment': index, 'Segment Roughness': roughness}
                          for index in range(1, len(diameters) + 1)]


def pump_inputs():
    return {
        'in_dia': '10', 'in_head': '2', 'in_loss': '0.5', 'in_flow': '36',
        'in_dens': '1000', 'in_press': '101325', 'out_dia': '10', 'out_head': '20',
        'out_loss': '0.7', 'out_flow': '36', 'out_dens': '1000', 'out_press': '101325',
        'effi': '80', 'power': 'Unspecified', 'safety': '1', 'gravity': '9.81',
        'designer_status_in': False, 'designer_status_out': False,
    }


@pytest.mark.parametrize('side,boundary_coefficient', [('inlet', 0.5), ('outlet', 1.0)])
def test_one_laminar_pipe_uses_explicit_tank_boundary(side, boundary_coefficient):
    calculator = PipeLossCalculator(side=side)
    inputs = pipe_inputs()
    before = deepcopy(inputs)
    result = calculator.calculate(*inputs, viscosity=1000, density=1000, volumetric=36)
    velocity = 0.01 / (pi * 0.1 ** 2 / 4)
    reynolds = 1000 * velocity * 0.1 / 1.0
    expected_major = (64 / reynolds) * (10 / 0.1) * velocity ** 2 / (2 * GRAVITY)
    expected_boundary = boundary_coefficient * velocity ** 2 / (2 * GRAVITY)
    assert result.major_loss == pytest.approx(expected_major)
    assert result.boundary_loss == pytest.approx(expected_boundary)
    assert result.total_loss == pytest.approx(expected_major + expected_boundary)
    assert result.contractions == result.expansions == 0
    assert inputs == before
    assert calculator.viscosity == 0.001


def test_outlet_first_segment_has_no_fictitious_last_to_first_transition():
    result = PipeLossCalculator(side='outlet').calculate(
        *pipe_inputs((10, 20), (0, 0)), viscosity=1, density=1000, volumetric=36)
    first, second = result.segments
    expected_expansion = (1 - 0.1 / 0.2) ** 2 * first.velocity ** 2 / (2 * GRAVITY)
    expected_exit = second.velocity ** 2 / (2 * GRAVITY)
    assert first.transition_loss == first.boundary_loss == 0
    assert second.transition_loss == pytest.approx(expected_expansion)
    assert result.boundary_loss == pytest.approx(expected_exit)
    assert result.total_loss == pytest.approx(expected_expansion + expected_exit)
    assert result.expansions == 1 and result.contractions == 0


def test_equal_diameters_have_no_laminar_contraction_penalty():
    result = PipeLossCalculator().calculate(
        *pipe_inputs((10, 10)), viscosity=1000, density=1000, volumetric=36)
    assert result.transition_loss == 0
    assert result.contractions == result.expansions == 0


def test_rough_laminar_friction_uses_reynolds_without_roughness_penalty():
    calculator = PipeLossCalculator()
    assert calculator.darcy_friction_factor(1000, 0.001, 0.0001) == pytest.approx(0.064)


def test_colebrook_rough_pipe_keeps_reynolds_and_roughness_arguments_in_order():
    calculator = PipeLossCalculator()
    friction = calculator.darcy_friction_factor(100000, 0.001, 0.0001)
    assert friction == pytest.approx(0.0221745359445, rel=1e-10)
    assert calculator.colebrook_equation(friction, 0.001, 100000) == pytest.approx(0, abs=1e-10)
    smooth_transition = calculator.darcy_friction_factor(3000, 0, 0)
    assert calculator.colebrook_equation(smooth_transition, 0, 3000) == pytest.approx(0, abs=1e-10)


@pytest.mark.parametrize('reynolds,relative_roughness,expected', [
    (4000, 0, 0.03990701405563489),
    (4000, 0.05, 0.07698683488922486),
    (100000, 0.001, 0.02217453594451508),
    (1000000, 0, 0.011645040997991622),
    (1000000, 0.01, 0.037964741876160064),
    (100000000, 0, 0.0059404663516367615),
    (100000000, 0.000001, 0.006432556519692281),
    (100000000, 0.05, 0.07155090409108326),
])
def test_colebrook_matches_independent_scipy_reference_roots(reynolds, relative_roughness, expected):
    # Golden values: scipy.optimize.fsolve on 1/sqrt(f) +
    # 2*log10(epsilon_D/3.7 + 2.51/(Re*sqrt(f))) = 0, with correct argument
    # order and Haaland initial guesses. No SciPy dependency at test/runtime.
    # Re=4000 is the boundary case of the correlation, not a new regime model.
    actual = PipeLossCalculator.solve_colebrook(reynolds, relative_roughness)
    assert actual == pytest.approx(expected, rel=1e-12, abs=5e-15)


def test_transition_equation_is_explicit_and_changes_only_selected_threshold():
    calculator = PipeLossCalculator()
    moody = calculator.darcy_friction_factor(200000, 0.01, 0.001, 'Moody')
    pigott = calculator.darcy_friction_factor(200000, 0.01, 0.001, 'R.J.S Pigott')
    assert moody == pytest.approx((1.14 + 2 * 2) ** -2)
    assert pigott == pytest.approx(calculator.solve_colebrook(200000, 0.01))
    assert moody != pytest.approx(pigott)
    assert calculator.transition_equation == 'Moody'


def test_zero_flow_has_zero_losses_instead_of_dividing_by_reynolds():
    result = PipeLossCalculator().calculate(
        *pipe_inputs(), viscosity=1, density=1000, volumetric=0)
    assert result.total_loss == 0
    assert result.minor_loss == result.segments[0].minor_loss == 0
    assert result.segments[0].flow_type == 'No flow'


def test_legacy_screenshot_with_explicit_entrance_k_point_four_reconciles_total():
    # Reproduce the original screenshot with its historical K=0.4 selected
    # explicitly; the new editable entrance default is K=0.5.
    result = PipeLossCalculator(side='inlet').calculate(
        *pipe_inputs((12,), (1,)), viscosity=0.89, density=998, volumetric=1283.64298,
        entrance_coefficient=0.4)
    segment = result.segments[0]
    assert segment.major_loss == pytest.approx(2.9405673301426964, rel=1e-12)
    assert segment.fittings_loss == segment.transition_loss == 0
    assert segment.boundary_loss == pytest.approx(20.271602038465968, rel=1e-12)
    assert segment.minor_loss == pytest.approx(20.271602038465968, rel=1e-12)
    assert segment.total_loss == pytest.approx(23.212169368608663, rel=1e-12)
    assert result.minor_loss == segment.minor_loss
    assert result.total_loss == pytest.approx(result.major_loss + result.minor_loss)


def test_screenshot_with_new_default_entrance_coefficient_point_five():
    result = PipeLossCalculator(side='inlet').calculate(
        *pipe_inputs((12,), (1,)), viscosity=0.89, density=998, volumetric=1283.64298)
    assert result.major_loss == pytest.approx(2.9405673301426964, rel=1e-12)
    assert result.entrance_loss == pytest.approx(25.33950254808246, rel=1e-12)
    assert result.exit_loss == 0
    assert result.minor_loss == result.entrance_loss
    assert result.total_loss == pytest.approx(28.28006987822516, rel=1e-12)


@pytest.mark.parametrize('entrance,exit', [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize('flow', [0, 36])
def test_editable_boundaries_use_first_and_last_velocity_once_without_mutating_inputs(entrance, exit, flow):
    inputs = pipe_inputs((10, 20, 15), (3, 5, 7))
    before = deepcopy(inputs)
    settings = {'entrance_enabled': entrance, 'entrance_coefficient': 0.25,
                'exit_enabled': exit, 'exit_coefficient': 1.7}
    before_settings = deepcopy(settings)
    calculator = PipeLossCalculator(side='outlet')
    before_calculator = dict(vars(calculator))
    result = calculator.calculate(*inputs, viscosity=1, density=1000, volumetric=flow, **settings)
    entrance_head = (flow / 3600 / (pi * 0.1 ** 2 / 4)) ** 2 / (2 * GRAVITY)
    exit_head = (flow / 3600 / (pi * 0.15 ** 2 / 4)) ** 2 / (2 * GRAVITY)
    expected_entrance = 0.25 * entrance_head if entrance else 0
    expected_exit = 1.7 * exit_head if exit else 0
    assert [item.entrance_loss for item in result.segments] == pytest.approx([expected_entrance, 0, 0])
    assert [item.exit_loss for item in result.segments] == pytest.approx([0, 0, expected_exit])
    assert result.entrance_loss == pytest.approx(expected_entrance)
    assert result.exit_loss == pytest.approx(expected_exit)
    assert result.boundary_loss == pytest.approx(expected_entrance + expected_exit)
    assert result.minor_loss == pytest.approx(
        result.fittings_loss + result.transition_loss + expected_entrance + expected_exit)
    assert result.total_loss == pytest.approx(result.major_loss + result.minor_loss)
    # Boundary toggles must leave internal diameter-change correlations alone.
    without_boundaries = calculator.calculate(
        *inputs, viscosity=1, density=1000, volumetric=flow, entrance_enabled=False, exit_enabled=False)
    assert result.transition_loss == without_boundaries.transition_loss
    assert result.major_loss == without_boundaries.major_loss
    assert inputs == before
    assert settings == before_settings
    assert vars(calculator) == before_calculator


def test_single_segment_can_include_both_entrance_and_exit_without_double_counting():
    segments, _, roughness = pipe_inputs((10,), (0,))
    fittings = [{'Line Segment': 1, 'Fitting 1, Fitting Type': 'Valve', 'Fitting 1, Loss Factor': '0.2'}]
    result = PipeLossCalculator().calculate(
        segments, fittings, roughness, viscosity=1, density=1000, volumetric=36,
        entrance_enabled=True, entrance_coefficient=0.3, exit_enabled=True, exit_coefficient=1.2)
    velocity_head = (0.01 / (pi * 0.1 ** 2 / 4)) ** 2 / (2 * GRAVITY)
    segment = result.segments[0]
    assert segment.entrance_loss == pytest.approx(0.3 * velocity_head)
    assert segment.exit_loss == pytest.approx(1.2 * velocity_head)
    assert segment.boundary_loss == pytest.approx(1.5 * velocity_head)
    assert segment.minor_loss == pytest.approx(1.7 * velocity_head)
    assert result.total_loss == pytest.approx(1.7 * velocity_head)


def test_enabled_zero_coefficients_produce_no_boundary_loss():
    result = PipeLossCalculator().calculate(
        *pipe_inputs(), viscosity=1, density=1000, volumetric=36,
        entrance_enabled=True, entrance_coefficient=0, exit_enabled=True, exit_coefficient=0)
    assert result.entrance_loss == result.exit_loss == result.boundary_loss == 0
    assert result.total_loss == result.major_loss


def test_boundary_defaults_follow_effective_side_override():
    calculator = PipeLossCalculator(side='inlet')
    result = calculator.calculate(
        *pipe_inputs(), viscosity=1000, density=1000, volumetric=36, side='outlet')
    velocity_head = result.segments[0].velocity ** 2 / (2 * GRAVITY)
    assert result.entrance_loss == 0
    assert result.exit_loss == pytest.approx(velocity_head)
    assert calculator.side == 'inlet'


@pytest.mark.parametrize('field,value', [
    ('entrance_enabled', 1), ('entrance_enabled', 0), ('entrance_enabled', 'True'),
    ('entrance_enabled', []), ('exit_enabled', 1), ('exit_enabled', 'False'),
    ('entrance_coefficient', -0.1), ('entrance_coefficient', float('nan')),
    ('entrance_coefficient', float('inf')), ('entrance_coefficient', '.'),
    ('entrance_coefficient', None), ('exit_coefficient', -1),
    ('exit_coefficient', float('nan')), ('exit_coefficient', float('inf')),
    ('exit_coefficient', None),
])
def test_invalid_boundary_settings_rejected_even_when_losses_disabled(field, value):
    inputs = pipe_inputs()
    before = deepcopy(inputs)
    settings = {'entrance_enabled': False, 'exit_enabled': False, field: value}
    calculator = PipeLossCalculator()
    with pytest.raises(CalculationError):
        calculator.calculate(*inputs, viscosity=1, density=1000, volumetric=36, **settings)
    assert inputs == before
    assert calculator.side == 'inlet' and calculator.viscosity == 0.001


@pytest.mark.parametrize('side', ['inlet', 'outlet'])
@pytest.mark.parametrize('flow', [36, 0])
def test_multisegment_minor_reconciles_fittings_transitions_and_one_tank_boundary(side, flow):
    segments, _, roughness = pipe_inputs((10, 20, 15), (3, 5, 7))
    coefficients = (0.3, 0.7, 0.2)
    fittings = [
        {'Line Segment': number, 'Fitting 1, Fitting Type': 'Valve',
         'Fitting 1, Loss Factor': str(coefficient)}
        for number, coefficient in enumerate(coefficients, 1)
    ]
    result = PipeLossCalculator(side=side).calculate(
        segments, fittings, roughness, viscosity=1, density=1000, volumetric=flow)
    diameters = (0.1, 0.2, 0.15)
    velocities = [flow / 3600 / (pi * diameter ** 2 / 4) for diameter in diameters]
    heads = [velocity ** 2 / (2 * GRAVITY) for velocity in velocities]
    # Retain the existing expansion/contraction correlations; a transition
    # belongs to its downstream segment, and each tank boundary occurs once.
    expected_transitions = (0, (1 - 0.1 / 0.2) ** 2 * heads[0],
                            0.4 * (1 - 0.15 / 0.2) * heads[2])
    expected_boundaries = ((0.5 * heads[0], 0, 0) if side == 'inlet'
                           else (0, 0, heads[2]))
    expected_minor = []
    for index, segment in enumerate(result.segments):
        fitting_loss = coefficients[index] * heads[index]
        minor = fitting_loss + expected_transitions[index] + expected_boundaries[index]
        expected_minor.append(minor)
        assert segment.fittings_loss == pytest.approx(fitting_loss)
        assert segment.transition_loss == pytest.approx(expected_transitions[index])
        assert segment.boundary_loss == pytest.approx(expected_boundaries[index])
        assert segment.minor_loss == pytest.approx(minor)
        assert segment.total_loss == pytest.approx(segment.major_loss + minor)
    assert result.minor_loss == pytest.approx(sum(expected_minor))
    assert result.minor_loss == pytest.approx(
        result.fittings_loss + result.transition_loss + result.boundary_loss)
    assert result.total_loss == pytest.approx(result.major_loss + result.minor_loss)
    assert result.total_loss == pytest.approx(sum(segment.total_loss for segment in result.segments))
    if flow == 0:
        assert result.major_loss == result.minor_loss == result.total_loss == 0


@pytest.mark.parametrize('change', ['viscosity', 'diameter', 'roughness', 'fitting'])
def test_invalid_pipe_inputs_do_not_mutate_data_or_calculator(change):
    segments, fittings, roughness = pipe_inputs()
    viscosity = '1'
    if change == 'viscosity':
        viscosity = '0'
    elif change == 'diameter':
        segments['Line Segment 1, Segment Diameter (cm)'] = ''
    elif change == 'roughness':
        roughness.clear()
    else:
        fittings.append({'Line Segment': 1, 'Fitting 1, Loss Factor': ''})
    before = deepcopy((segments, fittings, roughness))
    calculator = PipeLossCalculator()
    with pytest.raises(CalculationError):
        calculator.calculate(segments, fittings, roughness, viscosity, 1000, 36)
    assert (segments, fittings, roughness) == before
    assert calculator.viscosity == 0.001


def test_pump_head_matches_energy_balance_and_preserves_gui_units():
    parameters = pump_inputs()
    before = deepcopy(parameters)
    result = solve_pump(parameters)
    assert result.solved_key == 'power'
    assert result.solved_value == pytest.approx(25.25)
    assert result.unit == 'm'
    assert parameters == before
    assert result.values['in_dia'] == '10'
    assert result.values['in_flow'] == '36'
    assert result.values['effi'] == '80'


@pytest.mark.parametrize('unknown,expected', [('out_head', 20), ('effi', 80), ('in_press', 101325)])
def test_pump_linear_unknowns_match_known_balance(unknown, expected):
    parameters = pump_inputs()
    parameters['power'] = '25.25'
    parameters[unknown] = 'Unspecified'
    assert solve_pump(parameters).solved_value == pytest.approx(expected)


@pytest.mark.parametrize('unknown', ['in_flow', 'out_dia'])
def test_pump_nonlinear_unknown_selects_positive_real_root(unknown):
    parameters = pump_inputs()
    parameters['out_dia'] = '8'
    velocity_in = 0.01 / (pi * 0.1 ** 2 / 4)
    velocity_out = 0.01 / (pi * 0.08 ** 2 / 4)
    parameters['power'] = str((20.2 + (velocity_out ** 2 - velocity_in ** 2) / (2 * 9.81)) / 0.8)
    parameters[unknown] = 'Unspecified'
    expected = 36 if unknown == 'in_flow' else 8
    result = solve_pump(parameters)
    assert result.solved_value == pytest.approx(expected)
    if unknown == 'in_flow':
        assert float(result.values['out_flow']) == pytest.approx(expected)


def test_no_solution_does_not_leak_unit_conversions_into_input():
    parameters = pump_inputs()
    parameters['effi'] = '0'
    before = deepcopy(parameters)
    with pytest.raises(CalculationError):
        solve_pump(parameters)
    assert parameters == before


def test_npsh_matches_existing_pressure_head_basis_and_updates_comparison():
    parameters = pump_inputs()
    before = deepcopy(parameters)
    available = calculate_npsha(parameters, '23.8')
    expected = (101325 - 23.8 * 133.322) / (1000 * 9.81) + 2 - 0.5 - 1
    assert available == pytest.approx(expected)
    comparison = compare_npsh(available, 4)
    assert comparison.ratio == pytest.approx(expected / 4)
    assert comparison.difference == pytest.approx(expected - 4)
    assert compare_npsh(available, 0).ratio is None
    assert parameters == before
