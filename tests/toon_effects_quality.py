"""Each authored feature must visibly affect the final production CS output."""
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from toon import parameters_for  # noqa: E402
from toon_effects import build_material  # noqa: E402
from test_toon_effects import embedded  # noqa: E402
from toon_quality import sphere  # noqa: E402
from toon_gpu_fixture import build  # noqa: E402
from toon_uv_gpu import rgba_dds  # noqa: E402


def verify(output, shaders):
    output.mkdir(parents=True,exist_ok=True)
    build(output,ROOT/'tests/toon_effects_quality.cpp')
    source = sphere(output).read_bytes()
    nv,ni,kind,flags,threshold,alpha = struct.unpack_from('<5If',source,8)
    offset=32
    paths=[]
    for _ in range(3):
        n=struct.unpack_from('<I',source,offset)[0]
        paths.append(source[offset+4:offset+4+n])
        offset+=4+n
    vertices=np.frombuffer(source,dtype='<f4',count=nv*8,offset=offset).reshape((-1,8)).copy()
    indices=np.frombuffer(source,dtype='<u4',count=ni,offset=offset+nv*32).copy()
    normal=Image.new('RGBA',(7,5),(200,170,235,255))
    matcap=Image.new('RGBA',(7,5),(35,65,120,255))
    doc,binary=embedded([matcap,normal])
    mtoon={'shadeColorFactor':[.3]*3,'shadingToonyFactor':.9,'rimLightingMixFactor':1.}

    def mesh(marker, verts=vertices, tris=indices, draw_flags=flags):
        blob=bytearray(struct.pack('<5If',len(verts),len(tris),kind,draw_flags,threshold,alpha))
        for value in [*paths[:2],str(marker.resolve()).encode('utf8')]:
            blob+=struct.pack('<I',len(value))+value
        return blob+verts.astype('<f4').tobytes()+tris.astype('<u4').tobytes()

    def marker(name, changes=None, outline=False):
        m={'extensions':{'VRMC_materials_mtoon':{**mtoon,**(changes or {})}}}
        if name=='normal':
            m['normalTexture']={'index':1,'scale':1}
        data,_=build_material(output,doc,binary,m,parameters_for(m,authored=True),outline=outline)
        path=output/(name+'-atlas.dds')
        path.write_bytes(data)
        return path
    base=marker('base')
    rgba_dds(output/'layer-red.dds',Image.new('RGBA',(8,4),(180,15,15,255)))
    rgba_dds(output/'layer-blue.dds',Image.new('RGBA',(8,4),(15,15,180,255)))
    (output/'base.scene').write_bytes(struct.pack('<II',0x32535456,1)+mesh(base))
    for name,changes in [('matcap',{'matcapTexture':{'index':0},'matcapFactor':[1]*3}),
        ('rim',{'parametricRimColorFactor':[.4,.15,.1],'parametricRimFresnelPowerFactor':2.}),('normal',{})]:
        path=marker(name,changes)
        (output/(name+'.scene')).write_bytes(struct.pack('<II',0x32535456,1)+mesh(path))
    hull=vertices.copy()
    hull[:,:3]+=hull[:,3:6]*.025
    path=marker('outline',{'outlineColorFactor':[0,0,0],'outlineLightingMixFactor':1},True)
    reversed_tris=indices.reshape((-1,3))[:,[0,2,1]].ravel()
    (output/'outline.scene').write_bytes(struct.pack('<II',0x32535456,2)+mesh(path,hull,reversed_tris,0)+mesh(base))
    subprocess.run([str(output/'toon_gpu.exe'),str(output),str(shaders/'original-cutout.cso'),
                    str(shaders/'toon-cutout.cso')],check=True)


if __name__=='__main__':
    verify(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
