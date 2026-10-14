"""A later alpha draw behind an earlier alpha draw, with opaque depth blocking."""
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from blender_meshes import render_material_queues  # noqa: E402

output = Path(sys.argv[sys.argv.index('--')+1]).resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.render.resolution_x = scene.render.resolution_y = 64
scene.view_settings.view_transform = 'Standard'
scene.world = bpy.data.worlds.new('World')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.1,.3,.6,1)
for name, z, color, mode, queue in [('Face',0,(1,1,1,1),'OPAQUE',2000),
        ('EarlyWhite',.2,(1,1,1,1),'BLEND',3000), ('LateRed',.1,(1,0,0,1),'BLEND',4000),
        ('HiddenYellow',-.1,(1,1,0,1),'BLEND',5000)]:
    bpy.ops.mesh.primitive_plane_add(location=(0,0,z))
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    target = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(emission.outputs[0], target.inputs['Surface'])
    mat['V2S_Preview_Policy'] = json.dumps({'alphaMode':mode,'extras':{'V2S_render_queue':queue}})
    bpy.context.object.data.materials.append(mat)
bpy.ops.object.camera_add(location=(0,0,5))
camera = bpy.context.object
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 4
scene.camera = camera
scene.render.filepath = str(output/'physical-depth.png')
bpy.ops.render.render(write_still=True)
before = bpy.data.images.load(scene.render.filepath)
corner = tuple(before.pixels[:4])
scene.render.filepath = str(output/'queue-order.png')
render_material_queues(scene)
after = bpy.data.images.load(scene.render.filepath)
center = tuple(after.pixels[4*(32*64+32):4*(32*64+32)+4])
assert center[0] > .99 and center[1] < .01 and center[2] < .01, center
assert max(abs(a-b) for a,b in zip(corner,after.pixels[:4])) < .005
assert not scene.use_nodes and not scene.render.film_transparent
assert not list(output.glob('*-queue-[0-9]*.png'))
assert list((output/'.material-passes').glob('*-queue-[0-9]*.png'))
assert all(not any(n.type in ('HOLDOUT','BSDF_TRANSPARENT') for n in m.node_tree.nodes)
           for m in bpy.data.materials if m.use_nodes)
print('PASS: late alpha queue over early alpha, opaque depth occlusion, background and restored scene')
