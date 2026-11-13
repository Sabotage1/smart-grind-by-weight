#pragma once

#include <Arduino.h>
#include <cmath>
#include "../config/constants.h"
#include "../hardware/WeightSensor.h"

#if HW_MOTOR_RELAY_PIN >= 0
#error "USB scale logging is limited to the motor-disabled bench build"
#endif

// Called on the low-priority Arduino loop, not the ADC sampling task.
// Read existing samples only: no ADC clocking, tare, calibration or display-filter updates.
inline void bench_usb_telemetry(WeightSensor* sensor) {
    static uint32_t last_ms = 0;
    const uint32_t now = millis();
    if (now - last_ms < 1000) return;
    last_ms = now;
    if (!sensor || !Serial || sensor->has_hardware_fault() ||
        sensor->get_sample_count() < 2 || sensor->is_tare_in_progress()) return;

    const int32_t raw = sensor->get_raw_adc_instant();
    const int32_t smooth = sensor->get_raw_filter()->get_raw_high_latency();
    const int32_t tare = sensor->get_zero_offset();
    const float factor = sensor->get_calibration_factor();
    if (!std::isfinite(factor) || std::fabs(factor) < 1e-6f) return;
    const int32_t sd = sensor->get_standard_deviation_adc(500);
    char line[224];
    const int len = snprintf(line, sizeof(line),
        "ATOM_SAMPLE,%lu,%ld,%ld,%ld,%.6f,%.6f,%.6f,%ld\n",
        static_cast<unsigned long>(now), static_cast<long>(raw),
        static_cast<long>(smooth), static_cast<long>(tare), factor,
        static_cast<double>((raw - tare) / factor),
        static_cast<double>((smooth - tare) / factor), static_cast<long>(sd));
    // Drop a telemetry record if the host isn't draining USB; never wait for space.
    if (len > 0 && len < static_cast<int>(sizeof(line)) && Serial.availableForWrite() >= len) {
        Serial.write(reinterpret_cast<const uint8_t*>(line), len);
    }
}
