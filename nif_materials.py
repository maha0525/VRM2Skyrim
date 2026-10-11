"""Preserve glTF alpha mode in the exported Skyrim lighting material."""
from custom_skeleton import NifFile


def apply_alpha(path, materials):
    with NifFile(str(path)) as file:
        for shape in file.shapes:
            material = materials[shape.name]
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
