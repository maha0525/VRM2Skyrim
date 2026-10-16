// The old diagnostic shader emits constant pink but no deferred ownership tag.
// The new diagnostic adds only that tag; it must survive native GBuffer formats.
void verifyComposite(const Scene& base,const Scene& marked,const fs::path& oldPS,const fs::path& newPS,
                     const fs::path& oldCS,const fs::path& newCS,const fs::path& output,Fixture& f){
    auto pass=[&](const Scene& scene,const fs::path& ps,const fs::path& cs,float ao,float il,bool linear){
        f.render(scene,ps,false,1.f,0,linear,true);return f.composite(cs,ao,il,linear);
    };
    auto difference=[](const std::vector<uint8_t>& a,const std::vector<uint8_t>& b,const std::vector<uint8_t>& mask=std::vector<uint8_t>{}){
        int maximum=0;size_t changed=0;for(size_t i=0;i<a.size();i+=4){int diff=0;
            if(!mask.empty()&&!(mask[i]==255&&mask[i+1]==0&&mask[i+2]==255))continue;
            for(int c=0;c<3;c++){int d=abs(int(a[i+c])-b[i+c]);maximum=std::max(maximum,d);diff+=d;}
            if(diff>3)changed++;
        }return std::pair<int,size_t>{maximum,changed};
    };
    std::ofstream report(output/"composite-verification.json");report<<"{\"native_gbuffer_formats\":true,\"modes\":[";
    for(bool linear:{false,true}){
        auto oldClear=pass(marked,oldPS,oldCS,0,0,linear),oldAo=pass(marked,oldPS,oldCS,.8f,0,linear);
        auto newClear=pass(marked,newPS,newCS,0,0,linear),newAo=pass(marked,newPS,newCS,.8f,0,linear);
        auto newBoth=pass(marked,newPS,newCS,.8f,2.f,linear);
        auto ordinaryClear=pass(base,oldPS,oldCS,0,0,linear),ordinaryOld=pass(base,oldPS,oldCS,.8f,0,linear);
        auto ordinaryNew=pass(base,newPS,newCS,.8f,0,linear);
        auto ordinaryGiOld=pass(base,oldPS,oldCS,0,.8f,linear),ordinaryGiNew=pass(base,newPS,newCS,0,.8f,linear);
        auto positive=difference(oldClear,oldAo,oldClear),excluded=difference(ordinaryOld,ordinaryNew),stable=difference(newClear,newAo,oldClear);
        auto before=difference(oldClear,newClear),both=difference(newClear,newBoth,oldClear);
        auto ordinaryAo=difference(ordinaryClear,ordinaryOld,oldClear),ordinaryGi=difference(ordinaryClear,ordinaryGiOld,oldClear);
        std::cout<<"Composite deltas: old AO "<<positive.first<<"/"<<positive.second<<" marked AO "<<stable.first<<"/"<<stable.second<<" before "<<before.first<<"/"<<before.second<<" combined "<<both.first<<"/"<<both.second<<" ordinary "<<excluded.first<<"\n";
        
        if(positive.second<1000||ordinaryAo.second<1000||ordinaryGi.second<1000)throw std::runtime_error("Composite positive control has no AO/GI");
        if(excluded.first||difference(ordinaryGiOld,ordinaryGiNew).first)throw std::runtime_error("Ordinary composite changed");
        if(stable.first>1||before.first>1||both.first>1)throw std::runtime_error("Marked AO/GI was not bypassed");
        auto mode=std::string(linear?"linear":"legacy");
        Fixture::save(output/(mode+"-old-clear.ppm"),oldClear);Fixture::save(output/(mode+"-old-ao.ppm"),oldAo);
        Fixture::save(output/(mode+"-new-ao.ppm"),newAo);Fixture::save(output/(mode+"-ordinary-ao.ppm"),ordinaryNew);
        if(linear)report<<",";
        report<<"{\"linear\":"<<(linear?"true":"false")<<",\"old_ao_changed_pixels\":"<<positive.second
              <<",\"ordinary_ao_changed_pixels\":"<<ordinaryAo.second<<",\"ordinary_gi_changed_pixels\":"<<ordinaryGi.second
              <<",\"marked_ao_max_difference\":"<<stable.first<<",\"marked_combined_max_difference\":"<<both.first
              <<",\"ordinary_max_difference\":"<<excluded.first<<"}";
        std::cout<<mode<<": old AO changed "<<positive.second<<" pixels; marked new AO delta "<<stable.first<<"; ordinary delta "<<excluded.first<<"\n";
    }
    report<<"]}";std::cout<<"Full Lighting -> native GBuffer -> DeferredComposite: PASS\n";
}
