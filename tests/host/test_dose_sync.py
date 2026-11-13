from pathlib import Path
import subprocess,tempfile
base=Path(__file__).resolve().parents[2]
headers=r'''
#pragma once
#include <cstdint>
struct Q;
using QueueHandle_t=Q*;
constexpr int pdPASS=1;
QueueHandle_t xQueueCreate(unsigned,unsigned);
int xQueueReset(QueueHandle_t);
int xQueueSend(QueueHandle_t,const void*,uint32_t);
int xQueueReceive(QueueHandle_t,void*,uint32_t);
int xQueueOverwrite(QueueHandle_t,const void*);
int xQueuePeek(QueueHandle_t,void*,uint32_t);
'''
code=r'''
#include <cassert>
#include <vector>
#include <memory>
#include <cstring>
#include <iostream>
#include "dose_sync.h"
struct Q{unsigned capacity,size;std::vector<std::vector<uint8_t>> values;};
std::vector<std::unique_ptr<Q>> owned;
QueueHandle_t xQueueCreate(unsigned c,unsigned s){owned.emplace_back(new Q{c,s,{}});return owned.back().get();}
int xQueueReset(Q* q){q->values.clear();return 1;}
int xQueueSend(Q* q,const void* p,uint32_t){if(q->values.size()>=q->capacity)return 0;auto b=static_cast<const uint8_t*>(p);q->values.emplace_back(b,b+q->size);return 1;}
int xQueueReceive(Q* q,void* p,uint32_t){if(q->values.empty())return 0;memcpy(p,q->values[0].data(),q->size);q->values.erase(q->values.begin());return 1;}
int xQueueOverwrite(Q* q,const void* p){xQueueReset(q);return xQueueSend(q,p,0);}
int xQueuePeek(Q* q,void* p,uint32_t){if(q->values.empty())return 0;memcpy(p,q->values[0].data(),q->size);return 1;}
std::vector<uint8_t> frame(uint16_t seq,uint16_t dose){std::vector<uint8_t> p{166,1,1,0,0,0,0,0};atom_dose::put(p.data()+3,seq);atom_dose::put(p.data()+5,dose);p[7]=atom_dose::checksum(p.data(),7);return p;}
int main(){
 using namespace atom_dose;
 Command command;Status status;status.flags=ready;status.dose=125;status.slot=0;
 auto bytes=frame(1,125);assert(decode(bytes.data(),bytes.size(),command));assert(validate(command,status,0)==applied);
 for(int n=0;n<8;n++)assert(!decode(bytes.data(),n,command));
 for(int i=0;i<8;i++){auto bad=bytes;bad[i]^=1;assert(!decode(bad.data(),bad.size(),command));}
 auto zero=frame(0,125);assert(!decode(zero.data(),zero.size(),command));
 for(uint16_t n:{49,10001}){Command c{1,n};assert(validate(c,status,0)==invalid);}
 for(uint16_t n:{50,125,10000}){Command c{1,n};assert(validate(c,status,750)==applied);}
 assert(validate({1,125},status,751)==expired);
 for(int flag:{0,int(grinding),int(updating),int(editing),int(ready|grinding)}){auto busy_status=status;busy_status.flags=flag;assert(validate({1,125},busy_status,0)==busy);}
 auto timed=status;timed.mode=1;assert(validate({1,125},timed,0)==wrong_mode);
 uint8_t encoded[15];encode(status,encoded);assert(checksum(encoded,14)==encoded[14]&&word(encoded+6)==125);
 AtomDoseSync box;box.init();assert(box.available());box.connected(true);std::vector<float> applied_values;
 auto apply=[&](float weight){applied_values.push_back(weight);};
 box.receive(bytes.data(),bytes.size(),100);assert(box.process(status,120,apply));Status reply;assert(box.next(reply)&&reply.result==applied&&reply.dose==125&&reply.slot==2);assert(applied_values.back()==12.5f);
 assert(!box.process(status,130,apply)&&applied_values.size()==1);
 auto second=frame(2,180);box.receive(second.data(),8,200);box.connected(false);box.connected(true);assert(!box.process(status,210,apply)&&applied_values.size()==1);
 box.receive(second.data(),8,200);assert(!box.process(status,951,apply));assert(box.next(reply)&&reply.result==expired&&applied_values.size()==1);
 box.receive(second.data(),8,1000);auto busy_status=status;busy_status.flags=grinding;assert(!box.process(busy_status,1001,apply));assert(box.next(reply)&&reply.result==busy);
 box.receive(second.data(),8,1100);assert(!box.process(timed,1101,apply));assert(box.next(reply)&&reply.result==wrong_mode);
 auto third=frame(3,200);box.receive(second.data(),8,1200);box.receive(third.data(),8,1201);assert(box.process(status,1202,apply));assert(applied_values.back()==18.0f);assert(!box.process(status,1203,apply));
 box.receive(third.data(),8,1300);assert(box.process(status,1301,apply));box.connected(false);assert(!box.next(reply));
 box.receive(bytes.data(),8,1400);assert(!box.process(status,1401,apply));
 box.connected(true);box.receive(bytes.data(),8,UINT32_MAX-10);assert(box.process(status,20,apply));
 std::cout<<"PASS: protocol bounds/checksum, busy/edit/OTA/time-mode rejection, expiry, one-item queue, disconnect fencing and timer wrap\n";
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'freertos').mkdir();(p/'freertos/FreeRTOS.h').write_text(headers);(p/'freertos/queue.h').write_text('#include "FreeRTOS.h"\n')
 (p/'dose.cpp').write_text(code);exe=p/'dose'
 subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-I'+str(p),'-I'+str(base/'src/bluetooth'),str(p/'dose.cpp'),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
