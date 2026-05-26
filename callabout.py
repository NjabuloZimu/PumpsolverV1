import sys
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox, QMainWindow, QApplication, QAction, QFileDialog, QMessageBox
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl

#User import
from about import *

class About(QDialog):
 # This is the subwindow signal sent to main to write edit in green for successful solve.

    def __init__(self): # Need to pass in the data in the form of a dictionary to be calculated.
        super().__init__()
        self.ui = Ui_about()
        self.ui.setupUi(self)

        self.ui.labelLink.setOpenExternalLinks(True)
        urlLink="<a href=\"https://www.linkedin.com/in/njabulo-zimu-07366b192\">'https://www.linkedin.com/in/njabulo-zimu-07366b192.'</a>"
        self.ui.labelLink.setText(urlLink)
        self.ui.labelLink.linkActivated.connect(self.openLink)

        self.ui.pushButtonClose.clicked.connect(self.close)
        

    def openLink(self, link):
        QDesktopServices.openUrl(QUrl(link))

if __name__=="__main__":
    app = QApplication(sys.argv)
    w = About()    
    w.show()
    sys.exit(app.exec_())