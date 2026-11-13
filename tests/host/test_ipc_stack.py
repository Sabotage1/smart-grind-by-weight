"""Check the actual SDK task-creation adapter forwards all non-IPC tasks unchanged."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
def body(p):return '\n'.join(x for x in p.read_text().splitlines() if not x.startswith('#include') and x!='#pragma once')
stubs=r'''
#define ATOM_GPIO1_MOTOR_TEST 1
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
using TaskHandle_t=void*;using TaskFunction_t=void(*)(void*);using BaseType_t=int;using UBaseType_t=unsigned;
constexpr int pdPASS=1;
static uint32_t seen_depth;static unsigned seen_priority;static void* seen_arg;static int seen_core;static TaskFunction_t seen_code;static int outcome=pdPASS;
extern "C" int __real_xTaskCreatePinnedToCore(TaskFunction_t code,const char*const,uint32_t depth,void*const arg,unsigned priority,void**const handle,const int core){seen_depth=depth;seen_priority=priority;seen_arg=arg;seen_core=core;seen_code=code;if(handle)*handle=(void*)0x1234;return outcome;}
void task(void*){}
'''
tests=r'''
int main(){
 void* handle=nullptr;
 assert(__wrap_xTaskCreatePinnedToCore(task,"ipc0",1024,(void*)7,24,&handle,0)==pdPASS);
 assert(seen_depth==2048&&atom_ipc_stack_bytes[0]==2048&&atom_ipc_task_handles[0]==handle);
 assert(seen_priority==24&&seen_arg==(void*)7&&seen_core==0&&seen_code==task);
 __wrap_xTaskCreatePinnedToCore(task,"ipc1",1024,nullptr,24,&handle,1);assert(seen_depth==2048&&atom_ipc_stack_bytes[1]==2048&&seen_core==1);
 __wrap_xTaskCreatePinnedToCore(task,"ipc0",8192,nullptr,24,&handle,0);assert(seen_depth==8192);
 for(const char* name:{"loopTask","ipc2","ipc00","Bluetooth",(const char*)nullptr}){__wrap_xTaskCreatePinnedToCore(task,name,1024,nullptr,2,&handle,1);assert(seen_depth==1024&&seen_priority==2);}
 outcome=-1;atom_ipc_stack_bytes[0]=0;assert(__wrap_xTaskCreatePinnedToCore(task,"ipc0",1024,nullptr,24,&handle,0)==-1);assert(atom_ipc_stack_bytes[0]==0);
 puts("PASS: only ipc0/ipc1 stacks grow; larger stacks and every task argument/failure are preserved");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'ipc_test.cpp';p.write_text(stubs+'\n#include <initializer_list>\n'+body(root/'src/system/atom_ipc_stack.h')+'\n'+body(root/'src/system/atom_ipc_stack.cpp')+tests);exe=Path(d)/'ipc-test'
 subprocess.run(['clang++','-std=c++17','-Wall','-Wextra',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
