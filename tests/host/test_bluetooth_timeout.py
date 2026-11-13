"""Compile actual timeout/preferences/UI methods for both Atom and upstream defaults."""
from pathlib import Path
import subprocess,tempfile
base=Path(__file__).resolve().parents[2]
manager=(base/'src/bluetooth/manager.cpp').read_text()
settings=manager[manager.index('void BluetoothManager::load_auto_off_setting()'):manager.index('void BluetoothManager::set_ui_status_callback')]
start=manager.index('void BluetoothManager::handle()')
handle=manager[start:manager.index('    if (device_connected && dose_status_characteristic)',start)]+'}\n'
start=manager.index('unsigned long BluetoothManager::get_bluetooth_timeout_remaining_ms() const')
remaining=manager[start:manager.index('void BluetoothManager::start_data_export()',start)]
menu=(base/'src/ui/screens/menu_screen.cpp').read_text()
start=menu.index('void MenuScreen::update_ble_status()')
status=menu[start:menu.index('void MenuScreen::refresh_statistics(',start)]
code=r'''
#include <cassert>
#include <cstdint>
#include <atomic>
#include <map>
#include <string>
#include <cstdio>
#include <iostream>
#include "config/bluetooth.h"
uint32_t now=0;uint32_t millis(){return now;}
std::map<std::string,bool> saved;int writes=0;
struct Preferences{
 void begin(const char* name,bool){assert(std::string(name)=="bluetooth");}
 bool getBool(const char* key,bool fallback){return saved.count(key)?saved[key]:fallback;}
 void putBool(const char* key,bool value){saved[key]=value;++writes;}void end(){}
};
struct BluetoothManager{
 bool ble_enabled=true,device_connected=false;int disables=0;
 uint32_t timeout_ms=BLE_AUTO_DISABLE_TIMEOUT_MS,last_disconnect_time=0;
 std::atomic<bool> auto_off_enabled_{BLE_AUTO_OFF_DEFAULT},restart_idle_timer_{false};
 void load_auto_off_setting();void set_auto_off_enabled(bool);void handle();
 uint32_t get_bluetooth_timeout_remaining_ms()const;
 bool get_auto_off_enabled()const{return auto_off_enabled_.load();}
 bool is_enabled()const{return ble_enabled;}bool is_connected()const{return device_connected;}
 void disable(){++disables;ble_enabled=false;}
 void log(const char*,...){}
};
struct Obj{bool checked=false,hidden=false;std::string text;};
constexpr int LV_STATE_CHECKED=1,LV_OBJ_FLAG_HIDDEN=2;
void lv_obj_add_state(Obj*o,int){o->checked=true;}void lv_obj_clear_state(Obj*o,int){o->checked=false;}
void lv_obj_add_flag(Obj*o,int){o->hidden=true;}void lv_obj_clear_flag(Obj*o,int){o->hidden=false;}
void lv_label_set_text(Obj*o,const char*t){o->text=t;}
struct MenuScreen{BluetoothManager*bluetooth_manager;Obj*ble_toggle,*ble_status_label,*ble_timer_label;bool visible=true;void update_ble_status();};
'''+settings+handle+remaining+status+r'''
int main(){
 BluetoothManager m;saved["startup"]=false;m.load_auto_off_setting();
 assert(m.get_auto_off_enabled()==BLE_AUTO_OFF_DEFAULT && writes==0 && !saved["startup"]);
 saved["auto_off"]=true;m.load_auto_off_setting();assert(m.get_auto_off_enabled());
 m.set_auto_off_enabled(false);assert(!saved["auto_off"]&&writes==1&&!saved["startup"]);
 m.set_auto_off_enabled(false);assert(writes==1); // Same setting does not rewrite flash.
 m.timeout_ms=BLE_BOOTUP_AUTO_DISABLE_TIMEOUT_MS;now=8*60*60*1000u;m.handle();
 assert(m.ble_enabled && m.disables==0 && m.get_bluetooth_timeout_remaining_ms()==0); // Never expires after startup.
 m.set_auto_off_enabled(true);m.handle();assert(m.ble_enabled&&m.last_disconnect_time==now);
 assert(m.get_bluetooth_timeout_remaining_ms()==BLE_AUTO_DISABLE_TIMEOUT_MS); // Enabling policy grants a fresh window.
 now+=BLE_AUTO_DISABLE_TIMEOUT_MS;m.handle();assert(m.ble_enabled);
 now++;m.handle();assert(!m.ble_enabled&&m.disables==1);
 // Connected clients never expire, even with auto-off on.
 m.ble_enabled=true;m.device_connected=true;now+=12*60*60*1000u;m.handle();
 assert(m.ble_enabled&&m.disables==1&&m.get_bluetooth_timeout_remaining_ms()==0);
 m.device_connected=false;m.last_disconnect_time=now;now+=1000;m.handle();
 assert(m.ble_enabled&&m.get_bluetooth_timeout_remaining_ms()==BLE_AUTO_DISABLE_TIMEOUT_MS-1000);
 // Disabling the policy immediately stops expiry after a disconnection.
 m.set_auto_off_enabled(false);now+=24*60*60*1000u;m.handle();assert(m.ble_enabled&&m.disables==1);
 m.ble_enabled=false;now+=24*60*60*1000u;m.handle();assert(!m.ble_enabled); // Never re-enable a manually disabled radio.
 // Retain the legacy 5-minute startup timeout when the user opts in.
 m.ble_enabled=true;m.auto_off_enabled_.store(true);m.restart_idle_timer_.store(false);
 m.timeout_ms=BLE_BOOTUP_AUTO_DISABLE_TIMEOUT_MS;m.last_disconnect_time=now;
 now+=BLE_BOOTUP_AUTO_DISABLE_TIMEOUT_MS+1;m.handle();assert(!m.ble_enabled&&m.disables==2);
 // Timers have Arduino's 32-bit unsigned rollover semantics.
 m.ble_enabled=true;m.timeout_ms=BLE_AUTO_DISABLE_TIMEOUT_MS;m.last_disconnect_time=UINT32_MAX-100;
 now=200;m.handle();assert(m.ble_enabled&&m.get_bluetooth_timeout_remaining_ms()==BLE_AUTO_DISABLE_TIMEOUT_MS-301);
 // Actual menu labels describe policy/connection state instead of a false countdown.
 Obj toggle,label,timer;MenuScreen screen{&m,&toggle,&label,&timer};
 m.auto_off_enabled_.store(false);screen.update_ble_status();assert(label.text=="Advertising"&&timer.text=="Auto-off: Off"&&!timer.hidden);
 m.device_connected=true;screen.update_ble_status();assert(label.text=="Connected"&&timer.text=="Auto-off: Off");
 m.auto_off_enabled_.store(true);screen.update_ble_status();assert(label.text=="Connected"&&timer.text=="Auto-off paused");
 m.device_connected=false;screen.update_ble_status();assert(timer.text=="Auto-off in: 29 min");
 m.ble_enabled=false;screen.update_ble_status();assert(timer.hidden&&label.hidden&&!toggle.checked);
 std::cout<<"PASS: board defaults, persisted opt-in, indefinitely available advertising, connected pause, disconnect/startup expiry, fresh timer on policy change, manual-off, rollover and actual menu labels\n";
}
'''
# Arduino unsigned long is 32-bit; normalize only its type for the macOS host ABI.
code=code.replace('unsigned long','uint32_t').replace('%lu','%u')
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);src=p/'timeout.cpp';src.write_text(code)
 for atom in [True,False]:
  exe=p/('atom' if atom else 'upstream')
  flags=['-DATOM_GPIO1_MOTOR_TEST=1'] if atom else []
  subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',*flags,'-I'+str(base/'src'),str(src),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
