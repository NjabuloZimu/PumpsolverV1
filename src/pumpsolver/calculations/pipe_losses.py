"""Pipe physics without Qt. Design inputs use cm, m, mm, cP and m3/h.

Unit conversion is local; neither input collections nor instance settings are
changed by a calculation. Pipe transition correlations remain the application's
existing ones; entrance and exit losses use independently selected coefficients.
"""

from dataclasses import dataclass
from math import isfinite, log10, pi, sqrt
import re

GRAVITY = 9.80665


class CalculationError(ValueError):
    """Incomplete/invalid inputs or no physically usable solution."""


def _number(value, name, *, positive=False, nonnegative=False):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise CalculationError(f"{name} must be a number.") from error
    if not isfinite(number):
        raise CalculationError(f"{name} must be finite.")
    if positive and number <= 0:
        raise CalculationError(f"{name} must be greater than zero.")
    if nonnegative and number < 0:
        raise CalculationError(f"{name} cannot be negative.")
    return number


@dataclass(frozen=True)
class SegmentLossResult:
    line_segment: int
    length_m: float
    diameter_m: float
    velocity: float
    reynolds: float
    relative_roughness: float
    friction_factor: float
    flow_type: str
    major_loss: float
    fittings_loss: float
    transition_loss: float
    entrance_loss: float
    exit_loss: float

    @property
    def boundary_loss(self):
        return self.entrance_loss + self.exit_loss

    @property
    def minor_loss(self):
        """All local losses: fittings, diameter changes, and tank boundaries."""
        return self.fittings_loss + self.transition_loss + self.boundary_loss

    @property
    def total_loss(self):
        return self.major_loss + self.minor_loss


@dataclass(frozen=True)
class PipeLossResult:
    side: str
    transition_equation: str
    segments: tuple[SegmentLossResult, ...]
    contractions: int
    expansions: int

    @property
    def total_loss(self):
        return sum(item.total_loss for item in self.segments)

    @property
    def total_length(self):
        return sum(item.length_m for item in self.segments)

    @property
    def major_loss(self):
        return sum(item.major_loss for item in self.segments)

    @property
    def minor_loss(self):
        return sum(item.minor_loss for item in self.segments)

    @property
    def fittings_loss(self):
        return sum(item.fittings_loss for item in self.segments)

    @property
    def transition_loss(self):
        return sum(item.transition_loss for item in self.segments)

    @property
    def boundary_loss(self):
        return sum(item.boundary_loss for item in self.segments)

    @property
    def entrance_loss(self):
        return sum(item.entrance_loss for item in self.segments)

    @property
    def exit_loss(self):
        return sum(item.exit_loss for item in self.segments)


