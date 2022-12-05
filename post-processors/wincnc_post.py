# ***************************************************************************
# *   Copyright (c) 2022 ASMR Systems <wellnessvoid@gmail.com>               *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Lesser General Public License for more details.                   *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

from __future__ import print_function
import FreeCAD
from FreeCAD import Units
import Path
import argparse
import datetime
import shlex
from PathScripts import PostUtils
from PathScripts import PathUtils

TOOLTIP = '''
This is a postprocessor file for the Path workbench. It is used to
take a pseudo-gcode fragment outputted by a Path object, and output
real GCode suitable for a CAMaster Stinger 1 CNC Router @FatCatFabLab
(ATC disabled). This postprocessor, once placed in the appropriate
 PathScripts folder, can be used directly from inside FreeCAD, via
the GUI importer or via python scripts with:

import wincnc_post
wincnc_post.export(object,"/path/to/file.tap","")

see WinCNC Gcode documentation here:
https://www.wincnc.com/webfiles/CNC%20Windows/Manuals/WinManual_3.0r14.pdf

this postprocessor was adapted from the linuxcnc postprocessor
for FreeCAD.
'''

# :: Notes About WinCNC GCode Dialect
#
# Please refer to the pages in the manual linked above.
#
# :::: Comments (p.138)
#   Unlike linuxcnc, comments are enclosed by square brackets,
#   e.g. "[this is a comment]"
#
# :::: Note About WinCNC Macros
#   Only the commands listed in the manual are supported. However,
#   WinCNC allows macros to be defined (CNC.MAC) which can define
#   additional codes which aren't in the manual. For example,
#   M3 and M5 are not defined by default, but are included as
#   macros (which is why using M3 and M5 commands work in your gcode).

now = datetime.datetime.now()

parser = argparse.ArgumentParser(prog='wincnc', add_help=False)
parser.add_argument('--no-header', action='store_true', help='suppress header output')
parser.add_argument('--no-comments', action='store_true', help='suppress comment output')
parser.add_argument('--line-numbers', action='store_true', help='prefix with line numbers')
parser.add_argument('--no-show-editor', action='store_true', help='don\'t pop up editor before writing output')
parser.add_argument('--precision', default='3', help='number of digits of precision, default=3')
parser.add_argument('--preamble', help='set commands to be issued before the first command, default="G17\nG90"')
parser.add_argument('--postamble', help='set commands to be issued after the last command, default="M05\nG17 G90\nM2"')
parser.add_argument('--inches', action='store_true', help='Convert output for US imperial mode (G20)')
parser.add_argument('--modal', action='store_true', help='Output the Same G-command Name USE NonModal Mode')
parser.add_argument('--axis-modal', action='store_true', help='Output the Same Axis Value Mode')
parser.add_argument('--no-tlo', action='store_true', help='suppress tool length offset (G43) following tool changes')

TOOLTIP_ARGS = parser.format_help()

# These globals set common customization preferences
OUTPUT_COMMENTS = True
OUTPUT_HEADER = True
OUTPUT_LINE_NUMBERS = False
SHOW_EDITOR = True
MODAL = False  # if true commands are suppressed if the same as previous line.
USE_TLO = True # if true G43 will be output following tool changes
OUTPUT_DOUBLES = True  # if false duplicate axis values are suppressed if the same as previous line.
COMMAND_SPACE = " "
LINENR = 100  # line number starting value
SKIP_FIRST_TOOLCHANGE = True

# These globals will be reflected in the Machine configuration of the project
UNITS = "G20"  # G21 for metric, G20 for us standard
UNIT_SPEED_FORMAT = 'in/min'
UNIT_FORMAT = 'in'

MACHINE_NAME = "CAMaster Stinger 1"
CORNER_MIN = {'x': 0, 'y': 0, 'z': 0}
CORNER_MAX = {'x': 25, 'y': 36, 'z': 5}
PRECISION = 7

# Preamble text will appear at the beginning of the GCODE output file.
# G54  switch to 0,0 of 1st workspace (single tool machine usually only use G54)
# G40  tool radius compensation off
# G49  tool length offset compensation cancel
# G80  cancel canned cycle
# G90  absolute coordinates
PREAMBLE = '''G54\t\t[Using G54 Workspace]
G40\t\t[Tool Cutter Compensation Off]
G49\t\t[Tool Length Offset Off]
G90\t\t[Absolute Mode]
G53 Z0\t\t[Lift Z to top]
'''

