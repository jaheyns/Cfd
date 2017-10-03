# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2016 - Bernd Hahnebach <bernd@bimstatik.org>            *
# *   Copyright (c) 2017 - Alfred Bogaers (CSIR) <abogaers@csir.co.za>      *
# *   Copyright (c) 2017 - Johan Heyns (CSIR) <jheyns@csir.co.za>           *
# *   Copyright (c) 2017 - Oliver Oxtoby (CSIR) <ooxtoby@csir.co.za>        *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""
Gmsh meshing UI for CFD analysis object. Adapted from equivalent classes
in FEM module but removes the option to generate second-order
mesh cells.
"""

from __future__ import print_function

__title__ = "_TaskPanelCfdMeshCart"
__author__ = "Bernd Hahnebach"
__url__ = "http://www.freecadweb.org"

import FreeCAD
import os
import sys
import os.path
import platform
# from PyObjects import _FemMeshGmsh
import _CfdMeshCart
import time
import tempfile
import CfdTools
from CfdTools import inputCheckAndStore, setInputFieldQuantity

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore
    from PySide import QtCore
    from PySide import QtGui
    from PySide.QtCore import Qt
    from PySide.QtGui import QApplication
    import FemGui


class _TaskPanelCfdMeshCart:
    """ The TaskPanel for editing References property of CfdMeshCart objects and creation of new CFD mesh """
    def __init__(self, obj):
        self.mesh_obj = obj
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__), "TaskPanelCfdMeshCart.ui"))

        self.mesh_process = QtCore.QProcess()
        self.Timer = QtCore.QTimer()
        self.console_message_cart = ''
        self.error_message = ''
        self.cart_mesh = []
        self.paraviewScriptName = ""

        QtCore.QObject.connect(self.mesh_process, QtCore.SIGNAL("readyReadStandardOutput()"), self.read_output)
        QtCore.QObject.connect(self.mesh_process, QtCore.SIGNAL("readyReadStandardError()"), self.read_output)
        QtCore.QObject.connect(self.mesh_process, QtCore.SIGNAL("finished(int)"), self.mesh_finished)

        QtCore.QObject.connect(self.form.if_max, QtCore.SIGNAL("valueChanged(Base::Quantity)"), self.max_changed)
        QtCore.QObject.connect(self.form.if_pointInMeshX, QtCore.SIGNAL("valueChanged(Base::Quantity)"),
                               self.pointInMeshX_changed)
        QtCore.QObject.connect(self.form.if_pointInMeshY, QtCore.SIGNAL("valueChanged(Base::Quantity)"),
                               self.pointInMeshY_changed)
        QtCore.QObject.connect(self.form.if_pointInMeshZ, QtCore.SIGNAL("valueChanged(Base::Quantity)"),
                               self.pointInMeshZ_changed)
        QtCore.QObject.connect(self.form.if_cellsbetweenlevels, QtCore.SIGNAL("valueChanged(int)"),
                               self.cellsbetweenlevels_changed)
        QtCore.QObject.connect(self.form.if_edgerefine, QtCore.SIGNAL("valueChanged(int)"), self.edgerefine_changed)
        QtCore.QObject.connect(self.form.cb_dimension, QtCore.SIGNAL("activated(int)"), self.choose_dimension)
        QtCore.QObject.connect(self.form.cb_utility, QtCore.SIGNAL("activated(int)"), self.choose_utility)
        QtCore.QObject.connect(self.Timer, QtCore.SIGNAL("timeout()"), self.update_timer_text)

        self.open_paraview = QtCore.QProcess()

        QtCore.QObject.connect(self.form.pb_run_mesh, QtCore.SIGNAL("clicked()"), self.runMeshProcess)
        QtCore.QObject.connect(self.form.pb_stop_mesh, QtCore.SIGNAL("clicked()"), self.killMeshProcess)
        QtCore.QObject.connect(self.form.pb_paraview, QtCore.SIGNAL("clicked()"), self.openParaview)
        QtCore.QObject.connect(self.form.pb_searchPointInMesh, QtCore.SIGNAL("clicked()"), self.searchPointInMesh)
        self.form.pb_stop_mesh.setEnabled(False)
        self.form.pb_paraview.setEnabled(False)
        self.form.snappySpecificProperties.setVisible(False)

        # Limit mesh dimensions to 3D solids
        self.form.cb_dimension.addItems(_CfdMeshCart._CfdMeshCart.known_element_dimensions)
        self.form.cb_utility.addItems(_CfdMeshCart._CfdMeshCart.known_mesh_utility)

        self.form.if_max.setToolTip("Select 0 to use default value")
        self.form.pb_searchPointInMesh.setToolTip("Specify below a point vector inside of the mesh or press 'Search' "
                                                  "to try and automatically find a point")
        self.form.if_cellsbetweenlevels.setToolTip("Number of cells between each of level of refinement.")
        self.form.if_edgerefine.setToolTip("Number of refinement levels for all edges.")

        tmpdir = tempfile.gettempdir()
        self.meshCaseDir = os.path.join(tmpdir, 'meshCase')

        self.get_mesh_params()
        self.order = '1st'  # Default to first order for CFD mesh
        self.get_active_analysis()
        self.update()

    def getStandardButtons(self):
        return int(QtGui.QDialogButtonBox.Close)
        # def reject() is called on close button
        # def accept() in no longer needed, since there is no OK button

    def reject(self):
        self.mesh_obj.CharacteristicLengthMax = self.clmax
        self.mesh_obj.PointInMesh = self.PointInMesh
        self.mesh_obj.CellsBetweenLevels = self.cellsbetweenlevels
        self.mesh_obj.EdgeRefinement = self.edgerefine
        self.set_mesh_params()

        FreeCADGui.ActiveDocument.resetEdit()
        FreeCAD.ActiveDocument.recompute()
        return True

    def get_mesh_params(self):
        self.clmax = self.mesh_obj.CharacteristicLengthMax
        self.PointInMesh = self.mesh_obj.PointInMesh.copy()
        self.cellsbetweenlevels = self.mesh_obj.CellsBetweenLevels
        self.edgerefine = self.mesh_obj.EdgeRefinement
        self.dimension = self.mesh_obj.ElementDimension
        self.utility = self.mesh_obj.MeshUtility
        if self.utility == "snappyHexMesh":
            self.form.snappySpecificProperties.setVisible(True)
        elif self.utility == "cfMesh":
            self.form.snappySpecificProperties.setVisible(False)

    def set_mesh_params(self):
        self.mesh_obj.CharacteristicLengthMax = self.clmax
        self.mesh_obj.PointInMesh = self.PointInMesh
        self.mesh_obj.CellsBetweenLevels = self.cellsbetweenlevels
        self.mesh_obj.EdgeRefinement = self.edgerefine
        self.mesh_obj.ElementDimension = self.dimension
        self.mesh_obj.MeshUtility = self.form.cb_utility.currentText()

    def update(self):
        """ Fills the widgets """
        setInputFieldQuantity(self.form.if_max, self.clmax)
        setInputFieldQuantity(self.form.if_pointInMeshX, str(self.PointInMesh.get('x')) + "mm")
        setInputFieldQuantity(self.form.if_pointInMeshY, str(self.PointInMesh.get('y')) + "mm")
        setInputFieldQuantity(self.form.if_pointInMeshZ, str(self.PointInMesh.get('z')) + "mm")
        self.form.if_cellsbetweenlevels.setValue(self.cellsbetweenlevels)
        self.form.if_edgerefine.setValue(self.edgerefine)

        index_dimension = self.form.cb_dimension.findText(self.dimension)
        self.form.cb_dimension.setCurrentIndex(index_dimension)
        index_utility = self.form.cb_utility.findText(self.utility)
        self.form.cb_utility.setCurrentIndex(index_utility)

    def console_log(self, message="", color="#000000"):
        self.console_message_cart = self.console_message_cart \
                                    + '<font color="#0000FF">{0:4.1f}:</font> <font color="{1}">{2}</font><br>'.\
                                    format(time.time()
                                    - self.Start, color, message.encode('utf-8', 'replace'))
        self.form.te_output.setText(self.console_message_cart)
        self.form.te_output.moveCursor(QtGui.QTextCursor.End)

    def update_timer_text(self):
        self.form.l_time.setText('Time: {0:4.1f}'.format(time.time() - self.Start))

    def max_changed(self, base_quantity_value):
        self.clmax = base_quantity_value

    def pointInMeshX_changed(self, base_quantity_value):
        inputCheckAndStore(base_quantity_value, "mm", self.PointInMesh, 'x')

    def pointInMeshY_changed(self, base_quantity_value):
        inputCheckAndStore(base_quantity_value, "mm", self.PointInMesh, 'y')

    def pointInMeshZ_changed(self, base_quantity_value):
        inputCheckAndStore(base_quantity_value, "mm", self.PointInMesh, 'z')

    def cellsbetweenlevels_changed(self, base_quantity_value):
        self.cellsbetweenlevels = base_quantity_value

    def edgerefine_changed(self, base_quantity_value):
        self.edgerefine = base_quantity_value

    def choose_dimension(self, index):
        if index < 0:
            return
        self.form.cb_dimension.setCurrentIndex(index)
        self.dimension = str(self.form.cb_dimension.itemText(index))  # form returns unicode

    def choose_utility(self, index):
        if index < 0:
            return
        self.utility = self.form.cb_utility.currentText()
        if self.utility == "snappyHexMesh":
            self.form.snappySpecificProperties.setVisible(True)
        elif self.utility == "cfMesh":
            self.form.snappySpecificProperties.setVisible(False)

    def runMeshProcess(self):
        FreeCADGui.doCommand("\nFreeCAD.ActiveDocument.{}.CharacteristicLengthMax "
                             "= '{}'".format(self.mesh_obj.Name, self.clmax))
        FreeCADGui.doCommand("FreeCAD.ActiveDocument.{}.MeshUtility "
                             "= '{}'".format(self.mesh_obj.Name, self.utility))
        FreeCADGui.doCommand("FreeCAD.ActiveDocument.{}.CellsBetweenLevels "
                             "= {}".format(self.mesh_obj.Name, self.cellsbetweenlevels))
        FreeCADGui.doCommand("FreeCAD.ActiveDocument.{}.EdgeRefinement "
                             "= {}".format(self.mesh_obj.Name, self.edgerefine))
        FreeCADGui.doCommand("FreeCAD.ActiveDocument.{}.PointInMesh "
                             "= {}".format(self.mesh_obj.Name, self.PointInMesh))

        self.console_message_cart = ''
        self.Start = time.time()
        self.Timer.start()
        self.console_log("Starting cut-cell Cartesian meshing ...")
        # try:
        #     self.get_active_analysis()
        #     self.set_mesh_params()
        #     import CfdCartTools  # Fresh init before remeshing
        #     self.cart_mesh = CfdCartTools.CfdCartTools(self.obj)
        #     cart_mesh = self.cart_mesh
        #     self.form.if_max.setText(str(cart_mesh.get_clmax()))
        #     print("\nStarting cut-cell Cartesian meshing ...\n")
        #     print('  Part to mesh: Name --> '
        #           + cart_mesh.part_obj.Name + ',  Label --> '
        #           + cart_mesh.part_obj.Label + ', ShapeType --> '
        #           + cart_mesh.part_obj.Shape.ShapeType)
        #     print('  CharacteristicLengthMax: ' + str(cart_mesh.clmax))
        #     # print('  CharacteristicLengthMin: ' + str(cart_mesh.clmin))
        #     # print('  ElementOrder: ' + cart_mesh.order)
        #     cart_mesh.get_dimension()
        #     cart_mesh.get_tmp_file_paths(self.utility)
        #     cart_mesh.setupMeshCaseDir()
        #     cart_mesh.get_group_data()
        #     cart_mesh.get_region_data()
        #     cart_mesh.write_part_file()
        #     cart_mesh.setupMeshDict(self.utility)
        #     cart_mesh.createMeshScript(run_parallel='false',
        #                                mesher_name='cartesianMesh',
        #                                num_proc=1,
        #                                cartMethod=self.utility)  # Extend in time
        #     self.paraviewScriptName = self.cart_mesh.createParaviewScript()
        #     self.runCart(cart_mesh)
        # except Exception as ex:
        #     self.console_log("Error: " + ex.message, '#FF0000')
        #     self.Timer.stop()
        try:
            self.get_active_analysis()
            self.set_mesh_params()
            import CfdCartTools  # Fresh init before remeshing
            self.cart_mesh = CfdCartTools.CfdCartTools(self.obj)
            cart_mesh = self.cart_mesh
            setInputFieldQuantity(self.form.if_max, str(cart_mesh.get_clmax()))
            print("\nStarting cut-cell Cartesian meshing ...\n")
            print('  Part to mesh: Name --> '
                  + cart_mesh.part_obj.Name + ',  Label --> '
                  + cart_mesh.part_obj.Label + ', ShapeType --> '
                  + cart_mesh.part_obj.Shape.ShapeType)
            print('  CharacteristicLengthMax: ' + str(cart_mesh.clmax))
            cart_mesh.get_dimension()
            # cart_mesh.get_tmp_file_paths(self.utility)
            cart_mesh.get_tmp_file_paths()
            cart_mesh.setup_mesh_case_dir()
            cart_mesh.get_group_data()
            cart_mesh.get_region_data()  # Writes region stls so need file structure
            cart_mesh.write_mesh_case()
            self.console_log("Writing the STL files of the part surfaces ...")
            cart_mesh.write_part_file()
            self.console_log("Running {} ...".format(self.utility))
            self.runCart(cart_mesh)
        except Exception as ex:
            self.console_log("Error: " + ex.message, '#FF0000')
            self.Timer.stop()

    def runCart(self, cart_mesh):
        cart_mesh.error = False
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            cmd = CfdTools.makeRunCommand('./Allmesh', self.meshCaseDir, source_env=False)
            FreeCAD.Console.PrintMessage("Executing: " + ' '.join(cmd) + "\n")
            env = QtCore.QProcessEnvironment.systemEnvironment()
            env_vars = CfdTools.getRunEnvironment()
            for key in env_vars:
                env.insert(key, env_vars[key])
            self.mesh_process.setProcessEnvironment(env)
            self.mesh_process.start(cmd[0], cmd[1:])
            if self.mesh_process.waitForStarted():
                self.form.pb_run_mesh.setEnabled(False)  # Prevent user running a second instance
                self.form.pb_stop_mesh.setEnabled(True)
                self.form.pb_paraview.setEnabled(False)
            else:
                self.console_log("Error starting meshing process", "#FF0000")
                cart_mesh.error = True
        finally:
            QApplication.restoreOverrideCursor()

    def killMeshProcess(self):
        self.console_log("Meshing manually stopped")
        self.error_message = 'Meshing interrupted'
        if platform.system() == 'Windows':
            self.mesh_process.kill()
        else:
            self.mesh_process.terminate()
        self.mesh_process.waitForFinished()
        self.form.pb_run_mesh.setEnabled(True)
        self.form.pb_stop_mesh.setEnabled(False)
        self.form.pb_paraview.setEnabled(False)
        self.Timer.stop()

    def read_output(self):
        while self.mesh_process.canReadLine():
            print(str(self.mesh_process.readLine()), end="")  # Avoid displaying on FreeCAD status bar

        # Print any error output to console
        self.mesh_process.setReadChannel(QtCore.QProcess.StandardError)
        while self.mesh_process.canReadLine():
            err = str(self.mesh_process.readLine())
            self.console_log(err, "#FF0000")
            FreeCAD.Console.PrintError(err)
        self.mesh_process.setReadChannel(QtCore.QProcess.StandardOutput)

    def mesh_finished(self, exit_code):
        self.read_output()
        if exit_code == 0:
            self.console_log("Reading mesh")
            cart_mesh = self.cart_mesh
            cart_mesh.read_and_set_new_mesh()  # Only read once meshing has finished
            self.console_log('Meshing completed')
            self.console_log('Tetrahedral representation of the Cartesian mesh is shown')
            self.console_log("Warning: FEM Mesh may not display mesh accurately, please view in Paraview.\n")
            self.form.pb_run_mesh.setEnabled(True)
            self.form.pb_stop_mesh.setEnabled(False)
            self.form.pb_paraview.setEnabled(True)
        else:
            self.console_log("Meshing exited with error", "#FF0000")
            self.form.pb_run_mesh.setEnabled(True)
            self.form.pb_stop_mesh.setEnabled(False)
            self.form.pb_paraview.setEnabled(False)

        self.Timer.stop()
        self.update()
        self.error_message = ''

    def get_active_analysis(self):
        import FemGui
        self.analysis = FemGui.getActiveAnalysis()
        if self.analysis:
            for m in FemGui.getActiveAnalysis().Member:
                if m.Name == self.mesh_obj.Name:
                    print(self.analysis.Name)
                    return
            else:
                # print('Mesh is not member of active analysis, means no group meshing')
                self.analysis = None  # no group meshing
        else:
            # print('No active analyis, means no group meshing')
            self.analysis = None  # no group meshing

    def openParaview(self):
        self.Start = time.time()
        QApplication.setOverrideCursor(Qt.WaitCursor)

        paraview_cmd = "paraview"
        # If using blueCFD, use paraview supplied
        if CfdTools.getFoamRuntime() == 'BlueCFD':
            paraview_cmd = '{}\\..\\AddOns\\ParaView\\bin\\paraview.exe'.format(CfdTools.getFoamDir())
        # Otherwise, the command 'paraview' must be in the path. Possibly make path user-settable.
        # Test to see if it exists, as the exception thrown is cryptic on Windows if it doesn't
        import distutils.spawn
        if distutils.spawn.find_executable(paraview_cmd) is None:
            raise IOError("Paraview executable " + paraview_cmd + " not found in path.")

        self.paraviewScriptName = os.path.join(self.meshCaseDir, 'pvScriptMesh.py')
        arg = '--script={}'.format(self.paraviewScriptName)

        self.console_log("Running " + paraview_cmd + " " +arg)
        self.open_paraview.start(paraview_cmd, [arg])
        QApplication.restoreOverrideCursor()

    def searchPointInMesh(self):
        print ("Searching for an internal vector point ...")
        import CfdCartTools  # Fresh init before remeshing
        self.cart_mesh = CfdCartTools.CfdCartTools(self.obj)
        pointCheck = self.cart_mesh.automatic_inside_point_detect()
        iMPx, iMPy, iMPz = pointCheck
        setInputFieldQuantity(self.form.if_pointInMeshX, str(iMPx) + "mm")
        setInputFieldQuantity(self.form.if_pointInMeshY, str(iMPy) + "mm")
        setInputFieldQuantity(self.form.if_pointInMeshZ, str(iMPz) + "mm")
