#ifdef ATOM_GPIO1_MOTOR_TEST
#include "atom_ipc_stack.h"
#include <cstring>

// The prebuilt ESP-IDF 5.5.1 SDK creates ipc0/ipc1 with 1024-byte stacks.
// A captured boot panic exhausted ipc0 inside btdm_intr_alloc -> esp_intr_alloc
// -> heap_caps_malloc. A compiler -D cannot resize those prebuilt SDK tasks.
// The env's linker wrap forwards task creation unchanged except these two
// named system tasks, whose stack allocation is raised to 2048 bytes.
// SDK source: components/esp_system/esp_ipc.c, esp_ipc_init().
uint32_t atom_ipc_stack_bytes[2] = {};
TaskHandle_t atom_ipc_task_handles[2] = {};

extern "C" BaseType_t __real_xTaskCreatePinnedToCore(
    TaskFunction_t code, const char* const name, const uint32_t stack_bytes,
    void* const arg, UBaseType_t priority, TaskHandle_t* const handle,
    const BaseType_t core);

extern "C" BaseType_t __wrap_xTaskCreatePinnedToCore(
    TaskFunction_t code, const char* const name, const uint32_t stack_bytes,
    void* const arg, UBaseType_t priority, TaskHandle_t* const handle,
    const BaseType_t core) {
    int ipc_index = -1;
    if (name && std::strcmp(name, "ipc0") == 0) ipc_index = 0;
    else if (name && std::strcmp(name, "ipc1") == 0) ipc_index = 1;
    const uint32_t actual_stack = ipc_index >= 0 && stack_bytes < 2048 ? 2048 : stack_bytes;
    const BaseType_t result = __real_xTaskCreatePinnedToCore(
        code, name, actual_stack, arg, priority, handle, core);
    if (ipc_index >= 0 && result == pdPASS) {
        atom_ipc_stack_bytes[ipc_index] = actual_stack;
        atom_ipc_task_handles[ipc_index] = handle ? *handle : nullptr;
    }
    return result;
}
#endif
