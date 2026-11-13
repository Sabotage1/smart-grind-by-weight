from pathlib import Path
import tempfile,subprocess
base=Path(__file__).resolve().parents[2]
source=(base/'src/controllers/profile_controller.cpp').read_text()
body=source[source.index('void ProfileController::apply_external_dose('):source.index('void ProfileController::update_current_weight(')]
code=r'''
#include <cassert>
#include <cmath>
#include <iostream>
struct Preferences{int saved_profile=-1,calls=0;void putInt(const char*,int value){saved_profile=value;++calls;}} prefs;
struct Profile{float weight,time_seconds;};
struct ProfileController{
 Profile profiles[3]={{12.5f,5},{18,6},{20,7}};int current_profile=0,current_grind_mode=0,saves=0;Preferences* preferences=&prefs;
 bool is_weight_valid(float value){return value>=5&&value<=1000;}
 void save_profiles(){saves++;}
 void apply_external_dose(float);
};
'''+body+r'''
int main(){
 ProfileController p;p.apply_external_dose(12.5f);assert(p.current_profile==2&&p.profiles[2].weight==12.5f&&p.saves==1&&prefs.saved_profile==2);
 assert(p.profiles[0].weight==12.5f&&p.profiles[1].weight==18&&p.profiles[0].time_seconds==5&&p.profiles[1].time_seconds==6&&p.profiles[2].time_seconds==7&&p.current_grind_mode==0);
 p.apply_external_dose(12.5f);assert(p.saves==1&&prefs.calls==1);
 p.apply_external_dose(18);assert(p.saves==2&&p.profiles[2].weight==18&&prefs.calls==1);
 for(float bad:{0.0f,4.9f,1000.1f,NAN})p.apply_external_dose(bad);
 assert(p.saves==2&&p.profiles[2].weight==18);
 std::cout<<"PASS: external dose changes CUSTOM only; local presets, times and mode retained; identical targets avoid NVS rewrites\n";
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'profiles.cpp';p.write_text(code);exe=Path(tmp)/'profiles'
 subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
