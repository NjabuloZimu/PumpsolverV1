"""Pipe-designer help window."""

from PyQt5.QtWidgets import QDialog
from .generated.ui_help_dialog import Ui_Dialog
from .centered_canvas import center_window_contents


class Help(QDialog):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.ui.pushButtonClose.clicked.connect(self.close)
