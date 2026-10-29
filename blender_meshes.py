"""Geometry partitioning that does not depend on an avatar's mesh names."""
import bmesh
import bpy
import logging
import json
from pathlib import Path


def linked_texture_nodes(socket):
    """Find texture nodes feeding a glTF base-color multiply, without changing it."""
    result, visited = [], set()

    def visit(current):
        for link in current.links:
            node = link.from_node
            if node in visited:
                continue
            visited.add(node)
            if node.type == 'TEX_IMAGE' and node.image is not None:
                result.append(node)
            else:
                for input_socket in node.inputs:
                    visit(input_socket)

    visit(socket)
    return result


def render_material_queues(scene):
    """Render explicit MToon alpha queues as depth-masked layers.

    Cycles traces geometric depth, ignoring raster renderQueue. Holdouts retain
    opaque depth occlusion while alpha-over puts later queues over earlier ones.
    PNG image inputs are color-managed by Blender's compositor in linear space.
    """
    from nif_materials import render_queue
    scene.cycles.transparent_max_bounces = max(scene.cycles.transparent_max_bounces, 64)
    materials = {m for obj in scene.objects if obj.type == 'MESH' and not obj.hide_render
                 for m in obj.data.materials if m and m.use_nodes}
    policies = {m: json.loads(m.get('V2S_Preview_Policy', '{}')) for m in materials}
    queues = sorted({render_queue(p) for p in policies.values() if p.get('alphaMode') == 'BLEND'})
    if len(queues) <= 1:
        bpy.ops.render.render(write_still=True)
        return
    original_path, original_transparent = scene.render.filepath, scene.render.film_transparent
    layers = []
    sockets, temporary = {}, []
    for material in materials:
        outputs = [n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
        if outputs and outputs[0].inputs['Surface'].is_linked:
            socket = outputs[0].inputs['Surface']
            sockets[material] = (socket, socket.links[0].from_socket)
    try:
        for index, queue in enumerate(queues):
            for material, (surface, original) in sockets.items():
                tree, policy = material.node_tree, policies[material]
                mode, current = policy.get('alphaMode', 'OPAQUE'), render_queue(policy)
                if mode == 'BLEND' and (current > queue or (index and current < queue)):
                    node = tree.nodes.new('ShaderNodeBsdfTransparent')
                    temporary.append((tree, node))
                    tree.links.new(node.outputs[0], surface)
                elif index and mode != 'BLEND':
                    holdout = tree.nodes.new('ShaderNodeHoldout')
                    temporary.append((tree, holdout))
                    tree.links.new(holdout.outputs[0], surface)
                    # Masked holes and culled backfaces must not become depth blockers.
                    factors = []
                    if mode == 'MASK':
                        shader = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                        images = linked_texture_nodes(shader.inputs['Base Color']) if shader else [
                            n for n in tree.nodes if n.type == 'TEX_IMAGE' and n.image and 'flat_n' not in n.image.filepath]
                        multiply = tree.nodes.new('ShaderNodeMath')
                        multiply.operation = 'MULTIPLY'
                        multiply.inputs[0].default_value = 1
                        multiply.inputs[1].default_value = policy.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1]*4)[3]
                        if images:
                            tree.links.new(images[0].outputs['Alpha'], multiply.inputs[0])
                        test = tree.nodes.new('ShaderNodeMath')
                        test.operation = 'LESS_THAN'
                        test.inputs[1].default_value = policy.get('alphaCutoff', .5)
                        tree.links.new(multiply.outputs[0], test.inputs[0])
                        temporary.extend(((tree, multiply), (tree, test)))
                        factors.append(test.outputs[0])
                    if not policy.get('doubleSided', False):
                        geometry = tree.nodes.new('ShaderNodeNewGeometry')
                        temporary.append((tree, geometry))
                        factors.append(geometry.outputs['Backfacing'])
                    for factor in factors:
                        incoming = surface.links[0].from_socket
                        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
                        mix = tree.nodes.new('ShaderNodeMixShader')
                        tree.links.new(factor, mix.inputs[0])
                        tree.links.new(incoming, mix.inputs[1])
                        tree.links.new(transparent.outputs[0], mix.inputs[2])
                        tree.links.new(mix.outputs[0], surface)
                        temporary.extend(((tree, transparent), (tree, mix)))
                else:
                    tree.links.new(original, surface)
            scene.render.film_transparent = original_transparent if index == 0 else True
            path = Path(original_path)
            passes = path.parent/'.material-passes'
            passes.mkdir(exist_ok=True)
            scene.render.filepath = str(passes/(path.stem+f'-queue-{queue}.png'))
            bpy.ops.render.render(write_still=True)
            layers.append(scene.render.filepath)
        for material, (surface, original) in sockets.items():
            material.node_tree.links.new(original, surface)
        for tree, node in temporary:
            tree.nodes.remove(node)
        temporary.clear()
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()
        previous = None
        for path in layers:
            node = tree.nodes.new('CompositorNodeImage')
            node.image = bpy.data.images.load(path, check_existing=False)
            if previous is None:
                previous = node.outputs['Image']
            else:
                over = tree.nodes.new('CompositorNodeAlphaOver')
                tree.links.new(previous, over.inputs[1])
                tree.links.new(node.outputs['Image'], over.inputs[2])
                previous = over.outputs['Image']
        result = tree.nodes.new('CompositorNodeComposite')
        tree.links.new(previous, result.inputs['Image'])
        scene.render.filepath = original_path
        bpy.ops.render.render(write_still=True)
        logging.info('Preview retained explicit alpha queues %s: %s', queues, original_path)
    finally:
        for material, (surface, original) in sockets.items():
            material.node_tree.links.new(original, surface)
        for tree, node in temporary:
            tree.nodes.remove(node)
        scene.use_nodes = False
        scene.render.filepath, scene.render.film_transparent = original_path, original_transparent


