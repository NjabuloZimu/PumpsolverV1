"""Qt-independent project data. Physical quantities are stored in SI units.

CSV adapters retain the original editable text for unchanged values, so a
save/open cycle does not round a user's numbers or replace unfinished cells.
"""

from dataclasses import dataclass, field
import math
import re


# Legacy CSV field -> (SI model field, display-to-SI multiplier).
PARAMETER_FIELDS = {
    'in_dia': ('in_diameter_m', 0.01), 'in_head': ('in_elevation_m', 1.0),
    'in_loss': ('in_loss_m', 1.0), 'in_flow': ('in_flow_m3_s', 1 / 3600),
    'in_dens': ('in_density_kg_m3', 1.0), 'in_press': ('in_pressure_pa', 1.0),
    'out_dia': ('out_diameter_m', 0.01), 'out_head': ('out_elevation_m', 1.0),
    'out_loss': ('out_loss_m', 1.0), 'out_flow': ('out_flow_m3_s', 1 / 3600),
    'out_dens': ('out_density_kg_m3', 1.0), 'out_press': ('out_pressure_pa', 1.0),
    'effi': ('efficiency_fraction', 0.01), 'power': ('available_head_m', 1.0),
    'safety': ('safety_head_m', 1.0), 'gravity': ('gravity_m_s2', 1.0),
}
BOOLEAN_FIELDS = ('designer_status_in', 'designer_status_out')
TRANSITION_EQUATIONS = ('Moody', 'R.J.S Pigott')


def _numeric(value, factor=1.0):
    text = '' if value is None else str(value).strip()
    if text in ('', 'Unspecified'):
        return None, text
    try:
        number = float(text) * factor
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f'Expected a number, got {text!r}.') from error
    if not math.isfinite(number):
        raise ValueError('Numbers must be finite.')
    return number, text


