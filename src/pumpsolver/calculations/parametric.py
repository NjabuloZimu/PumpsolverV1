"""Immutable parametric studies of the pump balance and saved pipe designs.

Study ranges and results use the same display units as the main window. A
point count includes both endpoints. Each stepped value holds for one complete
range sweep. Calculations use isolated numeric copies, never the saved project.
"""

from dataclasses import dataclass
from math import isfinite, pi

from pumpsolver.models import PARAMETER_FIELDS, ProjectState

from .pipe_losses import CalculationError, PipeLossCalculator, _number
from .pump import LABELS, PARAMETERS as PUMP_KEYS, UNITS


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    unit: str


INDEPENDENT_PARAMETERS = (
    Parameter('flow', 'Volumetric flow rate', 'm³/h'),
    Parameter('density', 'Fluid density', 'kg/m³'),
    *(Parameter(key, LABELS[key], UNITS[key]) for key in (
        'effi', 'in_head', 'out_head', 'in_press', 'out_press', 'power',
        'safety')),
)

# Flow and density are inputs to the loss calculations. Keeping them as inputs
# avoids treating loss heads as constants while solving for their own causes.
# Gravity remains the project's fixed pump setting: the established pipe-loss
# calculator uses standard gravity and does not support a gravity sweep.
DEPENDENT_PARAMETERS = (
    *(Parameter(key, LABELS[key], UNITS[key]) for key in (
        'power', 'effi', 'in_head', 'out_head', 'in_press', 'out_press', 'safety')),
    Parameter('in_loss', 'Inlet dynamic losses', 'm'),
    Parameter('out_loss', 'Outlet dynamic losses', 'm'),
    Parameter('total_loss', 'Total dynamic losses', 'm'),
    Parameter('in_major_loss', 'Inlet major losses', 'm'),
    Parameter('in_minor_loss', 'Inlet minor losses', 'm'),
    Parameter('out_major_loss', 'Outlet major losses', 'm'),
    Parameter('out_minor_loss', 'Outlet minor losses', 'm'),
    Parameter('total_major_loss', 'Total major losses', 'm'),
    Parameter('total_minor_loss', 'Total minor losses', 'm'),
)
PARAMETERS = {item.key: item for item in (*INDEPENDENT_PARAMETERS, *DEPENDENT_PARAMETERS)}
MAX_STUDY_POINTS = 10_000


@dataclass(frozen=True)
class StudyRequest:
    independent_key: str
    start: float
    stop: float
    points: int
    dependent_key: str
    step_key: str | None = None
    step_values: tuple[float, ...] = ()


@dataclass(frozen=True)
class StudyCurve:
    step_value: float | None
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]


@dataclass(frozen=True)
class StudyResult:
    request: StudyRequest
    independent: Parameter
    dependent: Parameter
    step_parameter: Parameter | None
    curves: tuple[StudyCurve, ...]


def _input_number(key, value):
    """Validate an adjustable input in display units."""
    spec = PARAMETERS.get(key)
    label = spec.label if spec else LABELS[key]
    number = _number(value, label)
    if key in {'density', 'in_dens', 'out_dens', 'in_dia', 'out_dia', 'gravity'} and number <= 0:
        raise CalculationError(f'{label} must be greater than zero.')
    if key in {'flow', 'in_flow', 'out_flow', 'power', 'safety', 'in_loss', 'out_loss'} and number < 0:
        raise CalculationError(f'{label} cannot be negative.')
    if key == 'effi' and not 0 < number <= 100:
        raise CalculationError('Pump Efficiency must be greater than zero and at most 100%.')
    return number


def _set_parameter(values, key, value):
    if key == 'flow':
        values['in_flow'] = values['out_flow'] = value
    elif key == 'density':
        values['in_dens'] = values['out_dens'] = value
    else:
        values[key] = value


def _validate_request(request):
    independent = {item.key for item in INDEPENDENT_PARAMETERS}
    dependent = {item.key for item in DEPENDENT_PARAMETERS}
    if request.independent_key not in independent:
        raise CalculationError('Choose a supported independent variable.')
    if request.dependent_key not in dependent:
        raise CalculationError('Choose a supported dependent variable.')
    keys = [request.independent_key, request.dependent_key]
    if request.step_key is not None:
        if request.step_key not in independent:
            raise CalculationError('Choose a supported step variable.')
        keys.append(request.step_key)
    if len(keys) != len(set(keys)):
        raise CalculationError('Independent, dependent and step variables must be different.')
    if isinstance(request.points, bool) or not isinstance(request.points, int) or request.points < 2:
        raise CalculationError('Use at least two integer range points, including both endpoints.')
    start = _input_number(request.independent_key, request.start)
    stop = _input_number(request.independent_key, request.stop)
    if start == stop:
        raise CalculationError('Range start and stop must be different.')
    if request.step_key is None:
        if request.step_values:
            raise CalculationError('Choose a step variable before entering step values.')
        step_values = (None,)
    else:
        if not request.step_values:
            raise CalculationError('Enter at least one value for the step variable.')
        step_values = tuple(_input_number(request.step_key, value) for value in request.step_values)
    if request.points * len(step_values) > MAX_STUDY_POINTS:
        raise CalculationError(f'A study can contain at most {MAX_STUDY_POINTS:,} total points.')
    # Avoid overflow in (stop-start) for a large signed but finite range.
    x_values = tuple(start * (1 - index / (request.points - 1)) + stop * (index / (request.points - 1))
                     for index in range(request.points))
    return x_values, step_values


