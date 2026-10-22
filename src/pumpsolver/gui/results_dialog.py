"""Render pure pump/NPSH results without converting or solving UI state in place."""

from copy import deepcopy

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QDialog

from pumpsolver.calculations.pipe_losses import CalculationError
from pumpsolver.calculations.pump import (
    LABELS, UNITS, calculate_npsha, compare_npsh, solve_pump,
)
from pumpsolver.models import PumpInputs
from .centered_canvas import center_window_contents
from .generated.ui_results_dialog import Ui_SolvePage


class SolvePage(QDialog):
    resultsCommitted = pyqtSignal(object)

    def __init__(self, data):
        super().__init__()
        self.ui = Ui_SolvePage()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.data = deepcopy(data)
        self.solution = None
        self.NPSHa = None
        self.designer_status_in = None
        self.designer_status_out = None
        self.ui.pushButtonClose.clicked.connect(self.closewindow)
        self.ui.lineEditHeadRequired.textEdited.connect(self.updateNPSH)
        self.ui.lineEditVapourPress.textEdited.connect(self.cavitation)
        self.answer_f()
        self.cavitation()

    def designer_statuses(self, designer, identifier):
        if identifier == 'Inlet':
            self.designer_status_in = designer
        elif identifier == 'Outlet':
            self.designer_status_out = designer

    def closewindow(self):
        # Failed solves retain the draft and never send unconverted/partial data.
        if self.solution is not None:
            self.resultsCommitted.emit(PumpInputs.from_legacy(self.data))
        self.close()

    def answer_f(self):
        try:
            self.solution = solve_pump(self.data)
        except CalculationError as error:
            self.solution = None
            self.ui.labelMissingVar.setText(str(error))
            return
        self.data = self.solution.values
        label = LABELS[self.solution.solved_key]
        self.ui.labelMissingVar.setText(
            f'{label} = {self.solution.solved_value:#.9g} {self.solution.unit}')
        self.ui.labelLossesMeters.setText(
            f'Inlet head losses: {self.data["in_loss"]} m; '
            f'outlet head losses: {self.data["out_loss"]} m.')

    def set(self):
        """Display metadata retained for callers that used the old dialog API."""
        return LABELS.copy(), UNITS.copy()

    def cavitation(self, *args):
        try:
            self.NPSHa = calculate_npsha(self.data, self.ui.lineEditVapourPress.text())
        except (CalculationError, KeyError):
            self.NPSHa = None
            self.ui.label_NPSHa.clear()
        else:
            self.ui.label_NPSHa.setText(format(self.NPSHa, '#.6g'))
        self.updateNPSH()
        return self.NPSHa

    def updateNPSH(self, *args):
        try:
            comparison = compare_npsh(self.NPSHa, self.ui.lineEditHeadRequired.text())
        except CalculationError:
            self.ui.labelNPSHRatio.clear()
            self.ui.labelNPSHDiff.clear()
            return
        self.ui.labelNPSHRatio.setText(
            format(comparison.ratio, '#.6g') if comparison.ratio is not None else '')
        self.ui.labelNPSHDiff.setText(format(comparison.difference, '#.6g'))
