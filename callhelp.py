from centered_canvas import center_window_contents
import sys
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox, QMainWindow, QApplication, QAction, QFileDialog, QMessageBox
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl

#User import
from help import *

class Help(QDialog):
 # This is the subwindow signal sent to main to write edit in green for successful solve.

    def __init__(self): # Need to pass in the data in the form of a dictionary to be calculated.
        super().__init__()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        center_window_contents(self)

        self.ui.pushButtonClose.clicked.connect(self.close)

if __name__=="__main__":
    app = QApplication(sys.argv)
    w = Help()    
    w.show()
    sys.exit(app.exec_())