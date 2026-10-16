// Actual legacy/v1/v2 materials under the previous and current CS adapter.
#define main productionFixtureMain
#include "toon_gpu.cpp"
#undef main
int main(int argc,char** argv){try{
    if(argc!=4)throw std::runtime_error("Usage: compat marked.scene previous.cso current.cso");
    Fixture f;auto scene=loadScene(fs::u8path(argv[1]));int maximum=0;
    for(bool linear:{false,true})for(bool night:{false,true}){
        auto a=f.render(scene,fs::u8path(argv[2]),night,1.f,0,linear),b=f.render(scene,fs::u8path(argv[3]),night,1.f,0,linear);
        for(size_t i=0;i<a.size();i++)maximum=std::max(maximum,abs(int(a[i])-int(b[i])));
    }
    std::cout<<"Previous/current material maximum byte difference "<<maximum<<"\n";
    if(maximum>1)throw std::runtime_error("Existing material appearance changed");return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
