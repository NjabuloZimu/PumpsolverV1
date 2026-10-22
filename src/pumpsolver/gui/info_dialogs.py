"""Reference diagrams share one controller while retaining Designer forms."""

from PyQt5.QtWidgets import QDialog
from .centered_canvas import center_window_contents
from .generated.ui_info1 import Ui_Dialog as Ui_Info1
from .generated.ui_info2 import Ui_Dialog as Ui_Info2
from .generated.ui_info3 import Ui_Dialog as Ui_Info3


class _ReferenceDialog(QDialog):
    ui_class = None

    def __init__(self):
        super().__init__()
        self.ui = self.ui_class()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.ui.pushButtonClose.clicked.connect(self.close)


class Info1(_ReferenceDialog):
    ui_class = Ui_Info1


class Info2(_ReferenceDialog):
    ui_class = Ui_Info2


class Info3(_ReferenceDialog):
    ui_class = Ui_Info3
