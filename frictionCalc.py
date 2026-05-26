import sys
from PyQt5.QtWidgets import QDialog
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import Qt, QRegExp
from lossesCal import *
from sympy import solve, Symbol, sqrt


import scipy.optimize as opt
import numpy as np
from scipy.constants import pi

class Calculation(QDialog):
    totalLosses = QtCore.pyqtSignal(float) # This is the subwindow signal sent to properties, pass back data to eventially store in main.
    def __init__(self):
        super().__init__()
        self.ui = Ui_LineLossesDesigner()
        self.ui.setupUi(self)

        self.relativeRoughessList = []

        # List contains calculated friction for each pipe segment
        self.friction_segments = {}

        # Merged list that contains all information including friction calculation
        # Merge fittings data and line roughness data:
        self.merged_list = []


    def start_cal(self, stored_segments, list_fittings_by_segment, LineRoughnessList, viscosity, density, volumetric):

        # Store the total friction losses hf
        self.total_losses_hf = 0
        self.num_contractions = 0
        self.num_expansions  = 0
        self.total_pipe_length = 0
        self.total_minor = 0
        self.total_major = 0

        print("Start calculation started in frictionCalc.py")
        # friction calculations variables
        self.stored_segments = stored_segments
        self.list_fittings_by_segment = list_fittings_by_segment
        self.LineRoughnessList = LineRoughnessList

        # Convert to float on start-up
        try:
            self.viscosity = float(viscosity) / 1000 # Single Value, Applicable to all segments, converted from centipoise to pascal second. 
            self.density = float(density)
            self.volumetric = float(volumetric) / 3600 # Single Value, Applicable to all segments, converted from m^3/h to m^3/s pascal second. 
        except ValueError:
            print('Value Error on a constant one of them was not yet specified')

        merged_dict = {}
        print("Checkpoint 1 reached")
        # Merge dictionaries based on the common key 'Segment Row'
        for dictionary in self.list_fittings_by_segment + self.LineRoughnessList:
            part_no = dictionary['Line Segment']

            if part_no not in merged_dict:
                merged_dict[part_no] = {}

            merged_dict[part_no].update(dictionary)

        # Convert the merged dictionary back to a list of dictionaries
        merged_list = list(merged_dict.values())
        print(f'merged list before keyerror: {merged_list}')
        print("Checkpoint 2 reached")
        # Join the additional dictionary based on the key containing 'part no'
        for entry in merged_list:
            Line_Segment_key = f'Line Segment {entry["Line Segment"]}'
            try:
                entry.update({'Segment Length (m)': self.stored_segments[f'{Line_Segment_key}, Segment Length (m)'],
                            'Segment Diameter (cm)': self.stored_segments[f'{Line_Segment_key}, Segment Diameter (cm)']})
            except KeyError:
                return
            else:
                continue
        print("Checkpoint 3 reached")
        # Loop through the list of dictionaries
        for my_dict in merged_list:
            # Loop through each key-value pair in the dictionary
            for key, value in my_dict.items():
                try:
                    # Try to convert the value to a float
                    float_value = float(value)
                    # If successful, update the value in the dictionary
                    if 'Line Segment' not in key:
                        my_dict[key] = float_value
                    else:
                        continue
                except ValueError:
                    # If the conversion fails, continue to the next iteration
                    continue
        # Sort the list of dictionaries based on the 'Plate' key
        merged_list = sorted(merged_list, key=lambda x: x['Line Segment'])
        print(f'merged dict after sorting: {merged_list}')
        print("Checkpoint 4 reached")
        # Loop through each dictionary and call reynolds, call relative roughness and pass into darcy_friction_factor function to return friction factor list of dictinaries.
        for index, dictionary in enumerate(merged_list):
            # Conversion
            current_diameter = float(merged_list[index]['Segment Diameter (cm)'] / 100) # convert to meters from cm
            # We want the ability to go back to the previous dictionary to get needed information for expansion / contraction calculation.
            previous_diameter = float(merged_list[index - 1]['Segment Diameter (cm)'] / 100)
            print(f'The previous diameter was {previous_diameter}')
            print(f'The current diameter is {current_diameter}')


            print(f'Trying to see if conversion was done, diameter is {dictionary["Segment Diameter (cm)"]}')
            velocity = self.velocity(current_diameter, self.volumetric)
            re = self.reynolds(current_diameter, velocity, self.density)

            try:
                lineRoughness = float(dictionary['Segment Roughness']) / 1000 # mm to m
            except (TypeError, ValueError):
                lineRoughness = dictionary['Segment Roughness']
                
            rR = self.relativeRoughness(lineRoughness, current_diameter)
            segment_length = dictionary['Segment Length (m)']
            self.total_pipe_length = self.total_pipe_length + segment_length
            
            # now for each entry calculate darcy's friction factor and store in a dictionary
            darcy_friction_factor = self.darcy_friction_factor(re, rR, lineRoughness)

            print("Checkpoint 5 reached")
            
            print(f"The current index is {index}, and line segment {dictionary['Line Segment']}")
            if index == 0 and self.windowTitle().split(" ")[:1][0] == "Inlet":
                # it is the first segment
                # Assume the diameter of the storage tank is much greater than the diameter of the suction pipe
                # thus, the first segment will always be treated as a contraction.
                if re < 2100:
                    print("Flow in the first segment is laminar, head loss due to contraction neglible, contraction loss coefficient is less than 0.1")
                    contraction_coeff_tank = 0.1         
                else:
                    contraction_coeff_tank = 0.4 * (1 - 0) # Assume the tank is infinitely larger than the suction pipe 
                    print(f"The contraction coefficient is 0.4 {contraction_coeff_tank}")

                con_exp_loss = self.con_exp_fit_loss(contraction_coeff_tank, velocity)
                self.contraction_loss = con_exp_loss

            else:
                comparison_result = current_diameter > previous_diameter
                # Calculate the headloss due to contraction / expansion
                if comparison_result:
                    self.num_expansions = self.num_expansions + 1
                    expansion_coeff = self.expansion_coeff(current_diameter, previous_diameter)
                    # Get the velocity from the previous segment / dictionary
                    previous_velocity = self.velocity(previous_diameter, self.volumetric)
                    con_exp_loss = self.con_exp_fit_loss(expansion_coeff, previous_velocity)
                else:
                    self.num_contractions = self.num_contractions + 1
                    contraction_coeff = self.contraction_coeff(current_diameter, previous_diameter, re)
                    con_exp_loss = self.con_exp_fit_loss(contraction_coeff, velocity)

                if index == len(merged_list) - 1 and self.windowTitle().split(" ")[:1][0] == "Outlet":
                    # It is the last segment
                    # Assume the diameter of the storage tank is much greater than the diameter of the discharge pipe
                    # Thus, the last segment will always be treated as a expansion.
                    expansion_coeff_tank = 1 * (1 - 0) # Assume the tank is infinitely larger than the discharge pipe
                    # At the last segment its compared with the previous segment to get con_exp_loss then expansion due to disharge into tank is added.
                    con_exp_loss = self.con_exp_fit_loss(expansion_coeff_tank, velocity) + con_exp_loss
                    self.expansion_loss = con_exp_loss
                    
                    

            print("Checkpoint 6 reached")
            # Calculate total fittings losses for this pipe segment
            fitting_coefficients = 0.0
            for key, value in dictionary.items():
                if 'Fitting' in key and 'Type' not in key:
                    print(f"Fitting coefficient key:{key}, value:{value}")
                    fitting_coefficients = fitting_coefficients + value
                else:
                    continue
            # Start calculating minor losses
            fittings_loss = self.con_exp_fit_loss(fitting_coefficients, velocity)
            # add up total minor losses
            self.total_minor = self.total_minor + fittings_loss

            # Start calculating major losses
            darcy_loss = self.darcy_loss_cal(darcy_friction_factor, velocity, segment_length, current_diameter)
            # add up total major losses
            self.total_major = self.total_major + darcy_loss

            total_segment_loss = self.total_segment_loss(con_exp_loss, fittings_loss, darcy_loss)
            print(f'The total fittings_loss {fittings_loss} and total segment losses {total_segment_loss}')

            # append total segment losses to dictionary values then update the lineEdit data
            index = index + 1
            print(f"to append, the following should be true, {dictionary['Line Segment'] == index}, line segment: {dictionary['Line Segment']}, index: {index}")
            if dictionary['Line Segment'] == index:
                dictionary['Total Segment Loss'] = total_segment_loss
                print(f'The dictionary after Total Segment Loss addition {dictionary}')
                self.ui.pushButtonClose.setEnabled(True)
            else: 
                print('Insufficient information to calculate headlosses, disabled close button')
                self.ui.pushButtonClose.setEnabled(False)
            print("Checkpoint 7 reached")
            # Finally, update the values displayed in the line editboxes
            self.updateEditboxText(darcy_friction_factor, rR, re, velocity, dictionary, darcy_loss, fittings_loss, lineRoughness)


        # count total losses across all segments
        for dictionary in merged_list:
            self.total_losses_hf = dictionary['Total Segment Loss'] + self.total_losses_hf
        
        # Signal that total losses have been retrieved 
        self.totalLosses.emit(self.total_losses_hf)

        if self.windowTitle().split(" ")[:1][0] == "Inlet":
            self.ui.labelOverallSummary.clear()
            self.ui.labelOverallSummary.setText(f'<html><head/><body><p>There are {int(self.num_contractions)} contractions and {int(self.num_expansions)} expasions. The total pipe length is {self.total_pipe_length:#.6g} m. The total minor losses are {self.total_minor:#.6g}\
                                            m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>\
                                             and the total major losses are {self.total_major:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>. \
                                            Assuming the tank is infinitely larger than the pipe, the losses at the nose of the pipe, on suction, in the tank are {self.contraction_loss:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>\
                                            , the total losses are {self.total_losses_hf:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span></p></body></html>')
            
        elif self.windowTitle().split(" ")[:1][0] == "Outlet":
            self.ui.labelOverallSummary.clear()
            self.ui.labelOverallSummary.setText(f'<html><head/><body><p>There are {int(self.num_contractions)} contractions and {int(self.num_expansions)} expasions. The total pipe length is {self.total_pipe_length:#.6g} m. The total minor losses are {self.total_minor:#.6g}\
                                            m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>\
                                             and the total major losses are {self.total_major:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>. \
                                            Assuming the tank is infinitely larger than the pipe, the losses at the nose of the pipe, on disharge, in the tank are {self.expansion_loss:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span>\
                                            , the total losses are {self.total_losses_hf:#.6g} m<span style=\" vertical-align:super;\">2</span>/s<span style=\" vertical-align:super;\">2</span></p></body></html>')
    
    def updateEditboxText(self, darcy_friction_factor, rR, re, velocity, dictionary, darcy_loss, fittings_loss, lineRoughness):
        selected_indexes = self.ui.tableWidgetPipeSegment.selectionModel().selectedIndexes()
        try:
            selected_row = selected_indexes[0].row() + 1 # Add 1 to match dictionary save structure (i.e. there is no segmnet 0 in dictionary)
        except IndexError:
            self.ui.lineEditDarcys.clear()
            self.ui.lineEditRelativeRough.clear()
            self.ui.lineEditReynolds.clear()
            self.ui.lineEditFlowType.clear()
            self.ui.lineEditVelocity.clear()
            self.ui.lineEditMinorLosses.clear()
            self.ui.lineEditMajorLosses.clear()
        else:
            print(f'The selected row in tableWidgetPipeSegmnet is {selected_row} and the currently evaluated line segment in the dictionary is {dictionary["Line Segment"]}')
            if selected_row == dictionary['Line Segment']:
                self.ui.lineEditDarcys.setText(f'{darcy_friction_factor:#.6g}')
                try:
                    # Try Because relative roughness is smooth.
                    self.ui.lineEditRelativeRough.setText(f'{rR:#.6g}')
                except TypeError:
                    print("The relative roughness was not required and was set to None")
                    self.ui.lineEditRelativeRough.setText(str(rR))
                self.ui.lineEditReynolds.setText(f'{re:#.6g}') 
                self.ui.lineEditVelocity.setText(f'{velocity:#.6g}') 
                self.ui.lineEditMajorLosses.setText(f'{darcy_loss:#.6g}')
                self.ui.lineEditMinorLosses.setText(f'{fittings_loss:#.6g}')

                re_compare = self.region(rR)

                if re < 2100 and lineRoughness == "Smooth Pipe": # Laminar Flow
                    self.ui.lineEditFlowType.setText("Laminar flow, smooth pipe")
                elif re > 4000 and lineRoughness == "Smooth Pipe":
                    self.ui.lineEditFlowType.setText("Turbulent flow, smooth pipe")
                elif re >= 2100 and re <= 4000 and lineRoughness == "Smooth Pipe":
                    self.ui.lineEditFlowType.setText("Transitional flow, smooth pipe")
                elif re <= re_compare:
                    self.ui.lineEditFlowType.setText('Transitional flow / Colebrook Equation')
                elif re > re_compare:
                    self.ui.lineEditFlowType.setText('Turbulent flow')
                else:
                    print("Friction Calculation Failed.")

    def con_exp_fit_loss(self, coeff, velocity):
        loss = coeff * (velocity)**2 / 2
        return loss
    
    def darcy_loss_cal(self, darcy_friction_factor, velocity, length, diameter):
        darcy_loss = 4 * darcy_friction_factor * length / diameter * (velocity)**2 / 2
        return darcy_loss

    def total_segment_loss(self, con_or_exp_loss, fittings_loss, darcy_friction_factor):
        print(f"Total segment loss started adding {con_or_exp_loss} + {fittings_loss} + {darcy_friction_factor}")
        total_segment_loss = darcy_friction_factor + con_or_exp_loss + fittings_loss
        return total_segment_loss

    def expansion_coeff(self, current_diameter, previous_diameter):
        expansion_coeff = (1 - previous_diameter / current_diameter)**2
        return expansion_coeff
    
    def contraction_coeff(self, current_diameter, previous_diameter, re):
        if re < 2100:
            contraction_coeff = 0.1
        else:
            contraction_coeff = 0.4 * (1 - current_diameter / previous_diameter)
        return contraction_coeff

    def velocity(self, diameter, volumetric):
        print(f"Calculating the velocity. Diameter: {diameter}, volumetric flowrate: {volumetric}")
        cross_sectional_area = pi*(diameter/2)**2
        print(f"Calculating the velocity. Cross sectional area {cross_sectional_area}")
        velocity = volumetric / cross_sectional_area
        return velocity

    def darcy_friction_factor(self, re, rR, lineRoughness):
        # Reynolds to compare with, determines if (on the moody diagram the in the transition region or turbulant region
        re_compare = self.region(rR)

        print(f'The calculated Reynolds is {re}, relative roughness {rR}')

        # Check Flow type and calculate darcy's friction factor.
        print(f"the line roughness is {lineRoughness}, this should be true {lineRoughness == 'Smooth Pipe'}")
        if re < 2100 and lineRoughness == "Smooth Pipe": # Laminar Flow
            darcy_friction_factor = 64/re
            # self.ui.lineEditFlowType.setText("Laminar flow, smooth pipe")
            return darcy_friction_factor
        elif re > 4000 and lineRoughness == "Smooth Pipe":
            darcy_friction_factor = 0.316 / (re)**(1/4) # Smooth Pipe Turbulent Flow
            # self.ui.lineEditFlowType.setText("Turbulent flow, smooth pipe")
            return darcy_friction_factor
        elif re >= 2100 and re <= 4000 and lineRoughness == "Smooth Pipe":
            darcy_friction_factor = self.solve_colebrook(0.0, re) # Transitional Flow / Colebrook Equation # 0 relative roughness because smooth
            # self.ui.lineEditFlowType.setText("Transitional flow, smooth pipe")
            return darcy_friction_factor
        elif re <= re_compare:
            darcy_friction_factor = self.solve_colebrook(rR, re) # Transitional Flow / Colebrook Equation
            # self.ui.lineEditFlowType.setText('Transitional flow / Colebrook Equation')
            return darcy_friction_factor
        elif re > re_compare:
            darcy_friction_factor = (1.14 + 2 * np.log10(1/rR))**(-2) # Completely Turbulent Flow
            # self.ui.lineEditFlowType.setText('Turbulent flow')
            return darcy_friction_factor
        else:
            print("Friction Calculation Failed.")

    def colebrook_equation(self, f, rR, re):
        print(f"colebrook activated, relative roughness {rR}, reynolds {re}")
        return 1.0 / np.sqrt(f) + 2.0 * np.log10((rR / 3.7) + (2.51 / (re * np.sqrt(f))))
    
    def solve_colebrook(self, Re, epsilon_D, initial_guess=0.02):
        f_solution = opt.fsolve(self.colebrook_equation, initial_guess, args=(Re, epsilon_D))
        print(f'These are the coolbrook equations {f_solution}')
        return f_solution[0]

    def reynolds(self, diameter, velocity, density):
        print(f"Calculating the Reynolds number, diameter: {diameter}, velocity: {velocity}, density: {density}, Viscosity: {self.viscosity} ")
        reynolds = diameter * velocity * density / self.viscosity
        return reynolds
    
    def relativeRoughness(self, lineRoughness, diameter):
        try:
        # Relative Pipe Roughness
            rR = lineRoughness / diameter
        except TypeError:
            print("Relative Roughness Calculation, Pipe is classified as smooth, Relative Roughness is not Required")
            return None
        # Append to dictionary of solutions
        else:
            print(f"Relative Roughness Calculation, The relative roughness is calculated as {rR}, using diameter {diameter}")
            return rR
    
    def region(self, rR):
        # equation to determine the region (transitional or turbulant). equation determined through interpolation.
        if self.ui.comboBoxTransitionEquation.currentIndex() == 0:
            # Moody
            try:
                re_to_compare = 1600/ rR
            except TypeError:
                print("Region calculation, Pipe is classified as smooth, Relative Roughness is not Required")
                return None
            
        elif self.ui.comboBoxTransitionEquation.currentIndex() == 1:
            # R.J.S Pigott
            try:
                re_to_compare = 3500 / rR
            except TypeError:
                print("Region calculation, Pipe is classified as smooth, Relative Roughness is not Required")
                return None

        return re_to_compare
    