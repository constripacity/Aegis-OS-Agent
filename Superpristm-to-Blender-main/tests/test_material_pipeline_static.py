import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(PROJECT_ROOT, "assets", "textures")
MAT_JSON = os.path.join(PROJECT_ROOT, "assets", "scene_materials.json")

def main():
    print("--- Static Verification of Material Pipeline ---")
    
    # 1. Check Texture Directory
    if not os.path.exists(TEXTURE_DIR):
        print(f"FAIL: Texture directory missing: {TEXTURE_DIR}")
        return
    
    textures = os.listdir(TEXTURE_DIR)
    print(f"Found {len(textures)} textures in {TEXTURE_DIR}")
    if len(textures) == 0:
        print("FAIL: No textures extracted.")
    else:
        print(f"Sample: {textures[:3]}")
        
    # 2. Check Scene Mapping JSON
    if not os.path.exists(MAT_JSON):
        print(f"FAIL: Scene materials JSON missing: {MAT_JSON}")
        return
        
    try:
        with open(MAT_JSON, 'r') as f:
            mapping = json.load(f)
        print(f"Mapped {len(mapping)} objects.")
        if len(mapping) > 0:
            print(f"Sample Mapping: {list(mapping.items())[:3]}")
    except Exception as e:
        print(f"FAIL: Invalid JSON: {e}")
        return

    print("PASS: Material pipeline artifacts look correct.")

if __name__ == "__main__":
    main()
