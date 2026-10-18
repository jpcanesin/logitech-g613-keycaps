"""Export one STL per key from the parametric FreeCAD files.

Reads keyboard.FCStd (each key is a link to the Keycap in its shapes/*.FCStd) and layout.csv
(key order and names). Writes stl/NNN_<row>_<key>.stl; keys that share a shape file are meshed
once and copied. Exports whatever the FreeCAD files currently contain, edits included.

Run headless:
  ~/tools/FreeCAD.AppImage freecadcmd -c "exec(open('/home/jpcanesin/Documents/3d/keyboard/export_stl.py').read())"
"""
import csv
import os
import shutil

import FreeCAD as App
import MeshPart

HERE = "/home/jpcanesin/Documents/3d/keyboard"
LINEAR_DEFLECTION = 0.01  # mm, max distance between the mesh and the true surface
ANGULAR_DEFLECTION = 0.1  # rad


def main():
    layout = list(csv.DictReader(open(os.path.join(HERE, "layout.csv"))))
    doc = App.openDocument(os.path.join(HERE, "keyboard.FCStd"))
    for d in App.listDocuments().values():
        d.recompute()
    links = {o.Label: o for o in doc.Objects if o.TypeId == "App::Link"}
    out = os.path.join(HERE, "stl")
    os.makedirs(out, exist_ok=True)
    meshed = {}
    for i, k in enumerate(layout, 1):
        target = links["%s_%s" % (k["row"], k["key"])].LinkedObject
        path = os.path.join(out, "%03d_%s_%s.stl" % (i, k["row"], k["key"]))
        src = target.Document.FileName
        if src in meshed:
            shutil.copyfile(meshed[src], path)
            continue
        shape = target.Shape
        MeshPart.meshFromShape(Shape=shape, LinearDeflection=LINEAR_DEFLECTION,
                               AngularDeflection=ANGULAR_DEFLECTION).write(path)
        meshed[src] = path
        print("meshed", os.path.basename(src), "valid", shape.isValid(), flush=True)
    print("done:", len(layout), "keys in", out, flush=True)


main()
