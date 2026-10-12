"""Keep Blender primitive/chunk names stable through PyNifly's name cleanup."""
import re


def stable_shape_name(name):
    # PyNifly strips .NNN even when followed by a partition/chunk suffix. When
    # the unsuffixed primitive has been split into chunks, a different material
    # can unexpectedly claim that free base name. Never export such suffixes.
    return re.sub(r'\.(\d{3})', r'_Primitive\1', name)


def stabilize_mesh_names(meshes):
    names = set()
    for mesh in meshes:
        name = stable_shape_name(mesh.name)
        if name in names:
            raise ValueError('Duplicate stable NIF shape name: '+name)
        names.add(name)
        mesh.name = name
        if mesh.name != name:
            raise ValueError('Blender changed the stable NIF shape name: '+name)
