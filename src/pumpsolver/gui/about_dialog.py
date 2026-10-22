"""About dialog behaviour is separate from generated design code."""

from PyQt5.QtWidgets import QDialog
from .generated.ui_about_dialog import Ui_about
from .centered_canvas import center_window_contents
from pumpsolver.version import __version__


class About(QDialog):
    def __init__(self):
        super().__init__()
        self.ui = Ui_about()
        self.ui.setupUi(self)
        self.ui.label.setText(f'Process Pump Calculator Version {__version__}')
        self.ui.labelLink.setOpenExternalLinks(True)
        self.ui.labelLink.setText('<a href="https://www.linkedin.com/in/njabulo-zimu-07366b192">Njabulo Zimu</a>')
        self.ui.pushButtonClose.clicked.connect(self.close)
        center_window_contents(self)
