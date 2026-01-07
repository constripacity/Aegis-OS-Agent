"""Test script to verify material pipeline in Blender.

Usage:
1. Open Blender.
2. Open this file in Text Editor.
3. Run Script.
"""

import bpy
import os
import sys

# Add blender folder to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
blender_dir = os.path.join(project_root, "blender")
if blender_dir not in sys.path:
    sys.path.append(blender_dir)

import import_map
import auto_materials

def test_pipeline():
    print("TEST: Starting Material Pipeline Test...")
    
    # 1. Clear Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    # 2. Import *just one* mesh if possible, or run full import map
    # For this test, we run the full import_map but limited by what's in the folder
    print("TEST: Importing meshes...")
    import_map.main()
    
    # 3. Check if meshes imported
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        print("TEST FAIL: No meshes imported.")
        return
    print(f"TEST PASS: {len(meshes)} meshes imported.")
    
    # 4. Apply materials
    print("TEST: Applying materials...")
    auto_materials.main()
    
    # 5. Check assignments
    assigned_count = 0
    for obj in meshes:
        if obj.data.materials and obj.data.materials[0]:
            print(f"  Object {obj.name} -> Material {obj.data.materials[0].name}")
            assigned_count += 1
        else:
            print(f"  Object {obj.name} -> [NO MATERIAL]")
            
    if assigned_count > 0:
        print(f"TEST PASS: Materials assigned to {assigned_count} objects.")
    else:
        print("TEST FAIL: No materials assigned.")

if __name__ == "__main__":
    test_pipeline()
