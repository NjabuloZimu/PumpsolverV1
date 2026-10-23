"""Reference guidance for independently selected entrance and exit losses."""

from PyQt5.QtWidgets import QDialog

from .centered_canvas import center_window_contents
from .generated.ui_boundary_info_dialog import Ui_BoundaryLossInfo


class BoundaryLossInfo(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_BoundaryLossInfo()
        self.ui.setupUi(self)
        self.ui.pushButtonClose.clicked.connect(self.close)
        center_window_contents(self)
