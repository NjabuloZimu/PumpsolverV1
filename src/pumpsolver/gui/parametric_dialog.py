"""A project-snapshot study with a Matplotlib canvas embedded in a Qt dialog."""

import csv
from copy import deepcopy
from math import isfinite

from PyQt5.QtCore import QLocale, Qt
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import QApplication, QDialog, QFileDialog
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from pumpsolver.calculations.parametric import (
    DEPENDENT_PARAMETERS, INDEPENDENT_PARAMETERS, PARAMETERS, StudyRequest,
    run_study as calculate_study,
)
from pumpsolver.calculations.pipe_losses import CalculationError
from pumpsolver.persistence.csv_io import ensure_csv_path
from .generated.ui_parametric_dialog import Ui_ParametricStudyDialog


def _label(parameter):
    unit = parameter.unit.replace('m3', 'm³').replace('s2', 's²')
    return f'{parameter.label} ({unit})'


class ParametricStudyDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = deepcopy(project)
        self.result = None
        self.ui = Ui_ParametricStudyDialog()
        self.ui.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        for attribute, widget in (
            ('independent_combo', 'independentCombo'), ('dependent_combo', 'dependentCombo'),
            ('start_edit', 'startEdit'), ('stop_edit', 'stopEdit'),
            ('points_spin', 'pointsSpin'), ('step_check', 'stepCheck'),
            ('step_combo', 'stepCombo'), ('step_values_edit', 'stepValuesEdit'),
            ('run_button', 'runButton'), ('export_button', 'exportButton'),
        ):
            setattr(self, attribute, getattr(self.ui, widget))
        for editor in (self.start_edit, self.stop_edit):
            validator = QDoubleValidator(editor)
            validator.setLocale(QLocale.c())
            validator.setNotation(QDoubleValidator.ScientificNotation)
            editor.setValidator(validator)
        self.figure = Figure(figsize=(9, 4), layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(220)
        self.axes = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.ui.plotLayout.addWidget(self.toolbar)
        self.ui.plotLayout.addWidget(self.canvas, 1)
        self._fill_combo(self.independent_combo, INDEPENDENT_PARAMETERS)
        self._fill_combo(self.dependent_combo, DEPENDENT_PARAMETERS, preferred='power')
        self._fill_combo(self.step_combo, INDEPENDENT_PARAMETERS, preferred='effi')
        self.independent_combo.currentIndexChanged.connect(self._independent_changed)
        self.dependent_combo.currentIndexChanged.connect(self._dependent_changed)
        self.step_combo.currentIndexChanged.connect(self._step_changed)
        self.step_check.toggled.connect(self._configuration_changed)
        for editor in (self.start_edit, self.stop_edit, self.step_values_edit):
            editor.textChanged.connect(self._configuration_changed)
        self.points_spin.valueChanged.connect(self._configuration_changed)
        self.run_button.clicked.connect(self.run_study)
        self.export_button.clicked.connect(self.export_results)
        self.ui.closeButton.clicked.connect(self.close)
        self._independent_changed()

    @staticmethod
    def _fill_combo(combo, parameters, excluded=(), preferred=None):
        previous = preferred or combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for parameter in parameters:
            if parameter.key not in excluded:
                combo.addItem(_label(parameter), parameter.key)
        index = combo.findData(previous)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _default_range(self, key):
        values = self.project.parameters.to_legacy()
        raw = values.get({'flow': 'in_flow', 'density': 'in_dens'}.get(key, key))
        try:
            base = float(raw)
        except (TypeError, ValueError):
            base = 0.0
        if not isfinite(base):
            base = 0.0
        if key == 'effi':
            return 50.0, 100.0
        if key == 'flow':
            return 0.0, 2 * base if base > 0 else 72.0
        if key == 'density':
            return (base * 0.8, base * 1.2) if base > 0 else (800.0, 1200.0)
        if key == 'gravity':
            return 9.7, 9.9
        if key == 'safety':
            return 0.0, 2 * base if base > 0 else 2.0
        if base:
            return tuple(sorted((base * 0.8, base * 1.2)))
        return (10.0, 60.0) if key == 'power' else (0.0, 10.0)

    def _independent_changed(self, *_):
        key = self.independent_combo.currentData()
        self._fill_combo(self.dependent_combo, DEPENDENT_PARAMETERS, excluded=(key,))
        self._refresh_step_combo()
        start, stop = self._default_range(key)
        self.start_edit.setText(f'{start:.9g}')
        self.stop_edit.setText(f'{stop:.9g}')
        self._configuration_changed()

    def _dependent_changed(self, *_):
        self._refresh_step_combo()
        self._configuration_changed()

    def _refresh_step_combo(self):
        previous = self.step_combo.currentData()
        self._fill_combo(self.step_combo, INDEPENDENT_PARAMETERS,
                         excluded=(self.independent_combo.currentData(), self.dependent_combo.currentData()))
        if previous != self.step_combo.currentData():
            self._step_changed()

    def _step_changed(self, *_):
        key = self.step_combo.currentData()
        if key == 'effi':
            values = (60, 70, 80)
        else:
            start, stop = self._default_range(key)
            values = (start, (start + stop) / 2, stop)
        self.step_values_edit.setText(', '.join(f'{value:.9g}' for value in values))
        self._configuration_changed()

    def _loss_guard(self):
        key = self.dependent_combo.currentData()
        if key.startswith('total_'):
            sides = ('inlet', 'outlet')
        elif key in ('in_loss', 'in_major_loss', 'in_minor_loss'):
            sides = ('inlet',)
        elif key in ('out_loss', 'out_major_loss', 'out_minor_loss'):
            sides = ('outlet',)
        else:
            return ''
        inactive = [side for side in sides if not getattr(
            self.project.parameters, 'designer_status_in' if side == 'inlet' else 'designer_status_out')]
        if inactive:
            return f'Activate the {" and ".join(inactive)} losses calculator before studying this output.'
        return ''

    def _configuration_changed(self, *_):
        self.result = None
        self.export_button.setEnabled(False)
        self.step_combo.setEnabled(self.step_check.isChecked())
        self.step_values_edit.setEnabled(self.step_check.isChecked())
        self.ui.stepValuesLabel.setText(
            f'Held values ({PARAMETERS[self.step_combo.currentData()].unit})')
        active = [side for side, enabled in (
            ('inlet', self.project.parameters.designer_status_in),
            ('outlet', self.project.parameters.designer_status_out)) if enabled]
        status = ', '.join(active) if active else 'none'
        self.ui.lossesLabel.setText(
            f'Active loss calculators: {status}. Active designs recalculate major and minor losses at every point; '
            'manual losses remain fixed.')
        guard = self._loss_guard()
        self.ui.outputHint.setText(guard or 'The selected output is calculated at every point.')
        self.run_button.setEnabled(not guard)
        self._status(guard or 'Ready. Complete the range and run the study.', error=bool(guard))
        self.axes.clear()
        self._format_axes()
        self.axes.text(0.5, 0.5, 'Run a study to plot the system response',
                       transform=self.axes.transAxes, ha='center', va='center', color='#666666')
        self.toolbar.update()
        self.canvas.draw_idle()

    def _format_axes(self):
        self.axes.set_xlabel(_label(PARAMETERS[self.independent_combo.currentData()]))
        self.axes.set_ylabel(_label(PARAMETERS[self.dependent_combo.currentData()]))
        self.axes.set_title('Parametric system response', loc='left', fontsize=11)
        self.axes.grid(True, color='#d9dde2', linewidth=0.7)
        self.axes.set_axisbelow(True)
        self.axes.spines[['top', 'right']].set_visible(False)

    def _status(self, text, *, error=False):
        self.ui.statusLabel.setText(text)
        self.ui.statusLabel.setStyleSheet('color: #a12622;' if error else '')

    def run_study(self):
        self.result = None
        self.export_button.setEnabled(False)
        try:
            guard = self._loss_guard()
            if guard:
                raise CalculationError(guard)
            step_key = self.step_combo.currentData() if self.step_check.isChecked() else None
            parts = self.step_values_edit.text().split(',') if step_key else ()
            if len(parts) > 25:
                raise CalculationError('Use at most 25 held values so the curves remain readable.')
            request = StudyRequest(
                independent_key=self.independent_combo.currentData(),
                start=float(self.start_edit.text()), stop=float(self.stop_edit.text()),
                points=self.points_spin.value(), dependent_key=self.dependent_combo.currentData(),
                step_key=step_key, step_values=tuple(float(part.strip()) for part in parts),
            )
        except (ValueError, OverflowError) as error:
            message = str(error) if isinstance(error, CalculationError) else 'Enter complete numeric range and held values.'
            self._status(message, error=True)
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = calculate_study(self.project, request)
        except (CalculationError, ArithmeticError) as error:
            self.axes.clear()
            self._format_axes()
            self.toolbar.update()
            self.canvas.draw_idle()
            self._status(str(error), error=True)
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self.axes.clear()
        styles = ('-', '--', '-.', ':')
        for index, curve in enumerate(result.curves):
            label = (f'{result.step_parameter.label} = {curve.step_value:g} {result.step_parameter.unit}'
                     if result.step_parameter else 'System response')
            self.axes.plot(curve.x_values, curve.y_values, label=label,
                           linestyle=styles[index % len(styles)], linewidth=1.8)
        self._format_axes()
        if result.step_parameter:
            self.axes.legend(fontsize=8, loc='best')
        self.toolbar.update()
        self.canvas.draw_idle()
        self.result = result
        self.export_button.setEnabled(True)
        total = len(result.curves) * request.points
        self._status(f'{len(result.curves)} curve(s), {total:,} calculated points. Project inputs unchanged.')
        return result

    def export_results(self):
        result = self.result
        if result is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export parametric results', 'parametric-study.csv', 'CSV Files (*.csv)')
        if not filename:
            return
        try:
            with open(ensure_csv_path(filename), 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                heading = [_label(result.independent), _label(result.dependent)]
                if result.step_parameter:
                    heading.insert(0, _label(result.step_parameter))
                writer.writerow(heading)
                for curve in result.curves:
                    for x_value, y_value in zip(curve.x_values, curve.y_values):
                        row = [x_value, y_value]
                        if result.step_parameter:
                            row.insert(0, curve.step_value)
                        writer.writerow(row)
        except (OSError, csv.Error) as error:
            self._status(f'Export failed: {error}', error=True)
        else:
            self._status('Results exported to CSV.')
