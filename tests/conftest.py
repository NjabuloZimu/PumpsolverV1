"""Shared data and one QApplication lifetime for the test session."""

import os

import pytest


@pytest.fixture(scope="session")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def project_state():
    return {
        "parameters": {
            "in_dia": "10", "in_head": "-2.5", "in_loss": "0.1",
            "in_flow": "36", "in_dens": "1000", "in_press": "101325",
            "out_dia": "8", "out_head": "20", "out_loss": "1.2",
            "out_flow": "36", "out_dens": "1000", "out_press": "101325",
            "effi": "0.8", "power": "Unspecified", "safety": "1.1",
            "gravity": "9.81", "designer_status_in": False,
            "designer_status_out": True,
        },
        "inlet": {
            "segments": {
                "Line Segment 1, Segment Length (m)": "2.5",
                "Line Segment 1, Segment Diameter (cm)": "10",
                "Line Segment 2, Segment Length (m)": "",
                "Line Segment 2, Segment Diameter (cm)": "8",
            },
            "fittings": [
                {"Line Segment": 1, "Fitting 1, Fitting Type": 'Válve, "open"',
                 "Fitting 1, Loss Factor": "0.15", "Fitting 2, Fitting Type": "Bend",
                 "Fitting 2, Loss Factor": "0.3"},
                {"Line Segment": 2, "Fitting 1, Fitting Type": "",
                 "Fitting 1, Loss Factor": ""},
            ],
            "roughness": [
                {"Line Segment": 1, "Segment Roughness": "Smooth Pipe"},
                {"Line Segment": 2, "Segment Roughness": "0.045"},
            ],
            "viscosity": "1.005", "transition_equation": "R.J.S Pigott",
        },
        "outlet": {
            "segments": {"Line Segment 1, Segment Length (m)": "20",
                         "Line Segment 1, Segment Diameter (cm)": "8"},
            "fittings": [],
            "roughness": [{"Line Segment": 1, "Segment Roughness": ""}],
            "viscosity": "", "transition_equation": "Moody",
        },
    }
