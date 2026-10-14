"""Run in factory Blender: shared diffuse tint extraction and native NIF readback."""
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from convert_blender import save_images, select_only  # noqa: E402
from custom_skeleton import NifFile  # noqa: E402
from nif_materials import apply_alpha  # noqa: E402
from settings import FollowerSettings  # noqa: E402

output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='io_scene_nifly')
settings = FollowerSettings(mod_id='MaterialFixture')
settings.save(output/'settings.json')
image = bpy.data.images.new('SharedWhite', width=2, height=2)
image.generated_color = (1, 1, 1, .5)
original_path = image.filepath
original_pixels = list(image.pixels)
materials, meshes = {}, []
for index, factor in enumerate(((0, 0, 0, .375), (.5, .25, 1, .7), (1, 1, 1, 1))):
    material = bpy.data.materials.new('Test' + str(index))
    material.use_nodes = True
    tree = material.node_tree
    texture = tree.nodes.new('ShaderNodeTexImage')
    texture.image = image
    multiply = tree.nodes.new('ShaderNodeMixRGB')
    multiply.blend_type = 'MULTIPLY'
    multiply.inputs[0].default_value = 1
    multiply.inputs[2].default_value = factor
    shader = next(node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED')
    tree.links.new(texture.outputs['Color'], multiply.inputs[1])
    tree.links.new(multiply.outputs[0], shader.inputs['Base Color'])
    tree.links.new(texture.outputs['Alpha'], shader.inputs['Alpha'])
    if index == 0:
        normal_texture = tree.nodes.new('ShaderNodeTexImage')
        normal_texture.image = image
        normal = tree.nodes.new('ShaderNodeNormalMap')
        tree.links.new(normal_texture.outputs['Color'], normal.inputs['Color'])
        tree.links.new(normal.outputs['Normal'], shader.inputs['Normal'])
    materials[material.name] = {'alphaMode': 'BLEND', 'pbrMetallicRoughness': {
        'baseColorFactor': factor, 'baseColorTexture': {'index': 0}}}
    bpy.ops.mesh.primitive_plane_add(location=(index, 0, 0))
    obj = bpy.context.object
    obj.name = material.name
    obj.data.materials.append(material)
    meshes.append(obj)
save_images(meshes, output, settings, materials)
assert image.filepath == original_path and list(image.pixels) == original_pixels
recipes = json.loads((output/'textures.json').read_text())
assert {tuple(item['base_color_factor']) for item in recipes} == {(0, 0, 0), (.5, .25, 1), (1, 1, 1)}
assert len({item['relative'] for item in recipes}) == 3
assert len({obj.data.materials[0].node_tree.nodes.get('Image Texture').image for obj in meshes}) == 3
target = output/'fixture.nif'
select_only(meshes)
bpy.ops.export_scene.pynifly(filepath=str(target), target_game='SKYRIMSE', intuit_defaults=False)
apply_alpha(target, {obj.name: materials[obj.data.materials[0].name] for obj in meshes})
with NifFile(str(target)) as nif:
    assert len(nif.shapes) == 3
    for shape in nif.shapes:
        index = int(shape.name[-1])
        expected = meshes[index].data.materials[0]['V2S_Diffuse_Path'].replace('/', '\\')
        assert shape.textures['Diffuse'] == expected
        assert abs(shape.shader.properties.Alpha - (1 if index == 2 else .375 if index == 0 else .7)) < 1e-6
print('PASS: shared-image tint recipes, untouched original reference, distinct diffuse paths and shader alpha')
