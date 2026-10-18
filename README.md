# Parametric keycap set

A full keyboard of sculpted keycaps as native, parametric FreeCAD models, generated
from caliper measurements of a physical keycap set.

## Files

| File | Role |
|---|---|
| `keys_to_measure.csv` | Caliper measurements per key shape (source data) |
| `set_measurements.csv` | Measurements shared by the whole set: walls, stems, ribs (source data) |
| `layout.csv` | Every physical key: row, name, which measured shape it uses, grid position |
| `legends.csv` | Every key's legend: one or two lines, alignment, margin, size (source data) |
| `fonts/` | Legend font (Inter SemiBold, SIL Open Font License) |
| `build_native.py` | Builds the FreeCAD files from the three CSVs, fitting each shape |
| `fit_profile.py` | Fits a FreeCAD keycap model to caliper measurements (used by `build_native.py`) |
| `export_stl.py` | Exports the cap and inlay STLs of every key from the FreeCAD files |
| `set.FCStd` | Spreadsheet `Set` with the values shared by all keys |
| `shapes/<id>.FCStd` | One parametric model per distinct key shape: spreadsheet `Params` + result object `Keycap` |
| `keys/NNN_<row>_<key>.FCStd` | One file per physical key: its shape with the legend inlaid; spreadsheet `Legend`, results `Cap` and `Inlay` |
| `keyboard.FCStd` | The whole keyboard: every key's `Cap` and `Inlay`, linked and placed on the layout |
| `fitted_shapes.csv` | Fit cache (generated) |
| `stl/` | Print files, `NNN_<row>_<key>.stl` + `NNN_<row>_<key>_legend.stl` (generated, not versioned) |

## How it fits together

```
keys_to_measure.csv ─┐
set_measurements.csv ├─► build_native.py ──► set.FCStd, shapes/*.FCStd, keys/*.FCStd, keyboard.FCStd
layout.csv ──────────┤   (fit_profile.py)    fitted_shapes.csv
legends.csv ─────────┘                               │
                                    keys/*.FCStd ─► export_stl.py ─► stl/*.stl
```

The FreeCAD files are the only definition of the geometry. They need neither Python nor
the scripts once generated: open them, edit a spreadsheet cell, recompute.

- `set.FCStd` holds set-wide values. Every shape's `Params` sheet reads them through
  cross-file references (`set#Set.wall`), so changing one there updates every key.
- Each `shapes/<id>.FCStd` holds the key's own values in `Params` (footprint, height, tilt,
  dish, the three wall slants, stem rotation, raised-part length `body_w` and `step_height`), cells derived from them, and a model built
  from Draft rectangle lofts, a tilted dish cylinder, the cavity cut and PartDesign stems and
  ribs, all driven by expressions.
- Each `keys/NNN_<row>_<key>.FCStd` is one physical key. It links its shape's `Keycap` (keys
  with the same shape share one shape file, e.g. all letter keys of a row) and inlays its
  legend: its `Legend` sheet holds the text and placement and mirrors the shape's values, the
  text is a Draft ShapeString extruded straight down and kept within `legend_depth` below the
  dish, so the inlay follows the curved top. `Cap` is the keycap minus the inlay, `Inlay` the
  legend itself. Keys without a legend (Space) only link the shape.
- `keyboard.FCStd` links every key's `Cap` and `Inlay` at its layout position. Opening it also
  opens the key, shape and set files.

## Workflows

**Edit the design in FreeCAD.** Open `keyboard.FCStd`, a shape file or a key file, change
cells in `Set`, `Params` or `Legend`, recompute, save. To change the font for the whole set,
put the font file in `fonts/` and point `Set.font_file` at it. Then export STLs. Do not rerun `build_native.py` afterwards:
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
For a two-colour print, load a key's `.stl` and `_legend.stl` into the slicer as one
multi-part object (they share coordinates) and assign the legend its own filament.

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
- `step_body_length_mm` / `step_height_mm` (optional, stepped keys only): base length of the
  raised part, flush with the left edge, and height of the flat shelf that fills the rest of
  the footprint on the right. The raised part is fitted like a normal key (heights and top
  outline are measured on it), the shelf is hollow with a roof `top_thickness` thick, and the
  stems are centered on the raised part.

The fit derives the key's center height and tilt from the two mins, the dish from the higher
edge's max − min, the side slant from the top length and one shared front/back slant from the
top width.

Set-wide values (`set_measurements.csv`, column `key_1`): wall thickness, straight base height,
corner radius, stem sizes / gaps / tip heights, stem-tip-to-rib gaps, rib thickness, top
thickness.

## Legends

`legends.csv`, one row per key of `layout.csv`:

- `line1`, `line2`: the text. With two lines the legend is stacked (shifted symbol on top),
  both lines centered.
- `align`: `center` (centered on the top; on a stepped key, on the raised part), `left` or
  `right` (fixed `margin_mm` from that side's top edge: Left Shift / Right Shift, Enter) or
  `top` (fixed `margin_mm` from the front edge: Num Enter, Num +).
- `size_mm`: cap height of the text; blank uses `Set.legend_size` (3.6). Prefilled: stacked
  2.6, F-keys 2.8, words 2.2.

Set-wide legend values in `set.FCStd`: `font_file`, `legend_size`, `line_gap` (between the two
lines of a stacked legend, 1.0) and `legend_depth` (inlay depth perpendicular to the dish,
0.4 of the 0.6 mm top). The font path is absolute: on another computer, point
`Set.font_file` at the copy in `fonts/`.

### Parameters not measured

- `dish_sag` in `Params` is the dish dip at the end of the straight part of the higher top
  edge. It defines the dish exactly but reads slightly less than the caliper max − min.
- Set defaults in `build_native.py` (`SET_DEFAULTS`): base corner radius 1.5, stem fillet 0.35,
  rib fillet 0.25, and construction margins that do not change the shape.

## Known limits and estimates

- No stabilizer mounts on Backspace, Enter, Shifts, Space, Num 0, Num +, Num Enter: those keys
  have only the center stems.
- No homing bumps on F and J.
- Legends only on top, no front (side) legends.
- Estimated, not measured: top thickness (0.6 mm), Shift heights (set equal to Z/M), Num + and
  Num Enter heights (continued from the neighboring numpad keys), and the stepped Caps Lock's
  raised-part base length (27.8 mm, taken from Tab).
- Caps Lock is a stepped key: a Tab-like raised part with the ASD row's profile, and a 2.6 mm
  shelf on the right. The shelf objects only exist in stepped shape files, so turning another
  key into a stepped one means regenerating it with the step columns filled in.

## History

- Tag `script-v1`: the earlier version, where a Python model (`keycap.py`) generated plain
  solids and STLs. Its default values were reconstructed from an original reference keycap STL.
