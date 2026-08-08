import pytest
import numpy as np
from scipy.constants import g
from frictionCalc import Calculation
from PyQt5.QtWidgets import QApplication
import sys

# Create a QApplication instance for the Calculation dialog
app = QApplication(sys.argv)

def test_darcy_loss_cal():
    calc = Calculation()
    # Case: f=0.02, L=10, D=0.1, v=1
    # hf = 0.02 * (10/0.1) * (1^2 / (2 * g))
    expected = 0.02 * (10/0.1) * (1**2 / (2 * g))
    result = calc.darcy_loss_cal(0.02, 1.0, 10.0, 0.1)
    assert result == pytest.approx(expected)

def test_con_exp_fit_loss():
    calc = Calculation()
    # Case: K=0.5, v=1
    # hm = 0.5 * (1^2 / (2 * g))
    expected = 0.5 * (1**2 / (2 * g))
    result = calc.con_exp_fit_loss(0.5, 1.0)
    assert result == pytest.approx(expected)

def test_solve_colebrook():
    calc = Calculation()
    # For Re=1e5, epsilon/D=0.001, f is approx 0.02217
    result = calc.solve_colebrook(1e5, 0.001)
    assert result == pytest.approx(0.02217, abs=1e-3)

def test_robustness_zero_division():
    calc = Calculation()
    calc.viscosity = 0.001
    # Diameter 0
    assert calc.velocity(0, 100) == 0.0
    assert calc.reynolds(0, 1, 1000) == 0.0
    assert calc.relativeRoughness(0.001, 0) == 0.0

    # Viscosity 0
    calc.viscosity = 0.0
    assert calc.reynolds(0.1, 1, 1000) == 0.0

def test_smooth_pipe_logic():
    calc = Calculation()
    # Test smooth pipe friction factor (laminar)
    # Re = 1000, Smooth -> f = 64/1000 = 0.064
    result = calc.darcy_friction_factor(1000, None, 0.0)
    assert result == pytest.approx(0.064)

    # Test smooth pipe friction factor (turbulent)
    # Re = 1e5, Smooth -> f = 0.316 / (1e5^0.25)
    expected = 0.316 / (1e5**0.25)
    result = calc.darcy_friction_factor(1e5, None, 0.0)
    assert result == pytest.approx(expected)

if __name__ == "__main__":
    pytest.main([__file__])
