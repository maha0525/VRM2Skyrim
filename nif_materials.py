"""Preserve glTF alpha mode and face culling in Skyrim lighting materials."""
import logging

DOUBLE_SIDED = 1 << 4  # PyNifly ShaderFlags2.DOUBLE_SIDED / Skyrim shader flag.


def lighting_flags_2(material):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    flags = ['VERTEX_COLORS']
    if material.get('alphaMode', 'OPAQUE') != 'BLEND' or mtoon.get('transparentWithZWrite', False):
        flags.insert(0, 'ZBUFFER_WRITE')
    if material.get('doubleSided', False):
        flags.append('DOUBLE_SIDED')
    return ' | '.join(flags)


def culling_flags(flags, material):
    return flags | DOUBLE_SIDED if material.get('doubleSided', False) else flags & ~DOUBLE_SIDED


def apply_alpha(path, materials):
    from custom_skeleton import NifFile
    with NifFile(str(path)) as file:
        for shape in file.shapes:
            material = materials[shape.name]
            props = shape.shader.properties
            props.Shader_Flags_2 = culling_flags(props.Shader_Flags_2, material)
            shape.shader.write_properties()
            logging.debug('Material %s: doubleSided=%s alphaMode=%s', shape.name,
                          material.get('doubleSided', False), material.get('alphaMode', 'OPAQUE'))
            mode = material.get("alphaMode", "OPAQUE")
            if mode == "OPAQUE":
                continue
            shape.has_alpha_property = True
            alpha = shape.alpha_property.properties
            alpha.flags = 4844
            alpha.alpha_blend = mode == "BLEND"
            alpha.alpha_test = mode == "MASK"
            alpha.source_blend_mode = 6
            alpha.dst_blend_mode = 7
            alpha.threshold = round(material.get("alphaCutoff", .5) * 255)
            shape.save_alpha_property()
            shape.write_properties()
        file.save()
    # Read the actual exported flags, rather than treating exporter settings as proof.
    with NifFile(str(path)) as file:
        for shape in file.shapes:
            if bool(shape.shader.properties.Shader_Flags_2 & DOUBLE_SIDED) != bool(materials[shape.name].get('doubleSided', False)):
                raise ValueError('Exported material face culling differs from source: '+shape.name)
