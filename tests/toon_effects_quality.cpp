// Positive controls through the complete production CS pixel shader.
#define main productionFixtureMain
#include "toon_gpu.cpp"
#undef main
int main(int argc,char** argv){try{
    if(argc!=4)throw std::runtime_error("Usage: effect-quality cases-folder original.cso patched.cso");
    fs::path root=fs::u8path(argv[1]);Fixture f;auto base=loadScene(root/"base.scene");
    auto reference=f.render(base,fs::u8path(argv[3]));Fixture::save(root/"base.ppm",reference);
    std::ofstream report(root/"positive-controls.json");report<<"{";bool first=true;
    for(auto name:{"matcap","rim","normal","outline"}){
        auto changed=loadScene(root/(std::string(name)+".scene"));changed.lo=base.lo;changed.hi=base.hi;
        auto image=f.render(changed,fs::u8path(argv[3]));Fixture::save(root/(std::string(name)+".ppm"),image);
        size_t pixels=0;int maximum=0;for(size_t i=0;i<image.size();i+=4){int d=0;for(int c=0;c<3;c++)d+=abs(int(image[i+c])-int(reference[i+c]));if(d>3)pixels++;maximum=std::max(maximum,d);}
        std::cout<<name<<" changed "<<pixels<<" pixels; max RGB sum "<<maximum<<"\n";
        if(pixels<100||maximum<10)throw std::runtime_error(std::string("No visible effect: ")+name);
        // Outline expands coverage; compare darkness at the same shell geometry.
        auto night=f.render(changed,fs::u8path(argv[3]),true),baseNight=f.render(changed,fs::u8path(argv[2]),true);
        int nightError=0;for(size_t i=0;i<night.size();i+=4)for(int c=0;c<3;c++)nightError=std::max(nightError,abs(int(night[i+c])-int(baseNight[i+c])));
        if(nightError)throw std::runtime_error(std::string("Authored lit effect emits in darkness: ")+name);
        if(!first)report<<",";first=false;report<<"\""<<name<<"\":{\"changed_pixels\":"<<pixels<<",\"maximum_rgb_sum\":"<<maximum<<",\"night_error\":"<<nightError<<"}";
    }
    auto quad=[&](float y,const char* texture,uint32_t flags){
        Mesh m=base.meshes[0];m.flags=flags;m.textures[0]=(root/texture).string();
        m.vertices={{{-1,y,-1},{0,1,0},{0,0}},{{1,y,-1},{0,1,0},{1,0}},
                    {{1,y,1},{0,1,0},{1,1}},{{-1,y,1},{0,1,0},{0,1}}};
        m.indices={0,1,2,0,2,3};return m;
    };
    auto delta=[](const auto& a,const auto& b){int maximum=0;
        for(unsigned y=400;y<500;y++)for(unsigned x=310;x<410;x++)for(int c=0;c<3;c++){
            auto i=(y*Fixture::width+x)*4+c;maximum=std::max(maximum,abs(int(a[i])-int(b[i])));
        }return maximum;
    };
    for(bool writesDepth:{false,true}){
        Scene referenceScene;referenceScene.lo={-1,0,-1};referenceScene.hi={1,0,1};
        auto front=quad(0,"layer-red.dds",1u|(1u<<20)|(writesDepth?0:(1u<<21)));
        referenceScene.meshes={front};auto expected=f.render(referenceScene,fs::u8path(argv[3]));
        Scene layers=referenceScene;
        // No-write front before opaque back tests phase ordering. Write front
        // before a no-write back tests actual transparent depth writes.
        auto back=quad(-.4f,"layer-blue.dds",(1u<<20)|(writesDepth?(1u|(1u<<21)):0));
        layers.meshes={front,back};auto actual=f.render(layers,fs::u8path(argv[3]));
        int error=delta(expected,actual);if(error>1)throw std::runtime_error("Transparent depth/phase regression");
        if(writesDepth){layers.meshes[0].flags|=1u<<21;
            if(delta(expected,f.render(layers,fs::u8path(argv[3])))<10)throw std::runtime_error("Missing depth-write positive control");}
        std::cout<<"Transparent "<<(writesDepth?"depth write":"render phase")<<" error "<<error<<"\n";
    }
    report<<",\"transparent_depth_and_phases\":true}";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
