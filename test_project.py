from project import solve, pyqt5_test_fails, square

def main(): 
    test_solve()

def test_solve():
    assert solve()  == "Solve is returned"

def test_pyqt5_test_fails():

    assert pyqt5_test_fails()== "not sure how to test pyqt5 code for unittests"

def test_square():
    assert square(2) == 4
    assert square(3) == 9

if __name__ == "__main__":
    main()