import os
import shutil
import re
from pathlib import Path

# Configuration
SOURCE_ASSETS_DIR = r"C:\Users\Shadow\Desktop\UberUnity-main4.7\Assets"
LOCAL_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_MAT_DIR = os.path.join(LOCAL_PROJECT_DIR, "SuperPrismReactor", "Materials")
TARGET_TEX_DIR = os.path.join(LOCAL_PROJECT_DIR, "assets", "textures")
TARGET_MAT_JSON = os.path.join(LOCAL_PROJECT_DIR, "assets", "materials.json")

# Regex for parsing
GUID_PATTERN = re.compile(r"guid: ([a-fA-F0-9]{32})")
TEX_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tga', '.psd', '.tif', '.tiff'}

def build_guid_map(root_dir):
    """Scans directory for .meta files and maps GUIDs to asset paths."""
    print(f"Scanning for assets in {root_dir}...")
    guid_map = {}
    count = 0
    
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".meta"):
                meta_path = os.path.join(root, file)
                asset_path = meta_path[:-5] # remove .meta
                
                if not os.path.exists(asset_path):
                    continue
                    
                # Read GUID from meta file
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        match = GUID_PATTERN.search(content)
                        if match:
                            guid = match.group(1)
                            guid_map[guid] = asset_path
                            count += 1
                except Exception as e:
                    print(f"Error reading {meta_path}: {e}")
                    
    print(f"Indexed {count} assets.")
    return guid_map

def parse_material(mat_path):
    """Parses a .mat file to find texture GUIDs."""
    textures = {}
    try:
        with open(mat_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find _MainTex and similar properties
        # Simple regex approach for YAML
        # _MainTex: {fileID: 2800000, guid: 545f7e344c18d4445aa8ac2a794b28a2, type: 3}
        
        # We look for lines like " - _TextureName:" followed by "guid: ..."
        # This is a simplification; a full YAML parser is better but regex is faster for this specific task
        
        # Split by lines to track context
        lines = content.split('\n')
        current_prop = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("- _"):
                current_prop = line.split(':')[0].replace("- ", "")
            
            if "guid:" in line and current_prop:
                match = GUID_PATTERN.search(line)
                if match:
                    textures[current_prop] = match.group(1)
                current_prop = None # Reset
                
    except Exception as e:
        print(f"Error parsing material {mat_path}: {e}")
        
    return textures

def main():
    if not os.path.exists(LOCAL_MAT_DIR):
        print(f"Error: Material directory not found: {LOCAL_MAT_DIR}")
        return

    if not os.path.exists(TARGET_TEX_DIR):
        os.makedirs(TARGET_TEX_DIR)
        
    # 1. Build Index
    guid_map = build_guid_map(SOURCE_ASSETS_DIR)
    
    # 2. Process Local Materials
    print(f"Processing materials in {LOCAL_MAT_DIR}...")
    files = [f for f in os.listdir(LOCAL_MAT_DIR) if f.endswith(".mat")]
    
    for mat_file in files:
        mat_path = os.path.join(LOCAL_MAT_DIR, mat_file)
        print(f"Processing {mat_file}...")
        
        textures = parse_material(mat_path)
        
        for tex_slot, guid in textures.items():
            if guid in guid_map:
                source_path = guid_map[guid]
                ext = os.path.splitext(source_path)[1].lower()
                
                if ext in TEX_EXTENSIONS:
                    # Copy file
                    dest_name = f"{os.path.splitext(mat_file)[0]}_{tex_slot}{ext}"
                    dest_path = os.path.join(TARGET_TEX_DIR, dest_name)
                    
                    if not os.path.exists(dest_path):
                        print(f"  Copying {os.path.basename(source_path)} -> {dest_name}")
                        shutil.copy2(source_path, dest_path)
                    else:
                        print(f"  Skipping {dest_name} (exists)")
            else:
                print(f"  Warning: GUID {guid} not found for {tex_slot}")

    print("Done.")

if __name__ == "__main__":
    main()
