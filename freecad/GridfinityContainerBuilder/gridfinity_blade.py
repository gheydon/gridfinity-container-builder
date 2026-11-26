"""Parametric blade/tool holder object for FreeCAD (``Part::FeaturePython``).

A folded tool stored on edge (angle finder, caliper, folding rule): a keyhole
pocket with a shallow head+neck recess and a deep narrow blade slot, carved into
a gridfinity container. Defaults match the GemRed 82305 (Printables 430136)."""

from __future__ import annotations

import os

import FreeCAD as App

from gridfinity_geometry import GEMRED_DEFAULTS, build_blade_holder


class GridfinityBladeHolder:
    def __init__(self, obj):
        obj.Proxy = self
        d = GEMRED_DEFAULTS
        self._int(obj, "GridX", d["grid_x"], 1, 100, "Gridfinity", "Footprint width in 42 mm units")
        self._int(obj, "GridY", d["grid_y"], 1, 100, "Gridfinity", "Footprint depth in 42 mm units")
        self._int(obj, "HeightUnits", d["height_units"], 2, 100, "Gridfinity", "Height in 7 mm units")
        self._bool(obj, "StackingLip", True, "Gridfinity", "Add the gridfinity stacking lip")
        self._bool(obj, "RimGroove", True, "Gridfinity", "Recessed Pred ring below the lip")
        self._len(obj, "Length", d["length"], "Blade Pocket", "Overall pocket length (head end to slot end)")
        self._len(obj, "HeadWidth", d["head_w"], "Blade Pocket", "Width of the round head recess")
        self._len(obj, "HeadLength", d["head_len"], "Blade Pocket", "Length of the head recess")
        self._len(obj, "NeckWidth", d["neck_w"], "Blade Pocket", "Width of the neck section")
        self._len(obj, "NeckLength", d["neck_len"], "Blade Pocket", "Length of the neck section")
        self._len(obj, "SlotWidth", d["slot_w"], "Blade Pocket", "Width of the blade slot")
        self._len(obj, "HeadDepth", d["head_depth"], "Blade Pocket", "Depth of the head+neck recess")
        self._len(obj, "SlotDepth", d["slot_depth"], "Blade Pocket", "Depth of the deep blade slot (>= HeadDepth)")
        self._len(obj, "DeepSlotStart", d["deep_from"], "Blade Pocket", "Where the deep slot begins, from the head end")
        if not hasattr(obj, "Size"):
            obj.addProperty("App::PropertyString", "Size", "Gridfinity", "Overall size in mm (read-only)")
            obj.setEditorMode("Size", 1)

    def _int(self, obj, name, val, lo, hi, grp, doc):
        if not hasattr(obj, name):
            obj.addProperty("App::PropertyIntegerConstraint", name, grp, doc)
            setattr(obj, name, (val, lo, hi, 1))

    def _bool(self, obj, name, val, grp, doc):
        if not hasattr(obj, name):
            obj.addProperty("App::PropertyBool", name, grp, doc); setattr(obj, name, val)

    def _len(self, obj, name, val, grp, doc):
        if not hasattr(obj, name):
            obj.addProperty("App::PropertyLength", name, grp, doc); setattr(obj, name, val)

    def execute(self, obj):
        obj.Shape = build_blade_holder(
            int(obj.GridX), int(obj.GridY), int(obj.HeightUnits),
            float(obj.Length), float(obj.HeadWidth), float(obj.HeadLength),
            float(obj.NeckWidth), float(obj.NeckLength), float(obj.SlotWidth),
            float(obj.HeadDepth), float(obj.SlotDepth), float(obj.DeepSlotStart),
            bool(obj.StackingLip), bool(obj.RimGroove))
        if hasattr(obj, "Size"):
            bb = obj.Shape.BoundBox
            obj.Size = "%.1f x %.1f x %.1f mm" % (bb.XLength, bb.YLength, bb.ZLength)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderBladeHolder:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "icons", "gfcb.svg")

    def attach(self, vobj):
        self.Object = vobj.Object

    def dumps(self):
        return None

    def loads(self, state):
        return None


def create_blade_holder(doc=None, **props):
    if doc is None:
        doc = App.activeDocument() or App.newDocument("Gridfinity")
    obj = doc.addObject("Part::FeaturePython", "BladeHolder")
    GridfinityBladeHolder(obj)
    if App.GuiUp:
        ViewProviderBladeHolder(obj.ViewObject)
    for k, v in props.items():
        setattr(obj, k, v)
    doc.recompute()
    return obj
