# Parametric keycap set

A full keyboard of sculpted keycaps as native, parametric FreeCAD models, generated
from caliper measurements of a physical keycap set.

## Files

| File | Role |
|---|---|
| `keys_to_measure.csv` | Caliper measurements per key shape (source data) |
| `set_measurements.csv` | Measurements shared by the whole set: walls, stems, ribs (source data) |
| `layout.csv` | Every physical key: row, name, which measured shape it uses, grid position |
| `build_native.py` | Builds the FreeCAD files from the three CSVs, fitting each shape |
| `fit_profile.py` | Fits a FreeCAD keycap model to caliper measurements (used by `build_native.py`) |
| `export_stl.py` | Exports one STL per key from the FreeCAD files |
| `set.FCStd` | Spreadsheet `Set` with the values shared by all keys |
| `shapes/<id>.FCStd` | One parametric model per distinct key shape: spreadsheet `Params` + result object `Keycap` |
| `keyboard.FCStd` | The whole keyboard: every key is a link to its shape file, placed on the layout |
| `fitted_shapes.csv` | Fit cache (generated) |
| `stl/` | Print files, `NNN_<row>_<key>.stl` (generated, not versioned) |

## How it fits together

```
keys_to_measure.csv ─┐
set_measurements.csv ├─► build_native.py ──► set.FCStd, shapes/*.FCStd, keyboard.FCStd
layout.csv ──────────┘   (fit_profile.py)    fitted_shapes.csv
                                                     │
                       keyboard.FCStd ─► export_stl.py ─► stl/*.stl
```

The FreeCAD files are the only definition of the geometry. They need neither Python nor
the scripts once generated: open them, edit a spreadsheet cell, recompute.

- `set.FCStd` holds set-wide values. Every shape's `Params` sheet reads them through
  cross-file references (`set#Set.wall`), so changing one there updates every key.
- Each `shapes/<id>.FCStd` holds the key's own values in `Params` (footprint, height, tilt,
  dish, the three wall slants, stem rotation), cells derived from them, and a model built
  from Draft rectangle lofts, a tilted dish cylinder, the cavity cut and PartDesign stems and
  ribs, all driven by expressions.
- `keyboard.FCStd` links every key to its shape file. Keys with the same shape share one
  file (e.g. all letter keys of a row). Opening it also opens the shape files and `set.FCStd`.

## Workflows

**Edit the design in FreeCAD.** Open `keyboard.FCStd` or a shape file, change cells in `Set`
or `Params`, recompute, save. Then export STLs. Do not rerun `build_native.py` afterwards:
it regenerates the FreeCAD files from the CSVs and overwrites such edits.

**Re-measure and regenerate.** Update the CSVs, then run `build_native.py` inside the FreeCAD
GUI (Python console or the MCP `execute_code` tool):

```python
exec(open('/home/jpcanesin/Documents/3d/keyboard/build_native.py').read())
```

It must run in the GUI: files saved by a headless FreeCAD open with every object hidden.
Shapes whose measurements and set values are unchanged come from `fitted_shapes.csv` in
seconds; a full refit of all 20 shapes takes about 5 minutes.

**Export STLs** (headless is fine):

```sh
~/tools/FreeCAD.AppImage freecadcmd -c "exec(open('/home/jpcanesin/Documents/3d/keyboard/export_stl.py').read())"
```

STLs are meshed from the current FreeCAD files with 0.01 mm deflection, rim down on Z=0.

## Conventions

- Key frame: rim on Z=0, +Z up, X left-right, **-Y = back** (the edge nearest the user, at the
  bottom of the legend), +Y = front.
- **Width** is front-back, **length** is left-right.
- **Horizontal stems** are the pair beside each other left and right of the center; **vertical
  stems** are the pair in front of and behind it. Left Ctrl, Right Ctrl and Caps Lock have the
  arrangement turned 90° (`stem_rotated = 1`).
- `tilt` > 0 raises the back. Rows R3–R6 have the back edge higher, R1–R2 the front edge.
- Layout positions are on a 19.05 mm grid (full-size ANSI, 104 keys, with this set's
  bottom row: 1.5u Ctrl, 1.25u Win/Alt/Fn, 5.75u Space).

## Measurements

Per key shape (`keys_to_measure.csv`), with the key standing on its rim:

- `bottom_width_mm` / `bottom_length_mm`: footprint, on the straight band at the base.
- `front_min_mm` / `back_min_mm`: height at the middle of the top edge (caliper jaw pointing
  front-to-back so it touches only the middle).
- `front_max_mm` / `back_max_mm`: height at the corners (jaw laid along the edge). Only the
  higher edge's max is reliable; its max − min is the dish depth.
- `top_width_mm` / `top_length_mm`: top outline, measured across the middle.

The fit derives the key's center height and tilt from the two mins, the dish from the higher
edge's max − min, the side slant from the top length and one shared front/back slant from the
top width.

Set-wide values (`set_measurements.csv`, column `key_1`): wall thickness, straight base height,
corner radius, stem sizes / gaps / tip heights, stem-tip-to-rib gaps, rib thickness, top
thickness.

### Parameters not measured

- `dish_sag` in `Params` is the dish dip at the end of the straight part of the higher top
  edge. It defines the dish exactly but reads slightly less than the caliper max − min.
- Set defaults in `build_native.py` (`SET_DEFAULTS`): base corner radius 1.5, stem fillet 0.35,
  rib fillet 0.25, and construction margins that do not change the shape.

## Known limits and estimates

- No stabilizer mounts on Backspace, Enter, Shifts, Space, Num 0, Num +, Num Enter: those keys
  have only the center stems.
- No homing bumps on F and J.
- Estimated, not measured: top thickness (0.6 mm), Shift heights (set equal to Z/M), Caps Lock
  top length, Num + and Num Enter heights (continued from the neighboring numpad keys).

## History

- Tag `script-v1`: the earlier version, where a Python model (`keycap.py`) generated plain
  solids and STLs. Its default values were reconstructed from an original reference keycap STL.