# Postamble text will appear following the last operation.
POSTAMBLE = '''G53 Z0\t\t[Rapid Move Z to 0]
M05\t\t[Turn Spindle Off]
'''

# Pre operation text will be inserted before every operation
PRE_OPERATION = ''''''

# Post operation text will be inserted after every operation
POST_OPERATION = ''''''


# Tool Change commands will be inserted before a tool change
PRE_TOOL_CHANGE = '''G28Z\t\t\t\t[Go to Machine Z0]
G53Z\t\t\t\t[Lift Z (Rapid)]
M5\t\t\t\t[Turn Spindle Off]
G53 X0 Y0'''''
TOOL_CHANGE_NOTIFICATION = '''
G5 T2 M"Please Change Tool to '{tool_num:s}'. Press OK when done (Keep Dust Boot Off!)."
'''''
TOOL_CHANGE = '''G5 T2 M"Press OK to Measure Tool."
L21\t\t\t\t[Disable Soft Limits]
L210Z\t\t\t\t[Select Z Alt Low Limits]
G53 Z0
G53 X{TMX}Y{TMY}\t\t[Move to Tool Measure Switch X/Y Coordinates]
L91 G0 Z{TMD}
L91 G1 Z-9 M28 F20 G31\t\t[Perform Measurement of Tool]
M37 Z{TM1} H{TP1}\t\t[Set New Tool Offset]
G53 Z0
L91 G1 Z0 F50
L212\t\t\t\t[Select Primary Limits for All Axes]
G0
G53 X0 Y0
G5 T2 M"Please Replace Dust Boot. Press OK when done."
G5 T2 M"Continue Job?"
'''

first_tool_change_skipped = False

# to distinguish python built-in open function from the one declared below
if open.__module__ in ['__builtin__','io']:
    pythonopen = open


def processArguments(argstring):
    # pylint: disable=global-statement
    global OUTPUT_HEADER
    global OUTPUT_COMMENTS
    global OUTPUT_LINE_NUMBERS
    global SHOW_EDITOR
    global PRECISION
    global PREAMBLE
    global POSTAMBLE
    global UNITS
    global UNIT_SPEED_FORMAT
    global UNIT_FORMAT
    global MODAL
    global USE_TLO
    global OUTPUT_DOUBLES

    try:
        args = parser.parse_args(shlex.split(argstring))
        if args.no_header:
            OUTPUT_HEADER = False
        if args.no_comments:
            OUTPUT_COMMENTS = False
        if args.line_numbers:
            OUTPUT_LINE_NUMBERS = True
        if args.no_show_editor:
            SHOW_EDITOR = False
        print("Show editor = %d" % SHOW_EDITOR)
        PRECISION = args.precision
        if args.preamble is not None:
            PREAMBLE = args.preamble
        if args.postamble is not None:
            POSTAMBLE = args.postamble
        if args.inches:
            UNITS = 'G20'
            UNIT_SPEED_FORMAT = 'in/min'
            UNIT_FORMAT = 'in'
            PRECISION = 4
        if args.modal:
            MODAL = True
        if args.no_tlo:
            USE_TLO = False
        if args.axis_modal:
            print ('here')
            OUTPUT_DOUBLES = False

    except Exception: # pylint: disable=broad-except
        return False

    return True

