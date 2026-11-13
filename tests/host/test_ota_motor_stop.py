"""Check actual task suspension stops even standalone motor tests before flash I/O pauses."""
from pathlib import Path
import subprocess,tempfile
out=Path(__file__).resolve().parent
src=(out.parents[1]/'src/tasks/task_manager.cpp').read_text()
body=src[src.index('void TaskManager::suspend_hardware_tasks()'):src.index('void TaskManager::resume_hardware_tasks()')]
stubs=r'''
#include <cassert>
#define ATOM_GPIO1_MOTOR_TEST 1
#define LOG_BLE(...) ((void)0)
struct Motor {bool running=true;int stops=0;void stop(){running=false;++stops;}} motor;
struct Controller {bool active=true;int stops=0;bool is_active(){return active;}void stop_grind(){active=false;++stops;motor.stop();}} controller;
struct Hardware {Motor* get_grinder(){return &motor;}} hardware;
static bool control_suspended=false;
void vTaskSuspend(int handle){if(handle==2)control_suspended=true;if(handle==3)assert(control_suspended&&!motor.running);}
struct TaskManager {bool ota_suspended=false;struct {int weight_sampling_task=1,grind_control_task=2,file_io_task=3;}task_handles;Controller* grind_controller=&controller;Hardware* hardware_manager=&hardware;void suspend_hardware_tasks();};
'''
tests=r'''
int main(){
 TaskManager t;t.suspend_hardware_tasks();assert(t.ota_suspended&&!motor.running&&!controller.active&&controller.stops==1);
 int stopped=motor.stops;t.suspend_hardware_tasks();assert(motor.stops==stopped);
 // Menu/diagnostic motor output can be running with the normal controller idle.
 t.ota_suspended=false;motor.running=true;t.suspend_hardware_tasks();assert(!motor.running&&controller.stops==1);
 t.ota_suspended=false;t.hardware_manager=nullptr;t.grind_controller=nullptr;t.suspend_hardware_tasks();assert(t.ota_suspended);
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'ota-stop.cpp';p.write_text(stubs+body+tests);exe=Path(tmp)/'ota-stop'
 subprocess.run(['clang++','-std=c++17','-Wall','-Wextra',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: actual OTA task-suspension path stops controller and standalone motor output before file I/O suspension; repeated calls are idempotent')
