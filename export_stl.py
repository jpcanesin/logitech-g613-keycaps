"""Export STLs for every key from the parametric FreeCAD files.

Reads layout.csv (key order and names) and keys/NNN_<row>_<key>.FCStd. Writes
stl/NNN_<row>_<key>.stl (the cap, with the legend recess) and, for keys with a legend,
stl/NNN_<row>_<key>_legend.stl (the inlay). Load both into the slicer as one multi-part
object and give the legend its own filament for a two-colour print. Exports whatever the
FreeCAD files currently contain, edits included.

Run headless:
  ~/tools/FreeCAD.AppImage freecadcmd -c "exec(open('/home/jpcanesin/Documents/3d/keyboard/export_stl.py').read())"
"""
import csv
import os

import FreeCAD as App
import MeshPart
import Part

HERE = "/home/jpcanesin/Documents/3d/keyboard"
LINEAR_DEFLECTION = 0.01  # mm, max distance between the mesh and the true surface
ANGULAR_DEFLECTION = 0.1  # rad


def write(shape, path):
    MeshPart.meshFromShape(Shape=shape, LinearDeflection=LINEAR_DEFLECTION,
                           AngularDeflection=ANGULAR_DEFLECTION).write(path)


def main():
    layout = list(csv.DictReader(open(os.path.join(HERE, "layout.csv"))))
    out = os.path.join(HERE, "stl")
    os.makedirs(out, exist_ok=True)
    for i, k in enumerate(layout, 1):
        name = "%03d_%s_%s" % (i, k["row"], k["key"])
        doc = App.openDocument(os.path.join(HERE, "keys", name + ".FCStd"))
        doc.recompute()
        cap = doc.getObject("Cap") or doc.getObject("Body")  # keys without a legend only link the shape
        write(Part.getShape(cap), os.path.join(out, name + ".stl"))
        legend = doc.getObject("Inlay")
        if legend is not None:
            write(legend.Shape, os.path.join(out, name + "_legend.stl"))
        App.closeDocument(doc.Name)
    print("done:", len(layout), "keys in", out, flush=True)


main()
