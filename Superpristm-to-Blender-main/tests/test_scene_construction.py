import bpy
import os
import sys
import json
import importlib.util

# --- PATH SETUP ---
# Hardcoded root based on your provided environment to ensure absolute certainty
PROJECT_ROOT = r"C:\Users\Shadow\Desktop\Superpristm-to-Blender-main"
BLENDER_DIR = os.path.join(PROJECT_ROOT, "blender")

print(f"TEST INFO: Project Root: {PROJECT_ROOT}")
print(f"TEST INFO: Blender Dir: {BLENDER_DIR}")

if not os.path.exists(BLENDER_DIR):
    print(f"TEST ERROR: Directory not found: {BLENDER_DIR}")

# Add to sys.path for dependencies inside the modules (like if construct_scene imports coordinate_converter)
if BLENDER_DIR not in sys.path:
    sys.path.append(BLENDER_DIR)
    print(f"TEST INFO: Added {BLENDER_DIR} to sys.path")

# --- DYNAMIC IMPORT HELPER ---
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    else:
        raise ImportError(f"Could not load {module_name} from {file_path}")

# Load modules explicitly
try:
    construct_scene_path = os.path.join(BLENDER_DIR, "construct_scene.py")
    coord_converter_path = os.path.join(BLENDER_DIR, "coordinate_converter.py")
    
    print(f"TEST INFO: Loading {construct_scene_path}")
    construct_scene = load_module_from_path("construct_scene", construct_scene_path)
    
    print(f"TEST INFO: Loading {coord_converter_path}")
    coordinate_converter = load_module_from_path("coordinate_converter", coord_converter_path)
    
except Exception as e:
    print(f"TEST CRITICAL ERROR: Failed to load modules: {e}")
    # Stop execution if modules fail
    sys.exit()

# ------------------

def test_scene_construction():
    print("TEST: Starting Scene Construction Test...")
    
    # 1. Setup Dummy Data
    test_json_path = os.path.join(PROJECT_ROOT, "tests", "temp_hierarchy.json")
    
    test_data = [
        {
            "id": "root",
            "name": "RootObject",
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0, 1.0], # x,y,z,w
            "scale": [1.0, 1.0, 1.0],
            "parent_id": None,
            "mesh_asset": None
        },
        {
            "id": "child",
            "name": "ChildObject",
            "position": [10.0, 0.0, 5.0],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
            "parent_id": "root",
            "mesh_asset": None
        }
    ]
    
    with open(test_json_path, 'w') as f:
        json.dump(test_data, f)
        
    # 2. Clear Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    # 3. Run Construction
    print("TEST: Running build_hierarchy...")
    try:
        id_map = construct_scene.build_hierarchy(test_json_path)
    except Exception as e:
        print(f"TEST FAIL: Exception during hierarchy build: {e}")
        return
    
    # 4. Verify
    root = bpy.data.objects.get("RootObject")
    child = bpy.data.objects.get("ChildObject")
    
    success = True
    
    if not root:
        print("FAIL: Root object not created.")
        success = False
    if not child:
        print("FAIL: Child object not created.")
        success = False
        
    if success:
        # Check Parenting
        if child.parent != root:
            print(f"FAIL: Parenting incorrect. Expected RootObject, got {child.parent}")
            success = False
        else:
            print("PASS: Parenting correct.")
            
        # Check Position
        # Use the imported module
        expected_loc = coordinate_converter.unity_pos_to_blender([10.0, 0.0, 5.0])
        
        diff = (child.location - expected_loc).length
        if diff < 0.001:
            print(f"PASS: Position correct {child.location}")
        else:
            print(f"FAIL: Position mismatch. Expected {expected_loc}, got {child.location}")
            success = False

    # Cleanup
    if os.path.exists(test_json_path):
        os.remove(test_json_path)
        
    if success:
        print("TEST: All checks passed.")
    else:
        print("TEST: One or more checks failed.")

if __name__ == "__main__":
    test_scene_construction()