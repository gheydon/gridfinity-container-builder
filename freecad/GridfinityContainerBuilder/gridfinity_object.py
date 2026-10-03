"""Parametric Gridfinity bin object for FreeCAD (``Part::FeaturePython``)."""

from __future__ import annotations

import FreeCAD as App

from gridfinity_geometry import make_shell


class GridfinityBin:
    """A parametric gridfinity container shell. Edit the properties in the
    data panel and the solid rebuilds on recompute."""

    def __init__(self, obj):
        obj.Proxy = self
        if not hasattr(obj, "GridX"):
            obj.addProperty("App::PropertyIntegerConstraint", "GridX", "Gridfinity",
                            "Footprint width in 42 mm grid units")
            obj.GridX = (2, 1, 100, 1)
        if not hasattr(obj, "GridY"):
            obj.addProperty("App::PropertyIntegerConstraint", "GridY", "Gridfinity",
                            "Footprint depth in 42 mm grid units")
            obj.GridY = (1, 1, 100, 1)
        if not hasattr(obj, "HeightUnits"):
            obj.addProperty("App::PropertyIntegerConstraint", "HeightUnits", "Gridfinity",
                            "Height in 7 mm units (excludes the stacking lip)")
            obj.HeightUnits = (6, 2, 100, 1)
        if not hasattr(obj, "StackingLip"):
            obj.addProperty("App::PropertyBool", "StackingLip", "Gridfinity",
                            "Add the gridfinity stacking lip on the rim")
            obj.StackingLip = True
        if not hasattr(obj, "Hollow"):
            obj.addProperty("App::PropertyBool", "Hollow", "Gridfinity",
                            "Carve the interior (empty bin). Off = solid block")
            obj.Hollow = True
        if not hasattr(obj, "RimGroove"):
            obj.addProperty("App::PropertyBool", "RimGroove", "Gridfinity",
                            "Recessed Pred ring around the outer wall below the lip")
            obj.RimGroove = True
        if not hasattr(obj, "BaseHollows"):
            obj.addProperty("App::PropertyBool", "BaseHollows", "Gridfinity",
                            "Pred filament-saving kite pockets + corner tombstones under each foot")
            obj.BaseHollows = True
        if not hasattr(obj, "MagnetHoles"):
            obj.addProperty("App::PropertyBool", "MagnetHoles", "Gridfinity",
                            "6.5 mm magnet holes (x4/cell); replaces the tombstones")
            obj.MagnetHoles = False
        if not hasattr(obj, "ScrewHoles"):
            obj.addProperty("App::PropertyBool", "ScrewHoles", "Gridfinity",
                            "3 mm screw holes (x4 per cell) in the base")
            obj.ScrewHoles = False
        # read-only mm readout so the actual box size is visible
        if not hasattr(obj, "Size"):
            obj.addProperty("App::PropertyString", "Size", "Gridfinity",
                            "Overall size W x D x H in mm (read-only)")
            obj.setEditorMode("Size", 1)  # read-only

    def execute(self, obj):
        gx = int(obj.GridX)
        gy = int(obj.GridY)
        hu = int(obj.HeightUnits)
        obj.Shape = make_shell(gx, gy, hu, bool(obj.StackingLip), bool(obj.Hollow),
                               bool(obj.RimGroove), bool(obj.BaseHollows),
                               bool(obj.MagnetHoles), bool(obj.ScrewHoles))
        if hasattr(obj, "Size"):
            bb = obj.Shape.BoundBox
            obj.Size = "%.1f x %.1f x %.1f mm" % (bb.XLength, bb.YLength, bb.ZLength)

    # keep the object loadable across save/restore without the module on the path
    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderGridfinityBin:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        import os
        return os.path.join(os.path.dirname(__file__), "icons", "gfcb.svg")

    def attach(self, vobj):
        self.Object = vobj.Object

    def dumps(self):
        return None

    def loads(self, state):
        return None


def create_gridfinity_bin(doc=None, **props):
    """Create a GridfinityBin in ``doc`` (or the active/new document)."""
    if doc is None:
        doc = App.activeDocument() or App.newDocument("Gridfinity")
    obj = doc.addObject("Part::FeaturePython", "GridfinityBin")
    GridfinityBin(obj)
    if App.GuiUp:
        ViewProviderGridfinityBin(obj.ViewObject)
    for k, v in props.items():
        setattr(obj, k, v)
    doc.recompute()
    return obj
