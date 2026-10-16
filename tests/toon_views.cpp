// Consistent camera sweep of complete source layers with the production shader.
#define main productionFixtureMain
#include "toon_gpu.cpp"
#undef main
int main(int argc,char** argv){try{
    if(argc!=5)throw std::runtime_error("Usage: views full.scene focus.scene shader.cso output");
    Fixture f;auto scene=loadScene(fs::u8path(argv[1])),focus=loadScene(fs::u8path(argv[2]));
    f.focusHead=true;f.focusLo=focus.lo;f.focusHi=focus.hi;
    auto output=fs::u8path(argv[4]);fs::create_directories(output);
    for(auto pair:{std::pair<const char*,float>{"front",0.f},{"left",-.6f},{"right",.6f}}){
        f.focusYaw=pair.second;Fixture::save(output/(std::string(pair.first)+".ppm"),f.render(scene,fs::u8path(argv[3])));
    }return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
