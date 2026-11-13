"""Exercise the actual motor class/function bodies with a fake peripheral backend."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
def without_includes(p):
 return '\n'.join(line for line in p.read_text().splitlines() if not line.startswith('#include') and line!='#pragma once')
stubs=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <functional>
#include <atomic>
#define IRAM_ATTR
#include <algorithm>
#define DEBUG_ENABLE_LOADCELL_MOCK 0
#define HW_GRINDER_SETTLING_TIME_MS 500
#define LOG_BLE(...) ((void)0)
#define LOW 0
using esp_err_t=int; constexpr int ESP_OK=0, ESP_FAIL=-1, ESP_ERR_TIMEOUT=1;
using gpio_num_t=int; constexpr int GPIO_MODE_INPUT_OUTPUT=3, RMT_CLK_SRC_DEFAULT=0;
using rmt_channel_handle_t=void*; using rmt_encoder_handle_t=void*;
struct rmt_tx_done_event_data_t {};
struct rmt_tx_event_callbacks_t {bool (*on_trans_done)(void*,const rmt_tx_done_event_data_t*,void*);};
static rmt_tx_event_callbacks_t saved_callbacks; static void* saved_context;
int rmt_tx_register_event_callbacks(void*,const rmt_tx_event_callbacks_t*c,void*ctx){saved_callbacks=*c;saved_context=ctx;return ESP_OK;}
void fake_complete(){saved_callbacks.on_trans_done((void*)1,nullptr,saved_context);}
struct rmt_symbol_word_t { uint32_t duration0=0,level0=0,duration1=0,level1=0; };
struct rmt_tx_channel_config_t { int gpio_num=0,clk_src=0;uint32_t resolution_hz=0;size_t mem_block_symbols=0,trans_queue_depth=0;struct { unsigned init_level=0,io_loop_back=0;} flags;};
struct rmt_transmit_config_t {int loop_count=0;struct {unsigned eot_level=0;} flags;};
struct rmt_copy_encoder_config_t {};
static bool live=false,fail_create=false,fail_enable=false,fail_tx=false;
static int pad=0,touches=0,tx_count=0; static unsigned now_ms=1;
static const rmt_symbol_word_t* payload=nullptr;static size_t payload_bytes=0;
static rmt_transmit_config_t last_tx;static rmt_tx_channel_config_t last_config;
unsigned long millis(){return now_ms;}
int gpio_set_level(int pin,int level){assert(pin==1);++touches;pad=level;return ESP_OK;}
int gpio_set_direction(int pin,int){assert(pin==1);++touches;return ESP_OK;}
int gpio_pullup_dis(int pin){assert(pin==1);return ESP_OK;}
int gpio_pulldown_en(int pin){assert(pin==1);return ESP_OK;}
esp_err_t rmt_new_tx_channel(const rmt_tx_channel_config_t*c,void**out){last_config=*c;*out=(void*)1;return fail_create?ESP_FAIL:ESP_OK;}
esp_err_t rmt_enable(void*){if(fail_enable)return ESP_FAIL;pad=last_config.flags.init_level;return ESP_OK;}
esp_err_t rmt_disable(void*){live=false;pad=0;return ESP_OK;}
esp_err_t rmt_del_channel(void*){return ESP_OK;}
esp_err_t rmt_new_copy_encoder(const rmt_copy_encoder_config_t*,void**out){*out=(void*)2;return ESP_OK;}
esp_err_t rmt_del_encoder(void*){assert(!live);return ESP_OK;}
esp_err_t rmt_transmit(void*,void*,const void*p,size_t bytes,const rmt_transmit_config_t*c){
 if(fail_tx)return ESP_FAIL;
 payload=(const rmt_symbol_word_t*)p;payload_bytes=bytes;last_tx=*c;live=true;pad=1;++tx_count;return ESP_OK;
}
esp_err_t rmt_tx_wait_all_done(void*,int){return live?ESP_ERR_TIMEOUT:ESP_OK;}
struct SerialStub {template<typename...Args>void printf(const char*,Args...){} void println(const char*){}} Serial;
enum class UIGrindEvent {BACKGROUND_CHANGE}; enum class GrindPhase {IDLE};
struct GrindEventData {UIGrindEvent event;GrindPhase phase;float current_weight;int progress_percent;const char* phase_display_text;bool show_taring_text,background_active;};
'''
tests=r'''
int main(){
 Grinder bench;bench.init(-1);assert(bench.is_initialized());bench.start();bench.start_pulse_rmt(100);bench.stop();assert(tx_count==0&&touches==0);
 Grinder motor;motor.init(1);assert(motor.is_initialized()&&pad==0);assert(last_config.gpio_num==1&&last_config.flags.init_level==0&&last_config.flags.io_loop_back==1);
 for(unsigned ms:{1u,32u,33u,65u,100u,550u,1000u,2000u}){
  motor.start_pulse_rmt(ms);assert(motor.is_grinding()&&live&&last_tx.loop_count==0&&last_tx.flags.eot_level==0);
  // The asynchronous driver retains a pointer: it must refer to the motor object, not a returned stack frame.
  auto ptr=(uintptr_t)payload;assert(ptr>=(uintptr_t)&motor&&ptr+payload_bytes<=(uintptr_t)&motor+sizeof motor);
  unsigned high_us=0;assert(payload_bytes/sizeof(*payload)<=64);
  for(size_t k=0;k<payload_bytes/sizeof(*payload);++k){auto s=payload[k];assert(s.duration0<=32767&&s.duration1<=32767);if(s.level0)high_us+=s.duration0;if(s.level1)high_us+=s.duration1;}
  assert(high_us==ms*1000);
  pad=0;assert(!motor.is_pulse_complete()); // A queued transfer may still have a LOW pad.
  live=false;fake_complete();assert(motor.is_pulse_complete()&&!motor.is_grinding());
 }
 motor.start();assert(motor.is_grinding()&&live&&last_tx.loop_count==-1);
 assert(payload[0].duration0&&payload[0].duration1&&payload[0].level0&&payload[0].level1);
 motor.start();assert(motor.is_grinding()&&live); // Replacement must terminate the old transfer before deleting its encoder.
 motor.stop();assert(!motor.is_grinding()&&!live&&pad==0);
 int before=tx_count;motor.start_pulse_rmt(0);assert(tx_count==before&&pad==0);
 motor.start_pulse_rmt(2001);assert(tx_count==before&&pad==0&&!motor.is_grinding());
 fail_tx=true;motor.start();assert(pad==0&&!live&&!motor.is_grinding());motor.start_pulse_rmt(100);assert(pad==0&&!live&&!motor.is_grinding());fail_tx=false;
 fail_create=true;Grinder failed;failed.init(1);assert(!failed.is_initialized()&&pad==0);failed.start();assert(tx_count==before);fail_create=false;
 fail_enable=true;Grinder enable_failed;enable_failed.init(1);assert(!enable_failed.is_initialized()&&pad==0);fail_enable=false;
 puts("PASS: disabled bench, GPIO1 LOW init, 8 exact finite pulse durations, persistent payloads, queued-pulse completion, continuous start/cancel/replacement, invalid pulse rejection, and RMT failure paths");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'motor_test.cpp';p.write_text(stubs+without_includes(ROOT/'src/hardware/grinder.h')+'\n'+without_includes(ROOT/'src/hardware/grinder.cpp')+'\n'+tests)
 exe=Path(d)/'motor-test'
 subprocess.run(['clang++','-std=c++20','-Wall','-Wextra','-Wno-missing-field-initializers',str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
