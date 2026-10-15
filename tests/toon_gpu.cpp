// Offscreen Direct3D 11 fixture. Uses the actual original/patched CS pixel shaders.
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <d3d11shader.h>
#include <DirectXMath.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
using Microsoft::WRL::ComPtr;
using namespace DirectX;
namespace fs = std::filesystem;
void check(HRESULT result) { if(FAILED(result)) throw std::runtime_error("D3D failure "+std::to_string(result)); }
std::vector<char> readFile(const fs::path& path) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    if(!file)throw std::runtime_error("Missing file "+path.string());
    std::vector<char> data(static_cast<size_t>(file.tellg()));file.seekg(0);file.read(data.data(),data.size());return data;
}
template<class T> T read(std::istream& file){T value;file.read(reinterpret_cast<char*>(&value),sizeof(value));if(!file)throw std::runtime_error("Truncated scene");return value;}
std::string readString(std::istream& file){std::string value(read<uint32_t>(file),'\0');file.read(value.data(),value.size());return value;}
struct Vertex{float p[3],n[3],uv[2];};
struct Mesh{std::vector<Vertex> vertices;std::vector<uint32_t> indices;uint32_t type,flags,threshold;float alpha;std::array<std::string,3> textures;};
struct Scene{std::vector<Mesh> meshes;XMFLOAT3 lo{1e9f,1e9f,1e9f},hi{-1e9f,-1e9f,-1e9f};};
Scene loadScene(const fs::path& path){
    std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Scene missing");
    if(read<uint32_t>(file)!=0x32535456)throw std::runtime_error("Scene format");
    Scene scene;auto count=read<uint32_t>(file);
    for(uint32_t i=0;i<count;i++){
        Mesh mesh;auto nv=read<uint32_t>(file),ni=read<uint32_t>(file);
        mesh.type=read<uint32_t>(file);mesh.flags=read<uint32_t>(file);mesh.threshold=read<uint32_t>(file);mesh.alpha=read<float>(file);
        for(auto& texture:mesh.textures)texture=readString(file);
        mesh.vertices.resize(nv);mesh.indices.resize(ni);
        file.read(reinterpret_cast<char*>(mesh.vertices.data()),nv*sizeof(Vertex));
        file.read(reinterpret_cast<char*>(mesh.indices.data()),ni*4);
        for(auto v:mesh.vertices){
            scene.lo.x=std::min(scene.lo.x,v.p[0]);scene.lo.y=std::min(scene.lo.y,v.p[1]);scene.lo.z=std::min(scene.lo.z,v.p[2]);
            scene.hi.x=std::max(scene.hi.x,v.p[0]);scene.hi.y=std::max(scene.hi.y,v.p[1]);scene.hi.z=std::max(scene.hi.z,v.p[2]);
        }
        scene.meshes.push_back(std::move(mesh));
    }return scene;
}
ComPtr<ID3DBlob> compile(const char* text,const char* profile){
    ComPtr<ID3DBlob> result,error;auto hr=D3DCompile(text,strlen(text),"fixture",nullptr,nullptr,"main",profile,D3DCOMPILE_ENABLE_STRICTNESS,0,&result,&error);
    if(FAILED(hr)){if(error)std::cerr<<static_cast<char*>(error->GetBufferPointer());check(hr);}return result;
}
struct Fixture{
    static constexpr UINT width=720,height=900;
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Texture2D> target,depth;ComPtr<ID3D11RenderTargetView> rtv;ComPtr<ID3D11DepthStencilView> dsv;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11InputLayout> layout;
    ComPtr<ID3D11Buffer> cameraBuffer;
    std::map<std::string,ComPtr<ID3D11ShaderResourceView>> textures;
    Fixture(){
        D3D_FEATURE_LEVEL level;check(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,&level,&context));
        std::cout<<"D3D hardware feature level "<<std::hex<<level<<std::dec<<"\n";
        D3D11_TEXTURE2D_DESC td{};td.Width=width;td.Height=height;td.MipLevels=td.ArraySize=1;td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;td.SampleDesc.Count=1;td.BindFlags=D3D11_BIND_RENDER_TARGET;
        check(device->CreateTexture2D(&td,nullptr,&target));check(device->CreateRenderTargetView(target.Get(),nullptr,&rtv));
        td.Format=DXGI_FORMAT_D24_UNORM_S8_UINT;td.BindFlags=D3D11_BIND_DEPTH_STENCIL;
        check(device->CreateTexture2D(&td,nullptr,&depth));check(device->CreateDepthStencilView(depth.Get(),nullptr,&dsv));
        const char* vertex=R"(
cbuffer Camera:register(b0){row_major float4x4 VP;float4 Eye;};
struct Input{float3 p:POSITION;float3 n:NORMAL;float2 uv:TEXCOORD;};
struct Output{float4 p:SV_POSITION;float2 uv:TEXCOORD0;float3 a:TEXCOORD1;float3 b:TEXCOORD2;float3 c:TEXCOORD3;float4 world:POSITION1;float4 previous:POSITION2;float4 color:COLOR0;float4 fog:COLOR1;float3 model:TEXCOORD12;};
Output main(Input v){Output o=(Output)0;o.p=mul(float4(v.p,1),VP);o.uv=v.uv;float3 n=normalize(v.n);float3 t=normalize(cross(abs(n.z)>.95?float3(0,1,0):float3(0,0,1),n));float3 b=cross(n,t);o.a=float3(t.x,b.x,n.x);o.b=float3(t.y,b.y,n.y);o.c=float3(t.z,b.z,n.z);o.world=float4(v.p-Eye.xyz,1);o.previous=o.world;o.model=v.p;o.color=1;return o;})";
        auto blob=compile(vertex,"vs_5_0");check(device->CreateVertexShader(blob->GetBufferPointer(),blob->GetBufferSize(),nullptr,&vs));
        D3D11_INPUT_ELEMENT_DESC elements[]={{"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},{"NORMAL",0,DXGI_FORMAT_R32G32B32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},{"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0}};
        check(device->CreateInputLayout(elements,3,blob->GetBufferPointer(),blob->GetBufferSize(),&layout));
        D3D11_RASTERIZER_DESC rs{};rs.FillMode=D3D11_FILL_SOLID;rs.CullMode=D3D11_CULL_NONE;rs.DepthClipEnable=TRUE;
        ComPtr<ID3D11RasterizerState> raster;check(device->CreateRasterizerState(&rs,&raster));context->RSSetState(raster.Get());
        D3D11_VIEWPORT viewport{0,0,float(width),float(height),0,1};context->RSSetViewports(1,&viewport);
        D3D11_SAMPLER_DESC ss{};ss.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;ss.AddressU=ss.AddressV=ss.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;ss.MaxLOD=D3D11_FLOAT32_MAX;
        ComPtr<ID3D11SamplerState> sampler;check(device->CreateSamplerState(&ss,&sampler));
        for(UINT i=0;i<16;i++){auto ptr=sampler.Get();context->PSSetSamplers(i,1,&ptr);}
    }
    ComPtr<ID3D11Buffer> buffer(const void* data,UINT size,UINT bind){
        D3D11_BUFFER_DESC desc{};desc.ByteWidth=size;desc.BindFlags=bind;desc.Usage=D3D11_USAGE_DEFAULT;
        D3D11_SUBRESOURCE_DATA init{};init.pSysMem=data;ComPtr<ID3D11Buffer> result;check(device->CreateBuffer(&desc,&init,&result));return result;
    }
    ID3D11ShaderResourceView* texture(const std::string& path){
        auto found=textures.find(path);if(found!=textures.end())return found->second.Get();
        if(path.empty())return nullptr;
        auto bytes=readFile(fs::u8path(path));
        if(bytes.size()<148||std::string(bytes.data(),4)!="DDS "||std::string(bytes.data()+84,4)!="DX10")throw std::runtime_error("DX10 DDS required");
        auto u=[&](int offset){uint32_t v;memcpy(&v,bytes.data()+offset,4);return v;};
        D3D11_TEXTURE2D_DESC desc{};desc.Width=u(16);desc.Height=u(12);desc.MipLevels=std::max(1u,u(28));desc.ArraySize=1;desc.Format=DXGI_FORMAT(u(128));desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        std::vector<D3D11_SUBRESOURCE_DATA> sub(desc.MipLevels);UINT w=desc.Width,h=desc.Height;size_t offset=148;
        for(auto& s:sub){s.pSysMem=bytes.data()+offset;bool bc=desc.Format==DXGI_FORMAT_BC7_UNORM||desc.Format==DXGI_FORMAT_BC7_UNORM_SRGB;s.SysMemPitch=bc?((w+3)/4)*16:w*4;s.SysMemSlicePitch=s.SysMemPitch*(bc?((h+3)/4):h);offset+=s.SysMemSlicePitch;w=std::max(1u,w/2);h=std::max(1u,h/2);}
        if(offset>bytes.size())throw std::runtime_error("Truncated DDS payload");
        ComPtr<ID3D11Texture2D> tex;check(device->CreateTexture2D(&desc,sub.data(),&tex));ComPtr<ID3D11ShaderResourceView> srv;check(device->CreateShaderResourceView(tex.Get(),nullptr,&srv));auto result=srv.Get();textures[path]=std::move(srv);return result;
    }
    std::vector<uint8_t> render(const Scene& scene,const fs::path& shaderPath,bool night=false){
        auto shaderBytes=readFile(shaderPath);ComPtr<ID3D11PixelShader> ps;check(device->CreatePixelShader(shaderBytes.data(),shaderBytes.size(),nullptr,&ps));
        ComPtr<ID3D11ShaderReflection> reflection;check(D3DReflect(shaderBytes.data(),shaderBytes.size(),IID_ID3D11ShaderReflection,&reflection));
        D3D11_SHADER_DESC shaderDesc{};check(reflection->GetDesc(&shaderDesc));
        struct Constants{UINT slot;std::vector<uint8_t> bytes;ComPtr<ID3D11Buffer> gpu;ID3D11ShaderReflectionConstantBuffer* reflected;};
        std::vector<Constants> constants;
        for(UINT i=0;i<shaderDesc.ConstantBuffers;i++){
            auto cb=reflection->GetConstantBufferByIndex(i);D3D11_SHADER_BUFFER_DESC desc{};check(cb->GetDesc(&desc));D3D11_SHADER_INPUT_BIND_DESC binding{};check(reflection->GetResourceBindingDescByName(desc.Name,&binding));
            Constants value{binding.BindPoint,std::vector<uint8_t>((desc.Size+15)&~15u),{},cb};constants.push_back(std::move(value));
        }
        auto set=[&](const char* name,const void* ptr,size_t size){for(auto& c:constants){auto v=c.reflected->GetVariableByName(name);D3D11_SHADER_VARIABLE_DESC desc{};if(SUCCEEDED(v->GetDesc(&desc))){if(size>desc.Size)throw std::runtime_error(std::string("Constant size ")+name);memcpy(c.bytes.data()+desc.StartOffset,ptr,size);return true;}}return false;};
        auto f4=[&](const char* name,std::array<float,4> v){set(name,v.data(),sizeof(v));};
        auto f3=[&](const char* name,std::array<float,3> v){set(name,v.data(),sizeof(v));};
        XMFLOAT4X4 identity;XMStoreFloat4x4(&identity,XMMatrixIdentity());
        for(const char* name:{"FrameBuffer::CameraView","FrameBuffer::CameraViewProjUnjittered","FrameBuffer::CameraPreviousViewProjUnjittered"})set(name,&identity,sizeof(identity));
        f4("FrameBuffer::DynamicResolutionParams1",{1,1,1,1});f4("FrameBuffer::DynamicResolutionParams2",{1,1,1,1});f4("FrameBuffer::FrameParams",{1,0,0,0});
        f4("ColourOutputClamp",{100,100,100,100});f4("SharedData::BufferDim",{float(width),float(height),1.f/width,1.f/height});
        f3("DirLightDirection",{-.4056f,.7605f,.5070f});f3("DirLightColor",night?std::array<float,3>{0,0,0}:std::array<float,3>{1.f,.95f,.9f});
        float ambient[12]={0,0,0,.5f,0,0,0,.55f,0,0,0,.62f};if(night)std::fill(std::begin(ambient),std::end(ambient),0.f);set("DirectionalAmbient",ambient,sizeof(ambient));
        uint32_t interior=1;set("SharedData::InInterior",&interior,4);
        const float scale=scene.hi.z-scene.lo.z;XMVECTOR center=XMVectorSet((scene.lo.x+scene.hi.x)*.5f,(scene.lo.y+scene.hi.y)*.5f,(scene.lo.z+scene.hi.z)*.5f,1);
        XMVECTOR eye=XMVectorAdd(center,XMVectorSet(scale*1.8f,scale*4,scale*.55f,0));
        struct Camera{XMFLOAT4X4 vp;XMFLOAT4 eye;}camera;
        XMStoreFloat4(&camera.eye,eye);XMStoreFloat4x4(&camera.vp,XMMatrixMultiply(XMMatrixLookAtRH(eye,center,XMVectorSet(0,0,1,0)),XMMatrixOrthographicRH(scale*1.3f*width/height,scale*1.3f,.1f,scale*10)));
        cameraBuffer=buffer(&camera,sizeof(camera),D3D11_BIND_CONSTANT_BUFFER);auto cameraPtr=cameraBuffer.Get();context->VSSetConstantBuffers(0,1,&cameraPtr);
        context->VSSetShader(vs.Get(),nullptr,0);context->PSSetShader(ps.Get(),nullptr,0);context->IASetInputLayout(layout.Get());context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        auto targetPtr=rtv.Get();context->OMSetRenderTargets(1,&targetPtr,dsv.Get());float bg[]={.12f,.14f,.18f,1};context->ClearRenderTargetView(rtv.Get(),bg);context->ClearDepthStencilView(dsv.Get(),D3D11_CLEAR_DEPTH,1,0);
        for(auto& mesh:scene.meshes){
            D3D11_RASTERIZER_DESC rasterDesc{};rasterDesc.FillMode=D3D11_FILL_SOLID;rasterDesc.CullMode=(mesh.flags&(1u<<20))?D3D11_CULL_NONE:D3D11_CULL_BACK;rasterDesc.DepthClipEnable=TRUE;
            ComPtr<ID3D11RasterizerState> rasterState;check(device->CreateRasterizerState(&rasterDesc,&rasterState));context->RSSetState(rasterState.Get());
            f4("MaterialData",{1,1,mesh.alpha,0});f4("SpecularColor",{0,0,0,1});f4("TintColor",{1,1,1,1});f4("CharacterLightParams",{0,0,0,0});
            uint32_t descriptor=mesh.type<<24;set("Permutation::PixelShaderDescriptor",&descriptor,4);
            float threshold=(mesh.flags&512)?float(mesh.threshold)/255.f:0.f;set("AlphaTestRefRS",&threshold,4);
            for(auto& c:constants){c.gpu=buffer(c.bytes.data(),UINT(c.bytes.size()),D3D11_BIND_CONSTANT_BUFFER);auto ptr=c.gpu.Get();context->PSSetConstantBuffers(c.slot,1,&ptr);}
            auto diffuse=texture(mesh.textures[0]),normal=texture(mesh.textures[1]),glow=texture(mesh.textures[2]);context->PSSetShaderResources(0,1,&diffuse);context->PSSetShaderResources(1,1,&normal);context->PSSetShaderResources(6,1,&glow);
            auto vb=buffer(mesh.vertices.data(),UINT(mesh.vertices.size()*sizeof(Vertex)),D3D11_BIND_VERTEX_BUFFER);auto ib=buffer(mesh.indices.data(),UINT(mesh.indices.size()*4),D3D11_BIND_INDEX_BUFFER);auto vp=vb.Get();UINT stride=sizeof(Vertex),offset=0;context->IASetVertexBuffers(0,1,&vp,&stride,&offset);context->IASetIndexBuffer(ib.Get(),DXGI_FORMAT_R32_UINT,0);
            D3D11_BLEND_DESC blend{};auto& b=blend.RenderTarget[0];b.RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;b.BlendEnable=(mesh.flags&1)!=0;b.SrcBlend=D3D11_BLEND_SRC_ALPHA;b.DestBlend=D3D11_BLEND_INV_SRC_ALPHA;b.BlendOp=b.BlendOpAlpha=D3D11_BLEND_OP_ADD;b.SrcBlendAlpha=D3D11_BLEND_ONE;b.DestBlendAlpha=D3D11_BLEND_INV_SRC_ALPHA;ComPtr<ID3D11BlendState> bs;check(device->CreateBlendState(&blend,&bs));context->OMSetBlendState(bs.Get(),nullptr,0xffffffff);
            D3D11_DEPTH_STENCIL_DESC ds{};ds.DepthEnable=TRUE;ds.DepthWriteMask=b.BlendEnable?D3D11_DEPTH_WRITE_MASK_ZERO:D3D11_DEPTH_WRITE_MASK_ALL;ds.DepthFunc=D3D11_COMPARISON_LESS_EQUAL;ComPtr<ID3D11DepthStencilState> state;check(device->CreateDepthStencilState(&ds,&state));context->OMSetDepthStencilState(state.Get(),0);
            context->DrawIndexed(UINT(mesh.indices.size()),0,0);
        }
        context->OMSetRenderTargets(0,nullptr,nullptr);D3D11_TEXTURE2D_DESC desc{};target->GetDesc(&desc);desc.BindFlags=0;desc.Usage=D3D11_USAGE_STAGING;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;ComPtr<ID3D11Texture2D> staging;check(device->CreateTexture2D(&desc,nullptr,&staging));context->CopyResource(staging.Get(),target.Get());D3D11_MAPPED_SUBRESOURCE mapped{};check(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped));std::vector<uint8_t> result(width*height*4);for(UINT y=0;y<height;y++)memcpy(result.data()+y*width*4,static_cast<uint8_t*>(mapped.pData)+y*mapped.RowPitch,width*4);context->Unmap(staging.Get(),0);return result;
    }
    static void save(const fs::path& path,const std::vector<uint8_t>& rgba){std::ofstream file(path,std::ios::binary);file<<"P6\n"<<width<<" "<<height<<"\n255\n";for(size_t i=0;i<rgba.size();i+=4)file.write(reinterpret_cast<const char*>(rgba.data()+i),3);}
};
int main(int argc,char** argv){try{
    if(argc!=6)throw std::runtime_error("Usage: toon_gpu base.scene marked.scene original.cso patched.cso output-dir");
    fs::path output=fs::u8path(argv[5]);fs::create_directories(output);auto base=loadScene(fs::u8path(argv[1])),marked=loadScene(fs::u8path(argv[2]));Fixture f;
    auto original=f.render(base,fs::u8path(argv[3]));auto untouched=f.render(base,fs::u8path(argv[4]));auto fallback=f.render(marked,fs::u8path(argv[3]));auto toon=f.render(marked,fs::u8path(argv[4]));auto night=f.render(marked,fs::u8path(argv[4]),true);auto baselineNight=f.render(base,fs::u8path(argv[3]),true);
    Fixture::save(output/"original.ppm",original);Fixture::save(output/"unmarked.ppm",untouched);Fixture::save(output/"fallback.ppm",fallback);Fixture::save(output/"toon.ppm",toon);Fixture::save(output/"night.ppm",night);
    int unchanged=0,fallbackError=0,nightError=0;size_t changed=0,visible=0;for(size_t i=0;i<original.size();i+=4){for(int c=0;c<3;c++){unchanged=std::max(unchanged,abs(int(original[i+c])-untouched[i+c]));fallbackError=std::max(fallbackError,abs(int(original[i+c])-fallback[i+c]));nightError=std::max(nightError,abs(int(night[i+c])-baselineNight[i+c]));}if(original[i]!=31||original[i+1]!=36||original[i+2]!=46)visible++;if(abs(int(original[i])-toon[i])+abs(int(original[i+1])-toon[i+1])+abs(int(original[i+2])-toon[i+2])>3)changed++;}
    std::cout<<"Unmarked maximum byte difference "<<unchanged<<"; fallback "<<fallbackError<<"; night "<<nightError<<"; toon changed pixels "<<changed<<" / "<<visible<<"\n";
    if(unchanged>1||fallbackError>1||nightError>1||changed<1000)throw std::runtime_error("Shading isolation assertion failed");
    std::ofstream report(output/"gpu-verification.json");report<<"{\"actual_cs_pixel_shaders\":true,\"hardware_d3d11\":true,\"unmarked_max_byte_error\":"<<unchanged<<",\"fallback_max_byte_error\":"<<fallbackError<<",\"night_max_byte_error\":"<<nightError<<",\"toon_changed_pixels\":"<<changed<<"}";
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}}
