from PyQt5 import QtCore, QtGui
from .centered_canvas import center_window_contents
import csv
import re
from math import isfinite
from contextlib import contextmanager
from pumpsolver.persistence.csv_io import ensure_csv_path, read_segments, write_segments, read_fittings, write_fittings, read_roughness, write_roughness
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox, QStyledItemDelegate, QLineEdit, QTableWidgetItem, QComboBox
from PyQt5.QtGui import QRegExpValidator, QPixmap
from PyQt5.QtCore import Qt, QRegExp, QEvent, QTimer
from .generated.ui_pipe_designer import Ui_LineLossesDesigner
from pumpsolver.calculations.pipe_losses import PipeLossCalculator, CalculationError
from pumpsolver.models import DesignerCommit, PipeDesign

class RegexDelegate(QStyledItemDelegate):

    def __init__(self, regex, parent=None):
        super().__init__(parent)
        self.regex = regex

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QRegExpValidator(QRegExp(self.regex), editor))
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.DisplayRole)
        editor.setText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

class LossesCal(QDialog):
    totalLosses = QtCore.pyqtSignal(float)
    designCommitted = QtCore.pyqtSignal(object)
    designerEnabled = QtCore.pyqtSignal(bool)
    densityChanged = QtCore.pyqtSignal(str)
    volumetricChanged = QtCore.pyqtSignal(str)
    diameterChanged = QtCore.pyqtSignal(str)

    def __init__(self, instanceName, designerStatus=True, *, side='inlet'):
        super().__init__()
        self.ui = Ui_LineLossesDesigner()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.ui.groupBox_7.setTitle('Overall Results (all segments)')
        self.setWindowTitle(instanceName)
        self.side = PipeLossCalculator._side(side)
        self.calculator = PipeLossCalculator(side=self.side)
        self._last_result = None
        self._calculation_signature = None
        self._calculation_timer = QTimer(self)
        self._calculation_timer.setSingleShot(True)
        self._calculation_timer.timeout.connect(self.calculate_answer)
        self.label_instructions()
        self.stored_segments = {}
        self.list_fittings_by_segment = []
        self.ui.checkBoxLossesCal.setChecked(designerStatus)
        self.ui.checkBoxLossesCal.clicked.connect(self.disableVarious)
        self.ui.pushButtonClose.clicked.connect(self.saveandclose)
        self.tableLineSegmentEnable()
        self.ui.tableWidgetPipeSegment.itemSelectionChanged.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.itemActivated.connect(self.handle_selection_change)
        self.ui.tableWidgetPipeSegment.cellChanged.connect(self.save_table_data_Segment)
        self.ui.pushButtonAddSegment.clicked.connect(lambda: self.addRow('TablePipeSegment'))
        self.ui.pushButtonDeleteSegment.clicked.connect(lambda: self.deleteRow('TablePipeSegment'))
        self.ui.pushButtonAddFitting.clicked.connect(lambda: self.addRow('TableFittings'))
        self.ui.pushButtonDeleteFitting.clicked.connect(lambda: self.deleteRow('TableFittings'))
        self.ui.tableWidgetFittings.itemSelectionChanged.connect(self.save_table_data_fittings)
        self.ui.tableWidgetFittings.itemActivated.connect(self.save_table_data_fittings)
        self.ui.tableWidgetFittings.cellChanged.connect(self.schedule_calculation)
        self.ui.tableWidgetFittings.cellClicked.connect(self.disableSegmentTable)
        self.ui.pushButtonInfo.clicked.connect(self.openInfo)
        self.ui.pushButtonInfo2.clicked.connect(self.openInfo2)
        self.ui.pushButtonInfo3.clicked.connect(self.openInfo3)
        self.ui.toolButtonHelp.clicked.connect(self.openHelp)
        self.ui.pushButtonImportSegment.clicked.connect(lambda: self.import_data('segment'))
        self.ui.pushButtonExportSegment.clicked.connect(lambda: self.export_data('segment'))
        self.ui.pushButtonImportFittings.clicked.connect(lambda: self.import_data('fittings'))
        self.ui.pushButtonExportFittings.clicked.connect(lambda: self.export_data('fittings'))
        self.ui.pushButtonExportLineRoughness.clicked.connect(lambda: self.export_data('roughness'))
        self.ui.pushButtonImportLineRoughness.clicked.connect(lambda: self.import_data('roughness'))
        self.storeViscosity = None
        self.ui.lineEditViscosity.editingFinished.connect(self.save_viscosity)
        self.lineRoughnessList = []
        self.ui.comboBoxRoughness.installEventFilter(self)
        self.ui.comboBoxRoughness.lineEdit().editingFinished.connect(self.save_LineRoughness)
        self.ui.comboBoxRoughness.currentIndexChanged.connect(self.save_LineRoughness)
        self.validateTableEntry()
        self.storeDensity = self.ui.lineEditDensity.text()
        self.ui.lineEditDensity.editingFinished.connect(self.save_density)
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        self.ui.lineEditFlowrate.editingFinished.connect(self.save_volumetric)
        self.previous_row = None
        self.regex = QtCore.QRegExp('^[0-9]*\\.?[0-9]*$')
        self.validator = QtGui.QRegExpValidator(self.regex)
        self.ui.lineEditViscosity.setValidator(self.validator)
        self.ui.lineEditDensity.setValidator(self.validator)
        self.ui.lineEditFlowrate.setValidator(self.validator)
        self.ui.comboBoxRoughness.lineEdit().setValidator(self.validator)
        self.ui.comboBoxTransitionEquation.currentIndexChanged.connect(self.updateImage)
        self.updateImage(self.ui.comboBoxTransitionEquation.currentIndex())

    def updateImage(self, index):
        image_paths = {0: ':/assets/moodyEq.png', 1: ':/assets/RJSPigott.png'}
        image_path = image_paths.get(index, '')
        if image_path:
            pixmap = QPixmap(image_path)
            self.ui.labelBoundaryEquation.setPixmap(pixmap)
            self.ui.labelBoundaryEquation.setScaledContents(True)
        self.schedule_calculation()

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
        self.list_fittings_by_segment = [item for item in self.list_fittings_by_segment if item.get('Line Segment') != segment]
        if table.rowCount():
            self.list_fittings_by_segment.append(entry)
        self.list_fittings_by_segment.sort(key=lambda item: item['Line Segment'])

    def _capture_segments(self):
        table = self.ui.tableWidgetPipeSegment
        self.stored_segments = {f'Line Segment {row + 1}, {table.horizontalHeaderItem(column).text()}': table.item(row, column).text() if table.item(row, column) else '' for row in range(table.rowCount()) for column in range(table.columnCount())}

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
        file_name, _ = QFileDialog.getSaveFileName(self, 'Export CSV', '', 'CSV Files (*.csv)')
        if not file_name:
            return
        try:
            self._capture_current_tables()
            writer, data = {'segment': (write_segments, self.stored_segments), 'fittings': (write_fittings, self.list_fittings_by_segment), 'roughness': (write_roughness, self.lineRoughnessList)}[identifier]
            writer(ensure_csv_path(file_name), data)
        except (OSError, ValueError, csv.Error, UnicodeError) as error:
            QMessageBox.critical(self, 'CSV Export Failed', str(error))

    def import_data(self, identifier):
        file_name, _ = QFileDialog.getOpenFileName(self, 'Import CSV', '', 'CSV Files (*.csv)')
        if not file_name:
            return
        try:
            reader = {'segment': read_segments, 'fittings': read_fittings, 'roughness': read_roughness}[identifier]
            imported = reader(file_name)
            if identifier != 'segment':
                valid_segments = set(range(1, self.ui.tableWidgetPipeSegment.rowCount() + 1))
                missing = {item['Line Segment'] for item in imported} - valid_segments
                if missing:
                    raise ValueError(f'Import the corresponding pipe segments first. Unknown Line Segment: {sorted(missing)}')
        except (OSError, ValueError, csv.Error, UnicodeError) as error:
            QMessageBox.critical(self, 'CSV Import Failed', str(error))
            return
        if identifier == 'segment':
            self.stored_segments = imported
            valid_segments = {int(key.split(', ')[0].split()[-1]) for key in imported}
            self.list_fittings_by_segment = [item for item in self.list_fittings_by_segment if item.get('Line Segment') in valid_segments]
            self.lineRoughnessList = [item for item in self.lineRoughnessList if item.get('Line Segment') in valid_segments]
            self.restore_table_data_segments()
            self.save_diameter()
        elif identifier == 'fittings':
            self.list_fittings_by_segment = imported
            self.restore_table_data_fittings()
        else:
            self.lineRoughnessList = imported
            self.restore_lineRoughness()
        self.schedule_calculation()

    def label_instructions(self):
        if self.side == 'inlet':
            self.ui.labelinstructions.setText('Specify pipe lengths where the diameter changes. The first segment is the suction nossle that starts at the storage tank. Subsequent pipes connect to the pipe that preceeds it the last segment is the suction nossle that ends at the pump inlet (suction side).')
        elif self.side == 'outlet':
            self.ui.labelinstructions.setText('Specify pipe lengths where the diameter changes. The first segment connects to the pump outlet. Subsequent pipes connect to the pipe that preceeds it,                                              the last segment is the discharge nossle that ends at the outlet storage tank.')

    def openHelp(self):
        from .help_dialog import Help
        self.sub_window = Help()
        self.sub_window.show()

    def openInfo(self):
        from .info_dialogs import Info1
        self.sub_window = Info1()
        self.sub_window.show()

    def openInfo2(self):
        from .info_dialogs import Info2
        self.sub_window = Info2()
        self.sub_window.show()

    def openInfo3(self):
        from .info_dialogs import Info3
        self.sub_window = Info3()
        self.sub_window.show()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if isinstance(obj, QComboBox):
                self.table_segment_buttons_disable()
        elif event.type() == QEvent.FocusOut:
            if isinstance(obj, QComboBox):
                self.table_segment_buttons_enable()
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

    def previously_stored_data(self, stored_segments, list_fittings_by_segment, lineRoughnessList):
        self.stored_segments = stored_segments
        self.list_fittings_by_segment = list_fittings_by_segment
        self.lineRoughnessList = lineRoughnessList
        self.restore_table_data_segments()

    def restore_table_data_segments(self):
        table = self.ui.tableWidgetPipeSegment
        selected = table.selectedIndexes()
        selected_row = selected[0].row() if selected else None
        cells = []
        columns = {table.horizontalHeaderItem(index).text(): index for index in range(table.columnCount())}
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
        self.densityChanged.emit(self.ui.lineEditDensity.text())
        self.save_table_data_Segment()
        self.schedule_calculation()

    def save_volumetric(self):
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        self.volumetricChanged.emit(self.ui.lineEditFlowrate.text())
        self.save_table_data_Segment()
        self.schedule_calculation()

    def save_diameter(self):
        if self.side == 'inlet':
            try:
                last_row = self.ui.tableWidgetPipeSegment.rowCount() - 1
                self.diameter = self.ui.tableWidgetPipeSegment.item(last_row, 1).text()
            except (ValueError, AttributeError):
                pass
            else:
                self.diameterChanged.emit(self.diameter)
        elif self.side == 'outlet':
            try:
                self.diameter = self.ui.tableWidgetPipeSegment.item(0, 1).text()
            except (ValueError, AttributeError):
                pass
            else:
                self.diameterChanged.emit(self.diameter)

    def schedule_calculation(self, *args):
        self._calculation_timer.start(0)

    def flush_calculation(self):
        self._calculation_timer.stop()
        return self.calculate_answer()

    def calculate_answer(self, event=None):
        self._capture_segments()
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        if selected:
            self._capture_fittings(selected[0].row() + 1)
        self.storeViscosity = self.ui.lineEditViscosity.text()
        self.storeDensity = self.ui.lineEditDensity.text()
        self.storeVolumetric = self.ui.lineEditFlowrate.text()
        signature = (tuple(sorted(self.stored_segments.items())), tuple((tuple(sorted(item.items())) for item in self.list_fittings_by_segment)), tuple((tuple(sorted(item.items())) for item in self.lineRoughnessList)), self.storeViscosity, self.storeDensity, self.storeVolumetric, self.ui.comboBoxTransitionEquation.currentText(), self.side, self.ui.checkBoxLossesCal.isChecked())
        if signature == self._calculation_signature and self._last_result is not None:
            self._render_selected_result()
            return self._last_result
        self._calculation_signature = signature
        if not self.ui.checkBoxLossesCal.isChecked():
            self._last_result = None
            self.ui.pushButtonClose.setEnabled(True)
            return None
        try:
            result = self.calculator.calculate(self.stored_segments, self.list_fittings_by_segment, self.lineRoughnessList, self.storeViscosity, self.storeDensity, self.storeVolumetric, side=self.side, transition_equation=self.ui.comboBoxTransitionEquation.currentText())
        except CalculationError as error:
            self._last_result = None
            self._render_selected_result()
            self.ui.labelOverallSummary.clear()
            self.ui.pushButtonClose.setEnabled(False)
            self.ui.pushButtonClose.setToolTip(str(error))
            return None
        self._last_result = result
        self.total_losses_hf = result.total_loss
        self.ui.pushButtonClose.setEnabled(True)
        self.ui.pushButtonClose.setToolTip('')
        self._render_selected_result()
        boundary = 'tank entrance' if result.side == 'inlet' else 'tank exit'
        self.ui.labelOverallSummary.setText(
            f'All segments: major {result.major_loss:#.6g} m + minor {result.minor_loss:#.6g} m '
            f'= total {result.total_loss:#.6g} m.\n'
            f'Minor: fittings {result.fittings_loss:#.6g} m; diameter changes {result.transition_loss:#.6g} m; '
            f'{boundary} {result.boundary_loss:#.6g} m (assumed).\n'
            f'Length {result.total_length:#.6g} m; {result.contractions} contractions; {result.expansions} expansions.')
        self.ui.labelOverallSummary.setToolTip(
            'Close saves the total for all segments to Properties. Minor losses include fittings, '
            'diameter changes and the entrance from an infinitely large supply tank (inlet) '
            'or exit into an infinitely large receiving tank (outlet).')
        self.totalLosses.emit(result.total_loss)
        return result

    def _render_selected_result(self):
        widgets = (self.ui.lineEditDarcys, self.ui.lineEditRelativeRough, self.ui.lineEditReynolds, self.ui.lineEditFlowType, self.ui.lineEditVelocity, self.ui.lineEditMinorLosses, self.ui.lineEditMajorLosses)
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        number = selected[0].row() + 1 if selected else None
        result = next((item for item in self._last_result.segments if item.line_segment == number), None) if self._last_result else None
        if result is None:
            self.ui.groupBox_6.setTitle('Selected Segment Results')
            self.ui.lineEditMinorLosses.setToolTip('')
            for widget in widgets:
                widget.clear()
            return
        self.ui.groupBox_6.setTitle(f'Segment {result.line_segment} Results')
        self.ui.lineEditMinorLosses.setToolTip(
            f'Fittings: {result.fittings_loss:#.6g} m\n'
            f'Diameter change: {result.transition_loss:#.6g} m\n'
            f'Tank entrance/exit: {result.boundary_loss:#.6g} m\n'
            f'Segment total (major + minor): {result.total_loss:#.6g} m')
        values = (result.friction_factor, result.relative_roughness, result.reynolds, result.flow_type, result.velocity, result.minor_loss, result.major_loss)
        for widget, value in zip(widgets, values):
            widget.setText(value if isinstance(value, str) else format(value, '#.6g'))

    def closeEvent(self, event):
        self._calculation_timer.stop()
        super().closeEvent(event)

    def save_LineRoughness(self):
        sender = self.sender()
        if sender:
            pass
        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()
        if not selected_indexes:
            return
        selected_row = selected_indexes[0].row() + 1
        for dictionary in self.lineRoughnessList:
            if dictionary['Line Segment'] == selected_row:
                dictionary['Segment Roughness'] = self.ui.comboBoxRoughness.currentText()
        data = {'Line Segment': selected_row, 'Segment Roughness': self.ui.comboBoxRoughness.currentText()}
        data_no_selection = {'Line Segment': selected_row, 'Segment Roughness': ''}
        try:
            filtered_data = [d for d in self.lineRoughnessList if d.get('Line Segment') != selected_row]
            self.lineRoughnessList = filtered_data
        except IndexError:
            self.insert_roughness(selected_row, data, data_no_selection)
        else:
            self.insert_roughness(selected_row, data, data_no_selection)
        self.save_table_data_Segment()
        self.schedule_calculation()

    def insert_roughness(self, selected_row, data, data_no_selection):
        if self.ui.comboBoxRoughness.currentText() == 'Specify Pipe Roughness':
            self.lineRoughnessList.insert(selected_row, data_no_selection)
        else:
            self.lineRoughnessList.insert(selected_row, data)

    def restore_lineRoughness(self):
        combo = self.ui.comboBoxRoughness
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        segment = selected[0].row() + 1 if selected else None
        value = next((item['Segment Roughness'] for item in self.lineRoughnessList if item.get('Line Segment') == segment), '')
        with self._blocked_widgets(combo, combo.lineEdit()):
            if value:
                combo.setCurrentText(str(value))
            else:
                combo.setCurrentIndex(0)

    def save_viscosity(self):
        self.storeViscosity = self.ui.lineEditViscosity.text()
        self.save_table_data_Segment()
        self.schedule_calculation()

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
        regex_pattern = '^-?[0-9]*\\.?[0-9]*$'
        regex_delegate = RegexDelegate(regex_pattern, self.ui.tableWidgetPipeSegment)
        self.ui.tableWidgetPipeSegment.setItemDelegate(regex_delegate)
        self.ui.tableWidgetFittings.setItemDelegateForColumn(1, regex_delegate)

    def disableVarious(self):
        self.designerEnabled.emit(self.ui.checkBoxLossesCal.isChecked())
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
        selected_indexes = self.ui.tableWidgetPipeSegment.selectedIndexes()
        if self.ui.checkBoxLossesCal.isChecked() == True and selected_indexes:
            self.ui.tableWidgetFittings.setDisabled(False)
            self.ui.comboBoxRoughness.setDisabled(False)
            self.ui.lineEditViscosity.setDisabled(False)
            self.ui.lineEditFlowrate.setDisabled(False)
        self.schedule_calculation()

    def saveandclose(self):
        if self.save():
            self.close()

    def askclose(self):
        if self.ui.pushButtonApply.isEnabled():
            ret = QMessageBox.warning(self, 'Unsaved Changes', 'Values have been modified.\nDo you want to save your changes?', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if ret == QMessageBox.Save:
                self.saveandclose()
            elif ret == QMessageBox.Discard:
                self.close()
            elif ret == QMessageBox.Cancel:
                self.show
        else:
            self.close()

    def _capture_commit(self):
        self._capture_current_tables()
        result = self.flush_calculation()
        for name, value in (('Viscosity', self.storeViscosity),
                            ('Density', self.storeDensity),
                            ('Flow rate', self.storeVolumetric)):
            if not value.strip():
                continue
            try:
                valid = isfinite(float(value))
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f'{name} must be a complete finite number or left empty.')
        design = PipeDesign.from_legacy({
            'segments': self.stored_segments,
            'fittings': self.list_fittings_by_segment,
            'roughness': self.lineRoughnessList,
            'viscosity': self.storeViscosity,
            'transition_equation': self.ui.comboBoxTransitionEquation.currentText(),
        })
        enabled = self.ui.checkBoxLossesCal.isChecked()
        diameter = None
        if enabled and design.segments:
            boundary = design.segments[-1] if self.side == 'inlet' else design.segments[0]
            diameter = design.to_legacy()['segments'][
                f'Line Segment {boundary.number}, Segment Diameter (cm)']
        return DesignerCommit(
            side=self.side, design=design, density=self.storeDensity,
            flow=self.storeVolumetric, diameter=diameter,
            total_losses=result.total_loss if result is not None else None,
            enabled=enabled,
        )

    def save(self):
        try:
            update = self._capture_commit()
        except ValueError as error:
            QMessageBox.critical(
                self, 'Invalid Input',
                f'Enter complete numeric values or leave unfinished fields empty.\n{error}',
            )
            return False
        self.designCommitted.emit(update)
        return True

    def tableLineSegmentEnable(self):
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
        self.schedule_calculation()

    def _refresh_selection(self):
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        active = bool(selected) and self.ui.checkBoxLossesCal.isChecked()
        for widget in (self.ui.tableWidgetFittings, self.ui.comboBoxRoughness, self.ui.lineEditViscosity, self.ui.pushButtonAddFitting, self.ui.pushButtonDeleteFitting, self.ui.lineEditDensity, self.ui.lineEditFlowrate):
            widget.setEnabled(active)
        self.previous_row = selected[0].row() + 1 if selected else None
        self.restore_table_data_fittings()
        self.restore_lineRoughness()

    def save_table_data_Segment(self):
        sender = self.sender()
        self.stored_segments = {}
        for row in range(self.ui.tableWidgetPipeSegment.rowCount()):
            try:
                row_header = self.ui.tableWidgetPipeSegment.verticalHeaderItem(row).text()
            except AttributeError:
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
            self.stored_segments = {}
        self.save_diameter()
        self.schedule_calculation()

    def save_table_data_fittings(self):
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        if not selected:
            return
        self._capture_fittings(selected[0].row() + 1)
        self.enableSegmentTable()
        self.schedule_calculation()

    def restore_table_data_fittings(self):
        table = self.ui.tableWidgetFittings
        selected = self.ui.tableWidgetPipeSegment.selectedIndexes()
        segment = selected[0].row() + 1 if selected else None
        entry = next((item for item in self.list_fittings_by_segment if item.get('Line Segment') == segment), {})
        cells = []
        for key, value in entry.items():
            if key == 'Line Segment':
                continue
            match = re.fullmatch('Fitting (\\d+), (Fitting Type|Loss Factor)', key)
            if match:
                cells.append((int(match.group(1)) - 1, 0 if match.group(2) == 'Fitting Type' else 1, value))
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
        self.schedule_calculation()

    def deleteRow(self, identifier):
        self._capture_current_tables()
        table = self.ui.tableWidgetPipeSegment if identifier == 'TablePipeSegment' else self.ui.tableWidgetFittings
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
            self.list_fittings_by_segment = [entry for entry in self.list_fittings_by_segment if entry['Line Segment'] != segment]
            self.lineRoughnessList = [entry for entry in self.lineRoughnessList if entry['Line Segment'] != segment]
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
        self.schedule_calculation()

    def renameVerticalHeader(self, identifier, restore=False):
        if identifier == 'TablePipeSegment':
            rows = self.ui.tableWidgetPipeSegment.rowCount()
            for row in range(rows):
                item_text = f'Line Segment {row + 1}'
                item = QTableWidgetItem(item_text)
                self.ui.tableWidgetPipeSegment.setVerticalHeaderItem(row, item)
                if not restore:
                    self.save_table_data_Segment()
        if identifier == 'TableFittings':
            rows = self.ui.tableWidgetFittings.rowCount()
            for row in range(rows):
                item_text = f'Fitting {row + 1}'
                item = QTableWidgetItem(item_text)
                self.ui.tableWidgetFittings.setVerticalHeaderItem(row, item)
                if not restore:
                    self.save_table_data_fittings()
