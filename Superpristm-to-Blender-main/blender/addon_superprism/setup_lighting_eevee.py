"""Eevee lighting preset for quick map previews.

Enables bloom, sets a dark blue world background, and adds a simple key +
rim light setup. Designed for Blender 5.x.
"""

import bpy

# -----------------------------
# CONFIGURATION
# -----------------------------
USE_EEVEE = True
ENABLE_BLOOM = True
AREA_LIGHT_POWER = 2500.0
AREA_LIGHT_SIZE = 25.0
RIM_LIGHT_POWER = 1200.0
RIM_LIGHT_SIZE = 12.0
WORLD_COLOR = (0.01, 0.02, 0.05, 1.0)
WORLD_STRENGTH = 0.02
KEY_LIGHT_HEIGHT = 20.0
RIM_LIGHT_OFFSET = (18.0, -10.0, 10.0)
# -----------------------------


def ensure_light(name: str, light_type: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "LIGHT":
        return obj
    data = bpy.data.lights.new(name=name, type=light_type)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def configure_world() -> None:
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    node_tree = scene.world.node_tree
    nodes = node_tree.nodes

    background = nodes.get("Background")
    if background is None:
        background = nodes.new("ShaderNodeBackground")

    output = nodes.get("World Output")
    if output is None:
        output = nodes.new("ShaderNodeOutputWorld")

    if not any(link.to_node == output and link.from_node == background for link in node_tree.links):
        node_tree.links.new(background.outputs[0], output.inputs[0])

    background.inputs[0].default_value = WORLD_COLOR
    background.inputs[1].default_value = WORLD_STRENGTH


def configure_renderer() -> None:
    scene = bpy.context.scene
    if USE_EEVEE:
        build_opts = getattr(bpy.app, "build_options", None)
        supports_eevee_next = bool(build_opts and "BLENDER_EEVEE_NEXT" in build_opts)
        engine_name = "BLENDER_EEVEE_NEXT" if supports_eevee_next else "BLENDER_EEVEE"
        scene.render.engine = engine_name
        eevee_settings = getattr(scene, "eevee", None)
        if eevee_settings and hasattr(eevee_settings, "use_bloom"):
            eevee_settings.use_bloom = ENABLE_BLOOM


def configure_lights() -> None:
    key = ensure_light("Key_Area", "AREA")
    key.location = (0.0, 0.0, KEY_LIGHT_HEIGHT)
    key.data.energy = AREA_LIGHT_POWER
    key.data.size = AREA_LIGHT_SIZE

    rim_left = ensure_light("Rim_L", "AREA")
    rim_left.location = (-RIM_LIGHT_OFFSET[0], RIM_LIGHT_OFFSET[1], RIM_LIGHT_OFFSET[2])
    rim_left.rotation_euler = (0.7, 0.0, 0.8)
    rim_left.data.energy = RIM_LIGHT_POWER
    rim_left.data.size = RIM_LIGHT_SIZE

    rim_right = ensure_light("Rim_R", "AREA")
    rim_right.location = (RIM_LIGHT_OFFSET[0], RIM_LIGHT_OFFSET[1], RIM_LIGHT_OFFSET[2])
    rim_right.rotation_euler = (0.7, 0.0, -0.8)
    rim_right.data.energy = RIM_LIGHT_POWER
    rim_right.data.size = RIM_LIGHT_SIZE


def main() -> None:
    configure_renderer()
    configure_world()
    configure_lights()
    print("Configured Eevee bloom, world background, and area rim lighting.")


if __name__ == "__main__":
    main()