class PipeLossCalculator:
    """Explicit pipe side and equation; instance helper viscosity is in Pa.s."""

    def __init__(self, side="inlet", transition_equation="Moody", viscosity=0.001):
        self.side = self._side(side)
        self.transition_equation = self._equation(transition_equation)
        self.viscosity = viscosity

    @staticmethod
    def _side(side):
        if side not in ("inlet", "outlet"):
            raise CalculationError("Pipe side must be 'inlet' or 'outlet'.")
        return side

    @staticmethod
    def _equation(equation):
        if equation not in ("Moody", "R.J.S Pigott"):
            raise CalculationError("Choose Moody or R.J.S Pigott for the transition equation.")
        return equation

    @staticmethod
    def _boundary_enabled(value, default, name):
        if value is None:
            return default
        if not isinstance(value, bool):
            raise CalculationError(f'{name} must be True or False.')
        return value

    @staticmethod
    def con_exp_fit_loss(coeff, velocity):
        return coeff * velocity ** 2 / (2 * GRAVITY)

    @staticmethod
    def darcy_loss_cal(friction_factor, velocity, length, diameter):
        return friction_factor * length / diameter * velocity ** 2 / (2 * GRAVITY)

    @staticmethod
    def total_segment_loss(transition_loss, fittings_loss, major_loss):
        return transition_loss + fittings_loss + major_loss

    @staticmethod
    def expansion_coeff(current_diameter, previous_diameter):
        return (1 - previous_diameter / current_diameter) ** 2

    @staticmethod
    def contraction_coeff(current_diameter, previous_diameter, reynolds):
        return 0.1 if reynolds < 2100 else 0.4 * (1 - current_diameter / previous_diameter)

    @staticmethod
    def velocity(diameter, volumetric):
        return volumetric / (pi * (diameter / 2) ** 2) if diameter > 0 else 0.0

    def reynolds(self, diameter, velocity, density, viscosity=None):
        viscosity = self.viscosity if viscosity is None else viscosity
        return diameter * velocity * density / viscosity if viscosity > 0 and diameter > 0 else 0.0

    @staticmethod
    def relativeRoughness(roughness, diameter):
        return roughness / diameter if diameter > 0 else 0.0

    def region(self, relative_roughness, transition_equation=None):
        equation = self._equation(self.transition_equation if transition_equation is None else transition_equation)
        if relative_roughness is None or relative_roughness <= 0:
            return None
        return (1600 if equation == "Moody" else 3500) / relative_roughness

    @staticmethod
    def colebrook_equation(friction_factor, relative_roughness, reynolds):
        return (1 / sqrt(friction_factor) + 2 * log10(
            relative_roughness / 3.7 + 2.51 / (reynolds * sqrt(friction_factor))))

    @staticmethod
    def solve_colebrook(Re, epsilon_D, initial_guess=0.02):
        """Bisection in x=1/sqrt(f) keeps all iterates physically positive."""
        reynolds = _number(Re, "Reynolds number", positive=True)
        roughness = _number(epsilon_D, "Relative roughness", nonnegative=True)

        def residual(x):
            return x + 2 * log10(roughness / 3.7 + 2.51 * x / reynolds)

        low, high = 1e-12, 100.0
        if residual(low) >= 0:
            raise CalculationError("No positive Colebrook friction factor for this roughness.")
        while residual(high) <= 0 and high < 1e8:
            high *= 2
        if residual(high) <= 0:
            raise CalculationError("The Colebrook friction factor did not converge.")
        for _ in range(100):
            middle = (low + high) / 2
            if residual(middle) > 0:
                high = middle
            else:
                low = middle
        return 1 / ((low + high) / 2) ** 2

    def darcy_friction_factor(self, reynolds, relative_roughness, roughness,
                             transition_equation=None):
        if reynolds <= 0:
            return 0.0
        # Laminar f=64/Re applies regardless of wall roughness:
        # https://datatool.pumps.org/fluid-flow-iii/general
        if reynolds < 2100:
            return 64 / reynolds
        if roughness == 0 and reynolds > 4000:
            return 0.316 / reynolds ** 0.25
        threshold = self.region(relative_roughness, transition_equation)
        if threshold is not None and reynolds > threshold:
            return (1.14 + 2 * log10(1 / relative_roughness)) ** -2
        # Correct the legacy call that supplied Re and epsilon/D in reverse.
        return self.solve_colebrook(reynolds, relative_roughness or 0.0)

    def _flow_type(self, reynolds, relative_roughness, roughness, equation):
        if reynolds == 0:
            return "No flow"
        if reynolds < 2100:
            return "Laminar flow, smooth pipe" if roughness == 0 else "Laminar flow"
        if roughness == 0:
            return "Turbulent flow, smooth pipe" if reynolds > 4000 else "Transitional flow, smooth pipe"
        return ("Turbulent flow" if reynolds > self.region(relative_roughness, equation)
                else "Transitional flow / Colebrook Equation")

    @staticmethod
    def _segments(data):
        grouped = {}
        for key, value in data.items():
            match = re.fullmatch(r"Line Segment ([1-9]\d*), (Segment Length \(m\)|Segment Diameter \(cm\))", key)
            if match is None:
                raise CalculationError(f"Unknown pipe segment field: {key}")
            grouped.setdefault(int(match.group(1)), {})[match.group(2)] = value
        if not grouped:
            raise CalculationError("Enter at least one pipe segment.")
        if sorted(grouped) != list(range(1, len(grouped) + 1)):
            raise CalculationError("Pipe segment numbers must be consecutive from 1.")
        result = []
        for index, fields in sorted(grouped.items()):
            try:
                length = _number(fields["Segment Length (m)"], f"Segment {index} length", nonnegative=True)
                diameter = _number(fields["Segment Diameter (cm)"], f"Segment {index} diameter", positive=True) / 100
            except KeyError as error:
                raise CalculationError(f"Complete length and diameter for segment {index}.") from error
            result.append((index, length, diameter))
        return result

    def calculate(self, segments, fittings, roughness, viscosity, density, volumetric,
                  *, side=None, transition_equation=None,
                  entrance_enabled=None, entrance_coefficient=0.5,
                  exit_enabled=None, exit_coefficient=1.0):
        pipe_side = self._side(self.side if side is None else side)
        equation = self._equation(self.transition_equation if transition_equation is None else transition_equation)
        use_entrance = self._boundary_enabled(entrance_enabled, pipe_side == 'inlet', 'Entrance enabled')
        use_exit = self._boundary_enabled(exit_enabled, pipe_side == 'outlet', 'Exit enabled')
        entrance_k = _number(entrance_coefficient, 'Entrance coefficient', nonnegative=True)
        exit_k = _number(exit_coefficient, 'Exit coefficient', nonnegative=True)
        dynamic_viscosity = _number(viscosity, "Viscosity (cP)", positive=True) / 1000
        fluid_density = _number(density, "Density (kg/m3)", positive=True)
        flow = _number(volumetric, "Flow rate (m3/h)", nonnegative=True) / 3600
        pipes = self._segments(segments)
        ids = {index for index, _, _ in pipes}
        roughness_by_segment = {}
        for entry in roughness:
            index = entry.get("Line Segment")
            if index not in ids or index in roughness_by_segment:
                raise CalculationError(f"Unknown or duplicate roughness segment: {index}")
            raw = entry.get("Segment Roughness", "")
            roughness_by_segment[index] = (0.0 if raw == "Smooth Pipe" else
                _number(raw, f"Segment {index} roughness (mm)", nonnegative=True) / 1000)
        if set(roughness_by_segment) != ids:
            raise CalculationError("Specify roughness for every pipe segment.")
        fitting_coefficients = {}
        for entry in fittings:
            index = entry.get("Line Segment")
            if index not in ids or index in fitting_coefficients:
                raise CalculationError(f"Unknown or duplicate fitting segment: {index}")
            fitting_coefficients[index] = sum(
                _number(value, f"Segment {index}, {key}", nonnegative=True)
                for key, value in entry.items() if key.endswith(", Loss Factor"))
        results = []
        contractions = expansions = 0
        for position, (index, length, diameter) in enumerate(pipes):
            velocity = self.velocity(diameter, flow)
            reynolds = self.reynolds(diameter, velocity, fluid_density, dynamic_viscosity)
            absolute_roughness = roughness_by_segment[index]
            relative_roughness = self.relativeRoughness(absolute_roughness, diameter)
            friction = self.darcy_friction_factor(reynolds, relative_roughness, absolute_roughness, equation)
            transition_loss = entrance_loss = exit_loss = 0.0
            if position > 0:
                previous_diameter = pipes[position - 1][2]
                if diameter > previous_diameter:
                    expansions += 1
                    transition_loss = self.con_exp_fit_loss(
                        self.expansion_coeff(diameter, previous_diameter), self.velocity(previous_diameter, flow))
                elif diameter < previous_diameter:
                    contractions += 1
                    transition_loss = self.con_exp_fit_loss(
                        self.contraction_coeff(diameter, previous_diameter, reynolds), velocity)
            # Entrance and exit are independent; both apply once when a single
            # segment is simultaneously the first and last segment.
            if use_entrance and position == 0:
                entrance_loss = self.con_exp_fit_loss(entrance_k, velocity)
            if use_exit and position == len(pipes) - 1:
                exit_loss = self.con_exp_fit_loss(exit_k, velocity)
            results.append(SegmentLossResult(
                index, length, diameter, velocity, reynolds, relative_roughness, friction,
                self._flow_type(reynolds, relative_roughness, absolute_roughness, equation),
                self.darcy_loss_cal(friction, velocity, length, diameter),
                self.con_exp_fit_loss(fitting_coefficients.get(index, 0.0), velocity),
                transition_loss, entrance_loss, exit_loss))
        return PipeLossResult(pipe_side, equation, tuple(results), contractions, expansions)
