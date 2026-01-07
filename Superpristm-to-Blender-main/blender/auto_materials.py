"""Auto-create and assign materials for imported map pieces.

The script builds Principled BSDF materials from all images in
``assets/textures`` (repo-root relative) using the naming convention
``MaterialName__Slot.ext``. It assigns them to objects using a mapping file
``assets/scene_materials.json`` if available, falling back to name matching.
"""

import os
import json
import re
from typing import Dict, Iterable, Optional, Tuple

import bpy

# -----------------------------
# CONFIGURATION
# -----------------------------
TEXTURE_DIR = "assets/textures"  # Repo-root relative
MAPPING_FILE = "assets/scene_materials.json"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff")

# Shader Defaults
DEFAULT_ROUGHNESS = 0.5
DEFAULT_METALLIC = 0.0
DEFAULT_SPECULAR = 0.5

# Texture Slots (suffix -> node input)
SLOTS = {
    "_MainTex": "Base Color",
    "_EmissionMap": "Emission",
    "_BumpMap": "Normal",
    "_MetallicGlossMap": "Metallic",
    "_ParallaxMap": "Displacement" # Handled specially usually
}
# -----------------------------


def resolve_repo_path(path: str) -> str:
    """Resolve ``path`` relative to the .blend when saved, else repo root."""
    if os.path.isabs(path):
        return path

    if bpy.data.filepath:
        base = os.path.dirname(bpy.data.filepath)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.abspath(os.path.join(script_dir, os.pardir))

    resolved = os.path.abspath(os.path.join(base, path))
    print(f"[auto_materials] Resolved path: {resolved}")
    return resolved


def load_image(path: str) -> bpy.types.Image:
    abs_path = os.path.abspath(path)
    for img in bpy.data.images:
        if os.path.abspath(bpy.path.abspath(img.filepath)) == abs_path:
            return img
    img = bpy.data.images.load(path)
    # Set alpha to None for non-color data if needed, but defaults are usually safe
    return img


def get_or_create_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        mat.node_tree.nodes.clear()
        
        # Setup basic nodes
        nodes = mat.node_tree.nodes
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        principled.inputs["Roughness"].default_value = DEFAULT_ROUGHNESS
        principled.inputs["Metallic"].default_value = DEFAULT_METALLIC
        
        mat.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        
    return mat


def setup_texture_node(material: bpy.types.Material, image: bpy.types.Image, slot_suffix: str):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return

    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = image
    tex_node.location = (-300, -200 * len([n for n in nodes if n.type == 'TEX_IMAGE']))
    
    # Simple Slot Logic
    if slot_suffix == "_MainTex":
        links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])
        # If image has alpha, link to Alpha?
        if image.depth == 32 or (image.is_dirty or image.has_data): # checking depth is tricky without loading
            # Just link alpha for safety if it looks like it might have it
            links.new(tex_node.outputs["Alpha"], principled.inputs["Alpha"])
            material.blend_method = 'HASHED' # or BLEND

    elif slot_suffix == "_EmissionMap":
        # Blender 4.0+ rename: "Emission" -> "Emission Color"
        socket_name = "Emission"
        if "Emission Color" in principled.inputs:
            socket_name = "Emission Color"
            
        if socket_name in principled.inputs:
            links.new(tex_node.outputs["Color"], principled.inputs[socket_name])
            # Blender 4.0 also has "Emission Strength" usually
            if "Emission Strength" in principled.inputs:
                principled.inputs["Emission Strength"].default_value = 1.0 
        else:
            print(f"Warning: Could not find Emission input on Principled BSDF for {material.name}")

    elif slot_suffix == "_BumpMap":
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-150, -100)
        tex_node.colorspace_settings.name = 'Non-Color'
        links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
        
    elif slot_suffix == "_MetallicGlossMap":
        tex_node.colorspace_settings.name = 'Non-Color'
        links.new(tex_node.outputs["Color"], principled.inputs["Metallic"])


