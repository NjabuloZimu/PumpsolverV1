from centered_canvas import center_window_contents
import sys
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox
from solvePage import *
from PyQt5.QtWidgets import QMainWindow, QApplication, QAction, QFileDialog, QMessageBox
# User Import
from scipy.constants import g, pi
from sympy import solve, Symbol



class SolvePage(QDialog):
    resultsData = QtCore.pyqtSignal(dict, str, object, object, object) # This is the subwindow signal sent to main to write edit in green for successful solve.

    def __init__(self, data): # Need to pass in the data in the form of a dictionary to be calculated.
        super().__init__()
        self.ui = Ui_SolvePage()
        self.ui.setupUi(self)
        center_window_contents(self)
        self.ui.pushButtonClose.clicked.connect(self.closewindow)
        self.data = data
        self.answer_f()
        # Calculate the results to show on first time window open
        self.NPSHa = self.cavitation()
        self.updateNPSH()
        
        # Update the head required value everytime the text is changed
        self.ui.lineEditHeadRequired.textEdited.connect(self.updateNPSH)
        self.ui.lineEditVapourPress.textEdited.connect(self.cavitation)

        # Initialize designer inlet and outlet statuses
        self.designer_status_in = None
        self.designer_status_out = None

    # Setter for designer status
    def designer_statuses(self, designer: bool, identifier: str):
        if identifier == "Inlet":
            self.designer_status_in =  designer
        elif identifier == "Outlet":
            self.designer_status_out = designer


    def closewindow(self):
        #return results to main on startup
        print(f'this is what was returned to main {self.data}')
        self.resultsData.emit(self.data, self.windowTitle().split(" ")[:1][0], None, None, None)
        self.close()
        

    def answer_f(self):
        data = self.data
        data = self.tofloat(data)

        for key in data:
            # Convert value to float
            if data[key] != 'Unspecified' and isinstance(data[key], Symbol) == False:
                print(f'Convert to float {key, data[key]}')
                print(f'See {data[key] == "Unspecified"} or {isinstance(data[key], Symbol)}')
                data[key] = float(data[key])

            # Identify missing variable
            if data[key] == 'Unspecified' or isinstance(data[key], Symbol) == True:
                print(f'Identify missing variable {isinstance(data[key], Symbol)}')
                data[key] = Symbol('Unspecified', particular=True, rational=True)

                # if efficiency is not a symbol convert to fraction.
                if data[key] != data['effi']:
                    data['effi'] = data['effi'] / 100
                    
                n = data['effi']
                wm = data['power']
                hi = data['safety']

                # if inlet diameter is not a symbol convert to meters.
                if data[key] != data['in_dia']:
                    data['in_dia'] = data['in_dia'] / 100
                
                d1 = data['in_dia']
                z1 = data['in_head']

                # Make outlet and inlet symbols if outlet is the missing variable.
                if data[key] == data['in_flow']:
                    data['out_flow'] = Symbol('Unspecified', particular=True, rational=True)
                else:
                # if not a variable convert inlet and outlet flows from hours to seconds.
                    data['in_flow'] = data['in_flow'] / 3600
                    data['out_flow'] = data['out_flow'] / 3600
                
                q1 = data['in_flow']

                # Create symbols for both outlet density and inlet density if outlet is the missing variable because density remains constant.
                if data[key] == data['in_dens']:
                    data['out_dens'] = Symbol('Unspecified', particular=True, rational=True) 

                de1 = data['in_dens']
                p1 = data['in_press']

                # if outlet diameter is not a symbol convert to meters.
                if data[key] != data['out_dia']:
                    data['out_dia'] = data['out_dia'] / 100

                d2 = data['out_dia']
                z2 = data['out_head']
                q2 = data['out_flow']
                de2 = data['out_dens']
                p2 = data['out_press']
                hL1 = data['in_loss']
                hL2 = data['out_loss']

                g = data['gravity']

                # Energy balance equation unified (all losses in meters)
                ans = solve(p2/(de2*g) - p1/(de1*g) + ((q2/(pi*((d2)/2)**2))**2)/(2*g) - ((q1/(pi*((d1)/2)**2))**2)/(2*g) + (z2 - z1) - (n*wm) + (hL1 + hL2) + hi, data[key])

                print(f'answer {ans}')
                print(f'key {key}')

                # Convert the answer back to original units
                if len(ans) != 0:
                    if key == 'effi':
                        ans_converted = ans[0] * 100
                    elif key == 'in_dia' or key == 'out_dia':
                        ans_converted = ans[1] * 100
                    elif key == 'in_flow' or key == 'out_flow':
                        ans_converted = ans[1] * 3600
                    else:
                        ans_converted = ans[0]
                    # set the value in the key to the solved value
                    print(f'Answer converted just before added {data[key]}, {self.data[key]}')

                # Convert all other values that were converted back to their orignal values
                    data['effi'] = data['effi'] * 100
                    data['in_dia'] = data['in_dia'] * 100
                    data['out_dia'] = data['out_dia'] * 100
                    data['in_flow'] = data['in_flow'] * 3600
                    data['out_flow'] = data['out_flow'] * 3600

                # If there is a value print the answer otherwise no solution available
                if len(ans) == 0:
                    print('There is no solution')
                    text = 'There is no solution'
                    self.ui.labelMissingVar.setText(text)
                    print(f'what is the data after no solution verdict {data}')
                    return

                # If the answer is not a number print equation that give vector of applicable values (X E R).
                elif ans[0].is_number == False:
                    # Index 0 to get the name and Index 1 to get the units from the list of dictionaries
                    print(f"Found missing variable: {self.set()[0][key]}. Answer is a function of Real numbers {self.set()[1][key]}")
                    text = f"Found missing variable: {self.set()[0][key]}. Answer is a function of Real numbers, in {self.set()[1][key]}"
                    self.ui.labelMissingVar.setText(text)
                    # enable a button to plot vector on MATPLOTLIB

                # Otherwise just give the answer
                else:
                    print(f"Found missing variable: {self.set()[0][key]}. Answer = {ans_converted} {self.set()[1][key]}")

                    text = f"Found missing variable: {self.set()[0][key]}. Answer = {ans_converted} {self.set()[1][key]}"
                    self.ui.labelMissingVar.setText(text)
 
                self.set_answer(data, key, ans_converted)
                print(f'Answer converted just after added {data[key]}, {self.data[key]}')
                return

    def set_answer(self, data, key, ans_converted):
        print(f'set answer ran {data}')
            # set unspecified value to the the answer
        try:
            answer_converted_rounded = "{:.9g}".format(ans_converted)
        except UnboundLocalError:
            pass
        else:
            data[key] = answer_converted_rounded
            if key == 'in_flow':
                data['out_flow'] = answer_converted_rounded



    def set(self):
        # use the key to match the units, make a dictionary of units and full name

        coupledData = ({'in_dia': 'Inlet Diameter',
                'in_head': 'Static Suction Head', 
                'in_loss': "Inlet Pipe/Fitting Dynamic Head losses", 
                'in_flow': "Inlet Volumetric Flowrate", 
                'in_dens': "Inlet Density", 
                'in_press':"Inlet Pressure",

                'out_dia': 'Outlet Diameter',
                'out_head': 'Static Discharge Head', 
                'out_loss': 'Outlet Pipe/Fitting Dynamic Head losses',
                'out_flow': 'Outlet Volumetric Flowrate',
                'out_dens': 'Outlet Density',
                'out_press':'Outlet Pressure',

                'effi': 'Pump Efficiency',
                'power': 'Available Head', 
                'safety': 'Safety', 
                'gravity': 'Gravitational Acceleration'
                },

                {'in_dia': 'm',
                'in_head': 'm', 
                'in_loss': "m", 
                'in_flow': "m<sup>3</sup>/h", 
                'in_dens': "kg/m<sup>3</sup>", 
                'in_press':'Pascals (N/m<sup>2</sup>)',

                'out_dia': 'm',
                'out_head': 'm', 
                'out_loss': 'm',
                'out_flow': 'm<sup>3</sup>/h',
                'out_dens': 'kg/m<sup>3</sup>',
                'out_press':'Pascals (N/m<sup>2</sup>)',

                'effi': '%',
                'power': 'm of Required Head', 
                'safety': 'm', 
                'gravity': 'm/s<sup>2</sup>'
                })
        
        return coupledData

    def cavitation(self): # Calculate NPSH required and that available and report the ratio.
        data = self.data
    
        try:
            pv = float(self.ui.lineEditVapourPress.text()) * 133.322 # convert to Pa from mmHg
        except ValueError:
            pass
        else:
            p1 = float(data['in_press'])    
            de = float(data['in_dens'])
            z1 = float(data['in_head'])
            hL1 = float(data['in_loss'])
            hi = float(data['safety'])

            # for velocity calculate
            # q1 = float(data['in_flow'])
            d1 = float(data['in_dia'])
            print(d1)
            g = float(data['gravity'])

        
            # ve = ((q1/(pi*((d1)/2)**2))**2)
            # NPSHa = (p1 / de*g + ve/(2*g) - pv/de*g)
            # NPSHa = (((p1 - pv) / de) * 10.2) + z1 - hL1 + (ve**2 / 2 * g)
            print(f'Print P1 cavitation to see if its a string:  {isinstance(p1, str)}')
            # Correct NPSHa formula (all terms in meters)
            NPSHa = (p1 - pv) / (de * g) + z1 - hL1 - hi


            print(NPSHa)
            # :#.6g
            self.ui.label_NPSHa.setText(f'{NPSHa}')

            return NPSHa

    def tofloat(self, data):
        # Convert value to float
        for key in data:
            if data[key] != 'Unspecified':
                data[key] = float(data[key])
        return data

    def updateNPSH(self):
        NPSHr = self.ui.lineEditHeadRequired.text()
        # Update the head required value everytime the text is changed
        # NPSH = self.ui.labelNPSHRatio.setText(str(self.NPSHa))
        try:
            NPSHratio = self.NPSHa / float(NPSHr)
            NPSHDifference = self.NPSHa - float(NPSHr)
        except ValueError:  
            pass
        except ZeroDivisionError:
            NPSHDifference = self.NPSHa - float(NPSHr)
            self.ui.labelNPSHDiff.setText(f'{NPSHDifference:#.6g}')
        else:
            self.ui.labelNPSHRatio.setText(f'{NPSHratio:#.6g}')
            self.ui.labelNPSHDiff.setText(f'{NPSHDifference:#.6g}')

if __name__=="__main__":
    app = QApplication(sys.argv)
    w = SolvePage()    
    w.show()
    sys.exit(app.exec_())