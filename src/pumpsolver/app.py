"""Single application startup function for source, installed, and frozen runs."""

import argparse
import json
import logging
from pathlib import Path
import sys

from .version import __version__


def _smoke_test(window):
    """Exercise actual UI, resources, calculations, and CSV in a frozen build."""
    from tempfile import TemporaryDirectory
    from math import isclose
    from PyQt5.QtCore import QFile
    from PyQt5.QtWidgets import QApplication, QTableWidget
    from .calculations.pipe_losses import PipeLossCalculator
    from .calculations.pump import solve_pump
    from .gui.pipe_designer import LossesCal
    from .gui.properties_dialog import Properties
    from .gui.motor_dialog import MotorProp
    from .gui.results_dialog import SolvePage
    from .gui.about_dialog import About
    from .gui.help_dialog import Help
    from .gui.info_dialogs import Info1, Info2, Info3
    from .gui.boundary_info_dialog import BoundaryLossInfo
    from .persistence.csv_io import write_project, read_project

    aliases = [':/assets/moodyEq.png', ':/assets/RJSPigott.png',
               ':/assets/segments.png', ':/assets/contraction.png',
               ':/WindowIcons/pumpSoftware.svg']
    for alias in aliases:
        if not QFile.exists(alias):
            raise RuntimeError(f'Missing bundled resource: {alias}')
    data = window.project_state()
    data['parameters'].update(in_dia='10', in_head='2', in_loss='0.5', in_flow='36',
        in_dens='1000', in_press='101325', out_dia='10', out_head='20', out_loss='0.7',
        out_flow='36', out_dens='1000', out_press='101325', effi='80', power='Unspecified',
        safety='1', gravity='9.81')
    solution = solve_pump(data['parameters'])
    if abs(solution.solved_value - 25.25) > 1e-7:
        raise RuntimeError('Pump reference result did not match 25.25 m.')
    segments = {'Line Segment 1, Segment Length (m)': '10',
                'Line Segment 1, Segment Diameter (cm)': '10'}
    roughness = [{'Line Segment': 1, 'Segment Roughness': 'Smooth Pipe'}]
    pipe_result = PipeLossCalculator().calculate(segments, [], roughness, 1, 1000, 36)
    data['inlet'].update(segments=segments, roughness=roughness, viscosity='1')
    window.restore_project(data)
    dialogs = [LossesCal('Pipe Designer', side='inlet'), Properties('Pipe Properties', False, side='inlet'),
               MotorProp(), SolvePage(data['parameters']), About(), Help(), Info1(), Info2(), Info3(),
               BoundaryLossInfo()]
    try:
        if len(dialogs[0].findChildren(QTableWidget)) != 2:
            raise RuntimeError('The pipe designer contains duplicate tables.')
        designer = dialogs[0]
        designer.ui.lineEditDensity.setText('1000')
        designer.ui.lineEditFlowrate.setText('36')
        designer.ui.lineEditViscosity.setText('1')
        designer.previously_stored_data(segments, [], roughness)
        designer.ui.tableWidgetPipeSegment.selectRow(0)
        designer.show()
        QApplication.instance().processEvents()
        for table in (designer.ui.tableWidgetPipeSegment, designer.ui.tableWidgetFittings):
            if not table.horizontalHeader().isVisible():
                raise RuntimeError('The designer table headings are hidden.')
        designer.flush_calculation()
        displayed_loss = (float(designer.ui.lineEditMajorLosses.text())
                          + float(designer.ui.lineEditMinorLosses.text()))
        if not isclose(displayed_loss, pipe_result.total_loss, rel_tol=1e-5):
            raise RuntimeError('The displayed major and minor losses do not reconcile.')
        designer.ui.lineEditEntranceCoefficient.setText('0.2')
        designer.ui.checkBoxExitLoss.setChecked(True)
        designer.ui.lineEditExitCoefficient.setText('0.75')
        pipe_result = designer.flush_calculation()
        velocity_head = pipe_result.segments[0].velocity ** 2 / (2 * 9.80665)
        if not (isclose(pipe_result.entrance_loss, 0.2 * velocity_head)
                and isclose(pipe_result.exit_loss, 0.75 * velocity_head)):
            raise RuntimeError('Edited entrance and exit settings did not reach the calculation.')
        designer.designCommitted.connect(dialogs[1]._accept_design)
        designer.ui.pushButtonClose.click()
        if not isclose(float(dialogs[1].ui.lineEditLosses.text()), pipe_result.total_loss, rel_tol=1e-5):
            raise RuntimeError('The complete designer loss was not copied to Properties.')
        dialogs[1].dataCommitted.connect(window._accept_properties)
        dialogs[1].ui.pushButtonApply.click()
        if not (window.state.inlet.exit_enabled
                and window.state.inlet.entrance_coefficient == 0.2
                and window.state.inlet.exit_coefficient == 0.75):
            raise RuntimeError('Boundary settings were not committed to the project.')
        with TemporaryDirectory(prefix='pumpsolver-smoke-') as folder:
            path = Path(folder)/'project.csv'
            write_project(path, window.project_state())
            if read_project(path) != window.project_state():
                raise RuntimeError('Frozen CSV round trip failed.')
        return {'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False)),
                'resources': True, 'csv_roundtrip': True, 'calculations': True,
                'designer_tables': 2, 'pump_head_m': solution.solved_value,
                'designer_headers': True, 'loss_reconciliation': True, 'boundary_settings': True,
                'pipe_loss_m': pipe_result.total_loss, 'dialogs': len(dialogs)}
    finally:
        for dialog in dialogs:
            dialog.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='PumpSolver desktop application')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--smoke-test', type=Path, metavar='REPORT_JSON', help=argparse.SUPPRESS)
    parser.add_argument('--screenshot', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--quit-after', type=int, metavar='MILLISECONDS', help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from .gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('PumpSolver')
    app.setOrganizationName('PumpSolver')
    app.setApplicationVersion(__version__)
    logging.basicConfig(level=logging.WARNING)
    window = MainWindow()
    window.show()
    if options.smoke_test:
        try:
            app.processEvents()
            report = _smoke_test(window)
            if options.screenshot:
                options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                window.grab().save(str(options.screenshot))
            options.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            options.smoke_test.write_text(json.dumps({'success': True, **report}, indent=2), encoding='utf-8')
            return 0
        except Exception as error:
            logging.exception('Application smoke test failed')
            options.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            options.smoke_test.write_text(json.dumps({'success': False, 'error': str(error)}), encoding='utf-8')
            return 1
        finally:
            app.closeAllWindows()
            window.windows.clear()
    if options.quit_after is not None:
        QTimer.singleShot(options.quit_after, app.quit)
    return app.exec_()
