import sys
import csv
from copy import deepcopy
from PyQt5.QtWidgets import QMainWindow, QApplication, QAction, QFileDialog, QMessageBox
from main import *

# Added subwindows
from callproperties import Properties
from callmotorProp import MotorProp
from callsolvePage import SolvePage
from callabout import About
from csv_io import ensure_csv_path, read_project, write_project, validate_parameters
from version import __version__
from centered_canvas import center_window_contents

class MyForm(QMainWindow):
    # class variable to store references to open windows
    windows = []
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.setWindowTitle(f"Process Pump Solver Tool {__version__}")
        QApplication.instance().setApplicationVersion(__version__)

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
        
        self.viscosity_in = ''
        self.viscosity_out = ''
        self.transition_equation_in = 'Moody'
        self.transition_equation_out = 'Moody'

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
            self.sub_window.lossesData(deepcopy(self.stored_segments_in), deepcopy(self.list_fittings_by_segment_in), deepcopy(self.lineRoughnessList_in), self.viscosity_in)
            self.sub_window.transition_equation = self.transition_equation_in

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
            self.sub_window.lossesData(deepcopy(self.stored_segments_out), deepcopy(self.list_fittings_by_segment_out), deepcopy(self.lineRoughnessList_out), self.viscosity_out)
            self.sub_window.transition_equation = self.transition_equation_out
            
            # Based on the designer status change the display units, from head loss to 'total friction loss' and vice versa
            self.change_loss_units(designerStatus)

            # for the designer
            self.ui.radioButtonOutDesigner.setChecked(designerStatus)

        self.sub_window.submitClicked.connect(self.on_sub_window_confirm)
        self.sub_window.exec_()

    def change_loss_units(self, designerStatus):
        self.sub_window.ui.labelLossesUnits.setText("m")

    
    def on_sub_window_confirm(self, data, identifier, stored_segments, list_fittings_by_segment, lineRoughnessList, viscosity=None, transition_equation=None):
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
            if stored_segments is not None:
                self.stored_segments_in = stored_segments
            if list_fittings_by_segment is not None:
                self.list_fittings_by_segment_in = list_fittings_by_segment
            if lineRoughnessList is not None:
                self.lineRoughnessList_in = lineRoughnessList
            if viscosity is not None:
                self.viscosity_in = viscosity
            if transition_equation is not None:
                self.transition_equation_in = transition_equation
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
            if viscosity is not None:
                self.viscosity_out = viscosity
            if transition_equation is not None:
                self.transition_equation_out = transition_equation
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

    def datafunction(self, saved_data=None):
        if saved_data is not None:
            self.dataRestore(saved_data)
        data = {key: getattr(self.ui, widget).text()
                for key, widget in self.PARAMETER_WIDGETS.items()}
        data['designer_status_in'] = self.ui.radioButtonInDesigner.isChecked()
        data['designer_status_out'] = self.ui.radioButtonOutDesigner.isChecked()
        return data

    def dataRestore(self, data):
        # Validate the entire import before changing any displayed value.
        data = validate_parameters(data)
        for key, widget in self.PARAMETER_WIDGETS.items():
            getattr(self.ui, widget).setText(data[key])
        self.ui.radioButtonInDesigner.setChecked(data['designer_status_in'])
        self.ui.radioButtonOutDesigner.setChecked(data['designer_status_out'])
        self.set_designer_text('In')
        self.set_designer_text('Out')

    def project_state(self):
        state = {'parameters': self.datafunction()}
        for side, suffix in (('inlet', 'in'), ('outlet', 'out')):
            state[side] = {
                'segments': deepcopy(getattr(self, f'stored_segments_{suffix}')),
                'fittings': deepcopy(getattr(self, f'list_fittings_by_segment_{suffix}')),
                'roughness': deepcopy(getattr(self, f'lineRoughnessList_{suffix}')),
                'viscosity': getattr(self, f'viscosity_{suffix}'),
                'transition_equation': getattr(self, f'transition_equation_{suffix}'),
            }
        return state

    def restore_project(self, state):
        self.dataRestore(state['parameters'])
        for side, suffix in (('inlet', 'in'), ('outlet', 'out')):
            design = state[side]
            setattr(self, f'stored_segments_{suffix}', deepcopy(design['segments']))
            setattr(self, f'list_fittings_by_segment_{suffix}', deepcopy(design['fittings']))
            setattr(self, f'lineRoughnessList_{suffix}', deepcopy(design['roughness']))
            setattr(self, f'viscosity_{suffix}', design['viscosity'])
            setattr(self, f'transition_equation_{suffix}', design['transition_equation'])

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
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Project CSV", "project.csv", "CSV Files (*.csv)")
        if not file_name:
            return
        try:
            write_project(ensure_csv_path(file_name), self.project_state())
        except (OSError, ValueError, csv.Error) as error:
            QMessageBox.critical(self, "CSV Export Failed", str(error))

    def importCSV(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Project CSV", "", "CSV Files (*.csv)")
        if not file_name:
            return
        try:
            state = read_project(file_name)
        except (OSError, ValueError, csv.Error) as error:
            QMessageBox.critical(self, "CSV Import Failed", str(error))
            return
        self.restore_project(state)

    def for_testing(self):
        return print('hello, this is to test because pyqt cant be pytested')


if __name__=="__main__":
    app = QApplication(sys.argv)
    w = MyForm()
    w.show()
    sys.exit(app.exec_())
