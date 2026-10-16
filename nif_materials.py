"""Preserve glTF alpha mode and face culling in Skyrim lighting materials."""
import logging

DOUBLE_SIDED = 1 << 4  # PyNifly ShaderFlags2.DOUBLE_SIDED / Skyrim shader flag.
NO_SORTER = 0x2000  # NiAlphaProperty: preserve explicitly ordered alpha draws.


def render_queue(material):
    mode = material.get('alphaMode', 'OPAQUE')
    return material.get('extras', {}).get('V2S_render_queue',
                                        {'OPAQUE': 2000, 'MASK': 2450, 'BLEND': 3000}[mode])


def ordered_alpha(materials):
    return len({render_queue(m) for m in materials.values() if m.get('alphaMode') == 'BLEND'}) > 1


def order_alpha_shapes(file, materials):
    """Honor explicit source alpha queues, retaining all skeleton child slots."""
    if not ordered_alpha(materials):
        return
    from custom_skeleton import children, set_children
    groups = {}
    for shape in file.shapes:
        groups.setdefault(shape.parent.name, []).append(shape)
    for name, shapes in groups.items():
        parent = file.nodes[name]
        ids = children(file, parent)
        shape_ids = {s.id for s in shapes}
        ordered = iter(s.id for s in sorted(shapes, key=lambda s: render_queue(materials[s.name])))
        set_children(file, parent, [next(ordered) if n in shape_ids else n for n in ids])
    logging.info('Preserved explicit alpha queues: %s', sorted({render_queue(m) for m in materials.values()}))


def validate_alpha_order(file, materials):
    if not ordered_alpha(materials):
        return
    from custom_skeleton import children
    shapes = {s.id: s for s in file.shapes if s.name in materials}
    for parent in {s.parent.name for s in shapes.values()}:
        queues = [render_queue(materials[shapes[n].name]) for n in children(file, file.nodes[parent]) if n in shapes]
        if queues != sorted(queues):
            raise ValueError('NIF lost original alpha render queues: '+parent)
    for shape in shapes.values():
        if materials[shape.name].get('alphaMode') == 'BLEND' and not shape.alpha_property.properties.flags & NO_SORTER:
            raise ValueError('NIF enables depth sorting over original material order: '+shape.name)


