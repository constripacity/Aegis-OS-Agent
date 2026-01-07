import bpy
import json
import os
import math
from mathutils import Vector, Quaternion, Matrix
import coordinate_converter

# Default path relative to project root
HIERARCHY_PATH = "assets/scene_hierarchy.json"

def resolve_path(path):
    """Resolve path relative to the project root."""
    if os.path.isabs(path):
        return path
    
    # This script is in blender/addon_superprism/
    # Project root is two levels up: ../../
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    
    # Check if we are in a hardcoded location as a fallback
    fallback_root = r"C:\Users\Shadow\Desktop\Superpristm-to-Blender-main"
    if not os.path.exists(os.path.join(project_root, "assets")):
        if os.path.exists(fallback_root):
            project_root = fallback_root

    return os.path.join(project_root, path)

def find_mesh_object(mesh_asset_name, collection):
    """
    Finds an object in the collection that matches the mesh asset name.
    Matches by checking if object name starts with the asset name (minus extension).
    """
    if not mesh_asset_name:
        return None
        
    base_name = os.path.splitext(mesh_asset_name)[0]
    
    # 1. Try exact match in dictionary
    if base_name in collection.objects:
        return collection.objects[base_name]
        
    # 2. Try fuzzy match (startswith)
    # This is useful if Blender appended .001, or if the imported name varies slightly
    for obj in collection.objects:
        if obj.name.startswith(base_name):
            return obj
            
    return None

def build_hierarchy(json_path=HIERARCHY_PATH):
    print(f"[construct_scene] Loading hierarchy from {json_path}")
    
    abs_path = resolve_path(json_path)
    if not os.path.exists(abs_path):
        print(f"[construct_scene] Error: File not found at {abs_path}")
        return

    with open(abs_path, 'r') as f:
        data = json.load(f)
        
    # Source collection (where import_map put things)
    source_col_name = "MAP"
    source_col = bpy.data.collections.get(source_col_name)
    
    if not source_col:
        print(f"[construct_scene] Warning: Collection '{source_col_name}' not found. Using Scene Collection.")
        source_col = bpy.context.scene.collection

    # Target Collection for constructed scene
    target_col_name = "SuperPrism_Scene"
    target_col = bpy.data.collections.get(target_col_name)
    if not target_col:
        target_col = bpy.data.collections.new(target_col_name)
        bpy.context.scene.collection.children.link(target_col)

    # Track which source objects have been used
    # If a mesh is used multiple times, we must duplicate it for subsequent uses
    claimed_objects = set()
    
    # Map ID -> Created/Found Object
    id_to_obj = {}
    
    # --- Pass 1: Create/Find Objects ---
    print(f"[construct_scene] Processing {len(data)} objects...")
    
    for entry in data:
        obj_id = entry['id']
        name = entry['name']
        mesh_asset = entry['mesh_asset']
        
        blender_obj = None
        
        if mesh_asset:
            candidate = find_mesh_object(mesh_asset, source_col)
            
            if candidate:
                if candidate in claimed_objects:
                    # Object already used, make a duplicate (Linked Duplicate to share mesh data)
                    new_obj = candidate.copy()
                    # Link to target collection
                    target_col.objects.link(new_obj)
                    blender_obj = new_obj
                else:
                    # First use, claim the original
                    blender_obj = candidate
                    claimed_objects.add(candidate)
                    
                    # Move to target collection if not already there
                    # Unlink from source (MAP) and link to target
                    for col in blender_obj.users_collection:
                        col.objects.unlink(blender_obj)
                    target_col.objects.link(blender_obj)
                
                blender_obj.name = name
            else:
                # Mesh not found
                print(f"[construct_scene] Warning: Mesh '{mesh_asset}' not found for '{name}'. Creating placeholder.")
                blender_obj = bpy.data.objects.new(name, None)
                blender_obj.empty_display_type = 'CUBE' 
                blender_obj.empty_display_size = 1.0
                target_col.objects.link(blender_obj)
        else:
            # Empty GameObject (transform node)
            blender_obj = bpy.data.objects.new(name, None)
            blender_obj.empty_display_type = 'PLAIN_AXES'
            blender_obj.empty_display_size = 1.0
            target_col.objects.link(blender_obj)
        
        id_to_obj[obj_id] = blender_obj

    # --- Pass 2: Hierarchy & Transforms ---
    count_parented = 0
    
    # Global correction: X(90) * Z(180) (Stand upright + flip to correct forward)
    q_x = Quaternion((1.0, 0.0, 0.0), math.radians(90))
    q_z = Quaternion((0.0, 0.0, 1.0), math.radians(180))
    global_correction = q_x @ q_z
    
    for entry in data:
        obj_id = entry['id']
        obj = id_to_obj.get(obj_id)
        if not obj: continue
        
        # 1. Parenting
        parent_id = entry['parent_id']
        if parent_id and parent_id in id_to_obj:
            parent_obj = id_to_obj[parent_id]
            # Set parent without inverse correction (we will set local transform next)
            obj.parent = parent_obj
            count_parented += 1
            
        # 2. Transforms
        # Unity data is local to parent
        pos = entry['position']
        rot = entry['rotation']
        scale = entry['scale']
        
        # Convert to Blender Coords
        # Unity: (x, y, z) -> Blender: (x, z, y) usually
        # But we use the converter
        loc_b = coordinate_converter.unity_pos_to_blender(pos)
        rot_b = coordinate_converter.unity_rot_to_blender(rot)
        sca_b = coordinate_converter.unity_scale_to_blender(scale)
        
        if not parent_id:
            # Apply global correction to ROOT objects only
            # Rotate position
            obj.location = global_correction @ loc_b
            # Rotate rotation
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = global_correction @ rot_b
        else:
            # Child objects are local to parent, no correction needed
            obj.location = loc_b
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = rot_b
        
        obj.scale = sca_b

    print(f"[construct_scene] Built hierarchy with {count_parented} parent relationships.")
    
    # Optional: Cleanup unused objects in MAP collection?
    # Objects in MAP that were NOT claimed are extra meshes not referenced by hierarchy (unlikely)
    # or they are the originals of duplicated meshes.
    
    return id_to_obj

def main():
    build_hierarchy(HIERARCHY_PATH)

if __name__ == "__main__":
    main()