"""Create and assign emissive materials for color-coded map pieces.

Objects containing "green" or "yellow" in their names receive emission
materials to help neon/glow elements stand out after import. Designed for
Blender 5.x.
"""

from typing import Iterable, Optional

import bpy

# -----------------------------
# CONFIGURATION
# -----------------------------
EMISSION_STRENGTH_GREEN = 20.0
EMISSION_STRENGTH_YELLOW = 18.0
EMISSION_COLOR_GREEN = (0.25, 1.0, 0.35, 1.0)
EMISSION_COLOR_YELLOW = (1.0, 0.9, 0.25, 1.0)
EMISSIVE_GREEN_NAME = "EMISSIVE_GREEN"
EMISSIVE_YELLOW_NAME = "EMISSIVE_YELLOW"
TARGET_KEYWORDS = {
    "green": ("green",),
    "yellow": ("yellow",),
}
# -----------------------------


def build_emission_material(name: str, color: tuple[float, float, float, float], strength: float) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    material.use_nodes = True
    nodes = material.node_tree
    nodes.nodes.clear()

    output = nodes.nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.nodes.new("ShaderNodeEmission")

    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength

    nodes.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    emission.location = (-150, 0)
    output.location = (120, 0)

    return material


def choose_emission(obj_name: str, green_mat: bpy.types.Material, yellow_mat: bpy.types.Material):
    lower = obj_name.lower()
    if any(k in lower for k in TARGET_KEYWORDS["green"]):
        return green_mat
    if any(k in lower for k in TARGET_KEYWORDS["yellow"]):
        return yellow_mat
    return None


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if obj.type != "MESH":
        return
    if obj.data.materials:
        obj.data.materials.clear()
    obj.data.materials.append(material)


def iter_objects(objs: Optional[Iterable[bpy.types.Object]] = None):
    if objs is None:
        return bpy.data.objects
    return objs


def main(objects: Optional[Iterable[bpy.types.Object]] = None) -> None:
    green_mat = build_emission_material(
        EMISSIVE_GREEN_NAME, EMISSION_COLOR_GREEN, EMISSION_STRENGTH_GREEN
    )
    yellow_mat = build_emission_material(
        EMISSIVE_YELLOW_NAME, EMISSION_COLOR_YELLOW, EMISSION_STRENGTH_YELLOW
    )

    assigned = 0
    for obj in iter_objects(objects):
        if obj.type != "MESH":
            continue
        emission_mat = choose_emission(obj.name, green_mat, yellow_mat)
        if emission_mat:
            assign_material(obj, emission_mat)
            assigned += 1

    print(
        f"Applied emissive materials to {assigned} objects (keywords: green/yellow)."
    )


if __name__ == "__main__":
    main()
