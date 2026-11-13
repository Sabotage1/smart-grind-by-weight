"""Exercise actual preference, timeout, UI-selection and touch-guard code with host I/O."""
from pathlib import Path
import subprocess
import tempfile

base = Path(__file__).resolve().parents[2]

def run(name, code, headers=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for path, content in (headers or {}).items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        source = root / f'{name}.cpp'
        source.write_text(code)
        exe = root / name
        subprocess.run(['clang++', '-std=c++17', '-fsanitize=address,undefined',
                        '-I'+str(root), '-I'+str(base/'src/hardware'),
                        '-I'+str(base/'src/bluetooth'), str(source), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

profile_header = (base/'src/controllers/profile_controller.h').read_text().replace(
    '#include "../config/constants.h"', '#include "constants.h"')
preferences = r'''
#pragma once
#include <map>
#include <string>
struct Preferences {
 std::map<std::string,int> ints;
 std::map<std::string,float> floats;
 int int_writes=0, float_writes=0;
 int getInt(const char* k,int d){auto p=ints.find(k);return p==ints.end()?d:p->second;}
 float getFloat(const char* k,float d){auto p=floats.find(k);return p==floats.end()?d:p->second;}
 void putInt(const char* k,int v){ints[k]=v;++int_writes;}
 void putFloat(const char* k,float v){floats[k]=v;++float_writes;}
};
'''
constants = r'''
#pragma once
constexpr int USER_PROFILE_COUNT=3, USER_PROFILE_NAME_MAX_LENGTH=16;
constexpr float USER_SINGLE_ESPRESSO_WEIGHT_G=12.5f, USER_DOUBLE_ESPRESSO_WEIGHT_G=18,
 USER_CUSTOM_PROFILE_WEIGHT_G=20, USER_SINGLE_ESPRESSO_TIME_S=5,
 USER_DOUBLE_ESPRESSO_TIME_S=6, USER_CUSTOM_PROFILE_TIME_S=7,
 USER_MIN_TARGET_WEIGHT_G=5, USER_MAX_TARGET_WEIGHT_G=1000,
 USER_MIN_TARGET_TIME_S=1, USER_MAX_TARGET_TIME_S=60;
'''
profile_source = (base/'src/controllers/profile_controller.cpp').read_text()
run('preferences', '#include <cassert>\n#include <iostream>\n'+profile_source+r'''
int main(){
 for(int option:{-1,0,1,2,3,-2}) {
  Preferences prefs;prefs.ints={{"profile",2},{"auto_profile",option},{"grind_mode",1}};
  prefs.floats={{"weight0",12.4f},{"weight1",18.2f},{"weight2",21.7f},{"time2",8.5f},{"hx_cal",-5166.4f}};
  const auto before=prefs.floats;
  ProfileController p;p.init(&prefs);
  const int expected=option>=0&&option<3?option:2;
  assert(p.get_current_profile()==expected);
  assert(p.get_auto_select_profile()==(option>=-1&&option<3?option:-1));
  assert(prefs.floats==before && prefs.float_writes==0 && p.get_grind_mode()==GrindMode::TIME);
  const auto saved=prefs.int_writes;
  if(option>=0&&option<3)assert(p.select_auto_profile());else assert(!p.select_auto_profile());
  assert(prefs.int_writes==saved); // Already selected: no extra flash write.
 }
 Preferences prefs;prefs.ints["profile"]=1;
 ProfileController p;p.init(&prefs);
 assert(p.get_auto_select_profile()==-1 && p.get_current_profile()==1); // Upgrade is Off.
 p.set_auto_select_profile(0);assert(p.get_current_profile()==1 && prefs.ints["auto_profile"]==0);
 p.set_auto_select_profile(0);p.set_auto_select_profile(3);p.set_auto_select_profile(-2);
 assert(prefs.int_writes==1);
 assert(p.select_auto_profile() && p.get_current_profile()==0);
 p.apply_external_dose(12.5f);assert(p.get_current_profile()==2 && p.get_current_weight()==12.5f);
 assert(p.get_auto_select_profile()==0); // Remote dose never rewrites the saved default.
 const int writes=prefs.int_writes, floats=prefs.float_writes;
 p.apply_external_dose(12.5f);assert(prefs.int_writes==writes && prefs.float_writes==floats);
 assert(p.select_auto_profile() && p.get_current_profile()==0);
 p.apply_external_dose(12.5f);assert(p.get_current_profile()==2); // Equal dose still selects CUSTOM.
 assert(p.get_profile_weight(0)==12.5f && p.get_profile_weight(1)==18 && p.get_profile_time(2)==7);
 p.set_auto_select_profile(-1);assert(!p.select_auto_profile() && p.get_current_profile()==2);
 std::cout<<"PASS: boot/wake default, Off/invalid preferences, CUSTOM priority, unchanged doses, saved targets/times/calibration and bounded NVS writes\n";
}
''', {'profile_controller.h':profile_header, 'Preferences.h':preferences,
      'constants.h':constants, 'Arduino.h':'#pragma once\n',
      'grind_mode.h':(base/'src/controllers/grind_mode.h').read_text()})

timeout_source = (base/'src/ui/controllers/screen_timeout_controller.cpp').read_text()
timeout_source = '\n'.join(line for line in timeout_source.splitlines() if not line.startswith('#include'))
timeout_header = (base/'src/ui/controllers/screen_timeout_controller.h').read_text().replace('#pragma once', '')
run('timeout', r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include "wake_touch_guard.h"
uint32_t now=0;
uint32_t millis(){return now;}
constexpr uint32_t USER_SCREEN_AUTO_DIM_TIMEOUT_MS=300000;
constexpr float USER_WEIGHT_ACTIVITY_THRESHOLD_G=2, USER_SCREEN_BRIGHTNESS_NORMAL=1,
 USER_SCREEN_BRIGHTNESS_DIMMED=.35f;
struct Touch {uint32_t age=300000;uint32_t get_ms_since_last_touch(){return age;}};
struct Display {
 Touch touch;WakeTouchGuard guard;float brightness=1;int changes=0;
 Touch* get_touch_driver(){return &touch;}
 void set_dimmed(bool d,bool p){guard.set_dimmed(d,p);}
 void set_brightness(float b){brightness=b;++changes;}
};
struct Sensor {bool activity=false;bool weight_range_exceeds(uint32_t,float){return activity;}};
struct Hardware {Display display;Sensor sensor;Display* get_display(){return &display;}Sensor* get_weight_sensor(){return &sensor;}};
enum class UIState {READY,GRINDING};
struct State {UIState state=UIState::READY;bool is_state(UIState s){return s==state;}};
struct Profile {int option=0;int get_auto_select_profile(){return option;}};
struct Menu {float get_normal_brightness(){return .8f;}float get_screensaver_brightness(){return .2f;}};
struct UIManager {Hardware* hardware_manager;State* state_machine;Profile* profile_controller;Menu* menu_controller_;};
'''+timeout_header+timeout_source+r'''
int main(){
 Hardware hw;State state;Profile profile;Menu menu;UIManager ui{&hw,&state,&profile,&menu};
 ScreenTimeoutController timer(&ui);auto& d=hw.display;
 assert(!timer.update() && d.brightness==.2f);
 assert(!timer.update() && d.changes==1); // Dim once.
 assert(!d.guard.allow(true)); // First wake press never reaches LVGL.
 d.touch.age=0;assert(timer.update() && d.brightness==.8f);
 assert(!d.guard.allow(true));assert(!d.guard.allow(false));assert(d.guard.allow(true));
 assert(!timer.update());
 d.touch.age=300000;assert(!timer.update());
 hw.sensor.activity=true;assert(timer.update() && d.brightness==.8f); // Cup/weight wakes too.
 hw.sensor.activity=false;assert(!timer.update());
 state.state=UIState::GRINDING;assert(!timer.update() && d.brightness==.8f); // Never report a profile wake while grinding.
 state.state=UIState::READY;assert(!timer.update());
 now=UINT32_MAX-100;timer.wake_for_external_update();assert(d.brightness==.8f && !timer.update());
 now=100;assert(!timer.update() && d.brightness==.8f); // External wake grace crosses timer rollover.
 now=299898;assert(!timer.update() && d.brightness==.8f);
 now=299899;assert(!timer.update() && d.brightness==.2f); // Five minutes then normal dimming.
 profile.option=-1;assert(!timer.update());assert(d.guard.allow(true)); // Off preserves original wake input.
 WakeTouchGuard forced;forced.suppress_current_touch();assert(!forced.allow(true));
 forced.set_dimmed(false,false);assert(!forced.allow(true));assert(!forced.allow(false));assert(forced.allow(true));
 WakeTouchGuard no_touch;no_touch.suppress_current_touch();assert(!no_touch.allow(false));assert(no_touch.allow(true));
 ScreenTimeoutController absent(nullptr);assert(!absent.update());absent.wake_for_external_update();
 std::cout<<"PASS: touch/weight wake, consumed wake gesture, busy restoration, external wake grace, Off behavior and timer rollover\n";
}
''')

ui_source=(base/'src/ui/ui_manager.cpp').read_text()
selection=ui_source[ui_source.index('bool UIManager::can_switch_profile('):ui_source.index('void UIManager::switch_to_state(')]
states=(base/'src/system/state_machine.h').read_text().replace('#pragma once', '')
phases=(base/'src/controllers/grind_controller.h').read_text()
selection_safe=phases[phases.index('    bool can_select_profile() const {'):phases.index('\n    }',phases.index('    bool can_select_profile() const {'))+6]
phases=phases[phases.index('enum class GrindPhase {'):phases.index('\n};',phases.index('enum class GrindPhase {'))+3]
run('ui_selection', r'''
#include <cassert>
#include <iostream>
#include "dose_protocol.h"
#include "wake_touch_guard.h"
uint32_t millis(){return 100;}
constexpr float USER_MIN_TARGET_WEIGHT_G=5,USER_MAX_TARGET_WEIGHT_G=1000;
enum class GrindMode{WEIGHT,TIME};
'''+states+phases+r'''
struct Touch{bool pressed=false;bool is_pressed(){return pressed;}};
struct Display{Touch touch;WakeTouchGuard guard;int suppressions=0;Touch* get_touch_driver(){return &touch;}void suppress_current_touch(){++suppressions;guard.suppress_current_touch();}};
struct Motor{bool running=false;bool is_grinding(){return running;}};
struct Hardware{Display display;Motor motor;Display* get_display(){return &display;}Motor* get_grinder(){return &motor;}};
struct Profile{
 int slot=1,option=-1;float weights[3]={12.5f,18,20};GrindMode mode=GrindMode::WEIGHT;
 int get_current_profile(){return slot;}float get_current_weight(){return weights[slot];}GrindMode get_grind_mode(){return mode;}
 bool select_auto_profile(){if(option<0)return false;slot=option;return true;}
 void apply_external_dose(float dose){weights[2]=dose;slot=2;}
};
struct Grind{
 GrindPhase phase=GrindPhase::IDLE;int acknowledgements=0;
 '''+selection_safe+r'''
 bool is_active(){return phase!=GrindPhase::IDLE;}
 void return_to_idle(){if(phase==GrindPhase::COMPLETED||phase==GrindPhase::TIMEOUT)phase=GrindPhase::IDLE;++acknowledgements;}
};
struct Mailbox{
 bool pending=false;int applied=0;atom_dose::Status last;atom_dose::Result result;
 template<class Apply>bool process(atom_dose::Status status,uint32_t,Apply apply){
  last=status;if(!pending)return false;pending=false;result=atom_dose::validate({1,125},status,0);
  if(result!=atom_dose::applied)return false;apply(12.5f);++applied;return true;
 }
};
struct Bluetooth{bool updating=false;Mailbox mailbox;bool is_updating(){return updating;}Mailbox& profile_sync(){return mailbox;}};
struct Timeout{int external_wakes=0;void wake_for_external_update(){++external_wakes;}};
struct UIManager{
 Hardware* hardware_manager;StateMachine* state_machine;Profile* profile_controller;Grind* grind_controller;Bluetooth* bluetooth_manager;Timeout* screen_timeout_controller_;
 int current_tab=1,navigations=0;
 bool can_switch_profile(bool allow_wake_touch=false)const;
 void show_selected_profile();void update_profile_selection(bool);
 void switch_to_state(UIState state){state_machine->transition_to(state);++navigations;}
};
'''+(base/'src/system/state_machine.cpp').read_text().replace('#include "state_machine.h"','').replace('#include <Arduino.h>','')+selection+r'''
int main(){
 Hardware hw;StateMachine state;Profile profile;Grind grind;Bluetooth ble;Timeout timeout;
 for(int i=0;i<=static_cast<int>(GrindPhase::PURGE_CONFIRM);++i){
  grind.phase=static_cast<GrindPhase>(i);
  assert(grind.can_select_profile()==(grind.phase==GrindPhase::IDLE||grind.phase==GrindPhase::COMPLETED||grind.phase==GrindPhase::TIMEOUT));
 }
 grind.phase=GrindPhase::IDLE;
 UIManager ui{&hw,&state,&profile,&grind,&ble,&timeout};
 for(auto s:{UIState::READY,UIState::MENU,UIState::GRIND_COMPLETE,UIState::GRIND_TIMEOUT}){
  state.init(s);grind.phase=s==UIState::GRIND_COMPLETE?GrindPhase::COMPLETED:s==UIState::GRIND_TIMEOUT?GrindPhase::TIMEOUT:GrindPhase::IDLE;
  profile.slot=0;ble.mailbox.pending=true;ui.update_profile_selection(false);
  assert(profile.slot==2 && profile.weights[2]==12.5f && ui.current_tab==2 && state.is_state(UIState::READY));
  assert(grind.phase==GrindPhase::IDLE && !hw.motor.running);
 }
 for(auto s:{UIState::EDIT,UIState::CALIBRATION,UIState::CONFIRM,UIState::PURGE_CONFIRM,UIState::AUTOTUNING,UIState::OTA_UPDATE,UIState::OTA_UPDATE_FAILED,UIState::GRINDING}){
  state.init(s);profile.slot=1;profile.option=0;ble.mailbox.pending=true;ui.update_profile_selection(true);
  assert(profile.slot==1 && state.is_state(s) && ble.mailbox.result==atom_dose::busy);
 }
 state.init();profile.option=0;
 for(int busy=0;busy<4;++busy){
  profile.slot=1;hw.motor.running=busy==0;ble.updating=busy==1;hw.display.touch.pressed=busy==2;
  grind.phase=busy==3?GrindPhase::TARING:GrindPhase::IDLE;
  ble.mailbox.pending=true;ui.update_profile_selection(false);assert(profile.slot==1 && ble.mailbox.result==atom_dose::busy);
 }
 hw.motor.running=false;ble.updating=false;hw.display.touch.pressed=false;grind.phase=GrindPhase::IDLE;
 profile.mode=GrindMode::TIME;profile.slot=1;ble.mailbox.pending=true;ui.update_profile_selection(false);
 assert(profile.slot==1 && ble.mailbox.result==atom_dose::wrong_mode);profile.mode=GrindMode::WEIGHT;
 state.init(UIState::MENU);profile.option=-1;ui.update_profile_selection(true);assert(profile.slot==1 && state.is_state(UIState::MENU));
 profile.option=0;ui.update_profile_selection(true);assert(profile.slot==0 && state.is_state(UIState::READY));
 profile.slot=1;ble.mailbox.pending=true;ui.update_profile_selection(true);assert(profile.slot==2 && ui.current_tab==2); // Fresh remote beats default.
 const int commands=ble.mailbox.applied;ui.update_profile_selection(true);assert(profile.slot==0 && ble.mailbox.applied==commands);
 ui.update_profile_selection(false);assert(profile.slot==0); // No stale remote replay over the default.
 profile.slot=1;hw.display.touch.pressed=true;ui.update_profile_selection(true);assert(profile.slot==0); // Guard consumes wake touch, so default can select now.
 assert(timeout.external_wakes==5 && !hw.motor.running);
 std::cout<<"PASS: READY/menu/completion/timeout navigate CUSTOM; active/edit/calibration/OTA/time-mode protected; default and remote priority; no motor actuation\n";
}
''')
