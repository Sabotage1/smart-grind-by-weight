const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
test('actual firmware protocol and RTOS mailbox reject unsafe/stale commands and isolate sessions',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'atom65-dose-'));
  try{
    fs.mkdirSync(path.join(dir,'freertos'));
    fs.writeFileSync(path.join(dir,'freertos/FreeRTOS.h'),'#pragma once\n#define pdPASS 1\n');
    fs.writeFileSync(path.join(dir,'freertos/queue.h'),`#pragma once
#include <deque>
#include <vector>
#include <cstring>
struct Queue { size_t capacity, size; std::deque<std::vector<unsigned char>> data; };
using QueueHandle_t = Queue*;
inline QueueHandle_t xQueueCreate(size_t n,size_t s){return new Queue{n,s,{}};}
inline int xQueueReset(Queue* q){q->data.clear();return 1;}
inline int xQueueSend(Queue* q,const void* p,int){if(q->data.size()==q->capacity)return 0;auto b=(const unsigned char*)p;q->data.emplace_back(b,b+q->size);return 1;}
inline int xQueueOverwrite(Queue* q,const void* p){q->data.clear();return xQueueSend(q,p,0);}
inline int xQueuePeek(Queue* q,void* p,int){if(q->data.empty())return 0;memcpy(p,q->data.front().data(),q->size);return 1;}
inline int xQueueReceive(Queue* q,void* p,int){if(!xQueuePeek(q,p,0))return 0;q->data.pop_front();return 1;}
`);
    fs.writeFileSync(path.join(dir,'test.cpp'),`#include "dose_sync.h"
#include <array>
#include <cassert>
#include <iostream>
std::array<uint8_t,8> command(uint16_t seq,uint16_t dose) {std::array<uint8_t,8> b{166,1,1};atom_dose::put(b.data()+3,seq);atom_dose::put(b.data()+5,dose);b[7]=atom_dose::checksum(b.data(),7);return b;}
int main(){
  AtomDoseSync sync;sync.init();sync.connected(true);assert(sync.available());
  atom_dose::Status status;status.flags=atom_dose::ready;status.dose=180;status.slot=1;
  int applied=0;float target=0;auto apply=[&](float dose){applied++;target=dose;};
  auto send=[&](uint16_t seq,uint16_t dose,uint32_t received,uint32_t now){auto b=command(seq,dose);sync.receive(b.data(),b.size(),received);return sync.process(status,now,apply);};
  atom_dose::Status reply;
  assert(send(1,192,100,101));assert(applied==1 && target==19.2f);assert(sync.next(reply));assert(reply.result==atom_dose::applied && reply.sequence==1 && reply.slot==2 && reply.dose==192);
  uint8_t bytes[15];atom_dose::encode(reply,bytes);assert(atom_dose::checksum(bytes,15)==0 && atom_dose::word(bytes+6)==192);
  assert(!send(2,49,100,101));assert(sync.next(reply) && reply.result==atom_dose::invalid);
  assert(!send(3,10001,100,101));assert(sync.next(reply) && reply.result==atom_dose::invalid);
  assert(!send(4,180,100,851));assert(sync.next(reply) && reply.result==atom_dose::expired);
  assert(send(5,50,100,850));assert(sync.next(reply) && reply.result==atom_dose::applied);
  assert(send(6,10000,100,101));assert(sync.next(reply) && reply.dose==10000);
  for(uint8_t flags : {uint8_t(0),uint8_t(2),uint8_t(4),uint8_t(8),uint8_t(3),uint8_t(5),uint8_t(9)}){status.flags=flags;assert(!send(7,180,100,101));assert(sync.next(reply) && reply.result==atom_dose::busy);}
  status.flags=atom_dose::ready;status.mode=1;assert(!send(8,180,100,101));assert(sync.next(reply) && reply.result==atom_dose::wrong_mode);status.mode=0;
  int before=applied;
  for(size_t length=0;length<=9;length++){if(length==8)continue;auto b=command(9,180);uint8_t data[10]{};std::copy(b.begin(),b.end(),data);sync.receive(data,length,100);sync.process(status,101,apply);assert(sync.next(reply) && reply.result==atom_dose::invalid);}
  for(size_t index=0;index<8;index++){auto b=command(10,180);b[index]^=1;sync.receive(b.data(),b.size(),100);sync.process(status,101,apply);assert(sync.next(reply) && reply.result==atom_dose::invalid);}
  auto zero=command(0,180);sync.receive(zero.data(),8,100);sync.process(status,101,apply);assert(sync.next(reply) && reply.result==atom_dose::invalid);assert(applied==before);
  auto b=command(11,220);sync.receive(b.data(),8,100);sync.connected(false);sync.connected(true);assert(!sync.process(status,101,apply));assert(applied==before);
  status.flags=atom_dose::grinding;assert(!send(12,220,100,101));sync.next(reply);status.flags=atom_dose::ready;assert(!sync.process(status,102,apply));assert(applied==before);
  assert(send(13,200,0xfffffff0u,15));assert(sync.next(reply) && reply.result==atom_dose::applied);
  AtomDoseSync sibling;sibling.init();sibling.connected(true);auto c=command(1,170);sibling.receive(c.data(),8,100);assert(sibling.process(status,101,apply));assert(sibling.next(reply) && reply.dose==170);
  sync.connected(false);auto d=command(14,300);sync.receive(d.data(),8,100);assert(!sync.process(status,101,apply));
  std::cout<<"Protocol/mailbox: framing, checksum, bounds, expiry, clock wrap, all busy gates, time mode, CUSTOM ack, disconnect fencing, no deferred apply, sibling isolation passed\\n";
}
`);
    const include=path.resolve(__dirname,'../../../src/bluetooth');
    const binary=path.join(dir,'firmware-test');
    cp.execFileSync('c++',['-std=c++17','-Wall','-Wextra','-Werror','-I'+dir,'-I'+include,path.join(dir,'test.cpp'),'-o',binary]);
    const output=cp.execFileSync(binary,{encoding:'utf8'});assert.match(output,/passed/);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('actual ProfileController updates CUSTOM, preserves SINGLE/DOUBLE, calibration and mode',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'atom65-preset-'));
  try{
    const src=path.resolve(__dirname,'../../../src');
    const strip=name=>fs.readFileSync(path.join(src,name),'utf8').split('\n').filter(line=>!line.startsWith('#include')&&line!=='#pragma once').join('\n');
    const code=`#include <map>
#include <string>
#include <cstring>
#include <cassert>
#include <cmath>
#include "${path.join(src,'config/user.h')}"
enum class GrindMode {WEIGHT,TIME};
class Preferences {public:
std::map<std::string,float> floats{{"cal_factor",123.45f}};
std::map<std::string,int> ints;
int getInt(const char* key,int fallback){return ints.count(key)?ints[key]:fallback;}
float getFloat(const char* key,float fallback){return floats.count(key)?floats[key]:fallback;}
void putInt(const char* key,int value){ints[key]=value;}
void putFloat(const char* key,float value){floats[key]=value;}
};
${strip('controllers/profile_controller.h')}
${strip('controllers/profile_controller.cpp')}
int main(){Preferences prefs;ProfileController p;p.init(&prefs);
p.apply_external_dose(19.2f);assert(p.get_current_profile()==2 && p.get_current_weight()==19.2f);
assert(p.get_profile_weight(0)==9.0f && p.get_profile_weight(1)==18.0f);
assert(prefs.floats["weight2"]==19.2f && prefs.ints["profile"]==2 && prefs.floats["cal_factor"]==123.45f);
p.apply_external_dose(0);p.apply_external_dose(1001);p.apply_external_dose(NAN);assert(p.get_current_weight()==19.2f);
p.set_grind_mode(GrindMode::TIME);p.apply_external_dose(20.5f);assert(p.get_grind_mode()==GrindMode::TIME);
ProfileController after;after.init(&prefs);assert(after.get_current_weight()==20.5f && after.get_current_profile()==2);
assert(after.get_profile_weight(0)==9.0f && after.get_profile_weight(1)==18.0f);
}`;
    fs.writeFileSync(path.join(dir,'test.cpp'),code);
    const binary=path.join(dir,'preset-test');
    cp.execFileSync('c++',['-std=c++17','-Wall','-Wextra','-Werror',path.join(dir,'test.cpp'),'-o',binary]);
    cp.execFileSync(binary);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
