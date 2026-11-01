"""Run in factory Blender: a glTF color factor mixed with vertex colors, with no image."""
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from convert_blender import save_images  # noqa: E402
from settings import FollowerSettings  # noqa: E402

output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='io_scene_nifly')
settings = FollowerSettings(mod_id='VertexFixture')
factor = [.27, .037, .037, 1]
material = bpy.data.materials.new('VertexTint')
material.use_nodes = True
tree = material.node_tree
shader = next(node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED')
mix = tree.nodes.new('ShaderNodeMix')
mix.data_type = 'RGBA'
mix.inputs['B'].default_value = factor
colors = tree.nodes.new('ShaderNodeVertexColor')
tree.links.new(colors.outputs['Color'], mix.inputs['A'])
tree.links.new(mix.outputs['Result'], shader.inputs['Base Color'])
mesh = bpy.data.meshes.new('Tint')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
mesh.materials.append(material)
obj = bpy.data.objects.new('Tint', mesh)
bpy.context.scene.collection.objects.link(obj)
save_images([obj], output, settings, {material.name: {'pbrMetallicRoughness': {'baseColorFactor': factor}}})
linked = shader.inputs['Base Color'].links[0].from_node
image = bpy.data.images['solid_' + material.name]
(output / 'report.json').write_text(json.dumps({
    'diffuse': material['V2S_Diffuse_Path'], 'linked_to_image': linked.type == 'TEX_IMAGE' and linked.image == image,
    'pixel': list(image.pixels[:4])}), encoding='utf8')
