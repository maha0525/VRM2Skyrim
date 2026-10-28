// Authored MToon effects in the existing private glow texture. MIT license.
static bool V2SToonEffects = false;
static uint4 V2SToonRects[4];
static uint2 V2SToonMapWrap[4];
static uint V2SToonMapFlags = 0;
static float3 V2SToonRimColour = 0;
static float V2SToonRimPower = 5;
static float V2SToonRimLift = 0;
static float V2SToonRimMix = 1;
static float3 V2SToonOutlineColour = 0;
static float V2SToonOutlineMix = 1;
static float V2SToonNormalScale = 1;
static bool V2SToonOutline = false;
static float3 V2SToonRimDirectSum = 0;

uint V2SToonByte(uint slot) { return (uint)round(V2SToonData(slot)*255.0); }
uint V2SToonWord(uint slot) { return V2SToonByte(slot) | (V2SToonByte(slot+1) << 8); }
float V2SToonFloat(uint slot) {
    return asfloat(V2SToonByte(slot) | (V2SToonByte(slot+1)<<8) |
                   (V2SToonByte(slot+2)<<16) | (V2SToonByte(slot+3)<<24));
}
bool V2SInitializeEffects() {
    if (V2SToonTextureSize.x < 408) return false;
    V2SToonMapFlags = V2SToonByte(56);
    if ((V2SToonMapFlags & 1) == 0 || V2SToonMapFlags > 15) return false;
    [unroll] for (uint i=0;i<4;i++) {
        uint slot=16+i*10;
        V2SToonRects[i]=uint4(V2SToonWord(slot),V2SToonWord(slot+2),V2SToonWord(slot+4),V2SToonWord(slot+6));
        V2SToonMapWrap[i]=uint2(V2SToonByte(slot+8),V2SToonByte(slot+9));
        uint4 r=V2SToonRects[i];
        if ((V2SToonMapFlags & (1u<<i)) != 0) {
            if (any(r.xy<4) || any(r.zw==0) || r.x+r.z+4>V2SToonTextureSize.x || r.y+r.w+8>V2SToonTextureSize.y) return false;
            uint2 w=V2SToonMapWrap[i];
            if (any((w!=0) && (w!=128) && (w!=255))) return false;
        }
    }
    V2SToonRimColour=float3(V2SToonFloat(57),V2SToonFloat(61),V2SToonFloat(65));
    V2SToonRimPower=V2SToonFloat(69);V2SToonRimLift=V2SToonFloat(73);V2SToonRimMix=V2SToonFloat(77);
    V2SToonOutlineColour=float3(V2SToonFloat(81),V2SToonFloat(85),V2SToonFloat(89));
    V2SToonOutlineMix=V2SToonFloat(93);V2SToonOutline=V2SToonByte(97)!=0;V2SToonNormalScale=V2SToonFloat(98);
    return all(isfinite(V2SToonRimColour)) && all(isfinite(V2SToonOutlineColour)) &&
        isfinite(V2SToonRimPower) && isfinite(V2SToonRimLift) && isfinite(V2SToonRimMix) &&
        isfinite(V2SToonOutlineMix) && isfinite(V2SToonNormalScale);
}

float3 V2SSampleEffect(uint index,float2 uv) {
    uint4 r=V2SToonRects[index];uint2 w=V2SToonMapWrap[index];
    float2 address=float2(w.x==128?saturate(uv.x):w.x==255?1-abs(frac(uv.x*.5)*2-1):frac(uv.x),
                          w.y==128?saturate(uv.y):w.y==255?1-abs(frac(uv.y*.5)*2-1):frac(uv.y));
    float2 scale=float2(r.zw)/float2(V2SToonTextureSize);
    return TexGlowSampler.SampleGrad(SampGlowSampler,address*scale+float2(r.xy)/float2(V2SToonTextureSize),ddx(uv)*scale,ddy(uv)*scale).rgb;
}

float3 V2SApplySourceNormal(float3 normalWS,float3 positionWS,float2 uv) {
    if (!V2SToonEnabled || !V2SToonEffects || (V2SToonMapFlags & 8)==0) return normalWS;
    float3 normalTS=V2SSampleEffect(3,uv)*2-1;normalTS.xy*=V2SToonNormalScale;
    normalTS=normalize(normalTS);
    float3 qx=ddx(positionWS),qy=ddy(positionWS);float2 ux=ddx(uv),uy=ddy(uv);
    float determinant=ux.x*uy.y-ux.y*uy.x;
    if (abs(determinant)<1e-10) return normalWS;
    float3 n=normalize(normalWS),t=(qx*uy.y-qy*ux.y)*sign(determinant),b=(-qx*uy.x+qy*ux.x)*sign(determinant);
    t-=n*dot(n,t);
    if (dot(t,t)<1e-12) return normalWS;
    t=normalize(t);float handed=dot(cross(n,t),b)<0?-1:1;b=normalize(cross(n,t))*handed;
    return normalize(t*normalTS.x+b*normalTS.y+n*normalTS.z);
}

float3 V2SFinishEffects(float3 surface,float3 normalWS,float3 viewWS,float2 uv,float3 ambient,float3 equalizedAmbient) {
    if (!V2SToonEffects) return surface;
    float3 n=normalize(normalWS),v=normalize(viewWS),right=cross(v,float3(0,0,1));
    if (dot(right,right)<1e-8) right=cross(v,float3(0,1,0));
    right=normalize(right);float3 up=normalize(cross(right,v));
    float3 rim=0;
    if ((V2SToonMapFlags & 2)!=0) {
        float2 matcapUv=float2(dot(right,n),dot(up,n))*.495+.5;
        rim=V2SToonDiffuse(V2SSampleEffect(1,matcapUv));
    }
    float fresnel=pow(saturate(1-dot(n,v)+V2SToonRimLift),max(V2SToonRimPower,1e-5));
    // Gamma 2.2 transfer, as Color::LinearToSrgb / SrgbToLinear in 1.0.4.
    rim+=V2SToonDiffuse(TransferFunctions::LinearToGamma22(V2SToonRimColour))*fresnel;
    if ((V2SToonMapFlags & 4)!=0) rim*=TransferFunctions::Gamma22ToLinear(V2SSampleEffect(2,uv));
    float3 available=max(V2SToonUnshadedSum,0)+max(equalizedAmbient,0);
    float exposure=rcp(max(1,max(available.r,max(available.g,available.b))));
    rim*=lerp(1.0.xxx,(V2SToonRimDirectSum+max(ambient,0))*exposure,V2SToonRimMix);
    surface+=rim;
    if (V2SToonOutline) surface=V2SToonDiffuse(TransferFunctions::LinearToGamma22(V2SToonOutlineColour))*lerp(1.0.xxx,surface,V2SToonOutlineMix);
    return surface;
}
