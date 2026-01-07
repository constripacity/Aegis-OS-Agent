"""Coordinate system conversion utilities for Unity to Blender.

Unity: Left-handed, Y-up, Z-forward
Blender: Right-handed, Z-up, Y-forward (technically -Y forward in some contexts, but usually Z-up)

Transformation:
Position: (x, y, z) -> (x, z, y)  (Swapping Y and Z)
Rotation: Quaternion (x, y, z, w) -> (x, z, y, -w)  (Swapping Y and Z, inverting W)
Scale: (x, y, z) -> (x, z, y)
"""

import math
from mathutils import Vector, Quaternion, Matrix

def unity_pos_to_blender(pos):
    """Convert Unity position [x, y, z] to Blender [x, -z, y]."""
    # Check if input is list or Vector
    x, y, z = pos
    # Standard Unity -> Blender mapping often used:
    # Unity X -> Blender X
    # Unity Y -> Blender Z
    # Unity Z -> Blender Y
    return Vector((x, z, y))

def unity_rot_to_blender(rot):
    """Convert Unity Quaternion [x, y, z, w] to Blender Quaternion."""
    ux, uy, uz, uw = rot
    
    # Unity is Left-Handed (X, Y, Z)
    # Blender is Right-Handed (X, Y, Z)
    # Conversion from Unity (L) to Blender (R):
    # (bx, by, bz, bw) = (ux, uz, uy, -uw)
    
    return Quaternion((-uw, ux, uz, uy)) # Blender uses (W, X, Y, Z) order internally

def unity_scale_to_blender(scale):
    """Convert Unity scale [x, y, z] to Blender."""
    x, y, z = scale
    return Vector((x, z, y))

def convert_transform_matrix(pos, rot, scale):
    """Build a Blender matrix from Unity transform data."""
    loc = unity_pos_to_blender(pos)
    qua = unity_rot_to_blender(rot)
    sca = unity_scale_to_blender(scale)
    
    mat = Matrix.LocRotScale(loc, qua, sca)
    return mat
