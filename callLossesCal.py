from centered_canvas import center_window_contents
import sys
import csv
import inspect
import re
from contextlib import contextmanager
from csv_io import (ensure_csv_path, read_segments, write_segments, read_fittings,
                    write_fittings, read_roughness, write_roughness)
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
        center_window_contents(self)
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

    @contextmanager
    def _blocked_widgets(self, *widgets):
        previous = [widget.blockSignals(True) for widget in widgets]
        try:
            yield
        finally:
            for widget, blocked in zip(widgets, previous):
                widget.blockSignals(blocked)

    def _capture_fittings(self, segment):
        """Read the visible fitting table without triggering calculations."""
        if segment is None:
            return
        table = self.ui.tableWidgetFittings
        entry = {'Line Segment': segment}
        for row in range(table.rowCount()):
            for column, name in enumerate(('Fitting Type', 'Loss Factor')):
                item = table.item(row, column)
                entry[f'Fitting {row + 1}, {name}'] = item.text() if item else ''
        self.list_fittings_by_segment = [
            item for item in self.list_fittings_by_segment
            if item.get('Line Segment') != segment
        ]
        if table.rowCount():
            self.list_fittings_by_segment.append(entry)
        self.list_fittings_by_segment.sort(key=lambda item: item['Line Segment'])

    def _capture_segments(self):
        table = self.ui.tableWidgetPipeSegment
        self.stored_segments = {
            f'Line Segment {row + 1}, {table.horizontalHeaderItem(column).text()}':
            table.item(row, column).text() if table.item(row, column) else ''
            for row in range(table.rowCount())
            for column in range(table.columnCount())
        }

    def _capture_current_tables(self):
        focused = self.focusWidget()
        if focused:
            focused.clearFocus()
        self._capture_segments()
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        if selected:
            self._capture_fittings(selected[0].row() + 1)
        self.storeViscosity = self.ui.lineEditViscosity.text()

    def export_data(self, identifier):
        file_name, _ = QFileDialog.getSaveFileName(
            self, 'Export CSV', '', 'CSV Files (*.csv)'
        )
        if not file_name:
            return
        try:
            self._capture_current_tables()
            writer, data = {
                'segment': (write_segments, self.stored_segments),
                'fittings': (write_fittings, self.list_fittings_by_segment),
                'roughness': (write_roughness, self.lineRoughnessList),
            }[identifier]
            writer(ensure_csv_path(file_name), data)
        except (OSError, ValueError, csv.Error, UnicodeError) as error:
            QMessageBox.critical(self, 'CSV Export Failed', str(error))

    def import_data(self, identifier):
        file_name, _ = QFileDialog.getOpenFileName(
            self, 'Import CSV', '', 'CSV Files (*.csv)'
        )
        if not file_name:
            return
        try:
            reader = {
                'segment': read_segments,
                'fittings': read_fittings,
                'roughness': read_roughness,
            }[identifier]
            imported = reader(file_name)
            # Complete validation before replacing any existing designer data.
            if identifier != 'segment':
                valid_segments = set(range(1, self.ui.tableWidgetPipeSegment.rowCount() + 1))
                missing = {item['Line Segment'] for item in imported} - valid_segments
                if missing:
                    raise ValueError('Import the corresponding pipe segments first. '
                                     f'Unknown Line Segment: {sorted(missing)}')
        except (OSError, ValueError, csv.Error, UnicodeError) as error:
            QMessageBox.critical(self, 'CSV Import Failed', str(error))
            return

        if identifier == 'segment':
            self.stored_segments = imported
            valid_segments = {int(key.split(', ')[0].split()[-1]) for key in imported}
            self.list_fittings_by_segment = [item for item in self.list_fittings_by_segment
                                            if item.get('Line Segment') in valid_segments]
            self.lineRoughnessList = [item for item in self.lineRoughnessList
                                      if item.get('Line Segment') in valid_segments]
            self.restore_table_data_segments()
            self.save_diameter()
        elif identifier == 'fittings':
            self.list_fittings_by_segment = imported
            self.restore_table_data_fittings()
        else:
            self.lineRoughnessList = imported
            self.restore_lineRoughness()
        self.calculate_answer()

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
        table = self.ui.tableWidgetPipeSegment
        selected = table.selectedIndexes()
        selected_row = selected[0].row() if selected else None
        cells = []
        columns = {table.horizontalHeaderItem(index).text(): index
                   for index in range(table.columnCount())}
        for key, value in self.stored_segments.items():
            row_header, column_name = key.split(', ', 1)
            cells.append((int(row_header.split()[-1]) - 1, columns[column_name], value))
        row_count = max((row for row, _, _ in cells), default=-1) + 1
        with self._blocked_widgets(table):
            table.clearSelection()
            table.setRowCount(0)
            table.setRowCount(row_count)
            for row, column, value in cells:
                table.setItem(row, column, QTableWidgetItem(str(value)))
            self.renameVerticalHeader('TablePipeSegment', True)
            if selected_row is not None and row_count:
                table.selectRow(min(selected_row, row_count - 1))
        self.previous_row = None
        self._refresh_selection()

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

        if not selected_indexes:
            return
        selected_row = selected_indexes[0].row() + 1

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
        combo = self.ui.comboBoxRoughness
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        segment = selected[0].row() + 1 if selected else None
        value = next((item['Segment Roughness'] for item in self.lineRoughnessList
                      if item.get('Line Segment') == segment), '')
        with self._blocked_widgets(combo, combo.lineEdit()):
            if value:
                combo.setCurrentText(str(value))
            else:
                combo.setCurrentIndex(0)

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
        self._capture_current_tables()
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
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        current = selected[0].row() + 1 if selected else None
        previous = getattr(self, 'previous_row', None)
        if previous is not None and previous != current:
            self._capture_fittings(previous)
        self._refresh_selection()
        self.calculate_answer()

    def _refresh_selection(self):
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        active = bool(selected) and self.ui.checkBoxLossesCal.isChecked()
        for widget in (self.ui.tableWidgetFittings, self.ui.comboBoxRoughness,
                       self.ui.lineEditViscosity, self.ui.pushButtonAddFitting,
                       self.ui.pushButtonDeleteFitting, self.ui.lineEditDensity,
                       self.ui.lineEditFlowrate):
            widget.setEnabled(active)
        self.previous_row = selected[0].row() + 1 if selected else None
        self.restore_table_data_fittings()
        self.restore_lineRoughness()

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
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        if not selected:
            return
        self._capture_fittings(selected[0].row() + 1)
        self.enableSegmentTable()
        self.calculate_answer()

    def restore_table_data_fittings(self):
        table = self.ui.tableWidgetFittings
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        segment = selected[0].row() + 1 if selected else None
        entry = next((item for item in self.list_fittings_by_segment
                      if item.get('Line Segment') == segment), {})
        cells = []
        for key, value in entry.items():
            if key == 'Line Segment':
                continue
            match = re.fullmatch(r'Fitting (\d+), (Fitting Type|Loss Factor)', key)
            if match:
                cells.append((int(match.group(1)) - 1,
                              0 if match.group(2) == 'Fitting Type' else 1, value))
        with self._blocked_widgets(table):
            table.clearSelection()
            table.setRowCount(0)
            table.setRowCount(max((row for row, _, _ in cells), default=-1) + 1)
            for row, column, value in cells:
                table.setItem(row, column, QTableWidgetItem(str(value)))
            self.renameVerticalHeader('TableFittings', True)

    def addRow(self, identifier):
        self._capture_current_tables()
        if identifier == 'TablePipeSegment':
            table = self.ui.tableWidgetPipeSegment
            row = table.currentRow() if table.selectedIndexes() else table.rowCount()
            segment = row + 1
            with self._blocked_widgets(table):
                table.insertRow(row)
                for entry in self.lineRoughnessList + self.list_fittings_by_segment:
                    if entry['Line Segment'] >= segment:
                        entry['Line Segment'] += 1
                self.lineRoughnessList.append({'Line Segment': segment, 'Segment Roughness': ''})
                self.lineRoughnessList.sort(key=lambda entry: entry['Line Segment'])
                self.renameVerticalHeader(identifier, True)
                table.selectRow(row)
            self._capture_segments()
            self.previous_row = None
            self._refresh_selection()
        else:
            table = self.ui.tableWidgetFittings
            row = table.currentRow() if table.selectedIndexes() else table.rowCount()
            with self._blocked_widgets(table):
                table.insertRow(row)
                self.renameVerticalHeader(identifier, True)
                table.selectRow(row)
            selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
            if selected:
                self._capture_fittings(selected[0].row() + 1)
        self.ui.pushButtonClose.setEnabled(False)
        self.save_diameter()
        self.calculate_answer()

    def deleteRow(self, identifier):
        self._capture_current_tables()
        table = (self.ui.tableWidgetPipeSegment if identifier == 'TablePipeSegment'
                 else self.ui.tableWidgetFittings)
        if not table.rowCount():
            return
        row = table.currentRow() if table.selectedIndexes() else table.rowCount() - 1
        with self._blocked_widgets(table):
            table.removeRow(row)
            self.renameVerticalHeader(identifier, True)
            if table.rowCount():
                table.selectRow(min(row, table.rowCount() - 1))
        if identifier == 'TablePipeSegment':
            segment = row + 1
            self.list_fittings_by_segment = [entry for entry in self.list_fittings_by_segment
                                            if entry['Line Segment'] != segment]
            self.lineRoughnessList = [entry for entry in self.lineRoughnessList
                                      if entry['Line Segment'] != segment]
            for entry in self.list_fittings_by_segment + self.lineRoughnessList:
                if entry['Line Segment'] > segment:
                    entry['Line Segment'] -= 1
            self._capture_segments()
            self.previous_row = None
            self._refresh_selection()
        else:
            selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
            if selected:
                self._capture_fittings(selected[0].row() + 1)
        self.save_diameter()
        self.calculate_answer()

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