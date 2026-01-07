# Superpristm-to-Blender

A small Blender pipeline to bring a Unity-exported map (OBJ/FBX meshes + PNG textures)
into Blender and get a quick cinematic lighting setup. The scripts are light-weight,
runnable in Blender 4.x/5.x, and tested on Windows.

## Folder structure
- `assets/meshes/` – OBJ/FBX files exported from Unity
- `assets/textures/` – texture images (PNG/JPG/TGA/BMP)
- `blender/` – helper scripts to import, build materials, emissives, and lighting

## Quick Start
1. Place map meshes in `assets/meshes/` and textures in `assets/textures/` (keep the repo layout).
2. Open Blender 4.x/5.x (Windows supported) and load your `.blend` in the repo folder.
3. Run scripts (Text Editor > Open > Run Script) in this order:
   - `blender/auto_materials.py` (builds materials and keyword-based emissive variants)
   - `blender/import_map.py` (imports meshes into the `MAP` collection, clears old runs)
   - `blender/setup_lighting_eevee.py` (enables bloom, dark blue world, and key/rim lights)
4. Optionally run `blender/make_emissives.py` to force green/yellow emission on matching objects.

## Troubleshooting
- **"Directory not found"** – Verify `assets/meshes` and `assets/textures` exist relative to the repo root.
- **Duplicates after re-import** – Re-run `import_map.py`; it now clears the `MAP` collection before importing.
- **No glow/bloom** – Ensure Eevee bloom is enabled (the lighting script toggles it when available) and use the emissive materials created by the material scripts.

## Notes
- Paths are resolved relative to the current `.blend` when saved; otherwise they fall back to the repo root next to these scripts.
- Scripts are idempotent: re-running them will update in-place instead of duplicating data.