def export(objectslist, filename, argstring):
    # pylint: disable=global-statement
    if not processArguments(argstring):
        return None
    global UNITS
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT

    for obj in objectslist:
        if not hasattr(obj, "Path"):
            print("the object " + obj.Name + " is not a path. Please select only path and Compounds.")
            return None

    print("postprocessing...")
    gcode = ""

    # write header
    if OUTPUT_HEADER:
        gcode += linenumber() + "[Exported by FreeCAD]\n"
        gcode += linenumber() + "[Post Processor: " + __name__ + "]\n"
        gcode += linenumber() + "[Output Time:" + str(now) + "]\n\n"

    # Write the preamble
    if OUTPUT_COMMENTS:
        gcode += linenumber() + "[Begin Preamble]\n"
    for line in PREAMBLE.splitlines(False):
        gcode += linenumber() + line + "\n"
    gcode += linenumber() + UNITS + "\t\t[Units: " + UNIT_FORMAT + "]\n\n"

    for obj in objectslist:

        # Skip inactive operations
        if hasattr(obj, 'Active'):
            if not obj.Active:
                continue
        if hasattr(obj, 'Base') and hasattr(obj.Base, 'Active'):
            if not obj.Base.Active:
                continue

        # remove everything related to job as per:
        # https://forum.freecadweb.org/viewtopic.php?p=490458&sid=3cea99e5af6ca2a370869eac081fffe8#p490458

        # fetch machine details
        # job = PathUtils.findParentJob(obj)

        myMachine = 'not set'

        # if hasattr(job, "MachineName"):
        #     myMachine = job.MachineName

        # if hasattr(job, "MachineUnits"):
        #     if job.MachineUnits == "Metric":
        #         UNITS = "G21"
        #         UNIT_FORMAT = 'mm'
        #         UNIT_SPEED_FORMAT = 'mm/min'
        #     else:
        #         UNITS = "G20"
        #         UNIT_FORMAT = 'in'
        #         UNIT_SPEED_FORMAT = 'in/min'

        # do the pre_op
        if OUTPUT_COMMENTS:
            gcode += linenumber() + "[Operation: " + obj.Label + \
                " (" + UNIT_SPEED_FORMAT + ")]\n"
        for line in PRE_OPERATION.splitlines(True):
            gcode += linenumber() + line + "\n"

        # get coolant mode
        coolantMode = 'None'
        if hasattr(obj, "CoolantMode") or hasattr(obj, 'Base') and  hasattr(obj.Base, "CoolantMode"):
            if hasattr(obj, "CoolantMode"):
                coolantMode = obj.CoolantMode
            else:
                coolantMode = obj.Base.CoolantMode

        # turn coolant on if required
        if OUTPUT_COMMENTS:
            if not coolantMode == 'None':
                gcode += linenumber() + '[Coolant On:' + coolantMode + ']\n'
        if coolantMode == 'Flood':
            gcode  += linenumber() + 'M8' + '\n'
        if coolantMode == 'Mist':
            gcode += linenumber() + 'M7' + '\n'

        # process the operation gcode
        gcode += parse(obj)

        # do the post_op
        for line in POST_OPERATION.splitlines(True):
            gcode += linenumber() + line + ""
        gcode += "\n"

        # turn coolant off if required
        if not coolantMode == 'None':
            if OUTPUT_COMMENTS:
                gcode += linenumber() + '[Coolant Off:' + coolantMode + ']\n'
            gcode  += linenumber() +'M9' + '\n'

    # do the post_amble
    if OUTPUT_COMMENTS:
        gcode += "[Postamble]\n"
    for line in POSTAMBLE.splitlines(True):
        gcode += linenumber() + line

    if FreeCAD.GuiUp and SHOW_EDITOR:
        final = gcode
        if len(gcode) > 100000:
            print("Skipping editor since output is greater than 100kb")
        else:
            dia = PostUtils.GCodeEditorDialog()
            dia.editor.setText(gcode)
            result = dia.exec_()
            if result:
                final = dia.editor.toPlainText()
    else:
        final = gcode

    print("done postprocessing.")

    if not filename == '-':
        gfile = pythonopen(filename, "w")
        gfile.write(final)
        gfile.close()

    return final


def linenumber():
    # pylint: disable=global-statement
    global LINENR
    if OUTPUT_LINE_NUMBERS is True:
        LINENR += 10
        return "N" + str(LINENR) + " "
    return ""


