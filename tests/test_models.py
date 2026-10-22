"""Typed SI state preserves editable values and owns independent snapshots."""

import copy
from dataclasses import FrozenInstanceError, replace

import pytest

from pumpsolver.models import PipeDesign, ProjectState, PumpInputs


def test_pump_inputs_convert_display_units_to_si_and_preserve_original_text(project_state):
    source = copy.deepcopy(project_state["parameters"])
    source["in_dia"] = "10.0000"
    source["in_flow"] = "3.600e1"
    inputs = PumpInputs.from_legacy(source)
    assert inputs.in_diameter_m == pytest.approx(0.1)
    assert inputs.in_flow_m3_s == pytest.approx(0.01)
    assert inputs.efficiency_fraction == pytest.approx(0.008)
    assert inputs.in_elevation_m == pytest.approx(-2.5)
    assert inputs.available_head_m is None
    assert inputs.designer_status_in is False
    assert inputs.to_legacy() == source


def test_changed_si_pump_values_serialize_in_display_units(project_state):
    inputs = PumpInputs.from_legacy(project_state["parameters"])
    changed = replace(inputs, in_diameter_m=0.125, in_flow_m3_s=0.02,
                      efficiency_fraction=0.75, available_head_m=25.0)
    display = changed.to_legacy()
    assert display["in_dia"] == "12.5"
    assert display["in_flow"] == "72"
    assert display["effi"] == "75"
    assert display["power"] == "25"
    assert inputs.to_legacy() == project_state["parameters"]


def test_pipe_design_converts_geometry_roughness_and_viscosity_to_si(project_state):
    design = PipeDesign.from_legacy(project_state["inlet"])
    first, second = design.segments
    assert first.diameter_m == pytest.approx(0.1)
    assert first.length_m == pytest.approx(2.5)
    assert first.smooth is True
    assert first.roughness_m == 0.0
    assert second.length_m is None
    assert second.roughness_m == pytest.approx(0.000045)
    assert design.viscosity_pa_s == pytest.approx(0.001005)
    assert first.fittings[0].name == 'Válve, "open"'
    assert first.fittings[0].loss_factor == pytest.approx(0.15)
    assert design.to_legacy() == project_state["inlet"]


def test_changed_si_pipe_values_serialize_without_changing_original(project_state):
    design = PipeDesign.from_legacy(project_state["inlet"])
    second = replace(design.segments[1], length_m=4.75,
                     diameter_m=0.085, roughness_m=0.0002)
    changed = replace(design, segments=(design.segments[0], second), viscosity_pa_s=0.003)
    display = changed.to_legacy()
    assert display["segments"]["Line Segment 2, Segment Length (m)"] == "4.75"
    assert display["segments"]["Line Segment 2, Segment Diameter (cm)"] == "8.5"
    assert display["roughness"][1]["Segment Roughness"] == "0.2"
    assert display["viscosity"] == "3"
    assert design.to_legacy() == project_state["inlet"]


def test_empty_fitting_group_and_missing_roughness_survive_model_roundtrip(project_state):
    source = copy.deepcopy(project_state["inlet"])
    source["fittings"] = [{"Line Segment": 1}]
    source["roughness"] = []
    assert PipeDesign.from_legacy(source).to_legacy() == source


def test_model_does_not_retain_mutable_input_or_export_references(project_state):
    source = copy.deepcopy(project_state)
    model = ProjectState.from_legacy(source)
    original = copy.deepcopy(model.to_legacy())
    source["parameters"]["in_dia"] = "999"
    source["inlet"]["fittings"][0]["Fitting 1, Loss Factor"] = "999"
    source["inlet"]["roughness"][0]["Segment Roughness"] = "999"
    exported = model.to_legacy()
    exported["inlet"]["segments"].clear()
    exported["outlet"]["viscosity"] = "999"
    assert model.to_legacy() == original == project_state


def test_project_state_and_segment_values_are_immutable(project_state):
    state = ProjectState.from_legacy(project_state)
    with pytest.raises(FrozenInstanceError):
        state.parameters = PumpInputs()
    with pytest.raises(FrozenInstanceError):
        state.inlet.segments[0].length_m = 999
    changed = replace(state, inlet=replace(state.inlet, viscosity_pa_s=0.002))
    assert changed.inlet.viscosity_pa_s == 0.002
    assert changed.outlet == state.outlet
    assert state.to_legacy() == project_state


@pytest.mark.parametrize("key,value", [("in_dia", "NaN"), ("in_flow", "inf"),
                                      ("designer_status_in", "maybe")])
def test_model_rejects_invalid_scalar_values(project_state, key, value):
    project_state["parameters"][key] = value
    with pytest.raises(ValueError):
        ProjectState.from_legacy(project_state)


def test_model_rejects_orphan_fitting_references(project_state):
    project_state["inlet"]["fittings"][0]["Line Segment"] = 99
    with pytest.raises(ValueError):
        ProjectState.from_legacy(project_state)
