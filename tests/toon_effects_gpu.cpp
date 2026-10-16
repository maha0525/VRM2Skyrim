// Execute production effect helpers with real pixel derivatives and native DDS.
#define main productionFixtureMain
#include "toon_gpu.cpp"
#undef main
int main(int argc,char** argv){try{
    if(argc!=5)throw std::runtime_error("Usage: effects kernel.hlsl source.dds atlas.dds tolerance");
    Fixture f;auto code=readFile(fs::u8path(argv[1]));code.push_back(0);
    auto pixel=compile(code.data(),"ps_5_0");ComPtr<ID3D11PixelShader> ps;
    check(f.device->CreatePixelShader(pixel->GetBufferPointer(),pixel->GetBufferSize(),nullptr,&ps));
    const char* vertex=R"(float4 main(uint i:SV_VertexID):SV_POSITION {
        return float4(i==2?3:-1,i==1?3:-1,0,1);})";
    auto vertexCode=compile(vertex,"vs_5_0");ComPtr<ID3D11VertexShader> vs;
    check(f.device->CreateVertexShader(vertexCode->GetBufferPointer(),vertexCode->GetBufferSize(),nullptr,&vs));
    f.context->VSSetShader(vs.Get(),nullptr,0);f.context->PSSetShader(ps.Get(),nullptr,0);
    f.context->IASetInputLayout(nullptr);f.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    auto source=f.texture(argv[2]),atlas=f.texture(argv[3]);
    f.context->PSSetShaderResources(0,1,&source);f.context->PSSetShaderResources(6,1,&atlas);
    D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.MaxLOD=D3D11_FLOAT32_MAX;
    sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;
    ComPtr<ID3D11SamplerState> sampler;check(f.device->CreateSamplerState(&sd,&sampler));auto s=sampler.Get();
    f.context->PSSetSamplers(0,1,&s);f.context->PSSetSamplers(6,1,&s);
    D3D11_TEXTURE2D_DESC td{};td.Width=td.Height=256;td.MipLevels=td.ArraySize=1;td.Format=DXGI_FORMAT_R32G32B32A32_FLOAT;
    td.SampleDesc.Count=1;td.BindFlags=D3D11_BIND_RENDER_TARGET;
    ComPtr<ID3D11Texture2D> target,staging;ComPtr<ID3D11RenderTargetView> rtv;
    check(f.device->CreateTexture2D(&td,nullptr,&target));check(f.device->CreateRenderTargetView(target.Get(),nullptr,&rtv));
    auto r=rtv.Get();f.context->OMSetRenderTargets(1,&r,nullptr);
    D3D11_VIEWPORT viewport{0,0,256,256,0,1};f.context->RSSetViewports(1,&viewport);
    D3D11_RASTERIZER_DESC raster{};raster.FillMode=D3D11_FILL_SOLID;raster.CullMode=D3D11_CULL_NONE;
    ComPtr<ID3D11RasterizerState> state;check(f.device->CreateRasterizerState(&raster,&state));f.context->RSSetState(state.Get());
    f.context->Draw(3,0);f.context->OMSetRenderTargets(0,nullptr,nullptr);
    td.Usage=D3D11_USAGE_STAGING;td.BindFlags=0;td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    check(f.device->CreateTexture2D(&td,nullptr,&staging));f.context->CopyResource(staging.Get(),target.Get());
    D3D11_MAPPED_SUBRESOURCE mapped{};check(f.context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped));
    float maximum=0;double sum=0;
    for(unsigned y=0;y<256;y++){
        auto row=reinterpret_cast<float*>(static_cast<uint8_t*>(mapped.pData)+y*mapped.RowPitch);
        for(unsigned x=0;x<256;x++)for(unsigned c=0;c<3;c++){
            auto v=row[x*4+c];if(!std::isfinite(v))throw std::runtime_error("Non-finite effect result");
            maximum=std::max(maximum,v);sum+=v;
        }
    }
    f.context->Unmap(staging.Get(),0);
    std::cout<<"Production pixel helper maximum error "<<maximum<<" mean "<<sum/(256*256*3)<<"\n";
    if(maximum>std::stof(argv[4]))throw std::runtime_error("Authored effect reference mismatch");
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