def preview_face_culling(material, double_sided=False):
    """Cycles needs a shader branch; viewport backface culling alone is ignored."""
    material.use_backface_culling = not double_sided
    logging.debug('Preview material %s: doubleSided=%s', material.name, double_sided)
    if double_sided or not material.use_nodes or material.node_tree.nodes.get('V2S_BackfaceCulling'):
        return
    tree = material.node_tree
    outputs = [node for node in tree.nodes if node.type == 'OUTPUT_MATERIAL']
    output = next((node for node in outputs if node.is_active_output), outputs[0] if outputs else None)
    if output is None or not output.inputs['Surface'].is_linked:
        return
    incoming = output.inputs['Surface'].links[0].from_socket
    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    mix = tree.nodes.new('ShaderNodeMixShader')
    mix.name = 'V2S_BackfaceCulling'
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    tree.links.new(geometry.outputs['Backfacing'], mix.inputs[0])
    tree.links.new(incoming, mix.inputs[1])
    tree.links.new(transparent.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], output.inputs['Surface'])


def skin_bones(obj):
    """Bone vertex groups each vertex is weighted to; SBP_ groups mark body partitions, not bones."""
    bones = {g.index for g in obj.vertex_groups if not g.name.startswith('SBP_')}
    return [{g.group for g in vertex.groups if g.group in bones and g.weight > 0} for vertex in obj.data.vertices]


def partition_shape(obj, limit=60000, bone_limit=None):
    from nif_limits import SHAPE_BONE_LIMIT
    bone_limit = bone_limit or SHAPE_BONE_LIMIT
    weighted = skin_bones(obj)
    if (len(obj.data.vertices) <= limit and len(obj.data.loops) <= limit and
            len(set().union(*weighted)) <= bone_limit):
        return [obj]
    chunks, faces, used, loops, bones = [], [], set(), 0, set()
    for polygon in obj.data.polygons:
        vertices = set(polygon.vertices)
        face_bones = set().union(*(weighted[v] for v in vertices))
        if (len(used | vertices) > limit or loops + len(polygon.vertices) > limit or
                len(bones | face_bones) > bone_limit) and faces:
            chunks.append(faces)
            faces, used, loops, bones = [], set(), 0, set()
        faces.append(polygon.index)
        used |= vertices
        loops += len(polygon.vertices)
        bones |= face_bones
    if faces:
        chunks.append(faces)
    logging.info('Partition %s: %s vertices, %s bones -> %s shapes', obj.name, len(obj.data.vertices),
                 len(set().union(*weighted)), len(chunks))
    parts = []
    for index, indices in enumerate(chunks):
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.name = f"{obj.name}_Part{index:03}"
        bpy.context.scene.collection.objects.link(copy)
        mesh = bmesh.new()
        mesh.from_mesh(copy.data)
        layer = mesh.loops.layers.float_vector.new("V2S_preserved_normal")
        for face, polygon in zip(mesh.faces, obj.data.polygons):
            for loop, loop_index in zip(face.loops, polygon.loop_indices):
                loop[layer] = obj.data.corner_normals[loop_index].vector
        mesh.faces.ensure_lookup_table()
        keep = set(indices)
        bmesh.ops.delete(mesh, geom=[face for face in mesh.faces if face.index not in keep], context="FACES_ONLY")
        bmesh.ops.delete(mesh, geom=[vertex for vertex in mesh.verts if not vertex.link_faces], context="VERTS")
        mesh.to_mesh(copy.data)
        mesh.free()
        copy.data.normals_split_custom_set([item.vector for item in copy.data.attributes["V2S_preserved_normal"].data])
        copy.data.attributes.remove(copy.data.attributes["V2S_preserved_normal"])
        copy.data.update()
        # Every vertex group becomes a NIF bone; keep only the bones this part is weighted to.
        weighted = set().union(*skin_bones(copy))
        for name in [g.name for g in copy.vertex_groups if not g.name.startswith('SBP_') and g.index not in weighted]:
            copy.vertex_groups.remove(copy.vertex_groups[name])
        parts.append(copy)
    bpy.data.objects.remove(obj, do_unlink=True)
    return parts
