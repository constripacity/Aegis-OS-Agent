import os
import re
import json

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_PATH = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "SuperPRISM_Reactor.unity")
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "assets", "scene_lights.json")

# Regex Patterns
YAML_TAG_PATTERN = re.compile(r"^--- !u!(\d+) &(\d+)")
FILE_ID_PATTERN = re.compile(r"fileID: (-?\d+)")
GUID_PATTERN = re.compile(r"guid: ([a-fA-F0-9]{32})")

def parse_vector3(line):
    # {x: 0, y: 5, z: 0}
    m = re.search(r"x: ([\d\.-]+), y: ([\d\.-]+), z: ([\d\.-]+)", line)
    if m:
        return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return [0.0, 0.0, 0.0]

def parse_quat(line):
    # {x: 0, y: 0, z: 0, w: 1}
    m = re.search(r"x: ([\d\.-]+), y: ([\d\.-]+), z: ([\d\.-]+), w: ([\d\.-]+)", line)
    if m:
        return [float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))]
    return [0.0, 0.0, 0.0, 1.0]

def parse_color(line):
    # {r: 1, g: 1, b: 1, a: 1}
    m = re.search(r"r: ([\d\.-]+), g: ([\d\.-]+), b: ([\d\.-]+), a: ([\d\.-]+)", line)
    if m:
        return [float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))]
    return [1.0, 1.0, 1.0, 1.0]

def parse_float(line, key):
    # m_Intensity: 1
    if key in line:
        parts = line.split(f"{key}:")
        if len(parts) > 1:
            try:
                return float(parts[1].strip())
            except ValueError:
                pass
    return None

def parse_int(line, key):
    # m_Type: 2
    if key in line:
        parts = line.split(f"{key}:")
        if len(parts) > 1:
            try:
                return int(parts[1].strip())
            except ValueError:
                pass
    return None

def main():
    print(f"Scanning {SCENE_PATH} for lights...")
    
    # Data structures
    # components: file_id -> {type, data}
    # game_objects: file_id -> {name, components: []}
    # transforms: file_id -> {father_id, local_pos, local_rot, local_scale, game_object_id}
    
    components = {}
    game_objects = {}
    transforms = {}
    
    current_id = None
    current_type = None
    current_data = {}
    
    with open(SCENE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        tag_match = YAML_TAG_PATTERN.match(line)
        
        if tag_match:
            # Save previous
            if current_id:
                if current_type == 1: # GameObject
                    game_objects[current_id] = current_data
                elif current_type == 4: # Transform
                    transforms[current_id] = current_data
                elif current_type == 108: # Light
                    components[current_id] = current_data
            
            # Start new
            current_type = int(tag_match.group(1))
            current_id = tag_match.group(2)
            current_data = {}
            
            if current_type == 1:
                current_data = {'name': 'Unknown', 'components': []}
            elif current_type == 4:
                current_data = {'father': None, 'pos': [0,0,0], 'rot': [0,0,0,1], 'scale': [1,1,1], 'game_object': None}
            elif current_type == 108:
                current_data = {
                    'type': 2, 'color': [1,1,1,1], 'intensity': 1.0, 
                    'range': 10.0, 'spot_angle': 30.0, 'shadow_type': 0, 'game_object': None
                }
            continue
            
        if not current_id:
            continue
            
        # Parse fields
        if current_type == 1: # GameObject
            if line.startswith("m_Name:"):
                current_data['name'] = line.split("m_Name:")[1].strip()
            if line.startswith("- component:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['components'].append(fid.group(1))
                
        elif current_type == 4: # Transform
            if line.startswith("m_LocalPosition:"): current_data['pos'] = parse_vector3(line)
            if line.startswith("m_LocalRotation:"): current_data['rot'] = parse_quat(line)
            if line.startswith("m_LocalScale:"): current_data['scale'] = parse_vector3(line)
            if line.startswith("m_Father:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['father'] = fid.group(1)
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)

        elif current_type == 108: # Light
            if line.startswith("m_Type:"): 
                val = parse_int(line, "m_Type")
                if val is not None: current_data['type'] = val
            if line.startswith("m_Color:"): current_data['color'] = parse_color(line)
            if line.startswith("m_Intensity:"): 
                val = parse_float(line, "m_Intensity")
                if val is not None: current_data['intensity'] = val
            if line.startswith("m_Range:"):
                val = parse_float(line, "m_Range")
                if val is not None: current_data['range'] = val
            if line.startswith("m_SpotAngle:"):
                val = parse_float(line, "m_SpotAngle")
                if val is not None: current_data['spot_angle'] = val
            if line.startswith("m_Shadows:"):
                # Handle nested structure roughly or look for key
                pass
            if "m_Type:" in line and "m_Shadows" in line: # Fallback if single line
                 pass
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)

    # Save last
    if current_id:
        if current_type == 1: game_objects[current_id] = current_data
        elif current_type == 4: transforms[current_id] = current_data
        elif current_type == 108: components[current_id] = current_data

    # Link everything
    # Light Component -> GameObject -> Transform -> Position/Rotation
    
    extracted_lights = []
    
    # Map GameObject ID -> Transform Data
    go_to_transform = {}
    for tid, tdata in transforms.items():
        if tdata['game_object']:
            go_to_transform[tdata['game_object']] = tdata
            
    for lid, ldata in components.items():
        go_id = ldata.get('game_object')
        if not go_id or go_id not in game_objects:
            continue
            
        go_data = game_objects[go_id]
        name = go_data['name']
        
        # Get Transform
        trans_data = go_to_transform.get(go_id)
        if not trans_data:
            continue
            
        light_entry = {
            "name": name,
            "type": ldata['type'],
            "color": ldata['color'],
            "intensity": ldata['intensity'],
            "range": ldata['range'],
            "spot_angle": ldata['spot_angle'],
            "position": trans_data['pos'],
            "rotation": trans_data['rot'],
            "scale": trans_data['scale'],
            "parent": trans_data['father'] if trans_data['father'] and trans_data['father'] != "0" else None
        }
        
        extracted_lights.append(light_entry)
        
    output_data = {"lights": extracted_lights}
    
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output_data, f, indent=2)
        
    print(f"Extracted {len(extracted_lights)} lights to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
