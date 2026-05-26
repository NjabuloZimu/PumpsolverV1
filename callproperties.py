import sys
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox

from properties import *



from callLossesCal import LossesCal



class Properties(QDialog):
    submitClicked = QtCore.pyqtSignal(dict, str, dict, list, list) # This is the subwindow signal sent to main 
                                    # data, identifier, self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList, self.total_losses_hf
    
    def __init__(self, diaLogName, designerStatus): # Need to pass in a the name to identify window by changing its name
        super().__init__()
        self.ui = Ui_propertiesDialog()
        self.ui.setupUi(self)

        # Updata the status of designer if there are any changes
        self.designerStatus = designerStatus

        # Execute on action performed
        self.ui.pushButtonOpenDesigner.clicked.connect(lambda: self.opendesigner(self.designerStatus))
        self.ui.pushButtonSubmit.clicked.connect(self.saveandclose)
        self.ui.pushButtonApply.clicked.connect(self.save)
        self.ui.pushButtonCancel.clicked.connect(self.askclose)
 
        # Disable lineEditLosses if designer enabled (only on startup)
        self.lineEditLosses(self.designerStatus)
 
        self.setWindowTitle(diaLogName)

        self.ui.groupBox.setTitle(f'{self.windowTitle().split(" ")[:1][0]} Pipe Properties')  # slice and index the window title to name groupbox
        self.ui.groupBox_2.setTitle(f'{self.windowTitle().split(" ")[:1][0]} Fluid Properties')  # slice and index the window title to name groupbox
        
        # DetectLineEdit modification
        self.ui.lineEditDia.textEdited.connect(self.enablesave)
        self.ui.lineEditHead.textEdited.connect(self.enablesave)
        self.ui.lineEditLosses.textEdited.connect(self.enablesave)
        self.ui.lineEditVol.textEdited.connect(self.enablesave)
        self.ui.lineEditDensity.textEdited.connect(self.enablesave)
        self.ui.lineEditPressure.textEdited.connect(self.enablesave)

        # set the validator to validate inputs
        regex = QtCore.QRegExp("^[0-9]*\.?[0-9]*$")
        validator = QtGui.QRegExpValidator(regex)

        # this validator allows negative values
        regexNeg = QtCore.QRegExp("^-?[0-9]*\.?[0-9]*$")
        validatorNeg = QtGui.QRegExpValidator(regexNeg)

        # Set validators
        self.ui.lineEditDia.setValidator(validator)
        self.ui.lineEditHead.setValidator(validatorNeg)
        self.ui.lineEditLosses.setValidator(validator)
        self.ui.lineEditVol.setValidator(validator)
        self.ui.lineEditDensity.setValidator(validator)
        self.ui.lineEditPressure.setValidator(validatorNeg)


        # Disable save on startup
        self.ui.pushButtonApply.setEnabled(False)
        self.ui.pushButtonSubmit.setEnabled(False)

        # Initialize global variables
        self.stored_segments = {}
        self.list_fittings_by_segment = []
        self.lineRoughnessList = []
        self.viscosity = ''

    def stored_segments_f(self):
        # Feature: on startup modify segment data to set the dictionary to the initial diameter 
        if self.stored_segments == {} and self.ui.lineEditDia.text() != '' and self.designerStatus == True:
            self.stored_segments = {'Line Segment 1, Segment Length (m)': '1',
                                     'Line Segment 1, Segment Diameter (cm)': self.ui.lineEditDia.text()}
            
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
       
      
    def opendesigner(self, designerStatus): 
        print("Open Designer")

        # Enable the save button
        self.enablesave()
        self.stored_segments_f()

        self.sub_window_designer = LossesCal(f'{self.windowTitle().split(" ")[:1][0]} Pipe Fittings Losses Designer', designerStatus)
        print(f'The window title is {self.windowTitle().split(" ")[:1][0]}')

        if self.windowTitle().split(" ")[:1][0] == "Inlet":
            print('inlet')
            # Pass existing data into the subwindow
            print(f"the lineEdit density text is {self.ui.lineEditDensity.text()}")

        elif self.windowTitle().split(" ")[:1][0] == "Outlet":
            print('Outlet')
            # Pass existing data into the subwindow
            # self.sub_window_designer.ui.lineEditDensity.setText(self.ui.lineEditDensity.text())
            # self.sub_window_designer.ui.lineEditFlowrate.setText(self.ui.lineEditVol.text())

        # Pass existing data into the subwindow
        self.sub_window_designer.ui.lineEditDensity.setText(self.ui.lineEditDensity.text())
        self.sub_window_designer.ui.lineEditFlowrate.setText(self.ui.lineEditVol.text())
        self.sub_window_designer.ui.lineEditViscosity.setText(self.viscosity)

        # Call setter
        self.sub_window_designer.previously_stored_data(self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList)
        
        # signals
        self.sub_window_designer.densityChanged.connect(self.update_density)
        self.sub_window_designer.volumetricChanged.connect(self.update_volumetric)
        self.sub_window_designer.designerEnabled.connect(self.data)
        self.sub_window_designer.callLossesData.connect(self.lossesData)
        self.sub_window_designer.diameterChanged.connect(self.update_dia)

        self.sub_window_designer.totalLosses.connect(self.total_losses)
        
        self.sub_window_designer.show()

    def total_losses(self, total_losses_hf):
        self.ui.lineEditLosses.setText(f'{total_losses_hf:#.6g}') 
    
    # Setter method to update information in the subwindow
    def lossesData(self, stored_segments, list_fittings_by_segment, lineRoughnessList, viscosity):
        self.stored_segments = stored_segments
        self.list_fittings_by_segment = list_fittings_by_segment
        self.lineRoughnessList = lineRoughnessList
        self.viscosity = viscosity

    def update_dia(self, diameterValue):
        print('Signal to set diameter of the properties diameter recieved')
        self.ui.lineEditDia.setText(f'{diameterValue}')

    def update_density(self, densityValue):
        self.ui.lineEditDensity.setText(densityValue)

    def update_volumetric(self, volumtricFlowValue):
        self.ui.lineEditVol.setText(volumtricFlowValue)

    def save(self):
        print("Save")
        
        data = self.data(self.designerStatus)
        print(self.windowTitle())

        if self.windowTitle() == 'Inlet Properties':
            self.ui.groupBox_2.setTitle('Inlet Fluid Properties')
            for key in data:
                print(f"boolean check {data[key]==''}")
                if data[key] == '':
                    data[key] = 'Unspecified'
                    print('inlet added Unspecified to missing variable')
    

        if self.windowTitle() == 'Outlet Properties':
            self.ui.groupBox_2.setTitle('Outlet Fluid Properties')
            for key in data:
                if data[key] == '':
                    data[key] = 'Unspecified'
                    print('outlet')

        # signal is emitted Here, and the data is passed back, use window name to identify window and use if statement to fill in texts
        self.submitClicked.emit(data, self.windowTitle(), self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList) 
        
        # Initiate disabling the save button.
        self.disablesave(data) 

    def data(self, designerStatus):
        data = {
                'dia': self.ui.lineEditDia.text(),
                'head': self.ui.lineEditHead.text(), 
                'loss': self.ui.lineEditLosses.text(), 
                'flow': self.ui.lineEditVol.text(), 
                'dens': self.ui.lineEditDensity.text(), 
                'press': self.ui.lineEditPressure.text(),
                'designer': designerStatus
            }
         
        self.lineEditLosses(designerStatus)

        # Update the designer status
        self.designerStatus = designerStatus
        print(f'designer status at save/apply: {designerStatus}')
        return data
    
    def disablesave(self, data): # A function to compare data structure and save the value.
        if self.ui.lineEditDia.text() == data['dia']:
                self.ui.pushButtonApply.setEnabled(False)
                self.ui.pushButtonSubmit.setEnabled(False)

    def enablesave(self):
        self.ui.pushButtonApply.setEnabled(True) 
        self.ui.pushButtonSubmit.setEnabled(True)

    def lineEditLosses(self, status):
        # print(status)
        self.ui.lineEditLosses.setDisabled(status)
        self.ui.lineEditDensity.setDisabled(status)
        self.ui.lineEditVol.setDisabled(status)
        self.ui.lineEditDia.setDisabled(status)

        # Change the units to friction losses (from friction head loss)
        if status:
            self.ui.labelLossesUnits.setText("<html><head/><body><p>m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span></p></body></html>")
        else:
            self.ui.labelLossesUnits.setText("m")
            self.ui.lineEditLosses.setText("0")

        # save new designer status in global variable
        self.designerStatus = status
     
if __name__=="__main__":
    app = QApplication(sys.argv)
    w = Properties('passedInName')  # Passed in window name must be dynamic, to be passed in from main.py
    w.show()
    sys.exit(app.exec_())