"""Validate DDS storage and Direct3D block-compression dimension constraints."""
from pathlib import Path
import struct

DXGI_BLOCK_BYTES = {key: 8 for key in (70, 71, 72, 79, 80, 81)}
DXGI_BLOCK_BYTES.update({key: 16 for key in (73, 74, 75, 76, 77, 78, 82, 83, 84,
                                           94, 95, 96, 97, 98, 99)})
LEGACY_BLOCK_BYTES = {b'DXT1': 8, b'ATI1': 8, b'BC4U': 8, b'BC4S': 8,
                      b'DXT2': 16, b'DXT3': 16, b'DXT4': 16, b'DXT5': 16,
                      b'ATI2': 16, b'BC5U': 16, b'BC5S': 16}
DXGI_NAMES = {28: 'R8G8B8A8_UNORM', 29: 'R8G8B8A8_UNORM_SRGB',
              98: 'BC7_UNORM', 99: 'BC7_UNORM_SRGB'}


def texture_format(size):
    width, height = size
    if any(type(n) is not int or not 0 < n <= 16384 for n in size):
        raise ValueError(f'Texture dimensions exceed Direct3D 11 limits: {size}')
    return 'BC7_UNORM' if width % 4 == 0 and height % 4 == 0 else 'R8G8B8A8_UNORM'


def validate_dds(path, expected_size=None, expected_format=None):
    path = Path(path)
    with path.open('rb') as stream:
        header = stream.read(148)
    if len(header) < 128 or header[:4] != b'DDS ':
        raise ValueError(f'Invalid DDS header: {path}')
    if struct.unpack_from('<I', header, 4)[0] != 124 or struct.unpack_from('<I', header, 76)[0] != 32:
        raise ValueError(f'Invalid DDS header sizes: {path}')
    height, width = struct.unpack_from('<II', header, 12)
    if not 0 < width <= 16384 or not 0 < height <= 16384:
        raise ValueError(f'Invalid DDS dimensions {width}x{height}: {path}')
    fourcc = header[84:88]
    depth = max(1, struct.unpack_from('<I', header, 24)[0])
    mip_levels = max(1, struct.unpack_from('<I', header, 28)[0])
    caps2 = struct.unpack_from('<I', header, 112)[0]
    dxgi, resource_dimension, array_size = None, 3, 1
    faces = 6 if caps2 & 0x200 else 1
    header_bytes = 128
    if fourcc == b'DX10':
        if len(header) < 148:
            raise ValueError(f'Truncated DDS DX10 header: {path}')
        dxgi, resource_dimension, misc, array_size, _ = struct.unpack_from('<5I', header, 128)
        if resource_dimension not in (2, 3, 4) or array_size < 1:
            raise ValueError(f'Invalid DDS resource dimensions/array: {path}')
        faces = 6 if misc & 4 else 1
        header_bytes = 148
    if mip_levels > max(width, height, depth).bit_length():
        raise ValueError(f'Invalid DDS mip count {mip_levels}: {path}')
    block_bytes = DXGI_BLOCK_BYTES.get(dxgi) if dxgi is not None else LEGACY_BLOCK_BYTES.get(fourcc)
    format_name = DXGI_NAMES.get(dxgi, f'DXGI_{dxgi}') if dxgi is not None else fourcc.decode('ascii', errors='replace').strip('\0') or 'uncompressed'
    if block_bytes and (width % 4 or height % 4):
        raise ValueError(f'Direct3D rejects {width}x{height} block-compressed DDS ({format_name}); dimensions must be multiples of 4: {path}')
    if expected_size is not None and (width, height) != tuple(expected_size):
        raise ValueError(f'DDS dimensions changed from {expected_size} to {width}x{height}: {path}')
    if expected_format is not None and (format_name != expected_format or resource_dimension != 3 or array_size != 1 or faces != 1):
        raise ValueError(f'DDS output format differs from {expected_format}: {format_name}: {path}')
    # Verify mip storage when this is a recognized compressed or RGBA format.
    # Other imported game formats still receive the header/dimension checks.
    bytes_per_pixel = 4 if dxgi in (28, 29, 87, 88, 89, 90, 91, 92, 93) else None
    if dxgi is None and not block_bytes and struct.unpack_from('<I', header, 88)[0]:
        bytes_per_pixel = (struct.unpack_from('<I', header, 88)[0] + 7) // 8
    required = None
    if block_bytes or bytes_per_pixel:
        required = header_bytes
        w, h = width, height
        volume = depth if resource_dimension == 4 or caps2 & 0x200000 else 1
        for _ in range(mip_levels):
            plane = ((w + 3) // 4) * ((h + 3) // 4) * block_bytes if block_bytes else w * h * bytes_per_pixel
            required += plane * volume * faces * array_size
            w, h, volume = max(1, w // 2), max(1, h // 2), max(1, volume // 2)
        if path.stat().st_size < required:
            raise ValueError(f'Truncated DDS mip payload: {path}')
    return {'width': width, 'height': height, 'format': format_name, 'dxgi': dxgi,
            'compressed': bool(block_bytes), 'mip_levels': mip_levels,
            'minimum_bytes': required}