def build_materials_from_textures(directory: str) -> Dict[str, bpy.types.Material]:
    """Scans dir for Name__Slot.ext and builds materials."""
    materials = {}
    
    # Regex to parse Name__Slot.ext
    # Matches: material_name + "__" + slot_name + extension
    pattern = re.compile(r"(.+)__(.+)\.(\w+)")
    
    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue
            
        match = pattern.match(filename)
        if not match:
            print(f"Skipping non-conforming texture: {filename}")
            continue
            
        mat_name = match.group(1)
        slot_suffix = "_" + match.group(2) # e.g. _MainTex
        
        path = os.path.join(directory, filename)
        image = load_image(path)
        
        mat = get_or_create_material(mat_name)
        setup_texture_node(mat, image, slot_suffix)
        materials[mat_name] = mat
        
    return materials


def load_scene_mapping() -> Dict[str, str]:
    path = resolve_repo_path(MAPPING_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading mapping file: {e}")
    return {}


def iter_objects(objs: Optional[Iterable[bpy.types.Object]] = None):
    if objs is None:
        return bpy.data.objects
    return objs


def normalize_name(name):
    """Simplifies name to base identifier (e.g. 'VIFS006_0' -> 'VIFS006')."""
    # Split by common separators and take the first chunk
    # This handles "VIFS006-sharedassets" -> "VIFS006"
    # And "VIFS006_0" -> "VIFS006"
    import re
    # Remove extension if present
    name = os.path.splitext(name)[0]
    # Split by - or _ and take first part if it looks like an ID
    # Pattern: match VIFS\d+
    match = re.match(r"(VIFS\d+)", name, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Fallback for others: split by separators
    return re.split(r"[-_.]", name)[0]

def main(objects: Optional[Iterable[bpy.types.Object]] = None) -> None:
    texture_dir = resolve_repo_path(TEXTURE_DIR)
    if not os.path.isdir(texture_dir):
        raise RuntimeError(f"Texture directory not found: {texture_dir}")

    # 1. Build Materials
    print("Building materials from textures...")
    available_materials = build_materials_from_textures(texture_dir)
    print(f"Created/Updated {len(available_materials)} materials.")

    # 2. Load Mapping
    scene_mapping = load_scene_mapping()
    
    # Pre-calculate normalized mapping keys
    normalized_mapping = {}
    for filename, mat_name in scene_mapping.items():
        norm_key = normalize_name(filename)
        normalized_mapping[norm_key] = mat_name
        
    print(f"Debug: Mapped keys sample: {list(normalized_mapping.keys())[:5]}")

    # Debug: Print sample object names from scene to check against keys
    scene_mesh_names = [o.name for o in iter_objects(objects) if o.type == 'MESH'][:5]
    print(f"Debug: Scene object names sample: {scene_mesh_names}")

    # 3. Assign
    assigned_count = 0
    for obj in iter_objects(objects):
        if obj.type != "MESH":
            continue
            
        target_mat_name = None
        obj_norm = normalize_name(obj.name) # Calculate this early for debug
        
        # A. Exact/Prefix match with scene mapping (Existing logic)
        for filename, mat_name in scene_mapping.items():
            base_filename = os.path.splitext(filename)[0]
            if obj.name.startswith(base_filename):
                target_mat_name = mat_name
                break
        
        # B. Fuzzy Match (NEW)
        if not target_mat_name:
            if obj_norm in normalized_mapping:
                target_mat_name = normalized_mapping[obj_norm]
        
        # C. Fallback: If object name *is* the material name
        if not target_mat_name and obj.name in available_materials:
            target_mat_name = obj.name
            
        # Debug why it failed for first few
        if not target_mat_name and assigned_count < 3:
            print(f"Debug: Object '{obj.name}' (norm: '{obj_norm}') failed to match. Available norms example: 'VIFS006'")

        # Apply
        if target_mat_name and target_mat_name in available_materials:
            if obj.data.materials:
                obj.data.materials.clear()
            obj.data.materials.append(available_materials[target_mat_name])
            assigned_count += 1
        else:
            if target_mat_name:
                pass # Squelch spam
                # print(f"Object {obj.name} wants material '{target_mat_name}' but it was not created.")

    print(f"Assigned materials to {assigned_count} objects.")


if __name__ == "__main__":
    main()
