# PROCESS PUMP and PIPE LOSSES SOLVER
#### Video Demo:  https://youtu.be/MTGeXIs2tOM
#### Description: Automates Process Pump Calculations and Friction Loss Calculations in piping

# PumpSolver v1

PumpSolver is a PyQt5 desktop application for pump-related calculations and analysis.

## How to Run

1. Install Python 3.
2. Download or clone this repository.
3. Install the required packages.
4. Run the application using:

```bash
python callmain.py

#### **About**:
This project aims to simplify the life of a process engineer / chemical engineer by creating a desktop application that automatically executes calculations related to process pump applications. This desktop application aims to improve the accuracy and speed of the calculations as well as to reduce human error. To run this program run callmain.py i.e. python callmain.py

#### **Background**:
Process engineers and chemical engineers can control the flow of materials through a plant at a desired rate to a desired destination through piping. To transport the materials through the pipes pumps are used, to ensure that the pumps can meet the demands of the plant, the friction in the pipes and in the pumps must be accounted for. The friction in the pumps come in the form of mechanical losses due to minor and major losses. Minor Losses are friction losses caused by changes in flow magnitude, flow direction, change in diameter and pipe fittings. Major losses are friction losses within pipe with constant diameter (from shear stress on pipe wall which creates resistance to flow). The Friction factor (Fanning or Darcy's) i.e. head losses (hL) or correction for fluid skin friction (hfs) is used to estimate these losses.
 the motor connecting to a shaft which then connects to the impeller which then does work on the fluid. The mechanical work done on the fluid is thus less than that supplied by the motor, this is called pump motor efficiency and comes in the form of a percentage. Pipes usually consist of bends and fittings such as valves to control the flowrate, in addition, the pipes are not 100% smooth on the inside, all these factors increase the friction within the pipe which must be overcome by the pump to keep the fluid moving. These friction losses are accounted for in the ‘head’ form of the Engineering Bernoulli equation. The engineer can decide to calculate minor and major losses in the pipe using either the theory of equivalent lengths or using the more modern Darcey’s friction factor method, the latter of which the "Pipe Designer" Software allows you to do, the dynamic head losses are only required in meters if inputted manually otherwise the designer will automatically calculate the losses based on the information provided, such as the length, diameter and roughness of the pipe segment . The distance below the pipe centerline to and from where you are pumping can also accounted for in meters.

#### **The Design**:
The calculation is done almost instantly which would save the engineer time, it is always accurate to a total of 9 significant figures. To accomplish the task of coding the desktop application I have chosen to use python as the language as it offers advanced engineering and scientific modules and is relatively easy to implement. The scientific modules I have needed to complete this appliction are nympy and SciPy. A previous submission of the project in another cs50 course (Introduction to Computer Science) used tkinter as the GUI. In this upgraded version of the Process Pump Solver the graphical user interface (GUI) framework to pyqt5. This decision was made because the software comes with a PyQT5 Designer Software that speeds up the development of the GUI, the design of the code is also relatively easier than tkinter (e.g. slots and signals). PyQT5 is python 3 only. The application user interface consists of a graphic of a pump with inlet and outlet pipes which the user clicks on to fill in the required information, after which, the application will then determine and calculate the missing variable and print out the answer to the user. The pipe designer allows the user to choose to solve the friction losses by specifying the inlet or outlet pipe segments of differing diameters and lengths, fittings (valves, flowmeters, pressure sensors etc.), as well as design (45°/90° bends, Tee used as a bend etc. )

#### **Project Contents and Purpose**:
##### **Files Present**
In the main folder there are 15 png images and 24 python files, all of which are necessary to run the software successfully. The user should run the 'project.py' first, as this is the main file that calls all the other files present within the "root" folder. The python file for testing called "test_project.py" is not required for the functionality of the software.

The images consists of drawn images of the inlet, the outlet, and the pump itself. These images are used as pictures in the application. I made this design choice as I wanted a graphical representation of the pump itself rather than boring text boxes where one just inputs the values to give it a more appealing design and feel. These images are buttons that can then be interacted with. The other images are icons for certain buttons throughout the sofware.

##### **The Project Python File**
project.py is the main file that launches the application and calls on all the other supporting python files. All the files present in the folder have been imported into project.py either directly or indirectly. The main function imports some of the modules and their classes contained within the folder (including the graphics) and PyQT5 itself, subsequent modules may import other modules as well as numpy and sympy. A protocol is added such that if the user wishes to close the application a popup box asks them to confirm the exit if there have been any changes. The geometry of the window is set, although resizable the geometry of the button layout is set. This was done to ensure that the buttons remain in place to represent the pump intact. Buttons are created to represent the solve button, the inlet, outlet and pump parts. When a user clicks on either the inlet pipe, outlet pipe or the pump itself they get a popup dialogue box which asks for inputs to specify that specific part of the pump. When speciying the inlet or outlet pipe condition, it is at this point where the user can choose to utilise the pipe designer software. The pipe designer will automatically calculate the friction losses based on the required information provided by the user and automatically fill out the required information into the properties popup dialog window. Once the user has filled in all but one of the required boxes and presses the calculate button beneath the pump, they get an answer in the form of a popup box. The program checks for the degrees of freedom, if there are too many degrees of freedom the user gets an information alert alerting them to specify all but one variable, if they fill in all the variables the user again gets the information popup box that lets them know to specify all but one variable.

##### **The callproperties and callmotorProp Python Files**
The 'callproperties.py' and 'callmotorProp.py' python file contains the instructions to initiate the properties popup dialog window as well its' widgets. Labels and line edit boxes in groupboxes are available where the user enters variables that are passed onto project.py when the submit button is pressed, which allows the values to be saved in memory (in project.py) and filled in automatically the next time the user clicks the pump graphic button. The properties pop dialog window contains the pipe designer graphic button that launches the 'Pipe Designer' window. The required information about the pipes is filled in this window. The information is grouped in group boxes for ease of use through organisation. When the user clicks the submit or close button (and confims the save) the entries are passed back to 'project.py' to be stored in memory, once the information is checked by 'project.py' it is passed onto 'callsolvePage'.py to be used for calculations.

##### **The callsolvepage Python File**
The callsolvePage recieves the information on the variables filled in by the user which was stored in memory and passed by project.py. Numpy and Sympy are the chosen scientific and engineering modules and are imported in 'callsolvePage.py' to perform symbolic (sympy) calculations and to provide the required constants.  Sympy allows for the import of constants. Imported is pie (3.14...), the user in this update is allowed to specify the gravitational constant. Sympy used as the solver, a for loop is used to identify the missing variable which Sympy solver then automatically solves and returns and name of the variable and its’ value in the solvepage GUI. The determined missing variable is passed on back to project.py and automatically passed back to project.py GUI and filled into the appropriate label. The 'callsolvePage.py" GUI allows the user to specify the net positive head required (as rated by the pump manufacturer) as well as the vapour pressure of the liquid to calculate the net positive suction head available.

##### **The callLossesCal Python File**
The 'callLossesCal.py' python file contains the instructions required for the interaction of all the widgets in the 'Pipe Designer' dialog window. The 'callproperties.py' file gathers the information required to specify the pipe design. It was called by 'callpropertes.py' and passes user provided information back to it, which eventually gets passed back to 'project.py'. The 'close' window button will only be available once all the information has been specified, the user will be able to see a summary of values (calculted by 'frictionCalc.py') calculated for each pipe segment specified.

##### **The frictionCalc Python File**
The 'frictionCalc.py' takes the data specified in 'callsolvePage.py' and runs through the relevant calculations to get the required friction losses. It also evaluates the chosen solve methods.

##### **The Menubar**
A menubar is added although it is used mostly as an aesthetic. In the menubar two options are available one 'file' and another 'about' The 'file' button opens three other options one of which exits the application. The user has the option to import and export data stored about the all the properties of the pump as a csv file. The 'about' opens a dialogue that tells about the programme and gives the creaters details (links to the creaters linkd in page).

##### **The About Python File**
 This file dictates what the about file should present. It present information obout the application and its' purpose as well as a link to the creaters linkdIn for bug reporting or feature requests.

##### **GUI Files**
The python files that do not begin with 'call' contain instructions on the GUI that where coded by the PyQT designer.

##### **Future Development**
The application is again still far from finished. I plan to add more features that would allow other variables to be calculated as well as the ability for the user to select their unit of measurement, which the application will then change on calculation to ensure the answer remains accurate. I want to add the ability to run parametric studies on the calculation, as well as graph the results (pump performance curve). I to provide the user the ability to see where they are on the moody diagram. I want to add another feature called solid-fluid particle phenomena which would calculate the minimum settling velocity of the solids in the fluid to determin the required velocity (thus volumetric flowrate) for the particular fluid (called slurry). 

As a single developer this could take months for me to code. Application updates will be named using the semantic versioning convention. See you in the next update.

Small updates will include the ability to choose not to calculate losses due to tank discharge (expansion from infinite tank diameter) and tank suction (contraction from infinite tank diameter) as well as to specify the inlet tank and outlet tank diameters.

##### **Known Issues / Bugs**
The application on launch may take up to 10 seconds on first launch to start but faster on subsequent launches (due to '___pycache___'), I am not entirely sure why. I suspect it is inherent in python itself being relatively slower than other languages especially with the programme code getting larger and that PyQt5 is not as quick as tkinter, no performance issues are encountered once the program is active.

Report bugs encountered by messaging me on linkdIn (found in the 'about' section in the main menu).

Due to licensing issues, I might change the GUI interface from PyQt5 to Pyside 6.

### This was version 2.0.0
An update from version 1.0.0. My name is Njabulo Zimu and this was CS50p. Thank you for reading.