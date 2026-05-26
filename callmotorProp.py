import sys
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox
from motorProp import *





class MotorProp(QDialog):
    submitClicked = QtCore.pyqtSignal(dict) # This is the subwindow signal sent to main

    def __init__(self): # Need to pass in a the name to identify window by changing its name
        super().__init__()
        self.ui = Ui_MotorProp()
        self.ui.setupUi(self)

        self.ui.pushButtonOk.clicked.connect(self.saveandclose)
        self.ui.pushButtonApply.clicked.connect(self.save)
        self.ui.pushButtonClose.clicked.connect(self.askclose)        

        #disable save on startup
        self.ui.pushButtonApply.setEnabled(False)
        self.ui.pushButtonOk.setEnabled(False)

        # DetectLineEdit modification
        self.ui.lineEditEff.textEdited.connect(self.enablesave)
        self.ui.lineEditTPH.textEdited.connect(self.enablesave)
        self.ui.lineEditSF.textEdited.connect(self.enablesave)
        self.ui.lineEditGravConst.textEdited.connect(self.enablesave)


        # set the validator to validate inputs
        regex = QtCore.QRegExp("^[0-9]*\.?[0-9]*$")
        validator = QtGui.QRegExpValidator(regex)
        

        # this validator allows negative values
        regexNeg = QtCore.QRegExp("^-?[0-9]*\.?[0-9]*$")
        validatorNeg = QtGui.QRegExpValidator(regexNeg)


        # Set validators
        self.ui.lineEditEff.setValidator(validator)
        self.ui.lineEditTPH.setValidator(validator)
        self.ui.lineEditSF.setValidator(validator)
        self.ui.lineEditGravConst.setValidator(validator)




    def saveandclose(self): 
        self.save()
        self.close()

    def askclose(self):

        if self.ui.pushButtonApply.isEnabled():
            ret = QMessageBox.warning(self,"Unsaved Changes", "Values have been modified.\n" "Do you want to save your changes?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)

            if ret == QMessageBox.Save:
                self.saveandclose()
            elif ret == QMessageBox.Discard:
                self.close()
            elif ret == QMessageBox.Cancel:
                self.show
            else:
                print("should never be reached, user will be hacking.")

        else:
            self.close()

    def disableeditloss(self, bool):
        self.ui.lineEditEff.setDisabled(bool)


    def save(self):
        data = self.data()
        for key in data:
                print(f"boolean check {data[key]==''}")
                if data[key] == '':
                    data[key] = 'Unspecified'
                    print('MotorWindow added Unspecified to missing variable')

        print(data)
        self.submitClicked.emit(data)  # signal is emitted Here, and the data is passed back, use window name to identify window and use if statement to submit

        self.disablesave() # Initiate disabling the save button.

    def data(self):
        data = {
                'eff': self.ui.lineEditEff.text(),
                'power': self.ui.lineEditTPH.text(), 
                'safeF': self.ui.lineEditSF.text(), 
                'gravity': self.ui.lineEditGravConst.text(), 
            }
        
        return data
    
    def disablesave(self): # A function to compare data structure and save the value.
        self.ui.pushButtonApply.setEnabled(False)
        self.ui.pushButtonOk.setEnabled(False)
                

    def enablesave(self):
        self.ui.pushButtonApply.setEnabled(True) 
        self.ui.pushButtonOk.setEnabled(True)

    


if __name__=="__main__":
    app = QApplication(sys.argv)
    w = MotorProp()
    w.show()
    sys.exit(app.exec_())

