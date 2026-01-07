import os
import re
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_PATH = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "SuperPRISM_Reactor.unity")
MESH_DIR = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "Mesh")
MAT_DIR = os.path.join(PROJECT_ROOT, "SuperPrismReactor", "Materials")
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "assets", "scene_materials.json")

# Regex
GUID_PATTERN = re.compile(r"guid: ([a-fA-F0-9]{32})")
FILE_ID_PATTERN = re.compile(r"fileID: (-?\d+)")
YAML_TAG_PATTERN = re.compile(r"^--- !u!(\d+) &(\d+)")

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

def parse_scene(scene_path):
    # We need to link MeshFilter(mesh) -> GameObject <- MeshRenderer(material)
    
    # 1. Parse all objects
    # objects[file_id] = {type, components: [], mesh_guid: null, mat_guids: [], game_object_id: null}
    objects = {}
    
    current_id = None
    current_type = None
    current_data = {}
    
    with open(scene_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        tag_match = YAML_TAG_PATTERN.match(line)
        
        if tag_match:
            # Save previous
            if current_id:
                objects[current_id] = {'type': current_type, **current_data}
            
            # Start new
            current_type = int(tag_match.group(1))
            current_id = tag_match.group(2)
            current_data = {'components': [], 'materials': []}
            continue
            
        if not current_id:
            continue
            
        # Parse fields based on type
        # GameObject (1)
        if current_type == 1:
            if line.startswith("- component:"):
                 # - component: {fileID: 1688549749}
                 fid = FILE_ID_PATTERN.search(line)
                 if fid:
                     current_data['components'].append(fid.group(1))
                     
        # MeshFilter (33)
        elif current_type == 33:
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)
            if line.startswith("m_Mesh:"):
                guid = GUID_PATTERN.search(line)
                if guid: current_data['mesh_guid'] = guid.group(1)

        # MeshRenderer (23)
        elif current_type == 23:
            if line.startswith("m_GameObject:"):
                fid = FILE_ID_PATTERN.search(line)
                if fid: current_data['game_object'] = fid.group(1)
            if "guid:" in line and ("m_Materials" in line or line.startswith("- ")): # very loose parsing for list
                # Actually m_Materials is a list.
                # m_Materials:
                # - {fileID: 2100000, guid: ...}
                guid = GUID_PATTERN.search(line)
                if guid: current_data['materials'].append(guid.group(1))

    # Save last
    if current_id:
        objects[current_id] = {'type': current_type, **current_data}

    return objects

def resolve_links(objects, mesh_guids, mat_guids):
    # mesh_filename -> [material_names]
    mapping = {}
    
    # Map GameObject ID -> {mesh_guid, mat_guids}
    go_map = {}
    
    for obj_id, data in objects.items():
        if data['type'] in (23, 33): # Renderer or Filter
            go_id = data.get('game_object')
            if not go_id: continue
            
            if go_id not in go_map: go_map[go_id] = {'mesh': None, 'mats': []}
            
            if data['type'] == 33 and 'mesh_guid' in data:
                go_map[go_id]['mesh'] = data['mesh_guid']
            
            if data['type'] == 23 and 'materials' in data:
                go_map[go_id]['mats'] = data['materials']
                
    # Build final mapping
    for go_id, props in go_map.items():
        mesh_guid = props['mesh']
        mats = props['mats']
        
        if mesh_guid and mats:
            mesh_name = mesh_guids.get(mesh_guid)
            mat_names = [mat_guids.get(m) for m in mats if m in mat_guids]
            
            if mesh_name and mat_names:
                # For OBJ, we usually only support one material per file easily unless we use submeshes.
                # But here we just want a primary material.
                mapping[mesh_name] = mat_names[0] # Take first material
                
    return mapping

def main():
    print("Building GUID maps...")
    mesh_guids = build_guid_map(MESH_DIR, ext_filter=[".obj", ".fbx"])
    mat_guids = build_guid_map(MAT_DIR, ext_filter=[".mat"])
    
    # We also need to map mat filename to material name (usually same minus ext)
    mat_names = {k: os.path.splitext(v)[0] for k, v in mat_guids.items()}
    
    print("Parsing scene...")
    objects = parse_scene(SCENE_PATH)
    
    print("Resolving links...")
    mapping = resolve_links(objects, mesh_guids, mat_names)
    
    print(f"Mapped {len(mapping)} meshes to materials.")
    
    if not os.path.exists(os.path.dirname(OUTPUT_JSON)):
        os.makedirs(os.path.dirname(OUTPUT_JSON))
        
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(mapping, f, indent=2)
    print(f"Saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
