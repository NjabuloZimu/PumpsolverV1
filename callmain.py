import sys
import csv
from PyQt5.QtWidgets import QMainWindow, QApplication, QAction, QFileDialog, QMessageBox
from main import *

# Added subwindows
from callproperties import Properties
from callmotorProp import MotorProp
from callsolvePage import SolvePage
from callabout import About

class MyForm(QMainWindow):
    # class variable to store references to open windows
    windows = []
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Detect user interaction with button graphics.
        self.ui.pushButtonSolve.clicked.connect(self.dof)
        self.ui.inletPushButton.clicked.connect(lambda: self.show_sub_window_properties("Inlet", self.designerStatuses("Inlet")))
        self.ui.pumpPushButton.clicked.connect(self.show_sub_window_pump)
        self.ui.outletPushButton.clicked.connect(lambda: self.show_sub_window_properties("Outlet", self.designerStatuses("Outlet")))

        self.show()

        # Use Radiobutton to update designer status text
        self.ui.radioButtonInDesigner.clicked.connect(lambda: self.set_designer_text('In'))
        self.ui.radioButtonOutDesigner.clicked.connect(lambda: self.set_designer_text('Out'))

        # Change Colour of text on start-up
        self.set_designer_text('In')
        self.set_designer_text('Out')

        # Initailize required global variables for inlet conditions
        self.stored_segments_out = {}
        self.list_fittings_by_segment_out = []
        self.lineRoughnessList_out = []
        # self.total_losses_hf_out = 0.0

        # Initailize required global variables for outlet conditions
        self.stored_segments_in = {}
        self.list_fittings_by_segment_in = []
        self.lineRoughnessList_in = []
        # self.total_losses_hf_in = 0.0
        
        self.viscosity = ''

        self.ui.actionSave.triggered.connect(self.exportCSV)
        self.ui.actionOpen.triggered.connect(self.importCSV)
        self.ui.actionExit.triggered.connect(self.closeAllWindows)
        self.ui.actionAuthor.triggered.connect(self.open_window_about)

        MyForm.windows.append(self)

    def open_window_about(self):
        self.sub_window = About()
        self.sub_window.open()


    def closeAllWindows(self):
        for window in MyForm.windows:
            window.close()

    def set_designer_text(self, identifier):
        if identifier == "In":
            if self.ui.radioButtonInDesigner.isChecked() == True:
                self.ui.labelDesignerStateIn.setText('Active')
                self.ui.labelDesignerStateIn.setStyleSheet('color: green;')
                self.ui.labelLossesIn_Units.setText("m")
            elif self.ui.radioButtonInDesigner.isChecked() == False:
                self.ui.labelDesignerStateIn.setText('Inactive')
                self.ui.labelDesignerStateIn.setStyleSheet('color: red;')
                self.ui.labelLossesIn_Units.setText("m")
        elif identifier == "Out":
            if self.ui.radioButtonOutDesigner.isChecked() == True:
                self.ui.labelDesignerStateOut.setText('Active')
                self.ui.labelDesignerStateOut.setStyleSheet('color: green;')
                self.ui.labelLossesOut_Units.setText("m")
            elif self.ui.radioButtonOutDesigner.isChecked() == False:
                self.ui.labelDesignerStateOut.setText('Inactive')
                self.ui.labelDesignerStateOut.setStyleSheet('color: red;')
                self.ui.labelLossesOut_Units.setText("m")
        else:
            print('None was true, radiobutton possibilities')

    def show_sub_window_properties(self, identifier, designerStatus):  # <-- Here, we create *and connect* the sub window's signal to the main window's slot
        print(f' designer status: {designerStatus}')
        self.sub_window = Properties(f'{identifier} Properties', designerStatus)
        
        if identifier == "Inlet":
            print('inlet')
            # Pass existing data into the subwindow, first setText of widgets
            self.sub_window.ui.lineEditDia.setText(self.ui.labelDiaIn.text()) if self.ui.labelDiaIn.text() != 'Unspecified' else self.sub_window.ui.lineEditDia.setText('')
            self.sub_window.ui.lineEditHead.setText(self.ui.labelHeadIn.text()) if self.ui.labelHeadIn.text() != 'Unspecified' else self.sub_window.ui.lineEditHead.setText('')
            self.sub_window.ui.lineEditLosses.setText(self.ui.labelLossesIn.text()) if self.ui.labelLossesIn.text() != 'Unspecified' else self.sub_window.ui.lineEditLosses.setText('')
            self.sub_window.ui.lineEditVol.setText(self.ui.labelVolIn.text()) if self.ui.labelVolIn.text() != 'Unspecified' else self.sub_window.ui.lineEditVol.setText('')
            self.sub_window.ui.lineEditDensity.setText(self.ui.labelDensityIn.text()) if self.ui.labelDensityIn.text() != 'Unspecified' else self.sub_window.ui.lineEditDensity.setText('')
            self.sub_window.ui.lineEditPressure.setText(self.ui.labelPressIn.text()) if self.ui.labelPressIn.text() != 'Unspecified' else self.sub_window.ui.lineEditPressure.setText('')
            self.sub_window.ui.labelSuc.setText(f"{identifier} Suction Height")

            # Update global variable in submwindow
            self.sub_window.lossesData(self.stored_segments_in, self.list_fittings_by_segment_in, self.lineRoughnessList_in, self.viscosity)

            # Based on the designer status change the display units, from head loss to 'total friction loss' and vice versa
            self.change_loss_units(designerStatus)

            # for the designer
            self.ui.radioButtonInDesigner.setChecked(designerStatus)
        
        if identifier == 'Outlet':
            print('outlet')
            # Pass existing data into the subwindow, first setText of widgets
            self.sub_window.ui.lineEditDia.setText(self.ui.labelDiaOut.text()) if self.ui.labelDiaOut.text() != 'Unspecified' else self.sub_window.ui.lineEditDia.setText('')
            self.sub_window.ui.lineEditHead.setText(self.ui.labelHeadOut.text()) if self.ui.labelHeadOut.text() != 'Unspecified' else self.sub_window.ui.lineEditHead.setText('')
            self.sub_window.ui.lineEditLosses.setText(self.ui.labelLossesOut.text()) if self.ui.labelLossesOut.text() != 'Unspecified' else self.sub_window.ui.lineEditLosses.setText('')
            self.sub_window.ui.lineEditVol.setText(self.ui.labelVolOut.text()) if self.ui.labelVolOut.text() != 'Unspecified' else self.sub_window.ui.lineEditVol.setText('')
            self.sub_window.ui.lineEditDensity.setText(self.ui.labelDensityOut.text()) if self.ui.labelDensityOut.text() != 'Unspecified' else self.sub_window.ui.lineEditDensity.setText('')
            self.sub_window.ui.lineEditPressure.setText(self.ui.labelPressOut.text()) if self.ui.labelPressOut.text() != 'Unspecified' else self.sub_window.ui.lineEditPressure.setText('') 
            self.sub_window.ui.labelSuc.setText(f"{identifier} Discharge Height")

            # Update global variable in submwindow
            self.sub_window.lossesData(self.stored_segments_out, self.list_fittings_by_segment_out, self.lineRoughnessList_out, self.viscosity)
            
            # Based on the designer status change the display units, from head loss to 'total friction loss' and vice versa
            self.change_loss_units(designerStatus)

            # for the designer
            self.ui.radioButtonOutDesigner.setChecked(designerStatus)

        self.sub_window.submitClicked.connect(self.on_sub_window_confirm)
        self.sub_window.exec_()

    def change_loss_units(self, designerStatus):
        if designerStatus:
            self.sub_window.ui.labelLossesUnits.setText("<html><head/><body><p>m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span></p></body></html>")
        else:
            self.sub_window.ui.labelLossesUnits.setText("m")   

    
    def on_sub_window_confirm(self, data, identifier, stored_segments, list_fittings_by_segment, lineRoughnessList):  # <-- This is the main window's slot
        if identifier == 'Inlet Properties':
            self.ui.labelDiaIn.setText(data['dia'])
            self.ui.labelHeadIn.setText(data['head'])
            self.ui.labelLossesIn.setText(data['loss'])
            self.ui.labelVolIn.setText(data['flow'])
            self.ui.labelDensityIn.setText(data['dens'])
            self.ui.labelPressIn.setText(data['press'])

            # Flow is continuous
            self.ui.labelVolOut.setText(data['flow'])

            # density remains the same
            self.ui.labelDensityOut.setText(data['dens'])

            # Always save designer information regardless of status
            if stored_segments != None:
                self.stored_segments_in = stored_segments
            elif list_fittings_by_segment != None:
                self.list_fittings_by_segment_in = list_fittings_by_segment
            elif lineRoughnessList != None:
                self.lineRoughnessList_in = lineRoughnessList
            # self.total_losses_hf_in = total_losses_hf

            # Save the designer state
            if data['designer'] == True:
                self.ui.labelDesignerStateIn.setText('Active')
                self.ui.labelDesignerStateIn.setStyleSheet('color: green;')
                self.ui.labelLossesIn_Units.setText("m")
                self.ui.radioButtonInDesigner.setChecked(True)
            else:
                self.ui.labelDesignerStateIn.setText('Inactive')
                self.ui.labelDesignerStateIn.setStyleSheet('color: red;')
                self.ui.labelLossesIn_Units.setText("m")
                self.ui.radioButtonInDesigner.setChecked(False)

        if identifier == 'Outlet Properties':
            self.ui.labelDiaOut.setText(data['dia'])
            self.ui.labelHeadOut.setText(data['head'])
            self.ui.labelLossesOut.setText(data['loss'])
            self.ui.labelVolOut.setText(data['flow'])
            self.ui.labelDensityOut.setText(data['dens'])
            self.ui.labelPressOut.setText(data['press'])

            # Flow is continuous
            self.ui.labelVolIn.setText(data['flow'])

            # density remains the same
            self.ui.labelDensityIn.setText(data['dens'])

            # Always save designer information regardless of status
            self.stored_segments_out = stored_segments
            self.list_fittings_by_segment_out = list_fittings_by_segment
            self.lineRoughnessList_out = lineRoughnessList
            # self.total_losses_hf_in = total_losses_hf
            # Save the designer state
            if data['designer'] == True:
                self.ui.labelDesignerStateOut.setText('Active')
                self.ui.labelDesignerStateOut.setStyleSheet('color: green;')
                self.ui.labelLossesOut_Units.setText("m")
                self.ui.radioButtonOutDesigner.setChecked(True)

            else:
                self.ui.labelDesignerStateOut.setText('Inactive')
                self.ui.labelDesignerStateOut.setStyleSheet('color: red;')
                self.ui.labelLossesOut_Units.setText("m")
                self.ui.radioButtonOutDesigner.setChecked(False)
        print(f'printing identifier: {identifier}')

        if identifier == 'Results':
            # had to to convert values to strings.
            data = self.convert_integers_to_strings(data)

            self.ui.labelDiaIn.setText(data['in_dia'])
            self.ui.labelHeadIn.setText(data['in_head'])
            self.ui.labelLossesIn.setText(data['in_loss'])
            self.ui.labelVolIn.setText(data['in_flow'])
            self.ui.labelDensityIn.setText(data['in_dens'])
            self.ui.labelPressIn.setText(data['in_press'])

            self.ui.labelDiaOut.setText(data['out_dia'])
            self.ui.labelHeadOut.setText(data['out_head'])
            self.ui.labelLossesOut.setText(data['out_loss'])
            self.ui.labelVolOut.setText(data['out_flow'])
            self.ui.labelDensityOut.setText(data['out_dens'])
            self.ui.labelPressOut.setText(data['out_press'])

            self.ui.labelEff.setText(data['effi'])
            self.ui.labelAvHead.setText(data['power'])
            self.ui.labelSafeF.setText(data['safety'])
            self.ui.labelGravConst.setText(data['gravity'])

    def convert_integers_to_strings(self, input_dict):
        # Create a new dictionary to store the converted values
        output_dict = {}

        # Iterate through key-value pairs in the input dictionary
        for key, value in input_dict.items():
            value = str(value)

            # Add the key-value pair to the output dictionary
            output_dict[key] = value

        return output_dict

    def datafunction(self, saved_data={}):
        data = {
                'in_dia': self.ui.labelDiaIn.text(),
                'in_head': self.ui.labelHeadIn.text(), 
                'in_loss': self.ui.labelLossesIn.text(), 
                'in_flow': self.ui.labelVolIn.text(), 
                'in_dens': self.ui.labelDensityIn.text(), 
                'in_press':self.ui.labelPressIn.text(),

                'out_dia': self.ui.labelDiaOut.text(),
                'out_head': self.ui.labelHeadOut.text(), 
                'out_loss': self.ui.labelLossesOut.text(),
                'out_flow': self.ui.labelVolOut.text(),
                'out_dens': self.ui.labelDensityIn.text(),
                'out_press':self.ui.labelPressOut.text(),

                'effi': self.ui.labelEff.text(),
                'power': self.ui.labelAvHead.text(), 
                'safety': self.ui.labelSafeF.text(), 
                # Density removed to avoid double count
                # Flow removed to avoid double count
                'gravity':self.ui.labelGravConst.text(),
                # Pass in designer status
                'designer_status_in': self.ui.radioButtonInDesigner.isChecked(),
                'designer_status_out': self.ui.radioButtonOutDesigner.isChecked()
            }
        print(f'this is what is sent callsovlve {data}')
        if saved_data != {}:
            self.dataRestore(saved_data)
        
        return data
    
    def dataRestore(self, data):
        flag = False
        for key, value in data.items():
            if key == 'designer_status_in'or key == 'designer_status_out':
                try:
                    bool(value)
                except ValueError:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setWindowTitle("Error: Import Failed")
                    msg.setText(f"Corrupt/Invalid data at '{key}':'{value}'.")
                    msg.exec_()
                    return
            elif value == 'Unspecified':
                continue
            else:
                try:
                    float(value)
                except ValueError:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setWindowTitle("Error: Import Failed")
                    msg.setText(f"Corrupt/Invalid data at '{key}':'{value}'.")
                    msg.exec_()
                    return
                else:
                    flag = True
                
        if flag:  
            self.ui.labelDiaIn.setText(data['in_dia'])
            self.ui.labelHeadIn.setText(data['in_head'])
            self.ui.labelLossesIn.setText(data['in_loss'])
            self.ui.labelVolIn.setText(data['in_flow'])
            self.ui.labelDensityIn.setText(data['in_dens'])
            self.ui.labelPressIn.setText(data['in_press'])

            self.ui.labelDiaOut.setText(data['out_dia'])
            self.ui.labelHeadOut.setText(data['out_head'])
            self.ui.labelLossesOut.setText(data['out_loss'])
            self.ui.labelVolOut.setText(data['out_flow'])
            self.ui.labelDensityIn.setText(data['out_dens'])
            self.ui.labelPressOut.setText(data['out_press'])

            self.ui.labelEff.setText(data['effi'])
            self.ui.labelAvHead.setText(data['power'])
            self.ui.labelSafeF.setText(data['safety'])

            # Density removed to avoid double count
            # Flow removed to avoid double count
            self.ui.labelGravConst.setText(data['gravity'])

            # Pass in designer status
            self.ui.radioButtonInDesigner.setChecked(bool(data['designer_status_in']))
            self.ui.radioButtonOutDesigner.setChecked(bool(data['designer_status_out']))

        
    def dof(self): # Determine the degrees of freedom
        data = self.datafunction()
        
        # Count degrees of freedom
        dof = 0
        for key in data:
            if data[key] == 'Unspecified':
                if key == 'out_dens' or key == 'out_flow':
                    print("detected duplication pass")
                    pass
                else:
                    dof += 1

        if dof >= 2 or dof == 0:
            self.dofinfobox(dof)
        else:
            # Otherwise open the solve window with the results.
            print('open solve window')
            self.open_window_solve(data) # pass the data to use for calculating

    def dofinfobox(self, dof = "unspecified"):
        msgBox = QMessageBox()
        if dof >=2:
            msgBox.information(self, "Degrees of Freedom (DOF) Error", f"There are too many degrees of freedom: {dof} \n\nPlease Specify all but one variable to solve for.")
        elif dof == 0:
            msgBox.information(self, "Degrees of Freedom (DOF) Error", f"There are no degrees of freedom: {dof} \n\nPlease Specify all but one variable to solve for.")
        else:
            pass # Function to fill in missing value in labeltext and change colour to green, call calculate.py

    def show_sub_window_pump(self): # <-- Here, we create *and connect* the sub window's signal to the main window's slot
        self.sub_window = MotorProp()
        self.sub_window.submitClicked.connect(self.on_sub_window_pump_confirm)

        self.sub_window.ui.lineEditEff.setText(self.ui.labelEff.text()) if self.ui.labelEff.text() != 'Unspecified' else self.sub_window.ui.lineEditEff.setText('')
        self.sub_window.ui.lineEditTPH.setText(self.ui.labelAvHead.text()) if self.ui.labelAvHead.text() != 'Unspecified' else self.sub_window.ui.lineEditTPH.setText('')
        self.sub_window.ui.lineEditSF.setText(self.ui.labelSafeF.text()) if self.ui.labelSafeF.text() != 'Unspecified' else self.sub_window.ui.lineEditSF.setText('')
        self.sub_window.ui.lineEditGravConst.setText(self.ui.labelGravConst.text()) if self.ui.labelGravConst.text() != 'Unspecified' else self.sub_window.ui.lineEditGravConst.setText('')

        self.sub_window.show()
    
    def on_sub_window_pump_confirm(self, data):
        self.ui.labelEff.setText(data['eff'])
        self.ui.labelAvHead.setText(data['power'])
        self.ui.labelSafeF.setText(data['safeF'])
        self.ui.labelGravConst.setText(data['gravity'])

    def open_window_solve(self, data):
        self.sub_window = SolvePage(data)

        # connect to the signal to get answer
        self.sub_window.resultsData.connect(self.on_sub_window_confirm)

        self.sub_window.show()

    def designerStatuses(self, identifier):
        if identifier == 'Inlet':
            if self.ui.labelDesignerStateIn.text() == 'Inactive':
                designerStatusinlet = False
            else:
                designerStatusinlet = True

            return designerStatusinlet
        
        elif identifier == 'Outlet':
            if self.ui.labelDesignerStateOut.text() == 'Inactive':
                designerStatusOutlet = False
            else:
                designerStatusOutlet = True
            
            return designerStatusOutlet
        
    def exportCSV(self):
        # Get a file name from the user
        fileName, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv);;All Files (*)")

        if fileName:
            with open(fileName, 'w', newline='') as csvfile:
                csvwriter = csv.writer(csvfile)

                # Write header
                csvwriter.writerow(['Key', 'Value'])
                self.data_dict = self.datafunction()
                # Write data
                for key, value in self.data_dict.items():
                    csvwriter.writerow([key, value])

            print(f'Data exported to {fileName}')

    def importCSV(self):
        # Get a file name from the user
        fileName, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv);;All Files (*)")

        if fileName:
            with open(fileName, 'r') as csvfile:
                csvreader = csv.reader(csvfile)

                # Skip header
                next(csvreader)

                # Read data into a dictionary
                imported_data = {row[0]: row[1] for row in csvreader}
                self.datafunction(imported_data)

            print(f'Data imported from {fileName}: {imported_data}')

    def for_testing(self):
        return print('hello, this is to test because pyqt cant be pytested')


if __name__=="__main__":
    app = QApplication(sys.argv)
    w = MyForm()
    w.show()
    sys.exit(app.exec_())