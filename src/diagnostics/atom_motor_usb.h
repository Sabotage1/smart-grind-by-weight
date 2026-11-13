#pragma once

#include <Arduino.h>
#include <cstring>
#include <driver/gpio.h>
#include "../config/constants.h"
#include "../hardware/grinder.h"
#include "../system/atom_ipc_stack.h"

#if HW_MOTOR_RELAY_PIN != 1
#error "Atom motor commissioning diagnostics require GPIO1"
#endif

inline void atom_motor_status(Grinder* motor, bool ble_enabled) {
    Serial.printf("ATOM_MOTOR_STATUS version=%s pin=1 level=%d initialized=%d auto_start=OFF build=%d ble=%s ipc0_stack=%lu ipc1_stack=%lu ipc0_free=%u ipc1_free=%u\n",
                  BUILD_FIRMWARE_VERSION, gpio_get_level(GPIO_NUM_1),
                  motor && motor->is_initialized(), BUILD_NUMBER, ble_enabled ? "ON" : "OFF",
                  static_cast<unsigned long>(atom_ipc_stack_bytes[0]),
                  static_cast<unsigned long>(atom_ipc_stack_bytes[1]),
                  atom_ipc_task_handles[0] ? static_cast<unsigned>(uxTaskGetStackHighWaterMark(atom_ipc_task_handles[0])) : 0,
                  atom_ipc_task_handles[1] ? static_cast<unsigned>(uxTaskGetStackHighWaterMark(atom_ipc_task_handles[1])) : 0);
}

// Explicit USB command only; never run a pulse automatically at boot.
// Used with the Atom disconnected to check the local GPIO path before wiring RL.
inline void atom_motor_usb(Grinder* motor, bool controller_active, bool ota_active, bool ble_enabled) {
    static char command[32];
    static size_t used = 0;
    static bool overflow = false;
    while (Serial.available()) {
        const char ch = static_cast<char>(Serial.read());
        if (ch == '\r') continue;
        if (ch != '\n') {
            if (used < sizeof(command) - 1 && !overflow) command[used++] = ch;
            else overflow = true;
            continue;
        }
        command[used] = '\0';
        used = 0;
        if (overflow) {
            overflow = false;
            Serial.println("ATOM_MOTOR_REJECT oversized command");
            continue;
        }
        if (strcmp(command, "ATOM_MOTOR_STATUS") == 0) {
            atom_motor_status(motor, ble_enabled);
        } else if (strcmp(command, "ATOM_MOTOR_CHECK") == 0) {
            if (!motor || !motor->is_initialized() || controller_active || ota_active || motor->is_grinding()) {
                Serial.println("ATOM_MOTOR_REJECT busy or uninitialized");
                continue;
            }
            motor->stop();
            const int idle = gpio_get_level(GPIO_NUM_1);
            const uint32_t started = millis();
            motor->start_pulse_rmt(100);
            delay(20);
            const int pulse_high = gpio_get_level(GPIO_NUM_1);
            while (!motor->is_pulse_complete() && millis() - started < 300) delay(1);
            const uint32_t pulse_elapsed_ms = millis() - started;
            const bool pulse_finished = motor->is_pulse_complete();
            const int pulse_low = gpio_get_level(GPIO_NUM_1);
            motor->stop();
            // Check the continuous-grind start/cancel path as well, with no motor attached.
            motor->start();
            delay(20);
            const int run_high = gpio_get_level(GPIO_NUM_1);
            motor->stop();
            delay(2);
            const int stopped_low = gpio_get_level(GPIO_NUM_1);
            Serial.printf("ATOM_MOTOR_CHECK idle=%d pulse_high=%d pulse_done=%d pulse_low=%d pulse_ms=%lu run_high=%d stopped=%d\n",
                          idle, pulse_high, pulse_finished, pulse_low,
                          static_cast<unsigned long>(pulse_elapsed_ms), run_high, stopped_low);
        }
    }
}
