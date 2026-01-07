"""Import Unity lights into Blender from JSON data."""

import json
import os
import bpy
import math
from mathutils import Matrix

# Import local modules
# (In Blender text editor, these might need sys.path hacks, but assuming relative import works or file is run in context)
try:
    from . import coordinate_converter
except ImportError:
    import coordinate_converter

# -----------------------------
# CONFIGURATION
# -----------------------------
LIGHTS_JSON = "assets/scene_lights.json"
COLLECTION_NAME = "LIGHTS"

# Conversion Factors
INTENSITY_FACTOR = 10.0  # Unity 1.0 -> Blender Watts/Power (approx)
RANGE_FACTOR = 1.0       # Units should be similar (Meters)
# -----------------------------

def resolve_repo_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    if bpy.data.filepath:
        base = os.path.dirname(bpy.data.filepath)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.abspath(os.path.join(script_dir, os.pardir))
    return os.path.abspath(os.path.join(base, path))

def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def create_blender_light(light_data):
    """Create a Blender light object from Unity data."""
    
    # Unity Types: 0=Spot, 1=Directional, 2=Point, 3=Area
    # Note: Our extractor might have mapped them differently or used Unity raw enum.
    # Unity Enum: Spot=0, Directional=1, Point=2, Area=3, Disc=4
    # The extractor script output: 
    # "type": 2 (for Directional in previous output sample? Wait, check extract_lights.py)
    # in extract_lights.py, we saw:
    # m_Type: 2 (mapped to Point usually?)
    # Wait, let's re-verify Unity YAML Enum.
    # 0: Spot, 1: Directional, 2: Point, 3: Area.
    # In the sample output: "name": "Directional Light", "type": 2.
    # Wait. If name is Directional Light and type is 2, maybe 2 IS Directional in this version?
    # Unity 4.7 might have different enums?
    # Actually, in Unity 4:
    # Spot=0, Directional=1, Point=2, Area=3.
    # If the file says type: 1, it's Directional.
    # Let's assume standard mapping for now but look at name if ambiguous.
    
    u_type = light_data.get('type', 2)
    name = light_data.get('name', "Light")
    
    # Heuristic correction based on name if type seems weird
    if "Directional" in name:
        blender_type = 'SUN'
    elif "Spot" in name:
        blender_type = 'SPOT'
    elif u_type == 0:
        blender_type = 'SPOT'
    elif u_type == 1:
        blender_type = 'SUN'
    elif u_type == 2:
        blender_type = 'POINT'
    elif u_type == 3:
        blender_type = 'AREA'
    else:
        blender_type = 'POINT'

    # Create Data
    light_data_block = bpy.data.lights.new(name=name, type=blender_type)
    
    # Properties
    u_intensity = light_data.get('intensity', 1.0)
    u_color = light_data.get('color', [1,1,1,1])
    u_range = light_data.get('range', 10.0)
    u_spot_angle = light_data.get('spot_angle', 30.0)
    
    light_data_block.color = (u_color[0], u_color[1], u_color[2])
    
    # Energy Calculation
    # Point/Spot: Watts. Unity Intensity is arbitrary 0-8 usually.
    # Sun: Irradiance W/m2. Unity Intensity 0-1 usually.
    if blender_type == 'SUN':
        light_data_block.energy = u_intensity * 5.0 # Boost Sun
    else:
        # Boost Point/Spot lights significantly
        # Unity 1.0 -> Blender ~5000 Watts (heuristic)
        light_data_block.energy = u_intensity * INTENSITY_FACTOR * 500 
        
        # Optional: Disable custom distance for now to ensure visibility
        # light_data_block.use_custom_distance = True
        # light_data_block.cutoff_distance = u_range
        
    if blender_type == 'SPOT':
        # Unity angle is total cone angle (degrees)
        # Blender size is total cone angle (radians)
        light_data_block.spot_size = math.radians(u_spot_angle)
        light_data_block.spot_blend = 0.15 # Default blend

    # Create Object
    light_obj = bpy.data.objects.new(name=name, object_data=light_data_block)
    
    # Transform
    pos = light_data.get('position', [0,0,0])
    rot = light_data.get('rotation', [0,0,0,1]) # x,y,z,w
    scale = light_data.get('scale', [1,1,1])
    
    # Use Converter
    loc = coordinate_converter.unity_pos_to_blender(pos)
    q = coordinate_converter.unity_rot_to_blender(rot)
    
    # --- GLOBAL CORRECTION (Matches construct_scene.py v12) ---
    q_x = math.radians(90.0)
    q_z = math.radians(180.0)
    # Construct quaternions (Blender Quaternion is w,x,y,z)
    # Euler to Quat helper:
    from mathutils import Quaternion, Euler
    
    # Global fix: Rotate by X(90) then Z(180)
    # We apply this to the computed position and rotation
    
    # Create correction quaternion
    # q_correction = q_x @ q_z (Order matters)
    quat_x = Quaternion((1.0, 0.0, 0.0), q_x)
    quat_z = Quaternion((0.0, 0.0, 1.0), q_z)
    global_correction = quat_x @ quat_z 
    
    # Apply to Position
    light_obj.location = global_correction @ loc
    
    # Apply to Rotation
    light_obj.rotation_mode = 'QUATERNION'
    light_obj.rotation_quaternion = global_correction @ q
    # ----------------------------------------------------------
    
    # Corrections
    if blender_type == 'SUN':
        # If the conversion aligns axes, we might need to verify direction.
        pass

    return light_obj

def main():
    json_path = resolve_repo_path(LIGHTS_JSON)
    if not os.path.exists(json_path):
        print(f"Lights JSON not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)
        
    collection = ensure_collection(COLLECTION_NAME)
    
    # Clear existing
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
        
    count = 0
    for l_data in data.get('lights', []):
        obj = create_blender_light(l_data)
        collection.objects.link(obj)
        count += 1
        
    print(f"Imported {count} lights.")

if __name__ == "__main__":
    main()
