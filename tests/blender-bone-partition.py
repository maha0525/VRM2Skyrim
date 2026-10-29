"""Blender probe: partition_shape keeps every exported shape within the NIF bone limit."""
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from blender_meshes import partition_shape, skin_bones  # noqa: E402

output = Path(sys.argv[sys.argv.index('--') + 1])
count = int(sys.argv[sys.argv.index('--') + 2])
bpy.ops.wm.read_factory_settings(use_empty=True)
vertices, faces = [], []
for strand in range(count):
    start = len(vertices)
    vertices += [(strand, 0, 0), (strand + .5, 0, 0), (strand + .5, 0, 1), (strand, 0, 1)]
    faces.append((start, start + 1, start + 2, start + 3))
mesh = bpy.data.meshes.new('Hair')
mesh.from_pydata(vertices, [], faces)
obj = bpy.data.objects.new('Hair', mesh)
bpy.context.scene.collection.objects.link(obj)
obj.vertex_groups.new(name='SBP_130_HEAD').add(list(range(len(vertices))), 1., 'REPLACE')
for strand in range(count):
    # The strand root shares its neighbour's bone, so groups overlap across strands.
    own = obj.vertex_groups.new(name=f'Hair {strand:03}')
    own.add([4*strand + 2, 4*strand + 3], 1., 'REPLACE')
    root = obj.vertex_groups.get(f'Hair {max(strand - 1, 0):03}')
    root.add([4*strand, 4*strand + 1], 1., 'REPLACE')
parts = partition_shape(obj)
report = [{'name': p.name, 'vertices': len(p.data.vertices),
           'groups': sorted(g.name for g in p.vertex_groups),
           'weighted': sorted(p.vertex_groups[i].name for i in set().union(*skin_bones(p)))} for p in parts]
output.write_text(json.dumps(report), encoding='utf8')
