"""Place an original weapon on Skyrim's weapon axes and write its NIF with collision.

Imported by weapon_blender.py inside Blender and by the application runtime, so it
uses only numpy and PyNifly. Official weapons point along +Y with the root origin
at the grip (SteelSword, SteelMace, SteelGreatSword, ForswornStaff and
DragonPriestStaff3rd measured with PyNifly).
"""
from itertools import combinations, product
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dependencies/io_scene_nifly'))  # PyNifly loads in the functions below
from nif_materials import DOUBLE_SIDED  # noqa: E402

# Blender's glTF importer maps glTF (x, y, z) to Blender (x, -z, y).
GLTF_FROM_BLENDER = np.array([[1., 0, 0], [0, 0, 1], [0, -1, 0]])
GRIP_SLICE = .02  # length fraction around the grip whose X/Z bounding-box centre becomes the origin
MAX_SHAPE_VERTICES = 65535
HULL_DIRECTIONS = np.array([d for d in product((-1, 0, 1), repeat=3) if any(d)], float)
HULL_DIRECTIONS /= np.linalg.norm(HULL_DIRECTIONS, axis=1)[:, None]
MAX_HULL_VERTICES = 48  # official weapon hulls have 12-32 vertices
HULL_COVERAGE = .005  # largest allowed vertex distance outside the hull, as a fraction of the model size
# BSLightingShaderProperty values of the official SteelSword:0 (environment-masked
# metal) and ForswornStaff staff01:0 (no environment map) shapes.
METAL_SHADER = {'Shader_Type': 1, 'Shader_Flags_1': 0x82400381, 'Shader_Flags_2': 0x8001,
                'Glossiness': 80., 'Env_Map_Scale': 1.}
PLAIN_SHADER = {'Shader_Type': 0, 'Shader_Flags_1': 0x82400301, 'Shader_Flags_2': 0x8001,
                'Glossiness': 48., 'Env_Map_Scale': 1.}


def axis_map(points):
    """Rotation taking the longest bounding-box axis to +Y, keeping its low end at -Y."""
    extent = points.max(0) - points.min(0)
    long_axis = int(np.argmax(extent))
    result = np.zeros((3, 3))
    result[0, (long_axis + 2) % 3] = result[1, long_axis] = result[2, (long_axis + 1) % 3] = 1
    return result


def placement(points, grip, length, flip=False, roll=0.):
    """4x4 matrix from glTF coordinates to weapon NIF coordinates."""
    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
        raise ValueError('Weapon model has no usable vertices')
    if not 0 < grip < 1 or not length > 0:
        raise ValueError('Invalid weapon grip/length')
    rotation = axis_map(points)
    if flip:
        rotation = np.diag([-1., -1., 1.]) @ rotation
    cos, sin = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    rotation = np.array([[cos, 0, sin], [0, 1, 0], [-sin, 0, cos]]) @ rotation
    placed = points @ rotation.T
    low, high = placed[:, 1].min(), placed[:, 1].max()
    if not high - low > 0:
        raise ValueError('Weapon model has no length')
    scale = length / (high - low)
    placed *= scale
    grip_y = low * scale + grip * length
    near = placed[np.abs(placed[:, 1] - grip_y) <= GRIP_SLICE * length]
    if not len(near):
        near = placed
    centre = (near.min(0) + near.max(0)) / 2
    result = np.eye(4)
    result[:3, :3] = rotation * scale
    result[:3, 3] = (-centre[0], -grip_y, -centre[2])
    return result


def hull(points, max_vertices=MAX_HULL_VERTICES, coverage=HULL_COVERAGE):
    """Reduced convex hull: extreme points in 26 directions, then the farthest outside vertex
    is added until every vertex lies within coverage * size or max_vertices is reached.

    Returns (vertices, planes); planes are (normal, offset) rows with normal . x <= offset inside.
    """
    points = np.asarray(points, float)
    scale = max(float(np.ptp(points, axis=0).max()), 1e-9)
    picked = np.unique(points[np.argmax(points @ HULL_DIRECTIONS.T, axis=0)], axis=0)
    if len(picked) < 3:
        raise ValueError('Weapon collision needs at least three distinct extreme points')
    while True:
        planes = hull_planes(picked, scale)
        outside = (points @ planes[:, :3].T - planes[:, 3]).max(1)
        worst = int(np.argmax(outside))
        if outside[worst] <= coverage * scale or len(picked) >= max_vertices:
            break
        picked = np.vstack([picked, points[worst]])
    on_planes = np.abs(picked @ planes[:, :3].T - planes[:, 3]) <= 1e-6 * scale
    return picked[on_planes.sum(1) >= 3], planes


