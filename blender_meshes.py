"""Geometry partitioning that does not depend on an avatar's mesh names."""
import bmesh
import bpy
import logging


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


def partition_shape(obj, limit=60000):
    if len(obj.data.vertices) <= limit and len(obj.data.loops) <= limit:
        return [obj]
    chunks, faces, used, loops = [], [], set(), 0
    for polygon in obj.data.polygons:
        vertices = set(polygon.vertices)
        if (len(used | vertices) > limit or loops + len(polygon.vertices) > limit) and faces:
            chunks.append(faces)
            faces, used, loops = [], set(), 0
        faces.append(polygon.index)
        used |= vertices
        loops += len(polygon.vertices)
    if faces:
        chunks.append(faces)
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
        parts.append(copy)
    bpy.data.objects.remove(obj, do_unlink=True)
    return parts
