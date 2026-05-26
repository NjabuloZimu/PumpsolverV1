# main_file.py
import sys
from PyQt5.QtWidgets import QApplication
from callmain import MyForm

def main():
    # Create a QApplication instance
    app = QApplication(sys.argv)

    # Create an instance of the main window
    my_instance = MyForm()

    # Show the window
    my_instance.show()

    # Start the application event loop
    sys.exit(app.exec_())

def solve():
    return "Solve is returned"

def pyqt5_test_fails():
    return "not sure how to test pyqt5 code for unittests"

def square(n):
    return n * n

if __name__ == "__main__":
    main()