def hull_planes(picked, scale, tolerance=1e-6):
    """All supporting planes through triples of a few points (exact hull of a small set)."""
    i, j, k = np.array(list(combinations(range(len(picked)), 3))).T
    normals = np.cross(picked[j] - picked[i], picked[k] - picked[i])
    size = np.linalg.norm(normals, axis=1)
    keep = size > 1e-9 * scale * scale
    normals, base = normals[keep] / size[keep, None], picked[i[keep]]
    offsets = np.einsum('ij,ij->i', normals, base)
    distance = picked @ normals.T - offsets
    below = (distance <= tolerance * scale).all(0)
    above = (distance >= -tolerance * scale).all(0)
    planes = np.vstack([np.column_stack([normals[below], offsets[below]]),
                        np.column_stack([-normals[above], -offsets[above]])])
    if not len(planes):
        raise ValueError('Weapon collision hull is degenerate')
    _, unique = np.unique(np.round(planes / [1, 1, 1, scale], 5), axis=0, return_index=True)
    return planes[np.sort(unique)]


def base_collision(path):
    """Collision values of an official weapon NIF, copied onto the original weapon."""
    from pyn.pynifly import NifFile
    with NifFile(str(path)) as base:
        collision = base.root.collision_object
        if collision is None or collision.blockname != 'bhkCollisionObject' or collision.body is None:
            raise ValueError(f'Base weapon has no bhkCollisionObject rigid body: {path}')
        body = collision.body
        if body.blockname not in ('bhkRigidBody', 'bhkRigidBodyT') or body.shape is None:
            raise ValueError(f'Base weapon collision is not a rigid body with a shape: {path}')
        shape = body.shape.properties
        bsx = base.root.get_extra_data(blockname='BSXFlags')
        inventory = base.root.get_extra_data(blockname='BSInvMarker')
        return {'flags': collision.flags, 'body': body.properties.copy(), 'body_type': body.blockname,
                'shape_type': body.shape.blockname, 'material': shape.bhkMaterial, 'radius': shape.bhkRadius,
                'bsx': int(bsx.flags) if bsx else None,
                'prn': [e.string_data for e in base.root.extra_data(blockname='NiStringExtraData') if e.name == 'Prn'],
                'inventory': (tuple(inventory.rotation), inventory.zoom) if inventory else None}


