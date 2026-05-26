import sys
import csv
import inspect
import re
from PyQt5.QtWidgets import QMainWindow, QApplication, QAction, QFileDialog, QMessageBox, QStyledItemDelegate, QLineEdit, QTableWidgetItem, QComboBox
from PyQt5.QtGui import QRegExpValidator, QPixmap
from PyQt5.QtCore import Qt, QRegExp, QEvent
from lossesCal import *
from frictionCalc import Calculation
from callInfo1 import Info1
from callInfo2 import Info2
from callInfo3 import Info3
from callhelp import Help



class RegexDelegate(QStyledItemDelegate):
    def __init__(self, regex, parent=None):
        super().__init__(parent)
        self.regex = regex

    def createEditor(self, parent, option, index):
        if index.column() == index:  # Apply validation only to the first column
            editor = QLineEdit(parent)
            validator = QRegExpValidator(QRegExp(self.regex))
            editor.setValidator(validator)
            return editor
        else:
            editor = QLineEdit(parent) # Apply validation in all cells
            validator = QRegExpValidator(QRegExp(self.regex))
            editor.setValidator(validator)
            return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.DisplayRole)
        editor.setText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)


class LossesCal(Calculation):
    designerEnabled = QtCore.pyqtSignal(bool) # This is the subwindow signal sent to properties, pass back data to eventially store in main.
    densityChanged = QtCore.pyqtSignal(str) # This is the subwindow signal sent to properties, pass back data to eventially store in main.
    volumetricChanged = QtCore.pyqtSignal(str) # This is the subwindow signal sent to properties, pass back data to eventially store in main.
    callLossesData = QtCore.pyqtSignal(dict, list, list, str) # self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList.
    diameterChanged = QtCore.pyqtSignal(str) # First row of the table


    def __init__(self, instanceName, designerStatus=True): # Need to pass in a the name to identify window by changing its name, and whether designer is enabled or not
        super().__init__()
        self.ui = Ui_LineLossesDesigner()
        self.ui.setupUi(self)
        self.setWindowTitle(instanceName)

        # Set the instructions
        self.label_instructions()

        # Set global variables for updating, a list of dictionaries.
        # Store table data in a list according to the row selected from tableWidgetPipesegment
        self.stored_segments = {}
        self.list_fittings_by_segment = []
        
        # Set designer status on first open.
        self.ui.checkBoxLossesCal.setChecked(designerStatus)
        # Set the designer status
        self.ui.checkBoxLossesCal.clicked.connect(self.disableVarious)

        # Excecute action performed use clicked signal
        self.ui.pushButtonClose.clicked.connect(self.saveandclose)

        # Enable first table on startup if designer enabled
        self.tableLineSegmentEnable()
        # Enable add button and delete button on startup if designer enabled

        # Enable / Disable fittings table if a cell is not selected:
        self.ui.tableWidgetPipeSegment.itemSelectionChanged.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.itemActivated.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.cellChanged.connect(self.save_table_data_Segment)

        # Detect row selected and delete / add row selection.
        self.ui.pushButtonAddSegment.clicked.connect(lambda: self.addRow('TablePipeSegment'))
        self.ui.pushButtonDeleteSegment.clicked.connect(lambda: self.deleteRow('TablePipeSegment'))

        self.ui.pushButtonAddFitting.clicked.connect(lambda: self.addRow('TableFittings'))
        self.ui.pushButtonDeleteFitting.clicked.connect(lambda: self.deleteRow('TableFittings'))

        # Save the fitting values whenever fittings table interacted with (function also identifies segment type and gives the value)
        self.ui.tableWidgetFittings.itemSelectionChanged.connect(self.save_table_data_fittings)
        self.ui.tableWidgetFittings.itemActivated.connect(self.save_table_data_fittings)
        self.ui.tableWidgetFittings.cellChanged.connect(self.calculate_answer)

        # detect cell entered to prevent user from switching segments before save signal (itemSelectionChanged)
        self.ui.tableWidgetFittings.cellClicked.connect(self.disableSegmentTable)

        # information popups
        self.ui.pushButtonInfo.clicked.connect(self.openInfo)
        self.ui.pushButtonInfo2.clicked.connect(self.openInfo2)
        self.ui.pushButtonInfo3.clicked.connect(self.openInfo3)
        self.ui.toolButtonHelp.clicked.connect(self.openHelp)

        # export / import options
        self.ui.pushButtonImportSegment.clicked.connect(lambda: self.import_data("segment"))
        self.ui.pushButtonExportSegment.clicked.connect(lambda: self.export_data("segment"))

        self.ui.pushButtonImportFittings.clicked.connect(lambda: self.import_data("fittings"))
        self.ui.pushButtonExportFittings.clicked.connect(lambda: self.export_data('fittings'))

        self.ui.pushButtonExportLineRoughness.clicked.connect(lambda: self.export_data('roughness'))
        self.ui.pushButtonImportLineRoughness.clicked.connect(lambda: self.import_data('roughness'))

        # Store variable visocity
        self.storeViscosity = None
        # self.ui.lineEditViscosity.editingFinished.connect(self.save_viscosity)
        # Store LineRoughness
        self.lineRoughnessList = []
        self.ui.comboBoxRoughness.installEventFilter(self)
        self.ui.comboBoxRoughness.lineEdit().editingFinished.connect(self.save_LineRoughness)
        self.ui.comboBoxRoughness.currentIndexChanged.connect(self.save_LineRoughness)
        # Validate values typed in the line segment table
        self.validateTableEntry()

        # Store density value
        self.storeDensity = self.ui.lineEditDensity.text()
        print(f"Trying to store density on startup the text is {self.storeDensity}")
        self.ui.lineEditDensity.editingFinished.connect(self.save_density)

        # Detect user changes volumetric flowrate
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        self.ui.lineEditFlowrate.editingFinished.connect(self.save_volumetric)

        # Store previously selected row
        self.previous_row = None

        # set the validator to validate inputs
        self.regex = QtCore.QRegExp("^[0-9]*\.?[0-9]*$")
        self.validator = QtGui.QRegExpValidator(self.regex)

        # Assign Validation to Editbox
        self.ui.lineEditViscosity.setValidator(self.validator)
        self.ui.lineEditDensity.setValidator(self.validator)
        self.ui.lineEditFlowrate.setValidator(self.validator)
        self.ui.comboBoxRoughness.lineEdit().setValidator(self.validator)

        # detect a mouse press event on the window to lose focuse
        self.mousePressEvent = self.calculate_answer if self.ui.checkBoxLossesCal.isEnabled else print("Designer Disabled")

        # Connect the currentIndexChanged signal to the updateImage function
        self.ui.comboBoxTransitionEquation.currentIndexChanged.connect(self.updateImage)

        # Set transition equation on startup
        self.updateImage(self.ui.comboBoxTransitionEquation.currentIndex())


        print(f'The window title is callLosses {self.windowTitle().split(" ")[:1][0]}')
        self.show()

    def updateImage(self, index):
        # Define a dictionary mapping index to image file paths
        image_paths = {
            0: 'moodyEq.png',
            1: 'RJSPigott.png'
        }

        # Get the image path based on the selected index
        image_path = image_paths.get(index, '')

        # Update the QLabel pixmap with the selected image
        if image_path:
            pixmap = QPixmap(image_path)
            self.ui.labelBoundaryEquation.setPixmap(pixmap)
            self.ui.labelBoundaryEquation.setScaledContents(True)

        self.calculate_answer()

    def export_data(self, identifier):
        fileName, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv);;All Files (*)")
        if identifier == 'segment':
            # first save the data
            self.save_table_data_Segment()
            # Get a file name from the user

            if fileName:
                with open(fileName, 'w', newline='') as csvfile:
                    csvwriter = csv.writer(csvfile)

                    # Write header
                    csvwriter.writerow(['Key', 'Value'])
                    self.data_dict = self.stored_segments
                    # Write data
                    for key, value in self.data_dict.items():
                        csvwriter.writerow([key, value])

                print(f'Data exported to {fileName}')

        elif identifier == 'fittings':
            headers = set().union(*[d.keys() for d in self.list_fittings_by_segment])

            if fileName:
                with open(fileName, 'w', newline='') as csv_file:
                    # Create a CSV writer
                    csv_writer = csv.DictWriter(csv_file, fieldnames=headers)

                    # Write the header
                    csv_writer.writeheader()

                    # Write the data
                    csv_writer.writerows(self.list_fittings_by_segment)

        elif identifier == "roughness":
            # Extract column headers from the first dictionary
            headers = set().union(*[d.keys() for d in self.lineRoughnessList])

            if fileName:
                with open(fileName, 'w', newline='') as csv_file:
                    # Create a CSV writer
                    csv_writer = csv.DictWriter(csv_file, fieldnames=headers)

                    # Write the header
                    csv_writer.writeheader()

                    # Write the data
                    csv_writer.writerows(self.lineRoughnessList)

    def import_data(self, identifier):
        # Get a file name from the user
        fileName, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv);;All Files (*)")

        if identifier == 'segment':
            if fileName:
                with open(fileName, 'r') as csvfile:
                    csvreader = csv.reader(csvfile)

                    # Skip header
                    next(csvreader)

                    # Read data into a dictionary
                    imported_data = {row[0]: row[1] for row in csvreader}
                    
                    try:
                        for key, value in imported_data.items():
                            float(value)
                    except ValueError:
                        msg = QMessageBox()
                        msg.setIcon(QMessageBox.Critical)
                        msg.setWindowTitle("Error: Import Failed")
                        msg.setText(f"Corrupt/Invalid data at '{key}':'{value}'.")
                        msg.exec_()
                    else:
                        self.stored_segments = imported_data
                        print(f"imported segment {imported_data}")
                        self.restore_table_data_segments()
                        

                print(f'Data imported from {fileName}: {imported_data}')

        elif identifier == 'fittings':
            print('import data fittings')
            if fileName:
                print('import data fittings checkpoint 2')
                with open(fileName, 'r', newline='') as csv_file:
                    print('import data fittings checkpoint 3')
                    # Create a CSV reader
                    csv_reader = csv.DictReader(csv_file)
                    print(f'import data fittings checkpoint 3.5, {csv_reader}')

                    # Iterate over each row in the CSV file
                    for row in csv_reader:
                        print('import data fittings checkpoint 4')
                        # Check if a dictionary with the same 'Name' already exists
                        print(f'Nonetype check, print {row}')
                        try:
                            for key, value in row.items():
                                if 'Fitting Type' not in key and value != '':
                                    float(value)  # Try to convert value to float
                        except (ValueError, TypeError) :
                            msg = QMessageBox()
                            msg.setIcon(QMessageBox.Critical)
                            msg.setWindowTitle("Error: Import Failed")
                            msg.setText(f"Corrupt/Invalid data at '{key}':'{value}'.")
                            msg.exec_()
                            print(f"Skipping row: {row} - Not all values can be converted to floats.")
                        else:
                            print('import data fittings checkpoint 6')
                            for key, value in row.items():
                                if 'Line Segment' in key:
                                    row[key] = int(value)  # Try to convert value to float

                            found = False
                            for item in self.list_fittings_by_segment:
                                if item['Line Segment'] == row['Line Segment']:
                                    item.update(row)
                                    found = True

                            if not found:
                                # If no existing dictionary, append the new row
                                print(f'Apprently list of fittings is a dictionary check {self.list_fittings_by_segment}')
                                self.list_fittings_by_segment.append(row)
                                print('import data fittings checkpoint 7')  

                print(f'The imported fittings list. {self.list_fittings_by_segment}')
                            # self.ui.tableWidgetPipeSegment.clearSelection()
                self.ui.tableWidgetFittings.itemSelectionChanged.disconnect(self.save_table_data_fittings)
                self.ui.tableWidgetFittings.itemActivated.disconnect(self.save_table_data_fittings)
                self.restore_table_data_fittings()
                self.ui.tableWidgetFittings.itemActivated.connect(self.save_table_data_fittings)
                self.ui.tableWidgetFittings.itemSelectionChanged.connect(self.save_table_data_fittings)


        elif identifier == 'roughness':
            print('import data roughness')
            if fileName:
                print('import data roughness checkpoint 2')
                with open(fileName, 'r', newline='') as csv_file:
                    print('import data roughness checkpoint 3')
                    # Create a CSV reader
                    csv_reader = csv.DictReader(csv_file)
                    print(f'import data roughness checkpoint 3.5, {csv_reader}')

                    # Iterate over each row in the CSV file
                    for row in csv_reader:
                        print('import data roughness checkpoint 4')
                        # Check if a dictionary with the same 'Name' already exists
                        print(f'Nonetype check, print {row}')
                        try:
                            for key, value in row.items():
                                if row['Segment Roughness'] != 'Smooth Pipe' and value != '':
                                    float(value)  # Convert to integer
                        except (ValueError, TypeError) :
                            msg = QMessageBox()
                            msg.setIcon(QMessageBox.Critical)
                            msg.setWindowTitle("Error: Import Failed")
                            msg.setText(f"Corrupt/Invalid data at '{key}':'{value}'.")
                            msg.exec_()
                            print(f"Skipping row: {row} - Not all values can be converted to floats.")
                        else:
                            print('import data roughness checkpoint 6')
                            for key, value in row.items():
                                if 'Line Segment' in key:
                                    row[key] = int(value)  # Convert to integer

                            found = False
                            for item in self.lineRoughnessList:
                                if item['Line Segment'] == row['Line Segment']:
                                    item.update(row)
                                    found = True

                            if not found:
                                # If no existing dictionary, append the new row
                                print(f'Apprently list of fittings is a dictionary check {self.lineRoughnessList}')
                                self.lineRoughnessList.append(row)
                                print('import data fittings checkpoint 7')  

                print(f'The imported roughness list. {self.lineRoughnessList}')
                            # self.ui.tableWidgetPipeSegment.clearSelection()
                self.ui.tableWidgetFittings.itemSelectionChanged.disconnect(self.save_table_data_fittings)
                self.ui.tableWidgetFittings.itemActivated.disconnect(self.save_table_data_fittings)
                self.restore_lineRoughness()
                self.ui.tableWidgetFittings.itemActivated.connect(self.save_table_data_fittings)
                self.ui.tableWidgetFittings.itemSelectionChanged.connect(self.save_table_data_fittings)



    def label_instructions(self):
        if self.windowTitle().split(" ")[:1][0] == "Inlet":
            self.ui.labelinstructions.setText("Specify pipe lengths where the diameter changes. The first segment is the suction nossle that starts at the storage tank. Subsequent pipes connect to the pipe that preceeds it the last segment is the suction nossle that ends at the pump inlet (suction side).")

        elif self.windowTitle().split(" ")[:1][0] == "Outlet":
            self.ui.labelinstructions.setText("Specify pipe lengths where the diameter changes. The first segment connects to the pump outlet. Subsequent pipes connect to the pipe that preceeds it,\
                                              the last segment is the discharge nossle that ends at the outlet storage tank.")
    def openHelp(self):
        self.sub_window = Help()
        self.sub_window.show()

    def openInfo(self):
        self.sub_window = Info1()
        self.sub_window.show()

    def openInfo2(self):
        self.sub_window = Info2()
        self.sub_window.show()

    def openInfo3(self):
        self.sub_window = Info3()
        self.sub_window.show()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if isinstance(obj, QComboBox):
                self.table_segment_buttons_disable()
                print('ComboBox gained focus')
        elif event.type() == QEvent.FocusOut:
            if isinstance(obj, QComboBox):
                self.table_segment_buttons_enable()
                print('ComboBox lost focus')

        return super().eventFilter(obj, event)
    
    def table_segment_buttons_disable(self):
        self.ui.pushButtonAddSegment.setDisabled(True)
        self.ui.pushButtonDeleteSegment.setDisabled(True)
        self.ui.pushButtonImportSegment.setDisabled(True)
        self.ui.pushButtonExportSegment.setDisabled(True)

    def table_segment_buttons_enable(self):
        self.ui.pushButtonAddSegment.setDisabled(False)
        self.ui.pushButtonDeleteSegment.setDisabled(False)
        self.ui.pushButtonImportSegment.setDisabled(False)
        self.ui.pushButtonExportSegment.setDisabled(False)

        # Setter method, restored data previously inputted in callLossesCal.py called in callproperties.py
    def previously_stored_data(self, stored_segments, list_fittings_by_segment, lineRoughnessList):
        print(f"Setter method ran, the stored data is {stored_segments}, {list_fittings_by_segment}, {lineRoughnessList}")
        self.stored_segments = stored_segments
        self.list_fittings_by_segment = list_fittings_by_segment
        self.lineRoughnessList = lineRoughnessList

        self.restore_table_data_segments()

    def restore_table_data_segments(self):
        # Iterate through the stored_lines dictionary and restore data
        for key, value in self.stored_segments.items():
            try:
                row_header, column_name = key.split(', ')
            except ValueError:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Error: Import Failed")
                msg.setText(f"Invalid import CSV structure, import Segment CSV files only.")
                msg.exec_()
                print(f"Wrong input form")
                return

            # Ensure the table has enough rows
            row = int(row_header.split()[-1]) - 1
            if row >= self.ui.tableWidgetPipeSegment.rowCount():
                self.ui.tableWidgetPipeSegment.setRowCount(row + 1)
            
            # Get the column index based on the header text
            col = -1
            for i in range(self.ui.tableWidgetPipeSegment.columnCount()):
                if self.ui.tableWidgetPipeSegment.horizontalHeaderItem(i).text() == column_name:
                    col = i
                    break

            # Ensure the table has enough columns
            if col >= self.ui.tableWidgetPipeSegment.columnCount():
                self.ui.tableWidgetPipeSegment.setColumnCount(col + 1)

            item = QTableWidgetItem(value)
            print(f"the row is {row}, the column is {col} and the item is {item}")
            self.ui.tableWidgetPipeSegment.setItem(row, col, item)

            self.ui.tableWidgetPipeSegment.cellChanged.disconnect(self.save_table_data_Segment)
            self.renameVerticalHeader('TablePipeSegment', True) # pass in true for restoration
            self.ui.tableWidgetPipeSegment.cellChanged.connect(self.save_table_data_Segment)
        print('Restore table data segment ended, got into restoration code')

    def save_density(self):
        self.storeDensity = self.ui.lineEditDensity.text()
        print(f'Density stored as {self.storeDensity}')
        self.densityChanged.emit(self.ui.lineEditDensity.text())
        self.save_table_data_Segment()
        self.calculate_answer()

    def save_volumetric(self):
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        print(f'Volumetric flow stored as {self.storeVolumetric}')
        self.volumetricChanged.emit(self.ui.lineEditFlowrate.text())
        self.save_table_data_Segment()
        self.calculate_answer()

    def save_diameter(self):
        if self.windowTitle().split(" ")[:1][0] == "Inlet":
            try:
                # Retrieve the value in the second column of the last row
                last_row = self.ui.tableWidgetPipeSegment.rowCount() - 1
                self.diameter = self.ui.tableWidgetPipeSegment.item(last_row, 1).text()
            except (ValueError, AttributeError):
                pass
            else:
                self.diameterChanged.emit(self.diameter)
        elif self.windowTitle().split(" ")[:1][0] == "Outlet":
            try:
                # Retrieve the value in the first column of the first row
                self.diameter = self.ui.tableWidgetPipeSegment.item(0, 1).text()
            except (ValueError, AttributeError):
                pass
            else:
                self.diameterChanged.emit(self.diameter)

    def calculate_answer(self, event=None):
        caller_frame = inspect.stack()[1]
        caller_function = caller_frame.function
        caller_module = inspect.getmodule(caller_frame[0]).__name__
        
        print(f'This function Calculate answer was called by {caller_module}.{caller_function}')
        sender = self.sender()
        if sender:
            try:
                print(f'Calculate answer was activated by {sender.text()}')
            except:
                pass

        # Clear the focus on any focused widget
        focused_widget = self.focusWidget()
        if focused_widget:
            focused_widget.clearFocus()
        if self.ui.checkBoxLossesCal.isChecked() and self.ui.tableWidgetFittings.selectedItems() == None:
            self.enableSegmentTable()

        print("Calculate Answer Function Ran")
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        self.storeDensity = self.ui.lineEditDensity.text()
        self.storeViscosity = self.ui.lineEditViscosity.text()

        try:
            # Convert to float on start-up
            self.viscosity = float(self.storeViscosity) # Single Value / Applicable to all segments
            self.density = float(self.storeDensity) # Single Value / Applicable to all segments
            self.volumetric = float(self.storeVolumetric) # Single Value / Applicable to all segments
        except ValueError:
            print('Viscosity, density or volumentric Flowrate not yet specified')
            print(f'viscosity: {self.storeViscosity}, density: {self.storeDensity}, volumetric: {self.storeVolumetric}')
            self.ui.pushButtonClose.setEnabled(False)
        else:
            print(self.lineRoughnessList)
            if self.lineRoughnessList and self.stored_segments:
                print('Information passed to start calculation')
                for dictionary in self.lineRoughnessList:
                    if dictionary['Segment Roughness'] == '':
                        print('The user has not specified line roughness yet')
                    # if dictionary['Segment Roughness'] != 
                        return
                print(f'This is the code that we trying to evaluate{self.stored_segments}')
                for key, value in self.stored_segments.items():
                    if value == '':
                        print(f"The user has not specified {key}")
                        return
                self.start_cal(self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList, self.viscosity, self.density, self.volumetric)
            else:
                print("The segment table is empty or the user has not specified the pipe roughness yet")
                self.ui.pushButtonClose.setEnabled(False)

    def save_LineRoughness(self):
        caller_frame = inspect.stack()[1]
        caller_function = caller_frame.function
        caller_module = inspect.getmodule(caller_frame[0]).__name__
    
        print(f'This function save_LineRoughness was called by {caller_module}.{caller_function}')
        sender = self.sender()
        if sender:
            print(f'Save save_lineRoughness was activated by {sender}')
        print(f'Saving Line roughness Started (Before SAVE): {self.lineRoughnessList}')

        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()

        selected_row = selected_indexes[0].row() + 1

        if not selected_indexes and selected_row:
            print('not saved as user did not selecte a row. (Should not be possible)')
            return  # No selection (user made no selection)

        for dictionary in self.lineRoughnessList:
            if dictionary['Line Segment'] == selected_row:
                dictionary['Segment Roughness'] = self.ui.comboBoxRoughness.currentText()

        data = {'Line Segment': selected_row,
                'Segment Roughness': self.ui.comboBoxRoughness.currentText()}
        data_no_selection = {'Line Segment': selected_row,
                'Segment Roughness': ''}

        try:
            filtered_data = [d for d in self.lineRoughnessList if d.get('Line Segment') != selected_row]
            self.lineRoughnessList = filtered_data
            # print(f'\n Data after removal {self.lineRoughnessList}')
        except IndexError:
            # There is no need to remove first, insert the segment roughness
            self.insert_roughness(selected_row, data, data_no_selection)
        else:
            self.insert_roughness(selected_row, data, data_no_selection)
        
        self.save_table_data_Segment()
        self.calculate_answer()

        print(f'Saving Line roughness Ended, AFTER SAVE {self.lineRoughnessList}')
        # print(f'This function save_LineRoughness was called by {caller_module}.{caller_function}')

    def insert_roughness(self, selected_row, data, data_no_selection):
        # Check if user did not select default value, if so leave segment blank.
        if self.ui.comboBoxRoughness.currentText() == 'Specify Pipe Roughness':
            self.lineRoughnessList.insert(selected_row, data_no_selection)
        else:
            self.lineRoughnessList.insert(selected_row, data)

                
    def restore_lineRoughness(self):
        # clear the textbox to add data
        self.ui.comboBoxRoughness.setCurrentIndex(0)
        
        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()
        print(f"Restoring Roughness Started {self.lineRoughnessList}")

        try:
            selected_row = selected_indexes[0].row() + 1
            print(f"The selected Segment is {selected_row}")
        except IndexError:
            print("User selected empty an empty space, Nothing was restored. Restoration has ended")
            return
        else:
            # clear data before restoration (but this causes a save because text change detected -- not desired)
            # self.ui.comboBoxRoughness.clearEditText()
            for dictionary in self.lineRoughnessList:
                print(f"Roughness dictionary currently evaluating {dictionary}")
                if dictionary['Line Segment'] == selected_row:
                    print(f'Found roughness dictionary to restore {dictionary}')
                    text = dictionary["Segment Roughness"]
                    if text != '':
                        self.ui.comboBoxRoughness.setCurrentText(text)
                    else:
                        print("User previouse selection was default, reset to default")
                        self.ui.comboBoxRoughness.setCurrentIndex(0)
                    return
                else:
                    print('Did not find roughness to restore, restoring combobox to default. Restoration has ended')
                    self.ui.comboBoxRoughness.setCurrentIndex(0)
        print(f"Restoring Roughness Ended {self.lineRoughnessList}")
        
    def save_viscosity(self):
        self.storeViscosity = self.ui.lineEditViscosity.text()
        self.save_table_data_Segment()
        self.calculate_answer()
        print(f'Viscosity stored as {self.storeViscosity}')

    def disableSegmentTable(self):
        self.ui.tableWidgetPipeSegment.setDisabled(True)
        self.ui.pushButtonAddSegment.setDisabled(True)
        self.ui.pushButtonDeleteSegment.setDisabled(True)
        self.ui.pushButtonImportSegment.setDisabled(True)
        self.ui.pushButtonExportSegment.setDisabled(True)

    def enableSegmentTable(self):
        self.ui.tableWidgetPipeSegment.setDisabled(False)
        self.ui.pushButtonAddSegment.setDisabled(False)
        self.ui.pushButtonDeleteSegment.setDisabled(False)
        self.ui.pushButtonImportSegment.setDisabled(False)
        self.ui.pushButtonExportSegment.setDisabled(False)

    def validateTableEntry(self):
        # Validate values typed in the line segment table (only allows positive values)
        regex_pattern = r"^-?[0-9]*\.?[0-9]*$"
        regex_delegate = RegexDelegate(regex_pattern, self.ui.tableWidgetPipeSegment)
        self.ui.tableWidgetPipeSegment.setItemDelegate(regex_delegate)  

        self.ui.tableWidgetFittings.setItemDelegateForColumn(1, regex_delegate) # Apply delegate to the second column only 
   
    def disableVarious(self):  # Slot for when the designer is enabled.
        print(self.ui.checkBoxLossesCal.isChecked())
        self.designerEnabled.emit(self.ui.checkBoxLossesCal.isChecked())

        # Proceed to disable second table and line edits
        if self.ui.checkBoxLossesCal.isChecked() == False:
            self.ui.tableWidgetFittings.setDisabled(True)
            self.ui.comboBoxRoughness.setDisabled(True)
            self.ui.lineEditViscosity.setDisabled(True)
            self.ui.lineEditFlowrate.setDisabled(True)
            self.ui.lineEditDensity.setDisabled(True)
            self.ui.pushButtonAddFitting.setDisabled(True)
            self.ui.pushButtonDeleteFitting.setDisabled(True)
            self.ui.pushButtonImportFittings.setDisabled(True)
            self.ui.pushButtonExportFittings.setDisabled(True)

        print(f' The selected items are {self.ui.tableWidgetPipeSegment.selectedIndexes()}')
        selected_indexes = self.ui.tableWidgetPipeSegment.selectedIndexes()

        if self.ui.checkBoxLossesCal.isChecked() == True and selected_indexes:
            self.ui.tableWidgetFittings.setDisabled(False)
            self.ui.comboBoxRoughness.setDisabled(False)
            self.ui.lineEditViscosity.setDisabled(False)
            print(f'tried to enable flowrate Editbox')
            self.ui.lineEditFlowrate.setDisabled(False)
            print(f'flowrate editbox should be enabled {self.ui.lineEditFlowrate.isEnabled}')
            

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

    def save(self):
        self.callLossesData.emit(self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList, self.storeViscosity)

    def tableLineSegmentEnable(self):
        # print('Enable TableLineSegment')
        if self.ui.checkBoxLossesCal.isChecked():
            self.ui.tableWidgetPipeSegment.setEnabled(True)
            self.ui.pushButtonAddSegment.setEnabled(True)
            self.ui.pushButtonDeleteSegment.setEnabled(True)
            self.ui.pushButtonImportSegment.setEnabled(True)
            self.ui.pushButtonExportSegment.setEnabled(True)

    def handle_selection_change(self):
        selected_Indexes = self.ui.tableWidgetPipeSegment.selectedIndexes()

        # print(selected_items)
        if selected_Indexes:
            # print("Got in to activate")
            self.ui.tableWidgetFittings.setDisabled(False)
            self.ui.comboBoxRoughness.setDisabled(False)
            self.ui.lineEditViscosity.setDisabled(False)
            self.ui.pushButtonAddFitting.setDisabled(False)
            self.ui.pushButtonDeleteFitting.setDisabled(False)
            # self.ui.pushButtonImportFittings.setDisabled(False)
            # self.ui.pushButtonExportFittings.setDisabled(False)
            self.ui.lineEditDensity.setDisabled(False)
            self.ui.lineEditFlowrate.setDisabled(False)
        else:
            # print("Got in to disable")
            self.ui.tableWidgetFittings.setDisabled(True)
            self.ui.comboBoxRoughness.setDisabled(True)
            self.ui.lineEditViscosity.setDisabled(True)
            self.ui.pushButtonAddFitting.setDisabled(True)
            self.ui.pushButtonDeleteFitting.setDisabled(True)
            # self.ui.pushButtonImportFittings.setDisabled(True)
            # self.ui.pushButtonExportFittings.setDisabled(True)
            self.ui.lineEditDensity.setDisabled(True)
            self.ui.lineEditFlowrate.setDisabled(True)

        # clear the table for data thats going to displayed
        self.ui.tableWidgetFittings.setRowCount(0)

        # show the next data belonging to current selection
        self.restore_table_data_fittings()

        # Disconnect the signal before programmatically changing the index'
        # try:
        #     self.ui.comboBoxRoughness.currentIndexChanged.disconnect(self.save_LineRoughness)
        #     self.ui.comboBoxRoughness.lineEdit().editingFinished.disconnect(self.save_LineRoughness)
        # except TypeError:
        #     pass

        # restore previously saved
        # Programmatically change the selected index of the combo box (signal disconnected)
        self.ui.comboBoxRoughness.currentIndexChanged.disconnect(self.save_LineRoughness)
        self.restore_lineRoughness()
        self.ui.comboBoxRoughness.currentIndexChanged.connect(self.save_LineRoughness)

        # # Reconnect the signal after making the change
        # self.ui.comboBoxRoughness.currentIndexChanged.connect(self.save_LineRoughness)
        # self.ui.comboBoxRoughness.lineEdit().editingFinished.connect(self.save_LineRoughness)

        # run calculations
        self.calculate_answer()


    def save_table_data_Segment(self):
        caller_frame = inspect.stack()[1]
        caller_function = caller_frame.function
        caller_module = inspect.getmodule(caller_frame[0]).__name__
    
        print(f'This function save_table_data_Segment was called by {caller_module}.{caller_function}')
        sender = self.sender()
        # print(f'Save table data segment was activated by {sender.text()}')

        self.stored_segments = {}
        print("Save Table Data Segment Ran")
        for row in range(self.ui.tableWidgetPipeSegment.rowCount()):
            try:
                row_header = self.ui.tableWidgetPipeSegment.verticalHeaderItem(row).text()
            except AttributeError:
                # No input selected, Do not execute saving the table_data, cellchanged signal is activiated (thus handle_sel... then save_table..)
                # due to clearselection method in add_row or delete_row")
                print('Save table data segment ran, and exited using return')
                return
            else:
                for col in range(self.ui.tableWidgetPipeSegment.columnCount()):
                    item = self.ui.tableWidgetPipeSegment.item(row, col)
                    if item is not None:
                        column_name = self.ui.tableWidgetPipeSegment.horizontalHeaderItem(col).text()
                        key = f'{row_header}, {column_name}'
                        self.stored_segments[key] = item.text()
                    else:
                        column_name = self.ui.tableWidgetPipeSegment.horizontalHeaderItem(col).text()
                        key = f'{row_header}, {column_name}'
                        self.stored_segments[key] = ''
                        
        if self.ui.tableWidgetPipeSegment.rowCount() == 0:
            print(f"There are no rows left empty the segment dictionary")
            self.stored_segments = {}

        print(f'Saved table data: {self.stored_segments}. Save table segment data has ended')
        self.save_diameter()
        self.calculate_answer()

    def save_table_data_fittings(self):
        caller_frame = inspect.stack()[1]
        caller_function = caller_frame.function
        caller_module = inspect.getmodule(caller_frame[0]).__name__
    
        print(f'This function save_table_data_fitting was called by {caller_module}.{caller_function}')
        sender = self.sender()
        if sender:
            print(f'Save save_table_data_fittings was activated by {sender}')
        print(f'Saving save_table_data_fittings Started (Before SAVE): {self.lineRoughnessList}')
        # Identify the selected row
        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()

        if not selected_indexes:
            return  # No selection
        
        selected_row = selected_indexes[0].row() + 1
        # print(selected_row + 1)

        self.store_fittings = {}

        for row in range(self.ui.tableWidgetFittings.rowCount()):
            try:
                row_header = self.ui.tableWidgetFittings.verticalHeaderItem(row).text()
            except AttributeError:
                # No input selected, Do not execute saving the table_data, cellchanged signal is activiated (thus handle_sel... then save_table..)
                # due to clearselection method in add_row or delete_row")
                print("Row added, do not save.")
            else:
                self.store_fittings['Line Segment'] = selected_row
                for col in range(self.ui.tableWidgetFittings.columnCount()):
                    item = self.ui.tableWidgetFittings.item(row, col)
                    if item is not None:
                        column_name = self.ui.tableWidgetFittings.horizontalHeaderItem(col).text()
                        key = f'{row_header}, {column_name}'
                        self.store_fittings[key] = item.text()

        try:
            # Remove dictionaries with 'Line Segment' value of the row selected to avoid duplication of dictionaries with the same row.
            filtered_data = [d for d in self.list_fittings_by_segment if d.get('Line Segment') != selected_row]
            self.list_fittings_by_segment = filtered_data
            print(f'\n Data after removal and replacement {self.list_fittings_by_segment}')
        except IndexError:
            # There is no need to remove first, insert the store fittings table
            self.list_fittings_by_segment.insert(selected_row, self.store_fittings)
        else:
            # Now insert the stored fittings table
            self.list_fittings_by_segment.insert(selected_row, self.store_fittings)
        
        self.enableSegmentTable()
        self.calculate_answer()
        print(f'Saved data {self.list_fittings_by_segment}')

    def restore_table_data_fittings(self):
        # Restore must check if there is data already existing.
        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()

        try:
            selected_row = selected_indexes[0].row() + 1
        except IndexError:
            print("user is adding or deleting a row or there is no previous data associated with the pipesegment, there is nothing to restore")
            return
        else:
            print(f'restore the following segment row {selected_row}')
            print(f'Restoring stored table data fittings: {self.list_fittings_by_segment}.')

            self.list_fittings_by_segment = sorted(self.list_fittings_by_segment, key=lambda x: x['Line Segment'])

            for dictionary in self.list_fittings_by_segment:
                print(f"Started looping to restore table fittings. {dictionary}, {dictionary['Line Segment'] == selected_row}")
                # Look for and select the appropriate dictionary
                if dictionary['Line Segment'] == selected_row:
                    print(f'found dictionary {dictionary}')
                    
                    for key, value in dictionary.items():
                        if key != 'Line Segment':
                            match = re.search(r'Fitting (\d+)', key)
                            print(f'This is the key to match {key}, and this is the value {value}')
                            row = int(match.group(1)) - 1
                            print(f'This is the row to insert at {row}')
                            row_count = self.ui.tableWidgetFittings.rowCount()

                            if 'Fitting Type' in key:
                                while self.ui.tableWidgetFittings.rowCount() <= row:
                                    self.ui.tableWidgetFittings.insertRow(row)
                                fitting_type_item = QTableWidgetItem(value)
                                self.ui.tableWidgetFittings.setItem(row, 0, fitting_type_item)

                            elif 'Loss Factor' in key:
                                while self.ui.tableWidgetFittings.rowCount() <= row:
                                    self.ui.tableWidgetFittings.insertRow(row)
                                loss_factor_item = QTableWidgetItem(value)
                                self.ui.tableWidgetFittings.setItem(row, 1, loss_factor_item)
                    break


        # Get row count and rename vertical headers after deletion
        self.renameVerticalHeader('TableFittings',True)

    def addRow(self, identifier):
        caller_frame = inspect.stack()[1]
        caller_function = caller_frame.function
        caller_module = inspect.getmodule(caller_frame[0]).__name__
    
        print(f'This function AddRow was called by {caller_module}.{caller_function}')
        sender = self.sender()
        if sender:
            print(f'Addrow was activated by {sender.text()}')

        self.ui.tableWidgetPipeSegment.itemSelectionChanged.disconnect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.itemActivated.disconnect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.cellChanged.disconnect(self.save_table_data_Segment)


        if identifier == 'TablePipeSegment':
            row = self.ui.tableWidgetPipeSegment.currentRow()
            print(f'the added row index is {row}')
            
            if row != -1 and self.ui.tableWidgetPipeSegment.selectedIndexes():
                self.ui.tableWidgetPipeSegment.insertRow(row)
                row = row + 1 # Match the dictionary storage method, there is no row 0 
                added_dict = {'Line Segment': row, 'Segment Roughness': ''}
                # Update 'segment' values for existing dictionaries
                for item in self.lineRoughnessList:
                    if item['Line Segment'] >= added_dict['Line Segment']:
                        item['Line Segment'] += 1

                # Add the new dictionary to the list
                self.lineRoughnessList.append(added_dict)
                self.lineRoughnessList = sorted(self.lineRoughnessList, key=lambda x: x['Line Segment'])

                # Print the updated list
                print(f'Rougness list after the addition of a row {self.lineRoughnessList}')

                # Whenever there is a change in the segment table in the fittings table there should be an equivalent change in the 
                # dictionary that stores the fittings.
                added_dict = {'Line Segment': row, f'Fitting {row}, Fitting Type': '', f'Fitting {row}, Loss Factor': ''}
                # Update 'segment' values for existing dictionaries
                for item in self.list_fittings_by_segment:
                    if item['Line Segment'] >= added_dict['Line Segment']:
                        item['Line Segment'] += 1

                # Add the new dictionary to the list
                # self.list_fittings_by_segment.append(added_dict)
                self.list_fittings_by_segment = sorted(self.list_fittings_by_segment, key=lambda x: x['Line Segment'])

                # Print the updated list
                print(f'list fittings list after the addition of a row {self.list_fittings_by_segment}')

            else:
                row = self.ui.tableWidgetPipeSegment.rowCount()
                self.ui.tableWidgetPipeSegment.insertRow(row)
            # self.ui.tableWidgetPipeSegment.clearSelection()

            print(f'The segment dictionary after addition of PipeSegement {self.list_fittings_by_segment}')
            print(f'Line roughness dictionary after the addition of PipeSegment {self.lineRoughnessList}')

        self.ui.pushButtonClose.setEnabled(False)

        print(f'The segment dictionary after addition of PipeSegement {self.list_fittings_by_segment}')

        if identifier == 'TableFittings':
            row = self.ui.tableWidgetFittings.currentRow()
            print(f'TableFittings: the added row index is {row}')
            
            if row != -1 and self.ui.tableWidgetFittings.selectedIndexes():
                self.ui.tableWidgetFittings.insertRow(row)
                # Print the updated list
                print(f'Rougness List after the addition of a row in TableFittings {self.lineRoughnessList}')

            else:
                row = self.ui.tableWidgetFittings.rowCount()
                self.ui.tableWidgetFittings.insertRow(row)
            # self.ui.tableWidgetFittings.clearSelection()

        # Get row count and rename vertical headers after delection
        self.renameVerticalHeader(identifier)

        self.ui.tableWidgetPipeSegment.itemSelectionChanged.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.itemActivated.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.cellChanged.connect(self.save_table_data_Segment)
        

    def deleteRow(self, identifier):
        print(f'Deleted row and this is the identfier {identifier}')

        if identifier == 'TablePipeSegment':
            # Get the current row
            row = self.ui.tableWidgetPipeSegment.currentRow()
            print(f'The row that was deleted is {row}')
            if row != -1 and self.ui.tableWidgetPipeSegment.selectedIndexes():
                self.ui.tableWidgetPipeSegment.removeRow(row)

                row = row + 1 # Update the value of the row to match entries in the dicatioaries (i.e. there is no row 0 saved in dictionary)
                for item in self.lineRoughnessList:
                    if item['Line Segment'] == row:
                        self.lineRoughnessList.remove(item)
                        break

                for item in self.lineRoughnessList:
                    # Update the 'queue' values sequentially
                    if item['Line Segment'] > row:
                        item['Line Segment'] = item['Line Segment'] - 1
                    # Print the updated list
                    print(f'Deleted a row, Fittings list after row deletion {self.lineRoughnessList}')
                # Whenever there is a change in the segment table in the fittings table there should be an equivalent change in the 
                # dictionary that stores the fittings.
                for item in self.list_fittings_by_segment:
                    if item['Line Segment'] == row:
                        self.list_fittings_by_segment.remove(item)
                        break

                for item in self.list_fittings_by_segment:
                    # Update the 'queue' values sequentially
                    if item['Line Segment'] > row:
                        item['Line Segment'] = item['Line Segment'] - 1
                    # Print the updated list
                    print(f'Deleted a row, Fittings list after segment row deletion {self.list_fittings_by_segment}')

            else: # or else remove the last row if user has not selected a row
                row = self.ui.tableWidgetPipeSegment.rowCount() 
                self.ui.tableWidgetPipeSegment.removeRow(row)

            # Trigger a selection change to save the data (pipe segment data i.e. stored data)
            # self.ui.tableWidgetPipeSegment.clearSelection()

        if identifier == 'TableFittings':
            # Get the current row
            row = self.ui.tableWidgetFittings.currentRow()
            print(f'TableFittings: The row that was deleted is {row}')
            if row != -1 and self.ui.tableWidgetFittings.selectedIndexes():
                self.ui.tableWidgetFittings.removeRow(row)
                print(f"TableFittings data after deletion of fitting {self.list_fittings_by_segment}")
            else:
                row = self.ui.tableWidgetFittings.rowCount()
                self.ui.tableWidgetFittings.removeRow(row)
            
        # Get row count and rename vertical headers after deletion
        self.renameVerticalHeader(identifier)


    def renameVerticalHeader(self, identifier, restore=False):

        if identifier == 'TablePipeSegment':
            # Get row count and rename vertical headers after delection
            rows = self.ui.tableWidgetPipeSegment.rowCount()
            for row in range(rows):
                item_text = f'Line Segment {row + 1}'  # Create the item text based on the row number
                item = QTableWidgetItem(item_text)
                self.ui.tableWidgetPipeSegment.setVerticalHeaderItem(row, item)  # Set the item as the vertical header for the new row
                if not restore:
                    self.save_table_data_Segment()

        if identifier == 'TableFittings':
            rows = self.ui.tableWidgetFittings.rowCount()
            for row in range(rows):
                item_text = f'Fitting {row + 1}'  # Create the item text based on the row number
                item = QTableWidgetItem(item_text)
                self.ui.tableWidgetFittings.setVerticalHeaderItem(row, item)  # Set the item as the vertical header for the new row
                if not restore:
                    self.save_table_data_fittings()

    


if __name__=="__main__":
    app = QApplication(sys.argv)
    w = LossesCal('passedInName')  # Passed in window name must be dynamic, to be passed in from main.py
    w.show()
    sys.exit(app.exec_())