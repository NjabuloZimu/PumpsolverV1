"""Pump energy balance and NPSH, independent of GUI and input mutation."""

from dataclasses import dataclass
from math import isfinite, pi

from .pipe_losses import CalculationError, _number

PARAMETERS = (
    "in_dia", "in_head", "in_loss", "in_flow", "in_dens", "in_press",
    "out_dia", "out_head", "out_loss", "out_flow", "out_dens", "out_press",
    "effi", "power", "safety", "gravity")
LABELS = {
    "in_dia": "Inlet Diameter", "in_head": "Static Suction Head",
    "in_loss": "Inlet Pipe/Fitting Dynamic Head Losses", "in_flow": "Inlet Volumetric Flowrate",
    "in_dens": "Inlet Density", "in_press": "Inlet Pressure", "out_dia": "Outlet Diameter",
    "out_head": "Static Discharge Head", "out_loss": "Outlet Pipe/Fitting Dynamic Head Losses",
    "out_flow": "Outlet Volumetric Flowrate", "out_dens": "Outlet Density",
    "out_press": "Outlet Pressure", "effi": "Pump Efficiency", "power": "Available Head",
    "safety": "Safety", "gravity": "Gravitational Acceleration"}
UNITS = {key: "m" for key in PARAMETERS}
UNITS.update({"in_dia": "cm", "out_dia": "cm", "in_flow": "m3/h", "out_flow": "m3/h",
              "in_dens": "kg/m3", "out_dens": "kg/m3", "in_press": "Pa", "out_press": "Pa",
              "effi": "%", "gravity": "m/s2"})


@dataclass(frozen=True)
class PumpSolution:
    values: dict
    solved_key: str
    solved_value: float
    unit: str


@dataclass(frozen=True)
class NPSHComparison:
    available: float
    required: float
    ratio: float | None
    difference: float


def _unspecified(value):
    return value is None or (isinstance(value, str) and value.strip() in ("", "Unspecified"))


def solve_pump(parameters):
    """Solve one independent unknown; every returned value keeps GUI units.

    The existing application couples outlet flow/density to the corresponding
    unspecified inlet quantity. SymPy loads only when a solve is requested.
    """
    try:
        raw = {key: parameters[key] for key in PARAMETERS}
    except KeyError as error:
        raise CalculationError(f"Missing pump parameter: {error.args[0]}") from error
    unknown = [key for key, value in raw.items() if _unspecified(value)]
    for inlet, outlet in (("in_flow", "out_flow"), ("in_dens", "out_dens")):
        if inlet in unknown and outlet in unknown:
            unknown.remove(outlet)
    if len(unknown) != 1:
        raise CalculationError("Specify all but one independent pump parameter.")
    key = unknown[0]
    from sympy import Symbol, solve
    symbol = Symbol("unknown", real=True)
    converted = {}
    for name, value in raw.items():
        if name == key or (key == "in_flow" and name == "out_flow") or (key == "in_dens" and name == "out_dens"):
            converted[name] = symbol
        else:
            converted[name] = _number(value, LABELS[name])
    for name in ("in_dia", "out_dia", "in_dens", "out_dens", "gravity"):
        if converted[name] is not symbol and converted[name] <= 0:
            raise CalculationError(f"{LABELS[name]} must be greater than zero.")
    # This separate local map prevents error paths leaking SI conversions.
    si = dict(converted)
    for name in ("in_dia", "out_dia"):
        si[name] /= 100
    for name in ("in_flow", "out_flow"):
        si[name] /= 3600
    si["effi"] /= 100
    velocity_in = si["in_flow"] / (pi * (si["in_dia"] / 2) ** 2)
    velocity_out = si["out_flow"] / (pi * (si["out_dia"] / 2) ** 2)
    expression = (si["out_press"] / (si["out_dens"] * si["gravity"])
                  - si["in_press"] / (si["in_dens"] * si["gravity"])
                  + (velocity_out ** 2 - velocity_in ** 2) / (2 * si["gravity"])
                  + si["out_head"] - si["in_head"] - si["effi"] * si["power"]
                  + si["in_loss"] + si["out_loss"] + si["safety"])
    try:
        roots = solve(expression, symbol)
    except (ArithmeticError, ValueError, NotImplementedError) as error:
        raise CalculationError("The pump balance could not be solved for this input.") from error
    candidates = []
    signed = {"in_head", "out_head", "in_press", "out_press"}
    for root in roots:
        if root.free_symbols or root.is_real is False:
            continue
        try:
            candidate = complex(root.evalf())
        except (TypeError, ValueError, OverflowError):
            continue
        if abs(candidate.imag) > 1e-10 or not isfinite(candidate.real):
            continue
        value = float(candidate.real)
        if key not in signed and value < 0:
            continue
        if key in {"in_dia", "out_dia", "in_dens", "out_dens", "gravity"} and value <= 0:
            continue
        if key == "effi" and not 0 < value <= 100:
            continue
        candidates.append(value)
    if not candidates:
        raise CalculationError("There is no finite real solution in the parameter's valid range.")
    value = min(candidates)
    values = dict(parameters)
    values[key] = format(value, ".9g")
    if key in ("in_flow", "in_dens"):
        values["out_flow" if key == "in_flow" else "out_dens"] = values[key]
    return PumpSolution(values, key, value, UNITS[key])


def calculate_npsha(parameters, vapour_pressure_mmhg):
    """Available NPSH in metres, retaining the existing application basis."""
    pressure = _number(parameters["in_press"], "Inlet pressure (Pa)")
    density = _number(parameters["in_dens"], "Inlet density (kg/m3)", positive=True)
    gravity = _number(parameters["gravity"], "Gravity (m/s2)", positive=True)
    elevation = _number(parameters["in_head"], "Inlet head (m)")
    losses = _number(parameters["in_loss"], "Inlet losses (m)")
    safety = _number(parameters["safety"], "Safety (m)")
    vapour = _number(vapour_pressure_mmhg, "Vapour pressure (mmHg)", nonnegative=True) * 133.322
    return (pressure - vapour) / (density * gravity) + elevation - losses - safety


def compare_npsh(available, required):
    available = _number(available, "Available NPSH (m)")
    required = _number(required, "Required NPSH (m)", nonnegative=True)
    return NPSHComparison(available, required, available / required if required else None, available - required)
