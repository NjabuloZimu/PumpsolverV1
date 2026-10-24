"""Main application controller. ProjectState owns data; widgets render it."""

import csv
from dataclasses import replace
from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog, QMessageBox
from .generated.ui_main_window import Ui_MainWindow
from .centered_canvas import center_window_contents
from pumpsolver.models import ProjectState, PumpInputs, PipeDesign
from pumpsolver.persistence.csv_io import ensure_csv_path, read_project, write_project, validate_parameters
from pumpsolver.version import __version__


class MainWindow(QMainWindow):
    windows = []
    PARAMETER_WIDGETS = {
        'in_dia': 'labelDiaIn', 'in_head': 'labelHeadIn',
        'in_loss': 'labelLossesIn', 'in_flow': 'labelVolIn',
        'in_dens': 'labelDensityIn', 'in_press': 'labelPressIn',
        'out_dia': 'labelDiaOut', 'out_head': 'labelHeadOut',
        'out_loss': 'labelLossesOut', 'out_flow': 'labelVolOut',
        'out_dens': 'labelDensityOut', 'out_press': 'labelPressOut',
        'effi': 'labelEff', 'power': 'labelAvHead',
        'safety': 'labelSafeF', 'gravity': 'labelGravConst',
    }

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.setWindowTitle(f'Process Pump Solver Tool {__version__}')
        QApplication.instance().setApplicationVersion(__version__)
        self.ui.radioButtonInDesigner.setAutoExclusive(False)
        self.ui.radioButtonOutDesigner.setAutoExclusive(False)
        initial = {key: getattr(self.ui, widget).text()
                   for key, widget in self.PARAMETER_WIDGETS.items()}
        initial.update(designer_status_in=self.ui.radioButtonInDesigner.isChecked(),
                       designer_status_out=self.ui.radioButtonOutDesigner.isChecked())
        self.state = ProjectState(parameters=PumpInputs.from_legacy(initial))
        self._render()
        self.ui.pushButtonSolve.clicked.connect(self.dof)
        self.ui.inletPushButton.clicked.connect(lambda: self.show_sub_window_properties('Inlet', self.state.parameters.designer_status_in))
        self.ui.outletPushButton.clicked.connect(lambda: self.show_sub_window_properties('Outlet', self.state.parameters.designer_status_out))
        self.ui.pumpPushButton.clicked.connect(self.show_sub_window_pump)
        self.ui.radioButtonInDesigner.clicked.connect(lambda: self.set_designer_text('In'))
        self.ui.radioButtonOutDesigner.clicked.connect(lambda: self.set_designer_text('Out'))
        self.ui.actionSave.triggered.connect(self.exportCSV)
        self.ui.actionOpen.triggered.connect(self.importCSV)
        self.ui.actionExit.triggered.connect(QApplication.closeAllWindows)
        self.ui.actionAuthor.triggered.connect(self.open_window_about)
        self.ui.actionParametric_Study.triggered.connect(self.open_parametric_study)
        self.windows.append(self)

    def _render(self):
        values = self.state.parameters.to_legacy()
        for key, widget in self.PARAMETER_WIDGETS.items():
            getattr(self.ui, widget).setText(values[key])
        for suffix, label in (('in', 'In'), ('out', 'Out')):
            enabled = values[f'designer_status_{suffix}']
            getattr(self.ui, f'radioButton{label}Designer').setChecked(enabled)
            status = getattr(self.ui, f'labelDesignerState{label}')
            status.setText('Active' if enabled else 'Inactive')
            status.setStyleSheet('color: green;' if enabled else 'color: red;')
            getattr(self.ui, f'labelLosses{label}_Units').setText('m')

    def set_designer_text(self, identifier):
        suffix = 'in' if identifier == 'In' else 'out'
        enabled = getattr(self.ui, f'radioButton{identifier}Designer').isChecked()
        self.state = replace(self.state, parameters=replace(self.state.parameters, **{f'designer_status_{suffix}': enabled}))
        self._render()

    def datafunction(self, saved_data=None):
        if saved_data is not None:
            self.dataRestore(saved_data)
        return self.state.parameters.to_legacy()

    def dataRestore(self, data):
        candidate = PumpInputs.from_legacy(validate_parameters(data))
        self.state = replace(self.state, parameters=candidate)
        self._render()

    def project_state(self):
        return self.state.to_legacy()

    def restore_project(self, state):
        candidate = ProjectState.from_legacy(state)
        self.state = candidate
        self._render()

    def designerStatuses(self, identifier):
        return getattr(self.state.parameters, 'designer_status_in' if identifier == 'Inlet' else 'designer_status_out')

    def open_window_about(self):
        from .about_dialog import About
        self.sub_window = About()
        self.sub_window.open()

    def open_parametric_study(self):
        from .parametric_dialog import ParametricStudyDialog
        self.sub_window = ParametricStudyDialog(self.state, self)
        self.sub_window.open()

    def show_sub_window_properties(self, identifier, designerStatus):
        from .properties_dialog import Properties
        side = 'inlet' if identifier == 'Inlet' else 'outlet'
        suffix = 'in' if side == 'inlet' else 'out'
        values = self.state.parameters.to_legacy()
        opposite = 'out' if side == 'inlet' else 'in'
        window = Properties(f'{identifier} Properties', designerStatus, side=side,
                            shared_values_locked=values[f'designer_status_{opposite}'],
                            commit_handler=self._accept_properties)
        self.sub_window = window
        for field, editor in (('dia', 'lineEditDia'), ('head', 'lineEditHead'),
                              ('loss', 'lineEditLosses'), ('flow', 'lineEditVol'),
                              ('dens', 'lineEditDensity'), ('press', 'lineEditPressure')):
            value = values[f'{suffix}_{field}']
            getattr(window.ui, editor).setText('' if value == 'Unspecified' else value)
        window.ui.labelSuc.setText(f'{identifier} Suction Height')
        window.set_design(getattr(self.state, side))
        window.exec_()

    def _accept_properties(self, update):
        values = self.state.parameters.to_legacy()
        suffix = 'in' if update.side == 'inlet' else 'out'
        opposite = 'out' if suffix == 'in' else 'in'
        for field in ('dia', 'head', 'loss', 'press'):
            values[f'{suffix}_{field}'] = update.values[field]
        if not values[f'designer_status_{opposite}'] or update.shared_values_from_designer:
            for field in ('flow', 'dens'):
                values[f'in_{field}'] = values[f'out_{field}'] = update.values[field]
        values[f'designer_status_{suffix}'] = update.enabled
        try:
            candidate = replace(self.state, parameters=PumpInputs.from_legacy(values),
                                **{update.side: update.design})
            shared_fields = ('in_flow_m3_s', 'out_flow_m3_s',
                             'in_density_kg_m3', 'out_density_kg_m3')
            if any(getattr(candidate.parameters, field) != getattr(self.state.parameters, field)
                   for field in shared_fields):
                from pumpsolver.calculations.project import recalculate_active_losses
                candidate = recalculate_active_losses(candidate)
        except (ValueError, ArithmeticError) as error:
            QMessageBox.critical(self, 'Unable to Update Pipe Properties',
                                 f'The project was not changed.\n{error}')
            return False
        self.state = candidate
        self._render()
        return True

    def _accept_results(self, parameters):
        self.state = replace(self.state, parameters=parameters)
        self._render()

    def show_sub_window_pump(self):
        from .motor_dialog import MotorProp
        self.sub_window = MotorProp()
        values = self.state.parameters.to_legacy()
        for key, editor in (('effi', 'lineEditEff'), ('power', 'lineEditTPH'), ('safety', 'lineEditSF'), ('gravity', 'lineEditGravConst')):
            getattr(self.sub_window.ui, editor).setText('' if values[key] == 'Unspecified' else values[key])
        self.sub_window.submitClicked.connect(self.on_sub_window_pump_confirm)
        self.sub_window.show()

    def on_sub_window_pump_confirm(self, data):
        values = self.state.parameters.to_legacy()
        for field, key in (('eff', 'effi'), ('power', 'power'), ('safeF', 'safety'), ('gravity', 'gravity')):
            values[key] = data[field]
        self.dataRestore(values)

    def open_window_solve(self, data):
        from .results_dialog import SolvePage
        self.sub_window = SolvePage(data)
        self.sub_window.resultsCommitted.connect(self._accept_results)
        self.sub_window.show()

    def dof(self):
        values = self.state.parameters.to_legacy()
        missing = sum(value == 'Unspecified' for key, value in values.items() if key not in ('out_dens', 'out_flow'))
        if missing != 1:
            QMessageBox.information(self, 'Degrees of Freedom (DOF) Error',
                                    f'There are {missing} unspecified variables. Specify all but one variable to solve for.')
            return
        self.open_window_solve(values)

    def exportCSV(self):
        name, _ = QFileDialog.getSaveFileName(self, 'Save Project CSV', 'project.csv', 'CSV Files (*.csv)')
        if name:
            try:
                write_project(ensure_csv_path(name), self.state.to_legacy())
            except (OSError, ValueError, csv.Error) as error:
                QMessageBox.critical(self, 'CSV Export Failed', str(error))

    def importCSV(self):
        name, _ = QFileDialog.getOpenFileName(self, 'Open Project CSV', '', 'CSV Files (*.csv)')
        if name:
            try:
                self.restore_project(read_project(name))
            except (OSError, ValueError, csv.Error) as error:
                QMessageBox.critical(self, 'CSV Import Failed', str(error))


# Existing integrations may still import MyForm; there is one controller class.
MyForm = MainWindow


def _legacy_design_property(side, field):
    return property(lambda self: getattr(self.state, side).to_legacy()[field])


for _side, _suffix in (('inlet', 'in'), ('outlet', 'out')):
    for _attribute, _field in (('stored_segments', 'segments'), ('list_fittings_by_segment', 'fittings'),
                               ('lineRoughnessList', 'roughness'), ('viscosity', 'viscosity'),
                               ('transition_equation', 'transition_equation')):
        setattr(MainWindow, f'{_attribute}_{_suffix}', _legacy_design_property(_side, _field))
