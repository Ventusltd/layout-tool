# layout-tool
For scoping Solar and PV projects against real grid and GIS environments.

This repository owns the original Module Layout runtime. Its first immutable baseline also preserves Cable Geometry Visualiser and DC/AC/LV Topology Review as separate sibling components until they receive dedicated owners. GIS SLD Financial Sandbox belongs to `Ventusltd/gis-sld-sandbox` and is not duplicated here.

The producer baseline `releases/202609051858/` contains 18 original runtime files (211,559 bytes), copied unchanged from GlobalGrid2050 commit `4185020ade7da01869b4ffc0ee1d2656608da716`. `latest.json` pins the manifest hash. The three independent entry points are:

- `solar-bess-topology-v7/module-layout/index.html`
- `solar-bess-topology-v7/cable-geometry-visualiser/index.html`
- `solar-bess-topology-v7/dc-ac-lv-topology-review/index.html`

All paths above are relative to the release directory. Preserve their original interfaces and formulas. Consumers expose each component in a separate feature release and isolated layer; importing a baseline does not imply that all three features have been integrated or browser-tested.

The original HTML links between sibling tools. The two links to `../gis-sld-financial-sandbox/index.html` are declared cross-owner navigation, pinned to GIS producer commit `9fe7b2d920aaa11e95380de39b33fd98f04e9696` and its manifest. A consumer composition must mount that separately owned sibling route. The verifier records these declared links; it does not pretend the GIS implementation is present in this repository.

MapLibre 3.3.1 and Turf 6 remain external in Module Layout, along with map styles, imagery and root-origin data configuration. These versions intentionally remain the original ones; isolated documents prevent the different GIS MapLibre version from sharing globals. The manifest inventories literal external URLs and states that this is not an exhaustive offline dependency bundle.

```powershell
python -B tools/test_verify.py
python -B tools/verify.py --source C:/Users/vikra/globalgrid-testcode-publication --expected-origin 4185020ade7da01869b4ffc0ee1d2656608da716
```

Five focused tests reject changed formulas, absent dependencies and malformed JavaScript, and require explicit pins for missing cross-owner navigation. The baseline verifies 18 byte-identical files, nine JavaScript parses and 22 relative HTML references, including two explicitly declared GIS links. CI checks the same pinned original revision and retains a compact receipt. These checks establish preservation, syntax and declared composition boundaries, not engineering or financial correctness.

To import another immutable baseline, use `tools/import_original.py --source <checkout> --commit <full-SHA> --generation <new-UTC-stamp> --gis-producer-commit <full-GIS-SHA>`. Existing timestamp directories cannot be overwritten. The importer carries only runtime HTML, JavaScript and CSS, plus any actually referenced relative grid data; generated full-code reports are excluded.