def write_weapon_nif(path, shapes, base_nif, game='SKYRIMSE'):
    """Write BSFadeNode + BSTriShapes + bhkCollisionObject/bhkRigidBody/bhkConvexVerticesShape."""
    from pyn.nifconstants import HAVOC_SCALE_FACTOR
    from pyn.nifdefs import NODEID_NONE, PynBufferTypes, bhkConvexVerticesShapeProps
    from pyn.pynifly import BSInvMarker, BSTriShape, BSXFlags, NifFile, NiStringExtraData
    base = base_collision(base_nif)
    nif = NifFile()
    nif.initialize(game, str(path), root_type='BSFadeNode', root_name='weapon')
    root = nif.rootNode
    if base['bsx'] is not None:
        BSXFlags.New(nif, flags=base['bsx'], parent=root)
    for value in base['prn']:
        NiStringExtraData.New(nif, name='Prn', string_value=value, parent=root)
    if base['inventory']:
        BSInvMarker.New(nif, rotation=base['inventory'][0], zoom=base['inventory'][1], parent=root)
    for shape in shapes:
        vertices = np.asarray(shape['vertices'], float)
        if not 0 < len(vertices) <= MAX_SHAPE_VERTICES:
            raise ValueError(f"Weapon shape vertex count outside 1-{MAX_SHAPE_VERTICES}: {shape['name']}")
        created = nif.createShapeFromData(
            shape['name'], [tuple(v) for v in vertices], [tuple(t) for t in np.asarray(shape['triangles'], int)],
            [tuple(uv) for uv in np.asarray(shape['uvs'], float)], [tuple(n) for n in np.asarray(shape['normals'], float)],
            props=BSTriShape.getbuf(), parent=root)
        shader = created.shader.properties
        shader.bufType = PynBufferTypes.BSLightingShaderPropertyBufType
        for key, value in (METAL_SHADER if shape['metal'] else PLAIN_SHADER).items():
            setattr(shader, key, value)
        shader.Spec_Color = (1., 1., 1.)
        shader.Spec_Str = 1.
        shader.Alpha = shape.get('alpha', 1.)
        if shape.get('double_sided'):
            shader.Shader_Flags_2 |= DOUBLE_SIDED
        for slot, texture in shape['textures'].items():
            created.set_texture(slot, texture)
        created.save_shader_attributes()
    collision = root.add_collision(None, flags=base['flags'], collision_type=PynBufferTypes.bhkCollisionObjectBufType)
    body_props = base['body']
    body_props.shapeID = NODEID_NONE
    body = collision.add_body(body_props)
    points, planes = hull(np.concatenate([np.asarray(s['vertices'], float) for s in shapes]))
    props = bhkConvexVerticesShapeProps(game=game)
    props.bhkMaterial, props.bhkRadius = base['material'], base['radius']
    nif.add_shape(props, parent=body, vertices=[tuple(p) for p in points / HAVOC_SCALE_FACTOR],
                  normals=[(*n, -d / HAVOC_SCALE_FACTOR) for *n, d in planes])
    nif.save()
    return {'flags': base['flags'], 'hull_vertices': len(points), 'hull_planes': len(planes), 'base_shape_type': base['shape_type'],
            'mass': base['body'].mass, 'prn': base['prn']}


def read_weapon(path):
    """Read back geometry, textures and collision blocks of a weapon NIF."""
    from pyn.nifconstants import HAVOC_SCALE_FACTOR
    from pyn.pynifly import NifFile
    with NifFile(str(path)) as nif:
        shapes = []
        for shape in nif.shapes:
            shapes.append({'name': shape.name, 'block': shape.blockname, 'vertices': len(shape.verts),
                           'triangles': len(shape.tris), 'textures': dict(shape.textures),
                           'points': np.array(shape.verts, float),
                           'translation': list(shape.transform.translation[:]), 'scale': shape.transform.scale})
        collision = nif.root.collision_object
        body = collision.body if collision else None
        convex = body.shape if body else None
        return {'game': nif.game, 'root': nif.root.blockname, 'shapes': shapes,
                'collision': collision.blockname if collision else None,
                'collision_flags': collision.flags if collision else None,
                'body': body.blockname if body else None,
                'layer': body.properties.collisionFilter_layer if body else None,
                'mass': body.properties.mass if body else None,
                'shape': convex.blockname if convex else None,
                'hull': np.array(convex.vertices, float)[:, :3] * HAVOC_SCALE_FACTOR
                if convex is not None and convex.blockname == 'bhkConvexVerticesShape' else None,
                'hull_planes': len(convex.normals) if convex is not None and convex.blockname == 'bhkConvexVerticesShape' else 0}


def matrix(transform):
    result = np.eye(4)
    result[:3, :3] = np.array(transform.rotation, float) * transform.scale
    result[:3, 3] = transform.translation[:]
    return result


def base_dimensions(path):
    """Length along +Y and grip fraction of an official weapon NIF, without scabbard/blood shapes."""
    from pyn.pynifly import NifFile
    with NifFile(str(path)) as nif:
        points = []
        for shape in nif.shapes:
            name = shape.name.lower()
            if shape.shader.blockname != 'BSLightingShaderProperty' or name.startswith('scb') or 'blood' in name:
                continue
            # NiShape.global_transform is its parent's; compose the shape's own transform.
            world = matrix(shape.parent.global_transform) @ matrix(shape.transform)
            points.append(np.array(shape.verts, float) @ world[:3, :3].T + world[:3, 3])
    if not points:
        raise ValueError(f'Base weapon has no lighting-shader geometry: {path}')
    y = np.concatenate(points)[:, 1]
    length = float(y.max() - y.min())
    if not length > 0 or not y.min() < 0 < y.max():
        raise ValueError(f'Base weapon origin is not inside its +Y extent: {path}')
    return {'length': length, 'grip': float(-y.min() / length)}