def _required_sides(dependent_key):
    if dependent_key == 'in_loss' or dependent_key.startswith('in_') and dependent_key.endswith('_loss'):
        return ('inlet',)
    if dependent_key == 'out_loss' or dependent_key.startswith('out_') and dependent_key.endswith('_loss'):
        return ('outlet',)
    if dependent_key.startswith('total_'):
        return ('inlet', 'outlet')
    return ()


def _pipe_loss(side, design, values):
    prefix = 'in' if side == 'inlet' else 'out'
    settings = design.to_legacy()
    calculator = PipeLossCalculator(side, design.transition_equation)
    result = calculator.calculate(
        settings['segments'], settings['fittings'], settings['roughness'],
        settings['viscosity'], values[f'{prefix}_dens'], values[f'{prefix}_flow'],
        entrance_enabled=design.entrance_enabled,
        entrance_coefficient=design.entrance_coefficient,
        exit_enabled=design.exit_enabled, exit_coefficient=design.exit_coefficient,
    )
    values[f'{prefix}_loss'] = result.total_loss
    # These are the pipe segments attached to the pump, as in designer Save.
    boundary = design.segments[-1] if side == 'inlet' else design.segments[0]
    values[f'{prefix}_dia'] = boundary.diameter_m * 100
    return result


def _solve_balance(raw, dependent_key):
    values = {key: (0.0 if key == dependent_key else _input_number(key, raw[key]))
              for key in PUMP_KEYS}
    gravity = values['gravity']
    inlet_pressure_head = values['in_press'] / (values['in_dens'] * gravity)
    outlet_pressure_head = values['out_press'] / (values['out_dens'] * gravity)
    inlet_velocity = values['in_flow'] / 3600 / (pi * (values['in_dia'] / 200) ** 2)
    outlet_velocity = values['out_flow'] / 3600 / (pi * (values['out_dia'] / 200) ** 2)
    residual = (outlet_pressure_head - inlet_pressure_head
                + (outlet_velocity ** 2 - inlet_velocity ** 2) / (2 * gravity)
                + values['out_head'] - values['in_head']
                - values['effi'] / 100 * values['power']
                + values['in_loss'] + values['out_loss'] + values['safety'])
    coefficient = {
        'in_head': -1.0, 'out_head': 1.0,
        'in_press': -1 / (values['in_dens'] * gravity),
        'out_press': 1 / (values['out_dens'] * gravity),
        'power': -values['effi'] / 100,
        'effi': -values['power'] / 100,
        'safety': 1.0,
    }[dependent_key]
    if coefficient == 0:
        raise CalculationError('The pump balance has no unique solution for the dependent variable.')
    return _input_number(dependent_key, -residual / coefficient)


def run_study(project: ProjectState, request: StudyRequest) -> StudyResult:
    """Run every requested point or raise without changing ``project``.

    Pump dependents replace the corresponding saved value as the one unknown.
    Loss dependents read recalculated designs and need no other pump unknown to
    be filled. Every active design is recalculated at every point, including
    viscosity, roughness, fittings, transitions and selected tank boundaries.
    """
    x_values, step_values = _validate_request(request)
    active = {'inlet': project.parameters.designer_status_in,
              'outlet': project.parameters.designer_status_out}
    for side in _required_sides(request.dependent_key):
        if not active[side]:
            raise CalculationError(f'Activate the {side} losses calculator before studying these losses.')
    base_values = {key: (None if getattr(project.parameters, field) is None
                         else getattr(project.parameters, field) / factor)
                   for key, (field, factor) in PARAMETER_FIELDS.items()}
    curves = []
    for step_index, step_value in enumerate(step_values, 1):
        y_values = []
        for point_index, x_value in enumerate(x_values, 1):
            values = dict(base_values)
            _set_parameter(values, request.independent_key, x_value)
            if request.step_key is not None:
                _set_parameter(values, request.step_key, step_value)
            try:
                losses = {}
                for side in ('inlet', 'outlet'):
                    if active[side]:
                        losses[side] = _pipe_loss(side, getattr(project, side), values)
                required_sides = _required_sides(request.dependent_key)
                if required_sides:
                    attribute = ('major_loss' if 'major' in request.dependent_key else
                                 'minor_loss' if 'minor' in request.dependent_key else 'total_loss')
                    dependent_value = sum(getattr(losses[side], attribute) for side in required_sides)
                else:
                    dependent_value = _solve_balance(values, request.dependent_key)
                if not isfinite(dependent_value):
                    raise CalculationError('The calculated value must be finite.')
            except (CalculationError, ArithmeticError, ValueError) as error:
                step_context = (f', step {step_index} ({PARAMETERS[request.step_key].label} = {step_value:g})'
                                if request.step_key is not None else '')
                raise CalculationError(f'Point {point_index} ({PARAMETERS[request.independent_key].label} = '
                                       f'{x_value:g}){step_context}: {error}') from error
            y_values.append(dependent_value)
        curves.append(StudyCurve(step_value, x_values, tuple(y_values)))
    return StudyResult(request, PARAMETERS[request.independent_key], PARAMETERS[request.dependent_key],
                       PARAMETERS[request.step_key] if request.step_key else None, tuple(curves))
