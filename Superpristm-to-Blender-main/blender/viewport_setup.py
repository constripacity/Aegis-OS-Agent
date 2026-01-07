import bpy

def setup_viewport():
    """Configures the viewport for optimal viewing of the imported scene."""
    print("[viewport_setup] Configuring viewport and render settings...")
    
    # 1. Set Render Engine to EEVEE (Good balance for game assets)
    if bpy.context.scene.render.engine != 'BLENDER_EEVEE':
        bpy.context.scene.render.engine = 'BLENDER_EEVEE'
        
    # 2. Enable Ambient Occlusion and Bloom for better visuals
    if hasattr(bpy.context.scene, 'eevee'):
        # Blender < 4.2 uses 'use_gtao', 4.2+ uses 'ray_tracing' or different structure
        try:
            bpy.context.scene.eevee.use_gtao = True # Ambient Occlusion (Legacy)
        except AttributeError:
            pass # Property likely removed in this version
            
        try:
            bpy.context.scene.eevee.use_bloom = True
        except AttributeError:
            pass
            
    # 3. Set Viewport Shading to MATERIAL or RENDERED
    # We need to find a 3D View area to change its setting
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    # Set to Material Preview
                    space.shading.type = 'MATERIAL'
                    # Optional: Enable scene lights/world in preview if desired
                    # space.shading.use_scene_lights = True
                    # space.shading.use_scene_world = True
                    
    # 4. Set World Background (if not already set)
    if bpy.context.scene.world is None:
        bpy.context.scene.world = bpy.data.worlds.new("SuperPrismWorld")
        
    world = bpy.context.scene.world
    if world and world.use_nodes:
        # Check if background is too dark
        bg = world.node_tree.nodes.get("Background")
        if bg:
            # Set a nice neutral grey environment
            bg.inputs[0].default_value = (0.05, 0.05, 0.05, 1) # Dark grey space
            bg.inputs[1].default_value = 1.0 # Strength

def main():
    setup_viewport()

if __name__ == "__main__":
    main()
