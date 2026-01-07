# SuperPrism to Blender Import Workflow

This toolset automates the conversion of UberStrike Unity scenes (SuperPrism Reactor) into Blender.

## Prerequisites

- **Blender 3.6+**
- **Python Dependencies** (installed in your system Python):
  - `UnityPy`
  - `Pillow`
  - `PyYAML`

## Setup

1. **Extract Assets**:
   Run the asset collection tool to extract textures from your Unity project folder.
   ```bash
   python tools/collect_assets.py
   ```

2. **Parse Scene Data**:
   Run the parsing tools to generate the JSON data needed for Blender.
   ```bash
   python tools/map_scene_materials.py
   python tools/extract_lights.py
   python tools/parse_scene_hierarchy.py
   ```

## Import into Blender

1. Open Blender.
2. Switch to the **Scripting** tab.
3. Open `blender/import_full_scene.py`.
4. Click **Run Script** (Play button).

## Result

- **Collections**:
  - `Asset_Palette`: Contains the raw imported meshes (hidden).
  - `SuperPrism_Scene`: Contains the constructed scene hierarchy.
  - `LIGHTS`: Contains the imported lights.
- **Materials**: Automatically assigned based on scene data.

## Troubleshooting

- **Pink Materials**: Textures missing. Check `assets/textures` and run `collect_assets.py` again.
- **Wrong Rotation**: Unity and Blender have different coordinate systems. If objects are rotated 90 degrees incorrectly, check `blender/coordinate_converter.py`.
