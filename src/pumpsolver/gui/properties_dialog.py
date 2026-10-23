"""Pipe properties edit a draft and commit one structured update."""

import math
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QDialog, QMessageBox
from .generated.ui_properties_dialog import Ui_propertiesDialog
from .centered_canvas import center_window_contents
from pumpsolver.models import PipeDesign, PipePropertiesUpdate


class Properties(QDialog):
    dataCommitted = QtCore.pyqtSignal(object)
    EDITORS = {'dia': 'lineEditDia', 'head': 'lineEditHead', 'loss': 'lineEditLosses',
               'flow': 'lineEditVol', 'dens': 'lineEditDensity', 'press': 'lineEditPressure'}

    def __init__(self, diaLogName, designerStatus, *, side='inlet'):
        super().__init__()
        if side not in ('inlet', 'outlet'):
            raise ValueError('Pipe side must be inlet or outlet.')
        self.side = side
        self.design = PipeDesign.for_side(side)
        self.designerStatus = bool(designerStatus)
        self.ui = Ui_propertiesDialog()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.setWindowTitle(diaLogName)
        self.ui.groupBox.setTitle(f'{side.title()} Pipe Properties')
        self.ui.groupBox_2.setTitle(f'{side.title()} Fluid Properties')
        self.ui.pushButtonOpenDesigner.clicked.connect(lambda: self.opendesigner(self.designerStatus))
        self.ui.pushButtonSubmit.clicked.connect(self.saveandclose)
        self.ui.pushButtonApply.clicked.connect(self.save)
        self.ui.pushButtonCancel.clicked.connect(self.askclose)
        positive = QtGui.QRegExpValidator(QtCore.QRegExp(r'^[0-9]*\.?[0-9]*$'), self)
        signed = QtGui.QRegExpValidator(QtCore.QRegExp(r'^-?[0-9]*\.?[0-9]*$'), self)
        for key, name in self.EDITORS.items():
            editor = getattr(self.ui, name)
            editor.setValidator(signed if key in ('head', 'press') else positive)
            editor.textEdited.connect(self.enablesave)
        self.lineEditLosses(self.designerStatus)
        self.disablesave()

    def set_design(self, design):
        self.design = design

    def lossesData(self, stored_segments, list_fittings_by_segment, lineRoughnessList, viscosity):
        self.design = PipeDesign.from_legacy({**self.design.to_legacy(), 'segments': stored_segments,
            'fittings': list_fittings_by_segment, 'roughness': lineRoughnessList,
            'viscosity': viscosity}, side=self.side)

    def _accept_design(self, update):
        self.design = update.design
        self.ui.lineEditDensity.setText(update.density)
        self.ui.lineEditVol.setText(update.flow)
        if update.diameter is not None:
            self.ui.lineEditDia.setText(update.diameter)
        if update.total_losses is not None:
            self.ui.lineEditLosses.setText(f'{update.total_losses:#.6g}')
        self.lineEditLosses(update.enabled)
        self.enablesave()

    def opendesigner(self, designerStatus):
        from .pipe_designer import LossesCal
        self.enablesave()
        data = self.design.to_legacy()
        if not data['segments'] and self.ui.lineEditDia.text() and designerStatus:
            data['segments'] = {'Line Segment 1, Segment Length (m)': '1',
                                'Line Segment 1, Segment Diameter (cm)': self.ui.lineEditDia.text()}
        window = LossesCal(f'{self.side.title()} Pipe Fittings Losses Designer', designerStatus, side=self.side)
        self.sub_window_designer = window
        window.ui.lineEditDensity.setText(self.ui.lineEditDensity.text())
        window.ui.lineEditFlowrate.setText(self.ui.lineEditVol.text())
        window.ui.lineEditViscosity.setText(data['viscosity'])
        window.ui.comboBoxTransitionEquation.setCurrentText(data['transition_equation'])
        window.set_boundary_settings(self.design)
        window.previously_stored_data(data['segments'], data['fittings'], data['roughness'])
        window.designCommitted.connect(self._accept_design)
        window.show()

    def lineEditLosses(self, status):
        self.designerStatus = bool(status)
        for name in ('lineEditLosses', 'lineEditDensity', 'lineEditVol', 'lineEditDia'):
            getattr(self.ui, name).setDisabled(self.designerStatus)
        self.ui.labelLossesUnits.setText('m')

    def data(self, designerStatus=None):
        if designerStatus is not None:
            self.lineEditLosses(designerStatus)
        return {**{key: getattr(self.ui, name).text() or 'Unspecified' for key, name in self.EDITORS.items()},
                'designer': self.designerStatus}

    def save(self):
        data = self.data()
        try:
            for key in self.EDITORS:
                if data[key] != 'Unspecified' and not math.isfinite(float(data[key])):
                    raise ValueError('Numbers must be finite.')
        except ValueError:
            QMessageBox.critical(self, 'Invalid Input', 'Enter complete numeric values or leave fields empty.')
            return False
        self.dataCommitted.emit(PipePropertiesUpdate(self.side,
            {key: data[key] for key in self.EDITORS}, self.design, self.designerStatus))
        self.disablesave()
        return True

    def saveandclose(self):
        if self.save():
            self.close()

    def askclose(self):
        if not self.ui.pushButtonApply.isEnabled():
            self.close()
            return
        choice = QMessageBox.warning(self, 'Unsaved Changes', 'Values have been modified. Save your changes?',
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if choice == QMessageBox.Save:
            self.saveandclose()
        elif choice == QMessageBox.Discard:
            self.close()

    def enablesave(self):
        self.ui.pushButtonApply.setEnabled(True)
        self.ui.pushButtonSubmit.setEnabled(True)

    def disablesave(self, data=None):
        self.ui.pushButtonApply.setEnabled(False)
        self.ui.pushButtonSubmit.setEnabled(False)

    @property
    def stored_segments(self):
        return self.design.to_legacy()['segments']

    @property
    def list_fittings_by_segment(self):
        return self.design.to_legacy()['fittings']

    @property
    def lineRoughnessList(self):
        return self.design.to_legacy()['roughness']

    @property
    def viscosity(self):
        return self.design.to_legacy()['viscosity']

    @property
    def transition_equation(self):
        return self.design.transition_equation
