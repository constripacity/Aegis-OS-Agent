"""Master import script for SuperPrism to Blender.

Runs the full pipeline:
1. Import Meshes (import_map.py) -> Loads raw assets
2. Apply Materials (auto_materials.py) -> Sets up shaders
3. Construct Scene (construct_scene.py) -> Builds hierarchy & instances
4. Import Lights (import_lights.py) -> Adds lighting
"""

import bpy
import os
import sys
import importlib.util

# --- PATH SETUP ---
# Hardcoded root to ensure absolute certainty in Blender
PROJECT_ROOT = r"C:\Users\Shadow\Desktop\Superpristm-to-Blender-main"
BLENDER_DIR = os.path.join(PROJECT_ROOT, "blender")

print(f"INFO: Project Root: {PROJECT_ROOT}")
print(f"INFO: Blender Dir: {BLENDER_DIR}")

# Add to sys.path so the modules themselves can find each other if needed
if BLENDER_DIR not in sys.path:
    sys.path.append(BLENDER_DIR)

# --- DYNAMIC IMPORT HELPER ---
def load_module_from_path(module_name, file_path):
    """Loads a python module from a specific file path."""
    if not os.path.exists(file_path):
        print(f"ERROR: Could not find module file: {file_path}")
        return None
        
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    else:
        print(f"ERROR: Could not load spec for {module_name}")
        return None

# --- LOAD MODULES ---
print("INFO: Loading modules...")
import_map = load_module_from_path("import_map", os.path.join(BLENDER_DIR, "import_map.py"))
auto_materials = load_module_from_path("auto_materials", os.path.join(BLENDER_DIR, "auto_materials.py"))
construct_scene = load_module_from_path("construct_scene", os.path.join(BLENDER_DIR, "construct_scene.py"))
import_lights = load_module_from_path("import_lights", os.path.join(BLENDER_DIR, "import_lights.py"))
viewport_setup = load_module_from_path("viewport_setup", os.path.join(BLENDER_DIR, "viewport_setup.py"))

# Force Reload (Crucial for Blender development)
import importlib
if import_map: importlib.reload(import_map)
if auto_materials: importlib.reload(auto_materials)
if construct_scene: importlib.reload(construct_scene)
if import_lights: importlib.reload(import_lights)
if viewport_setup: importlib.reload(viewport_setup)

# --- Configuration ---
IMPORT_MESHES = True
APPLY_MATERIALS = True
CREATE_HIERARCHY = True
IMPORT_LIGHTS = True
SETUP_VIEWPORT = True
# ---------------------

def clear_scene():
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Clear collections
    for col in bpy.data.collections:
        bpy.data.collections.remove(col)
        
    # Purge orphans
    for i in range(3):
        bpy.ops.outliner.orphans_purge()

def main():
    print("=== Starting Full Scene Import (v18 - Brighter Lights) ===")
    
    if not (import_map and auto_materials and construct_scene and import_lights and viewport_setup):
        print("CRITICAL ERROR: One or more modules failed to load. Aborting.")
        return

    # 0. Cleanup
    print("\n--- Step 0: Cleaning Scene ---")
    clear_scene()
    
    # 1. Import Assets
    if IMPORT_MESHES:
        print("\n--- Step 1: Importing Assets (Meshes) ---")
        try:
            import_map.main()
        except Exception as e:
            print(f"Mesh import failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n--- Step 1: Skipped (IMPORT_MESHES=False) ---")
        
    # 2. Materials
    if APPLY_MATERIALS:
        print("\n--- Step 2: Applying Materials ---")
        try:
            auto_materials.main()
        except Exception as e:
            print(f"Material setup failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n--- Step 2: Skipped (APPLY_MATERIALS=False) ---")

    # 3. Hierarchy
    if CREATE_HIERARCHY:
        print("\n--- Step 3: Constructing Scene Hierarchy ---")
        try:
            construct_scene.main()
        except Exception as e:
            print(f"Scene construction failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n--- Step 3: Skipped (CREATE_HIERARCHY=False) ---")
        
    # 4. Lights
    if IMPORT_LIGHTS:
        print("\n--- Step 4: Importing Lights ---")
        try:
            import_lights.main()
        except Exception as e:
            print(f"Light import failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n--- Step 4: Skipped (IMPORT_LIGHTS=False) ---")
        
    # 5. Viewport
    if SETUP_VIEWPORT:
        print("\n--- Step 5: Configuring Viewport ---")
        try:
            viewport_setup.main()
        except Exception as e:
            print(f"Viewport setup failed: {e}")
            
    print("\n=== Import Complete ===")

if __name__ == "__main__":
    main()