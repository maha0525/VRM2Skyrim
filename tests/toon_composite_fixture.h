// Included in Fixture. Run the real CS deferred compositor on the preceding
// Lighting draw's native-format GBuffer. Only AO/IL inputs are controlled.
    std::vector<uint8_t> composite(const fs::path& shaderPath,float ao,float il,bool linear=false){
        auto bytes=readFile(shaderPath);ComPtr<ID3D11ComputeShader> shader;
        check(device->CreateComputeShader(bytes.data(),bytes.size(),nullptr,&shader));
        ComPtr<ID3D11ShaderReflection> reflection;check(D3DReflect(bytes.data(),bytes.size(),IID_ID3D11ShaderReflection,&reflection));
        D3D11_SHADER_DESC shaderDesc{};check(reflection->GetDesc(&shaderDesc));
        struct Constants{UINT slot;std::vector<uint8_t> bytes;ComPtr<ID3D11Buffer> gpu;ID3D11ShaderReflectionConstantBuffer* reflected;};
        std::vector<Constants> constants;
        for(UINT i=0;i<shaderDesc.ConstantBuffers;i++){
            auto cb=reflection->GetConstantBufferByIndex(i);D3D11_SHADER_BUFFER_DESC desc{};check(cb->GetDesc(&desc));
            D3D11_SHADER_INPUT_BIND_DESC binding{};check(reflection->GetResourceBindingDescByName(desc.Name,&binding));
            constants.push_back({binding.BindPoint,std::vector<uint8_t>((desc.Size+15)&~15u),{},cb});
        }
        auto set=[&](const std::string& name,const void* ptr,size_t size){
            auto dot=name.find('.');auto root=name.substr(0,dot);
            for(auto& c:constants){auto v=c.reflected->GetVariableByName(root.c_str());D3D11_SHADER_VARIABLE_DESC desc{};
                if(FAILED(v->GetDesc(&desc)))continue;
                UINT offset=desc.StartOffset;
                if(dot!=std::string::npos){D3D11_SHADER_TYPE_DESC member{};
                    check(v->GetType()->GetMemberTypeByName(name.substr(dot+1).c_str())->GetDesc(&member));offset+=member.Offset;
                }else if(size>desc.Size)throw std::runtime_error("Composite constant size "+name);
                if(offset+size>c.bytes.size())throw std::runtime_error("Composite constant overflow");
                memcpy(c.bytes.data()+offset,ptr,size);return true;
            }return false;
        };
        std::array<float,4> dim={float(width),float(height),1.f/width,1.f/height};set("SharedData::BufferDim",dim.data(),sizeof(dim));
        std::array<float,4> one={1,1,1,1};set("FrameBuffer::DynamicResolutionParams2",one.data(),sizeof(one));
        XMFLOAT4X4 identity;XMStoreFloat4x4(&identity,XMMatrixIdentity());
        for(auto name:{"FrameBuffer::CameraViewInverse","FrameBuffer::CameraViewProjInverse","FrameBuffer::CameraViewProjUnjittered","FrameBuffer::CameraPreviousViewProjUnjittered"})set(name,&identity,sizeof(identity));
        uint32_t enableLinear=linear;set("SharedData::linearLightingSettings.enableLinearLighting",&enableLinear,4);
        for(auto name:{"colorGamma","lightGamma","ambientGamma","emitColorGamma","glowmapGamma","fogGamma","fogAlphaGamma"}){float value=1.8f;set(std::string("SharedData::linearLightingSettings.")+name,&value,4);}
        for(auto& c:constants){c.gpu=buffer(c.bytes.data(),UINT(c.bytes.size()),D3D11_BIND_CONSTANT_BUFFER);auto p=c.gpu.Get();context->CSSetConstantBuffers(c.slot,1,&p);}
        std::vector<ComPtr<ID3D11Texture2D>> resources;
        std::vector<ComPtr<ID3D11ShaderResourceView>> views;
        std::array<ID3D11ShaderResourceView*,14> bindings{};
        for(auto pair:{std::pair<int,int>{0,4},{1,3},{2,2},{3,6},{5,5},{9,7}}){
            ComPtr<ID3D11ShaderResourceView> view;check(device->CreateShaderResourceView(lastGBuffer[pair.second].Get(),nullptr,&view));
            bindings[pair.first]=view.Get();views.push_back(view);
        }
        auto input=[&](int slot,DXGI_FORMAT format,const std::vector<float>& data,UINT channels){
            D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.MipLevels=desc.ArraySize=1;
            desc.Format=format;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;desc.Usage=D3D11_USAGE_IMMUTABLE;
            D3D11_SUBRESOURCE_DATA init{data.data(),width*channels*4,0};ComPtr<ID3D11Texture2D> texture;check(device->CreateTexture2D(&desc,&init,&texture));
            ComPtr<ID3D11ShaderResourceView> view;check(device->CreateShaderResourceView(texture.Get(),nullptr,&view));
            bindings[slot]=view.Get();resources.push_back(texture);views.push_back(view);
        };
        input(4,DXGI_FORMAT_R32_FLOAT,std::vector<float>(width*height,.5f),1);
        std::vector<float> occlusion(width*height*4),irradiance(width*height*4),chroma(width*height*4),zero(width*height*4);
        float energy=std::max(il,1e-6f);
        for(UINT y=0;y<height;y++)for(UINT x=0;x<width;x++){
            size_t i=(y*width+x)*4;occlusion[i]=ao*(.2f+.8f*x/(width-1));
            irradiance[i]=energy;irradiance[i+1]=energy*.01f;irradiance[i+2]=energy*.02f;irradiance[i+3]=energy*.03f;
        }
        input(10,DXGI_FORMAT_R32G32B32A32_FLOAT,occlusion,4);input(11,DXGI_FORMAT_R32G32B32A32_FLOAT,irradiance,4);
        input(12,DXGI_FORMAT_R32G32B32A32_FLOAT,chroma,4);input(13,DXGI_FORMAT_R32G32B32A32_FLOAT,zero,4);
        std::array<ComPtr<ID3D11Texture2D>,2> aux;std::array<ComPtr<ID3D11UnorderedAccessView>,3> outputs;
        check(device->CreateUnorderedAccessView(lastGBuffer[0].Get(),nullptr,&outputs[0]));
        for(int i=0;i<2;i++){
            D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.MipLevels=desc.ArraySize=1;
            desc.Format=i?DXGI_FORMAT_R32G32_FLOAT:DXGI_FORMAT_R32G32B32A32_FLOAT;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_UNORDERED_ACCESS;
            check(device->CreateTexture2D(&desc,nullptr,&aux[i]));check(device->CreateUnorderedAccessView(aux[i].Get(),nullptr,&outputs[i+1]));
        }
        std::array<ID3D11UnorderedAccessView*,3> uavs={outputs[0].Get(),outputs[1].Get(),outputs[2].Get()};
        context->CSSetShader(shader.Get(),nullptr,0);context->CSSetShaderResources(0,UINT(bindings.size()),bindings.data());
        context->CSSetUnorderedAccessViews(0,3,uavs.data(),nullptr);context->Dispatch((width+7)/8,(height+7)/8,1);
        bindings.fill(nullptr);uavs.fill(nullptr);context->CSSetShaderResources(0,UINT(bindings.size()),bindings.data());context->CSSetUnorderedAccessViews(0,3,uavs.data(),nullptr);
        context->CSSetShader(nullptr,nullptr,0);return readPixels(lastGBuffer[0].Get());
    }
