"""Master import script for SuperPrism to Blender.
(Addon Version)
"""

import bpy
import os
import sys
import importlib

# In the addon folder, we can import directly
try:
    from . import import_map
    from . import auto_materials
    from . import construct_scene
    from . import import_lights
    from . import viewport_setup
except ImportError:
    # Fallback for running as standalone script
    import import_map
    import auto_materials
    import construct_scene
    import import_lights
    import viewport_setup

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
    
    # Select all and delete
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Clear collections (except Scene Collection)
    for col in bpy.data.collections:
        # Don't delete the collection if it has children in a way that causes issues, 
        # but for our case we want a full wipe.
        bpy.data.collections.remove(col)
        
    # Purge orphans
    for i in range(2):
        bpy.ops.outliner.orphans_purge()

def main():
    print("=== Starting Full Scene Import (Addon Mode) ===")
    
    # Force reload modules to pick up changes
    importlib.reload(import_map)
    importlib.reload(auto_materials)
    importlib.reload(construct_scene)
    importlib.reload(import_lights)
    importlib.reload(viewport_setup)

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
    
    # 2. Materials
    if APPLY_MATERIALS:
        print("\n--- Step 2: Applying Materials ---")
        try:
            auto_materials.main()
        except Exception as e:
            print(f"Material setup failed: {e}")

    # 3. Hierarchy
    if CREATE_HIERARCHY:
        print("\n--- Step 3: Constructing Scene Hierarchy ---")
        try:
            construct_scene.main()
        except Exception as e:
            print(f"Scene construction failed: {e}")
        
    # 4. Lights
    if IMPORT_LIGHTS:
        print("\n--- Step 4: Importing Lights ---")
        try:
            import_lights.main()
        except Exception as e:
            print(f"Light import failed: {e}")
        
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
