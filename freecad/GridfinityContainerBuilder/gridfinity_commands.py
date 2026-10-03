"""GUI commands for the Gridfinity Container workbench."""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

from gridfinity_object import create_gridfinity_bin

_ICON = os.path.join(os.path.dirname(__file__), "icons", "gfcb.svg")


class CreateGridfinityBin:
    """Add a parametric gridfinity bin shell to the active document."""

    def GetResources(self):
        return {
            "Pixmap": _ICON,
            "MenuText": "New Gridfinity Bin",
            "ToolTip": "Create a parametric gridfinity container shell "
                       "(grid size, height, stacking lip, hollow).",
        }

    def Activated(self):
        create_gridfinity_bin()
        if Gui.ActiveDocument:
            view = Gui.ActiveDocument.ActiveView
            view.viewIsometric()
            view.fitAll()

    def IsActive(self):
        return True


Gui.addCommand("GFCB_CreateBin", CreateGridfinityBin())
