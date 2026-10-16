// Compare production UV code against independent native glTF sampler modes.
#define main productionFixtureMain
#include "toon_gpu.cpp"
#undef main
int main(int argc,char** argv){try{
    if(argc!=7)throw std::runtime_error("Usage: uv kernel source.dds packed.dds wrapU wrapV tolerance");
    Fixture f;auto code=readFile(fs::u8path(argv[1]));code.push_back(0);
    auto blob=compile(code.data(),"cs_5_0");ComPtr<ID3D11ComputeShader> shader;
    check(f.device->CreateComputeShader(blob->GetBufferPointer(),blob->GetBufferSize(),nullptr,&shader));
    f.context->CSSetShader(shader.Get(),nullptr,0);
    ID3D11ShaderResourceView* views[]={f.texture(argv[2]),f.texture(argv[3])};
    f.context->CSSetShaderResources(0,2,views);
    auto address=[](int mode){return mode==33071?D3D11_TEXTURE_ADDRESS_CLAMP:mode==33648?D3D11_TEXTURE_ADDRESS_MIRROR:D3D11_TEXTURE_ADDRESS_WRAP;};
    D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.MaxLOD=D3D11_FLOAT32_MAX;
    sd.AddressU=address(std::stoi(argv[4]));sd.AddressV=address(std::stoi(argv[5]));sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;
    ComPtr<ID3D11SamplerState> sourceSampler,packedSampler;
    check(f.device->CreateSamplerState(&sd,&sourceSampler));
    sd.AddressU=sd.AddressV=D3D11_TEXTURE_ADDRESS_WRAP;check(f.device->CreateSamplerState(&sd,&packedSampler));
    ID3D11SamplerState* samplers[]={sourceSampler.Get(),packedSampler.Get()};f.context->CSSetSamplers(0,2,samplers);
    D3D11_TEXTURE2D_DESC td{};td.Width=td.Height=257;td.MipLevels=td.ArraySize=1;td.Format=DXGI_FORMAT_R32G32B32A32_FLOAT;
    td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_DEFAULT;td.BindFlags=D3D11_BIND_UNORDERED_ACCESS;
    ComPtr<ID3D11Texture2D> target,staging;ComPtr<ID3D11UnorderedAccessView> uav;
    check(f.device->CreateTexture2D(&td,nullptr,&target));check(f.device->CreateUnorderedAccessView(target.Get(),nullptr,&uav));
    auto ptr=uav.Get();f.context->CSSetUnorderedAccessViews(0,1,&ptr,nullptr);f.context->Dispatch(33,33,1);
    ptr=nullptr;f.context->CSSetUnorderedAccessViews(0,1,&ptr,nullptr);
    td.Usage=D3D11_USAGE_STAGING;td.BindFlags=0;td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    check(f.device->CreateTexture2D(&td,nullptr,&staging));f.context->CopyResource(staging.Get(),target.Get());
    D3D11_MAPPED_SUBRESOURCE mapped{};check(f.context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped));
    float maximum=0;double total=0;
    for(unsigned y=0;y<257;y++){
        auto row=reinterpret_cast<float*>(static_cast<uint8_t*>(mapped.pData)+y*mapped.RowPitch);
        for(unsigned x=0;x<257;x++)for(unsigned c=0;c<3;c++){
            float v=row[x*4+c];if(!std::isfinite(v))throw std::runtime_error("Non-finite UV result");
            maximum=std::max(maximum,v);total+=v;
        }
    }
    f.context->Unmap(staging.Get(),0);
    std::cout<<"Native sampler RGB max error "<<maximum<<" mean "<<total/(257*257*3)<<"\n";
    if(maximum>std::stof(argv[6]))throw std::runtime_error("Source texture domain/addressing changed");
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}}
