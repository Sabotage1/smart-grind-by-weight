#pragma once

#ifdef ATOM_GPIO1_MOTOR_TEST
#include <cstdint>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

extern uint32_t atom_ipc_stack_bytes[2];
extern TaskHandle_t atom_ipc_task_handles[2];
#endif
