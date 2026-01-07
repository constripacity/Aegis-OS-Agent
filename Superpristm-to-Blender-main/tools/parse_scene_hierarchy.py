import os
import re
import json

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_PATH = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "SuperPRISM_Reactor.unity")
MESH_DIR = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "Mesh")
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "assets", "scene_hierarchy.json")

# Regex Patterns
YAML_TAG_PATTERN = re.compile(r"^--- !u!(\d+) &(\d+)")
FILE_ID_PATTERN = re.compile(r"fileID: (-?\d+)")
GUID_PATTERN = re.compile(r"guid: ([a-fA-F0-9]{32})")

def parse_vector3(line):
    m = re.search(r"x: ([\d\.-]+), y: ([\d\.-]+), z: ([\d\.-]+)", line)
    if m: return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return [0.0, 0.0, 0.0]

def parse_quat(line):
    m = re.search(r"x: ([\d\.-]+), y: ([\d\.-]+), z: ([\d\.-]+), w: ([\d\.-]+)", line)
    if m: return [float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))]
    return [0.0, 0.0, 0.0, 1.0]

def build_guid_map(directory, ext_filter=None):
    guid_map = {} # guid -> filename
    if not os.path.exists(directory):
        return guid_map
        
    for f in os.listdir(directory):
        if f.endswith(".meta"):
            asset_file = f[:-5]
            if ext_filter and not any(asset_file.endswith(e) for e in ext_filter):
                continue
                
            path = os.path.join(directory, f)
            with open(path, 'r', encoding='utf-8') as meta:
                content = meta.read()
                match = GUID_PATTERN.search(content)
                if match:
                    guid_map[match.group(1)] = asset_file
    return guid_map

def main():
    print(f"Parsing hierarchy from {SCENE_PATH}...")
    
    # 0. Build Mesh GUID Map
    print("Building Mesh GUID map...")
    mesh_guid_map = build_guid_map(MESH_DIR, ext_filter=[".obj", ".fbx"])
    
    # 1. Parse raw data
    game_objects = {} # id -> {name}
    transforms = {}   # id -> {father, pos, rot, scale, game_object_id}
    mesh_filters = {} # id -> {mesh_guid, game_object_id}
    
    current_id = None
    current_type = None
    current_data = {}
    
    with open(SCENE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        tag_match = YAML_TAG_PATTERN.match(line)
        
        if tag_match:
            if current_id:
                if current_type == 1: game_objects[current_id] = current_data
                elif current_type == 4: transforms[current_id] = current_data
                elif current_type == 33: mesh_filters[current_id] = current_data
            
            current_type = int(tag_match.group(1))
            current_id = tag_match.group(2)
            current_data = {}
            
            if current_type == 1:
                current_data = {'name': 'Unknown'}
            elif current_type == 4:
                current_data = {'father': None, 'pos': [0,0,0], 'rot': [0,0,0,1], 'scale': [1,1,1], 'game_object': None}
            elif current_type == 33:
                current_data = {'mesh_guid': None, 'game_object': None}
            continue
            
        if not current_id: continue
        
        if current_type == 1:
            if line.startswith("m_Name:"):
                current_data['name'] = line.split("m_Name:")[1].strip()
        
        elif current_type == 4:
            if line.startswith("m_LocalPosition:"): current_data['pos'] = parse_vector3(line)
            if line.startswith("m_LocalRotation:"): current_data['rot'] = parse_quat(line)
            if line.startswith("m_LocalScale:"): current_data['scale'] = parse_vector3(line)
            if line.startswith("m_Father:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['father'] = fid.group(1)
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)

        elif current_type == 33: # MeshFilter
            if line.startswith("m_Mesh:"):
                guid = GUID_PATTERN.search(line)
                if guid: current_data['mesh_guid'] = guid.group(1)
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)

    if current_id:
        if current_type == 1: game_objects[current_id] = current_data
        elif current_type == 4: transforms[current_id] = current_data
        elif current_type == 33: mesh_filters[current_id] = current_data

    # 2. Build Tree
    hierarchy = []
    
    # Helper to find Transform for a GO
    go_to_trans_id = {}
    for tid, tdata in transforms.items():
        if tdata['game_object']:
            go_to_trans_id[tdata['game_object']] = tid
            
    # Helper to find Mesh for a GO
    go_to_mesh_filename = {}
    for mid, mdata in mesh_filters.items():
        if mdata['game_object'] and mdata['mesh_guid']:
            filename = mesh_guid_map.get(mdata['mesh_guid'])
            if filename:
                go_to_mesh_filename[mdata['game_object']] = filename

    for go_id, go_data in game_objects.items():
        if go_id not in go_to_trans_id:
            continue
            
        trans_id = go_to_trans_id[go_id]
        trans = transforms[trans_id]
        
        parent_go_id = None
        if trans['father'] and trans['father'] != "0":
             parent_trans = transforms.get(trans['father'])
             if parent_trans:
                 parent_go_id = parent_trans.get('game_object')
        
        mesh_filename = go_to_mesh_filename.get(go_id)

        hierarchy.append({
            "id": go_id,
            "name": go_data['name'],
            "position": trans['pos'],
            "rotation": trans['rot'],
            "scale": trans['scale'],
            "parent_id": parent_go_id,
            "mesh_asset": mesh_filename 
        })
        
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(hierarchy, f, indent=2)
        
    print(f"Exported hierarchy of {len(hierarchy)} objects to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
