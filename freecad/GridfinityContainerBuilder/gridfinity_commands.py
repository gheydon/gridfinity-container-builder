"""GUI commands for the Gridfinity Container workbench."""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

from gridfinity_object import create_gridfinity_bin

_ICON = os.path.join(os.path.dirname(__file__), "icons", "gfcb.svg")


def _show_dialog():
    """Modal dialog to pick the bin dimensions. Returns a props dict or None."""
    try:
        from PySide import QtWidgets
    except Exception:
        return {}  # no Qt: just create a default bin

    dlg = QtWidgets.QDialog(Gui.getMainWindow())
    dlg.setWindowTitle("New Gridfinity Bin")
    form = QtWidgets.QFormLayout(dlg)

    def spin(lo, hi, val):
        s = QtWidgets.QSpinBox(); s.setRange(lo, hi); s.setValue(val); return s

    gx = spin(1, 100, 2); gy = spin(1, 100, 1); hu = spin(2, 100, 6)
    lip = QtWidgets.QCheckBox(); lip.setChecked(True)
    hollow = QtWidgets.QCheckBox(); hollow.setChecked(True)
    fill = QtWidgets.QCheckBox(); fill.setChecked(False)
    groove = QtWidgets.QCheckBox(); groove.setChecked(True)
    hollows = QtWidgets.QCheckBox(); hollows.setChecked(True)
    mag = QtWidgets.QCheckBox(); mag.setChecked(False)
    scr = QtWidgets.QCheckBox(); scr.setChecked(False)
    size = QtWidgets.QLabel()

    form.addRow("Grid X (x 42 mm):", gx)
    form.addRow("Grid Y (x 42 mm):", gy)
    form.addRow("Height (x 7 mm):", hu)
    form.addRow("Stacking lip:", lip)
    form.addRow("Hollow interior:", hollow)
    form.addRow("Fill inside (carve blank):", fill)
    form.addRow("Rim groove:", groove)
    form.addRow("Base hollows:", hollows)
    form.addRow("Magnet holes:", mag)
    form.addRow("Screw holes:", scr)
    form.addRow("Overall size:", size)

    def upd(*_):
        w = 42 * gx.value() - 0.5
        l = 42 * gy.value() - 0.5
        h = 7 * hu.value()
        size.setText("%.1f x %.1f x %.1f mm%s" % (w, l, h, " (+ lip)" if lip.isChecked() else ""))
    for s in (gx, gy, hu):
        s.valueChanged.connect(upd)
    lip.toggled.connect(upd)
    upd()

    box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    box.accepted.connect(dlg.accept); box.rejected.connect(dlg.reject)
    form.addRow(box)

    if dlg.exec_() != QtWidgets.QDialog.Accepted:
        return None
    return {
        "GridX": gx.value(), "GridY": gy.value(), "HeightUnits": hu.value(),
        "StackingLip": lip.isChecked(), "Hollow": hollow.isChecked(),
        "FillInside": fill.isChecked(),
        "RimGroove": groove.isChecked(), "BaseHollows": hollows.isChecked(),
        "MagnetHoles": mag.isChecked(), "ScrewHoles": scr.isChecked(),
    }


class CreateGridfinityBin:
    """Add a parametric gridfinity bin shell to the active document."""

    def GetResources(self):
        return {
            "Pixmap": _ICON,
            "MenuText": "New Gridfinity Bin",
            "ToolTip": "Create a parametric gridfinity container shell "
                       "(grid size, height, lip, holes).",
        }

    def Activated(self):
        props = _show_dialog()
        if props is None:
            return  # cancelled
        create_gridfinity_bin(**props)
        if Gui.ActiveDocument:
            view = Gui.ActiveDocument.ActiveView
            view.viewIsometric()
            view.fitAll()

    def IsActive(self):
        return True


Gui.addCommand("GFCB_CreateBin", CreateGridfinityBin())
