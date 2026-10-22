"""Motor settings dialog; validation happens before committing the draft."""

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QDialog, QMessageBox

from .centered_canvas import center_window_contents
from .generated.ui_motor_dialog import Ui_MotorProp


class MotorProp(QDialog):
    submitClicked = QtCore.pyqtSignal(dict)
    EDITORS = {
        'eff': 'lineEditEff', 'power': 'lineEditTPH',
        'safeF': 'lineEditSF', 'gravity': 'lineEditGravConst',
    }

    def __init__(self):
        super().__init__()
        self.ui = Ui_MotorProp()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.ui.pushButtonOk.clicked.connect(self.saveandclose)
        self.ui.pushButtonApply.clicked.connect(self.save)
        self.ui.pushButtonClose.clicked.connect(self.askclose)
        validator = QtGui.QRegExpValidator(QtCore.QRegExp(r'^[0-9]*\.?[0-9]*$'), self)
        for name in self.EDITORS.values():
            editor = getattr(self.ui, name)
            editor.setValidator(validator)
            editor.textEdited.connect(self.enablesave)
        self.disablesave()

    def data(self):
        return {key: getattr(self.ui, name).text() for key, name in self.EDITORS.items()}

    def save(self):
        data = {key: value or 'Unspecified' for key, value in self.data().items()}
        try:
            for value in data.values():
                if value != 'Unspecified' and not math.isfinite(float(value)):
                    raise ValueError('Numbers must be finite.')
        except ValueError:
            QMessageBox.critical(self, 'Invalid Input', 'Enter complete numeric values or leave fields empty.')
            return False
        self.submitClicked.emit(data)
        self.disablesave()
        return True

    def saveandclose(self):
        if self.save():
            self.close()

    def askclose(self):
        if not self.ui.pushButtonApply.isEnabled():
            self.close()
            return
        choice = QMessageBox.warning(
            self, 'Unsaved Changes', 'Values have been modified. Save your changes?',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
        )
        if choice == QMessageBox.Save:
            self.saveandclose()
        elif choice == QMessageBox.Discard:
            self.close()

    def disableeditloss(self, disabled):
        self.ui.lineEditEff.setDisabled(disabled)

    def disablesave(self):
        self.ui.pushButtonApply.setEnabled(False)
        self.ui.pushButtonOk.setEnabled(False)

    def enablesave(self):
        self.ui.pushButtonApply.setEnabled(True)
        self.ui.pushButtonOk.setEnabled(True)
