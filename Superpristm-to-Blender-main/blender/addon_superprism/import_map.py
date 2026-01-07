"""Utility to import Unity-exported map pieces into Blender.

This script bulk-imports meshes from ``assets/meshes`` (repo-root relative),
applies orientation fixes, and organizes them into a single collection for
easy management. Designed for Blender 5.x and safe to re-run without
creating duplicates.
"""

import os
from math import radians

import bpy

# -----------------------------
# CONFIGURATION
# -----------------------------
MESH_DIR = "assets/meshes"  # Repo-root relative
IMPORT_EXTENSIONS = (".obj", ".fbx")
GLOBAL_SCALE = 1.0
ROTATE_X_DEGREES = 90.0  # Unity -> Blender upright fix
APPLY_TRANSFORMS = True  # Apply rotation/scale after import
SHADE_SMOOTH = False
COLLECTION_NAME = "MAP"
# -----------------------------


def resolve_repo_path(path: str) -> str:
    """Resolve ``path`` relative to the .blend when saved, else repo root."""

    if os.path.isabs(path):
        return path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    
    fallback_root = r"C:\Users\Shadow\Desktop\Superpristm-to-Blender-main"
    if not os.path.exists(os.path.join(project_root, "assets")):
        if os.path.exists(fallback_root):
            project_root = fallback_root

    resolved = os.path.abspath(os.path.join(project_root, path))
    print(f"[import_map] Resolved path: {resolved}")
    return resolved


def ensure_collection(name: str) -> bpy.types.Collection:
    """Get or create a collection and ensure it is linked to the scene."""
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def clear_collection(collection: bpy.types.Collection) -> None:
    """Remove all objects inside the collection and clean orphaned data."""

    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for image in list(bpy.data.images):
        if image.users == 0:
            bpy.data.images.remove(image)
    for material in list(bpy.data.materials):
        if material.users == 0:
            bpy.data.materials.remove(material)


def link_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    """Unlink an object from existing collections and link it to the target."""
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)


def import_mesh(filepath: str):
    """Import a single mesh file and return the newly created objects."""
    before = set(bpy.context.scene.objects)
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".obj":
        obj_import = getattr(bpy.ops.wm, "obj_import", None)
        if obj_import is None:
            raise RuntimeError(
                "OBJ importer not available. Enable the OBJ add-on in Blender preferences (io_scene_obj) or use FBX."
            )
        obj_import(filepath=filepath, global_scale=GLOBAL_SCALE)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath, global_scale=GLOBAL_SCALE)
    else:
        raise RuntimeError(f"Unsupported file type: {filepath}")

    after = set(bpy.context.scene.objects)
    return list(after - before)


def apply_orientation(objs: list[bpy.types.Object]) -> None:
    """Rotate imported objects and optionally apply transforms."""
    rot_x = radians(90.0)
    
    for obj in objs:
        # 1. Rotate X 90 (Stand upright)
        obj.rotation_euler.rotate_axis("X", rot_x)
        
    if APPLY_TRANSFORMS and objs:
        
        # 2. Scale Y -1: (x, -z, y) -> (x, z, y)
        # This fixes the "twisted" / mirrored geometry
        obj.scale.y *= -1

    if APPLY_TRANSFORMS and objs:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objs:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        # Apply Rotation AND Scale
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        
        # After negative scale, normals might be flipped. Recalculate.
        if objs:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')

    if objs:
        for obj in objs:
            if obj.type == "MESH":
                for poly in obj.data.polygons:
                    poly.use_smooth = SHADE_SMOOTH


def main() -> None:
    mesh_dir = resolve_repo_path(MESH_DIR)
    if not os.path.isdir(mesh_dir):
        raise RuntimeError(f"Mesh directory not found: {mesh_dir}")

    collection = ensure_collection(COLLECTION_NAME)
    clear_collection(collection)

    obj_files = sorted(
        f for f in os.listdir(mesh_dir) if f.lower().endswith(IMPORT_EXTENSIONS)
    )
    if not obj_files:
        raise RuntimeError(
            f"No files with extensions {IMPORT_EXTENSIONS} found in: {mesh_dir}"
        )

    imported_objects: list[bpy.types.Object] = []
    for filename in obj_files:
        filepath = os.path.join(mesh_dir, filename)
        new_objects = import_mesh(filepath)
        for obj in new_objects:
            link_to_collection(obj, collection)
        imported_objects.extend(new_objects)

    apply_orientation(imported_objects)
    print(
        f"Imported {len(imported_objects)} objects into collection '{COLLECTION_NAME}' from {mesh_dir}"
    )


if __name__ == "__main__":
    main()