def normalize_material_colors(document):
    """VRM0 MToon _Color is sRGB; glTF baseColorFactor must be linear.

    UniVRM MigrationMToonMaterial converts LitColor from sRGB to Linear.
    Read the authoritative legacy property each time, so this is idempotent.
    VRM1 and ordinary glTF factors already use linear color and stay unchanged.
    """
    legacy = document.get('extensions', {}).get('VRM', {}).get('materialProperties', [])
    for material, properties in zip(document.get('materials', []), legacy):
        if properties.get('shader') != 'VRM/MToon':
            continue
        color = properties.get('vectorProperties', {}).get('_Color')
        if color is not None:
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in color[:3]] + [color[3]]
            material.setdefault('pbrMetallicRoughness', {})['baseColorFactor'] = linear
            logging.info('VRM0 MToon color %s: sRGB %s -> linear %s; alpha unchanged',
                         material.get('name', ''), color, linear)
        props = properties.get('floatProperties', {})
        material.setdefault('extras', {})['V2S_render_queue'] = properties.get('renderQueue', 3000
                                                      if material.get('alphaMode') == 'BLEND' else 2000)
        mtoon = material.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {})
        mtoon['transparentWithZWrite'] = props.get('_BlendMode') == 3
        shade = properties.get('vectorProperties', {}).get('_ShadeColor')
        if shade is not None:
            mtoon['shadeColorFactor'] = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in shade[:3]]
        # VRM0 ramps from shift to lerp(1, shift, toony); VRM1 uses a
        # symmetric interval around -shift. Migrate the actual interval.
        low = props.get('_ShadeShift', 0.)
        high = 1+(low-1)*props.get('_ShadeToony', .9)
        mtoon['shadingToonyFactor'] = max(0., min(1., 1-(high-low)/2))
        mtoon['shadingShiftFactor'] = -(low+high)/2
        mtoon['giEqualizationFactor'] = 1-props.get('_IndirectLightIntensity', .1)
        texture = properties.get('textureProperties', {}).get('_ShadeTexture')
        if texture is not None and texture >= 0:
            mtoon['shadeMultiplyTexture'] = {'index': texture}
        vectors = properties.get('vectorProperties', {})
        textures = properties.get('textureProperties', {})
        def linear_rgb(key, default):
            return [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in vectors.get(key, default)[:3]]
        mtoon['parametricRimColorFactor'] = linear_rgb('_RimColor', [0, 0, 0, 1])
        mtoon['parametricRimFresnelPowerFactor'] = props.get('_RimFresnelPower', 5.)
        mtoon['parametricRimLiftFactor'] = props.get('_RimLift', 0.)
        # UniVRM migration fixes this to 1 because VRM1 combines rim and MatCap.
        mtoon['rimLightingMixFactor'] = 1.
        for legacy_key, key in [('_SphereAdd', 'matcapTexture'), ('_RimTexture', 'rimMultiplyTexture'),
                                ('_OutlineWidthTexture', 'outlineWidthMultiplyTexture')]:
            if textures.get(legacy_key, -1) >= 0:
                mtoon[key] = {'index': textures[legacy_key]}
        mtoon['matcapFactor'] = [1, 1, 1] if 'matcapTexture' in mtoon else [0, 0, 0]
        outline_mode = int(props.get('_OutlineWidthMode', 0))
        mtoon['outlineWidthMode'] = {0: 'none', 1: 'worldCoordinates', 2: 'screenCoordinates'}[outline_mode]
        mtoon['outlineWidthFactor'] = props.get('_OutlineWidth', 0.) * (.01 if outline_mode == 1 else .005)
        mtoon['outlineColorFactor'] = linear_rgb('_OutlineColor', [0, 0, 0, 1])
        mtoon['outlineLightingMixFactor'] = props.get('_OutlineLightingMix', 1.)
        if textures.get('_BumpMap', -1) >= 0:
            material['normalTexture'] = {'index': textures['_BumpMap'], 'scale': props.get('_BumpScale', 1.)}


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
        names = [shape.name for shape in file.shapes]
    for name in names:
        if name not in materials:
            raise ValueError(f'NIF exporter changed a material binding: {name}; expected shapes: {list(materials)}')
        # The pinned DLL replaces alpha blocks and renumbers other blocks. Reload
        # between shapes so cached IDs never cross an alpha-block replacement.
        with NifFile(str(path)) as file:
            shape = next(s for s in file.shapes if s.name == name)
            material = materials[shape.name]
            props = shape.shader.properties
            props.Shader_Flags_2 = culling_flags(props.Shader_Flags_2, material)
            shape.shader.write_properties()
            logging.debug('Material %s: doubleSided=%s alphaMode=%s', shape.name,
                          material.get('doubleSided', False), material.get('alphaMode', 'OPAQUE'))
            mode = material.get("alphaMode", "OPAQUE")
            if mode == "OPAQUE":
                file.save()
                continue
            new_alpha = not shape.has_alpha_property
            if new_alpha:
                shape.has_alpha_property = True
            alpha = shape.alpha_property.properties
            original = (alpha.flags, alpha.threshold) if not new_alpha else None
            alpha.flags = 4844
            alpha.alpha_blend = mode == "BLEND"
            alpha.alpha_test = mode == "MASK"
            alpha.source_blend_mode = 6
            alpha.dst_blend_mode = 7
            alpha.threshold = round(material.get("alphaCutoff", .5) * 255)
            if mode == 'BLEND' and ordered_alpha(materials):
                alpha.flags |= NO_SORTER
            if original != (alpha.flags, alpha.threshold):
                shape.save_alpha_property()
            file.save()
    with NifFile(str(path)) as file:
        order_alpha_shapes(file, materials)
        file.save()
    # Read the actual exported flags, rather than treating exporter settings as proof.
    with NifFile(str(path)) as file:
        validate_alpha_order(file, materials)
        for shape in file.shapes:
            if bool(shape.shader.properties.Shader_Flags_2 & DOUBLE_SIDED) != bool(materials[shape.name].get('doubleSided', False)):
                raise ValueError('Exported material face culling differs from source: '+shape.name)
