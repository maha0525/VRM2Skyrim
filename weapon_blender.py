"""Original GLB weapon -> Skyrim weapon NIF (+Y blade, grip at the origin, collision)."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'dependencies'))
from weapon_nif import GLTF_FROM_BLENDER, placement, read_weapon, write_weapon_nif  # noqa: E402

LOG = logging.getLogger('converter')
NORMAL_ATTRIBUTE = 'V2S_weapon_normal'


def select_only(objects, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[0]


def shape_arrays(obj):
    """NIF vertices are unique (vertex, corner normal, UV) triples of the Blender mesh."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    positions = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', positions)
    loop_vertices = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get('vertex_index', loop_vertices)
    normals = np.empty(len(mesh.loops) * 3)
    mesh.attributes[NORMAL_ATTRIBUTE].data.foreach_get('vector', normals)
    uvs = np.zeros(len(mesh.loops) * 2)
    if mesh.uv_layers:
        mesh.uv_layers[0].data.foreach_get('uv', uvs)
    corners = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get('loops', corners)
    keys = np.column_stack([loop_vertices[corners], normals.reshape(-1, 3)[corners], uvs.reshape(-1, 2)[corners]])
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    vertex = unique[:, 0].astype(np.int64)
    return {'vertices': positions.reshape(-1, 3)[vertex], 'normals': unique[:, 1:4],
            # Blender UVs start at the bottom; NIF UVs start at the top.
            'uvs': np.column_stack([unique[:, 4], 1 - unique[:, 5]]),
            'triangles': inverse.reshape(-1, 3)}


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args(sys.argv[sys.argv.index('--') + 1:]).output.resolve()
    plan = json.loads((output / 'weapon-plan.json').read_text(encoding='utf8'))
    source = Path(plan['glb'])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    sources = [obj for obj in imported if obj.type == 'MESH']
    if not sources:
        raise ValueError('The GLB contains no mesh')
    depsgraph = bpy.context.evaluated_depsgraph_get()
    meshes = [(bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph)), np.array(obj.matrix_world))
              for obj in sources]
    points = []
    for mesh, world in meshes:
        values = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get('co', values)
        points.append((values.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]) @ GLTF_FROM_BLENDER.T)
    to_nif = placement(np.concatenate(points), plan['grip'], plan['length'], plan['flip'], plan['roll'])
    total = np.eye(4)
    total[:3, :3] = GLTF_FROM_BLENDER
    total = to_nif @ total
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    objects = []
    for index, (mesh, world) in enumerate(meshes):
        full = total @ world
        # Mesh.transform re-derives custom normals and flips some on degenerate fans
        # (70 of 59,997 corners on the first Tripo staff); carry rotated normals instead.
        normals = np.empty(len(mesh.loops) * 3)
        mesh.corner_normals.foreach_get('vector', normals)
        normals = normals.reshape(-1, 3) @ np.linalg.inv(full[:3, :3])
        normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
        mesh.attributes.new(NORMAL_ATTRIBUTE, 'FLOAT_VECTOR', 'CORNER').data.foreach_set('vector', normals.reshape(-1))
        mesh.transform(Matrix(full.tolist()))
        if np.linalg.det(full[:3, :3]) < 0:
            # Mesh.transform keeps the corner order of a mirrored node, which turns its faces inside out;
            # flip_normals reverses each face and carries its UVs and NORMAL_ATTRIBUTE corners with it.
            mesh.flip_normals()
        obj = bpy.data.objects.new(f'V2SWeapon_{index:03}', mesh)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
    if len(objects) > 1:
        select_only(objects)
        bpy.ops.object.join()
        objects = [bpy.context.view_layer.objects.active]
    weapon = objects[0]
    # PyNifly writes one shader per shape; give each glTF material its own shape.
    if len(weapon.material_slots) > 1:
        select_only([weapon])
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')
    from blender_meshes import partition_shape
    materials = plan['materials']
    shapes = []
    for obj in sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'), key=lambda o: o.name):
        if not obj.data.polygons:
            continue
        slot = obj.data.polygons[0].material_index
        material = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
        key = material.name if material and material.name in materials else 'default'
        if key not in materials:
            raise ValueError(f'Weapon shape uses an unexpected material: {material.name if material else None}')
        obj.name = 'Weapon_' + key.rsplit('_', 1)[-1]
        for part in partition_shape(obj):
            arrays = shape_arrays(part)
            if not len(arrays['triangles']):
                continue
            shapes.append({'name': part.name, 'material': key, **arrays, **materials[key]})
    shapes.sort(key=lambda s: s['name'])
    nif = output / 'mod' / plan['nif']
    nif.parent.mkdir(parents=True, exist_ok=True)
    collision = write_weapon_nif(nif, shapes, plan['base_nif'], plan['prn'])
    policies = {s['name']: plan['policies'][s['material']] for s in shapes}
    from nif_materials import apply_alpha
    apply_alpha(nif, policies)
    readback = read_weapon(nif)
    if (readback['collision'] != 'bhkCollisionObject' or readback['body'] != 'bhkRigidBody'
            or readback['shape'] != 'bhkConvexVerticesShape'):
        raise RuntimeError('Weapon collision did not survive export')
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError('Weapon GLB changed during conversion')
    report = {'placement': to_nif.tolist(), 'collision': collision,
              'shapes': [{'name': s['name'], 'material': s['material'], 'vertices': len(s['vertices']),
                          'triangles': len(s['triangles'])} for s in shapes]}
    (output / 'weapon-nif.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    LOG.info('Original weapon NIF: %s shapes, %s triangles, hull %s vertices/%s planes', len(shapes),
             sum(len(s['triangles']) for s in shapes), collision['hull_vertices'], collision['hull_planes'])


if __name__ == '__main__':
    main()
