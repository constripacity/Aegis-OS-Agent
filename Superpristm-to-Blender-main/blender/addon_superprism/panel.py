import bpy

class SUPERPRISM_PT_main_panel(bpy.types.Panel):
    """Creates a Panel in the 3D View Sidebar"""
    bl_label = "SuperPrism Importer"
    bl_idname = "SUPERPRISM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SuperPrism'

    def draw(self, context):
        layout = self.layout
        
        col = layout.column(align=True)
        col.label(text="Map Import")
        col.operator("superprism.import_scene", text="IMPORT MAP", icon='IMPORT')
        
        layout.separator()
        
        col = layout.column(align=True)
        col.label(text="Scene Management")
        col.operator("superprism.clear_scene", text="Clear Scene", icon='TRASH')
        
        layout.separator()
        
        # Status Area
        box = layout.box()
        box.label(text="Status: Ready", icon='CHECKMARK')
        box.label(text="Project: UberStrike 4.7")
