bl_info = {
    "name": "SuperPrism Map Importer",
    "author": "Shadow & Gemini",
    "version": (1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SuperPrism",
    "description": "Imports UberStrike Unity maps into Blender",
    "category": "Import-Export",
}

import bpy
import os
import sys
import importlib

# Add current dir to sys.path to ensure local imports work
if os.path.dirname(__file__) not in sys.path:
    sys.path.append(os.path.dirname(__file__))

from . import import_full_scene
from . import panel

# List of modules to reload
modules_to_reload = [
    import_full_scene,
    panel
]

class SUPERPRISM_OT_import_scene(bpy.types.Operator):
    """Run the full SuperPrism import pipeline"""
    bl_idname = "superprism.import_scene"
    bl_label = "Import Full Scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Force reload modules
        for mod in modules_to_reload:
            importlib.reload(mod)
            
        try:
            import_full_scene.main()
            self.report({'INFO'}, "Import Complete!")
        except Exception as e:
            self.report({'ERROR'}, f"Import Failed: {e}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

class SUPERPRISM_OT_clear_scene(bpy.types.Operator):
    """Clear everything from the current scene"""
    bl_idname = "superprism.clear_scene"
    bl_label = "Clear Scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            import_full_scene.clear_scene()
            self.report({'INFO'}, "Scene Cleared")
        except Exception as e:
            self.report({'ERROR'}, f"Clear Failed: {e}")
        return {'FINISHED'}

classes = (
    SUPERPRISM_OT_import_scene,
    SUPERPRISM_OT_clear_scene,
    panel.SUPERPRISM_PT_main_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
