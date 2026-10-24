"""Keep active pipe losses consistent when shared project fluid inputs change."""

from dataclasses import replace

from .pipe_losses import CalculationError, PipeLossCalculator


def recalculate_active_losses(project):
    """Return a complete recalculated snapshot, or leave the source untouched.

    Each side keeps its own geometry, viscosity, roughness and boundary settings.
    Inactive designs and their manual loss values remain unchanged.
    """
    parameters = project.parameters
    updates = {}
    for side, prefix in (('inlet', 'in'), ('outlet', 'out')):
        if not getattr(parameters, f'designer_status_{prefix}'):
            continue
        design = getattr(project, side)
        data = design.to_legacy()
        flow = getattr(parameters, f'{prefix}_flow_m3_s')
        try:
            result = PipeLossCalculator(side, design.transition_equation).calculate(
                data['segments'], data['fittings'], data['roughness'], data['viscosity'],
                getattr(parameters, f'{prefix}_density_kg_m3'),
                None if flow is None else flow * 3600,
                entrance_enabled=design.entrance_enabled,
                entrance_coefficient=design.entrance_coefficient,
                exit_enabled=design.exit_enabled, exit_coefficient=design.exit_coefficient,
            )
        except (ValueError, ArithmeticError) as error:
            raise CalculationError(f'{side.title()} losses: {error}') from error
        boundary = design.segments[-1] if side == 'inlet' else design.segments[0]
        updates[f'{prefix}_loss_m'] = result.total_loss
        updates[f'{prefix}_diameter_m'] = boundary.diameter_m
    return replace(project, parameters=replace(parameters, **updates))