def parse(pathobj):
    # pylint: disable=global-statement
    global PRECISION
    global MODAL
    global OUTPUT_DOUBLES
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT
    global SKIP_FIRST_TOOLCHANGE
    global first_tool_change_skipped

    out = ""
    lastcommand = None
    precision_string = '.' + str(PRECISION) + 'f'
    currLocation = {}  # keep track for no doubles

    # the order of parameters
    # linuxcnc doesn't want K properties on XY plane  Arcs need work.
    params = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'S', 'T', 'Q', 'R', 'F', 'L', 'H', 'D', 'P']
    firstmove = Path.Command("G0", {"X": -1, "Y": -1, "Z": -1, "F": 0.0})
    currLocation.update(firstmove.Parameters)  # set First location Parameters

    if hasattr(pathobj, "Group"):  # We have a compound or project.
        # if OUTPUT_COMMENTS:
        #     out += linenumber() + "(compound: " + pathobj.Label + ")\n"
        for p in pathobj.Group:
            out += parse(p)
        return out
    else:  # parsing simple path

        # groups might contain non-path things like stock.
        if not hasattr(pathobj, "Path"):
            return out

        # if OUTPUT_COMMENTS:
        #     out += linenumber() + "(" + pathobj.Label + ")\n"

        for c in pathobj.Path.Commands:

            outstring = []
            command = c.Name
            outstring.append(command)

            # if modal: suppress the command if it is the same as the last one
            if MODAL is True:
                if command == lastcommand:
                    outstring.pop(0)

            if c.Name[0] == '(': # command is a comment
                if not OUTPUT_COMMENTS:
                    continue
                else:
                    outstring.pop()
                    outstring.append(command.replace('(', '[').replace(')', ']'))

            # intercept G99 -- not supported by WinCNC
            if c.Name == "G99":
                continue

            # Now add the remaining parameters in order
            for param in params:
                if param in c.Parameters:
                    if param == 'F' and (currLocation[param] != c.Parameters[param] or OUTPUT_DOUBLES):
                        if c.Name not in ["G0", "G00"]:  # linuxcnc doesn't use rapid speeds
                            speed = Units.Quantity(c.Parameters['F'], FreeCAD.Units.Velocity)
                            if speed.getValueAs(UNIT_SPEED_FORMAT) > 0.0:
                                outstring.append(param + format(float(speed.getValueAs(UNIT_SPEED_FORMAT)), precision_string))
                        else:
                            continue
                    elif param == 'T':
                        outstring.append(param + str(int(c.Parameters['T'])))
                    elif param == 'H':
                        outstring.append(param + str(int(c.Parameters['H'])))
                    elif param == 'D':
                        outstring.append(param + str(int(c.Parameters['D'])))
                    elif param == 'S':
                        outstring.append(param + str(int(c.Parameters['S'])))
                    else:
                        if (not OUTPUT_DOUBLES) and (param in currLocation) and (currLocation[param] == c.Parameters[param]):
                            continue
                        else:
                            pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                            outstring.append(
                                param + format(float(pos.getValueAs(UNIT_FORMAT)), precision_string))

            # store the latest command
            lastcommand = command
            currLocation.update(c.Parameters)

            # Check for Tool Change:
            if command == 'M6':
                # since we are assuming that the operator has already measured the tool
                # and zeroed the tooltip before starting the job, we do not run the tool
                # change operation for the initial tool.
                if SKIP_FIRST_TOOLCHANGE and not first_tool_change_skipped:
                    first_tool_change_skipped = True
                    continue

                for line in PRE_TOOL_CHANGE.splitlines(True):
                    out += linenumber() + line

                out += TOOL_CHANGE_NOTIFICATION.format(tool_num = pathobj.Tool.Label)

                for line in TOOL_CHANGE.splitlines(True):
                    out += linenumber() + line

                # add height offset
                # M37 (used in the TOOL_CHANGE gcodes) enables G43 in WinCNC, so we
                # don't have to explicitly set it. (see p.32)
                # if USE_TLO:
                #     tool_height = '\nG43 H' + str(int(c.Parameters['T']))
                #     out += linenumber() + tool_height + "\n"

                # do not actually add the M6 command: WinCNC doesn't recognize it.
                continue


            if command == "message":
                if OUTPUT_COMMENTS is False:
                    out = []
                else:
                    outstring.pop(0)  # remove the command

            # prepend a line number and append a newline
            if len(outstring) >= 1:
                if OUTPUT_LINE_NUMBERS:
                    outstring.insert(0, (linenumber()))

                # append the line to the final output
                for w in outstring:
                    out += w + COMMAND_SPACE
                # Note: Do *not* strip `out`, since that forces the allocation
                # of a contiguous string & thus quadratic complexity.
                out += "\n"

        return out

# print(__name__ + " gcode postprocessor loaded.")