def _boolean(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text not in ('true', 'false'):
        raise ValueError('Designer states must be True or False.')
    return text == 'true'


def _display(value, factor=1.0, original=None, missing=''):
    if value is None:
        return missing
    if original is not None and value == original[0]:
        return original[1]
    return format(value / factor, '.15g')


@dataclass(frozen=True)
class PumpInputs:
    in_diameter_m: float | None = None
    in_elevation_m: float | None = None
    in_loss_m: float | None = None
    in_flow_m3_s: float | None = None
    in_density_kg_m3: float | None = None
    in_pressure_pa: float | None = None
    out_diameter_m: float | None = None
    out_elevation_m: float | None = None
    out_loss_m: float | None = None
    out_flow_m3_s: float | None = None
    out_density_kg_m3: float | None = None
    out_pressure_pa: float | None = None
    efficiency_fraction: float | None = None
    available_head_m: float | None = None
    safety_head_m: float | None = None
    gravity_m_s2: float | None = None
    designer_status_in: bool = False
    designer_status_out: bool = False
    _display_values: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_legacy(cls, values):
        expected = set(PARAMETER_FIELDS) | set(BOOLEAN_FIELDS)
        if set(values) != expected:
            raise ValueError('Project parameters must contain every known pump field.')
        fields, originals = {}, {}
        for key, (name, factor) in PARAMETER_FIELDS.items():
            value, text = _numeric(values[key], factor)
            fields[name] = value
            originals[key] = (value, text)
        for key in BOOLEAN_FIELDS:
            fields[key] = _boolean(values[key])
        return cls(**fields, _display_values=originals)

    def to_legacy(self):
        values = {
            key: _display(getattr(self, name), factor,
                          self._display_values.get(key), missing='Unspecified')
            for key, (name, factor) in PARAMETER_FIELDS.items()
        }
        values.update({key: getattr(self, key) for key in BOOLEAN_FIELDS})
        return values


@dataclass(frozen=True)
class Fitting:
    number: int
    name: str
    loss_factor: float | None
    _display_value: tuple | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class Segment:
    number: int
    length_m: float | None
    diameter_m: float | None
    fittings: tuple[Fitting, ...] = ()
    roughness_m: float | None = None
    smooth: bool = False
    has_roughness: bool = False
    has_fitting_group: bool = False
    _display_values: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class PipeDesign:
    segments: tuple[Segment, ...] = ()
    viscosity_pa_s: float | None = None
    transition_equation: str = 'Moody'
    _viscosity_display: tuple | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_legacy(cls, data):
        grouped = {}
        for key, value in data.get('segments', {}).items():
            match = re.fullmatch(r'Line Segment ([1-9][0-9]*), (Segment Length \(m\)|Segment Diameter \(cm\))', key)
            if not match:
                raise ValueError(f'Unknown pipe segment field: {key}.')
            grouped.setdefault(int(match[1]), {})[match[2]] = value
        numbers = sorted(grouped)
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError('Pipe segment numbers must start at 1 without gaps.')
        fitting_groups, roughness = {}, {}
        for entry in data.get('fittings', []):
            number = int(entry['Line Segment'])
            if number not in grouped or number in fitting_groups:
                raise ValueError('Fittings must reference a unique existing segment.')
            fitting_groups[number] = entry
        for entry in data.get('roughness', []):
            number = int(entry['Line Segment'])
            if number not in grouped or number in roughness:
                raise ValueError('Roughness must reference a unique existing segment.')
            roughness[number] = entry['Segment Roughness']
        segments = []
        for number in numbers:
            source = grouped[number]
            if set(source) != {'Segment Length (m)', 'Segment Diameter (cm)'}:
                raise ValueError('Each segment requires length and diameter fields.')
            length, length_text = _numeric(source['Segment Length (m)'])
            diameter, diameter_text = _numeric(source['Segment Diameter (cm)'], 0.01)
            group = fitting_groups.get(number, {})
            fittings = {}
            for key, value in group.items():
                if key == 'Line Segment':
                    continue
                match = re.fullmatch(r'Fitting ([1-9][0-9]*), (Fitting Type|Loss Factor)', key)
                if not match:
                    raise ValueError(f'Unknown fitting field: {key}.')
                fittings.setdefault(int(match[1]), {})[match[2]] = value
            if sorted(fittings) != list(range(1, len(fittings) + 1)):
                raise ValueError('Fitting numbers must start at 1 without gaps.')
            typed_fittings = []
            for fitting_number, fitting in sorted(fittings.items()):
                if set(fitting) != {'Fitting Type', 'Loss Factor'}:
                    raise ValueError('Each fitting requires its type and loss factor.')
                factor, factor_text = _numeric(fitting['Loss Factor'])
                typed_fittings.append(Fitting(fitting_number, str(fitting['Fitting Type']), factor, (factor, factor_text)))
            roughness_text = str(roughness.get(number, ''))
            smooth = roughness_text == 'Smooth Pipe'
            rough, rough_text = (0.0, roughness_text) if smooth else _numeric(roughness_text, 0.001)
            segments.append(Segment(
                number, length, diameter, tuple(typed_fittings), rough, smooth,
                number in roughness, number in fitting_groups,
                {'length': (length, length_text), 'diameter': (diameter, diameter_text),
                 'roughness': (rough, rough_text)},
            ))
        viscosity, viscosity_text = _numeric(data.get('viscosity', ''), 0.001)
        transition = data.get('transition_equation', 'Moody')
        if transition not in TRANSITION_EQUATIONS:
            raise ValueError('Unknown transition equation.')
        return cls(tuple(segments), viscosity, transition, (viscosity, viscosity_text))

    def to_legacy(self):
        segments, fittings, roughness = {}, [], []
        for segment in self.segments:
            prefix = f'Line Segment {segment.number}, '
            segments[prefix + 'Segment Length (m)'] = _display(segment.length_m, original=segment._display_values.get('length'))
            segments[prefix + 'Segment Diameter (cm)'] = _display(segment.diameter_m, 0.01, segment._display_values.get('diameter'))
            if segment.has_fitting_group or segment.fittings:
                entry = {'Line Segment': segment.number}
                for fitting in segment.fittings:
                    entry[f'Fitting {fitting.number}, Fitting Type'] = fitting.name
                    entry[f'Fitting {fitting.number}, Loss Factor'] = _display(fitting.loss_factor, original=fitting._display_value)
                fittings.append(entry)
            if segment.has_roughness:
                value = 'Smooth Pipe' if segment.smooth else _display(segment.roughness_m, 0.001, segment._display_values.get('roughness'))
                roughness.append({'Line Segment': segment.number, 'Segment Roughness': value})
        return {'segments': segments, 'fittings': fittings, 'roughness': roughness,
                'viscosity': _display(self.viscosity_pa_s, 0.001, self._viscosity_display),
                'transition_equation': self.transition_equation}


@dataclass(frozen=True)
class ProjectState:
    parameters: PumpInputs = field(default_factory=PumpInputs)
    inlet: PipeDesign = field(default_factory=PipeDesign)
    outlet: PipeDesign = field(default_factory=PipeDesign)

    @classmethod
    def from_legacy(cls, state):
        if set(state) != {'parameters', 'inlet', 'outlet'}:
            raise ValueError('A project requires parameters, inlet, and outlet sections.')
        return cls(PumpInputs.from_legacy(state['parameters']),
                   PipeDesign.from_legacy(state['inlet']), PipeDesign.from_legacy(state['outlet']))

    def to_legacy(self):
        return {'parameters': self.parameters.to_legacy(),
                'inlet': self.inlet.to_legacy(), 'outlet': self.outlet.to_legacy()}


@dataclass(frozen=True)
class PipePropertiesUpdate:
    """One committed dialog edit; values use the CSV/display adapter keys."""

    side: str
    values: dict[str, str]
    design: PipeDesign
    enabled: bool


@dataclass(frozen=True)
class DesignerCommit:
    """One explicit designer save, including the scalar outputs it produced."""

    side: str
    design: PipeDesign
    density: str
    flow: str
    diameter: str | None
    total_losses: float | None
    enabled: bool
