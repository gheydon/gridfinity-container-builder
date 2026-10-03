"""Gridfinity Container workbench registration (GUI)."""

import FreeCADGui as Gui


class GridfinityContainerWorkbench(Gui.Workbench):
    """Parametric gridfinity containers, ported from the gridfinity-container-builder design."""

    import os
    MenuText = "Gridfinity Container"
    ToolTip = "Parametric gridfinity container shells"
    Icon = os.path.join(os.path.dirname(__file__), "icons", "gfcb.svg")

    def Initialize(self):
        import gridfinity_commands  # noqa: F401 — registers the commands
        self.commands = ["GFCB_CreateBin"]
        self.appendToolbar("Gridfinity Container", self.commands)
        self.appendMenu("Gridfinity Container", self.commands)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(GridfinityContainerWorkbench())
