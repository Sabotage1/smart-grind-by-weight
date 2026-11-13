#include "grinder.h"
#include "../controllers/grind_events.h"
#include "../config/constants.h"
#include <driver/gpio.h>
#if DEBUG_ENABLE_LOADCELL_MOCK
#include "mock_hx711_driver.h"
#endif

bool IRAM_ATTR Grinder::on_rmt_done(rmt_channel_handle_t,
                                  const rmt_tx_done_event_data_t*, void* context) {
    static_cast<Grinder*>(context)->rmt_transfer_done_.store(true, std::memory_order_relaxed);
    return false;
}

void Grinder::init(int pin) {
    motor_pin = pin;
    initialized = false;
    grinding = false;
    pulse_active = false;
    rmt_initialized = false;
    rmt_transfer_done_.store(true, std::memory_order_relaxed);
    current_encoder = nullptr;
    rmt_channel = nullptr;
    motor_start_time = 0;

    // Initialize background indicator
    background_active = false;
    ui_event_callback = nullptr;

#if DEBUG_ENABLE_LOADCELL_MOCK
    initialized = true;
    return;
#endif
    
    // Standalone bench build: leave all motor GPIOs untouched.
    // V1.1 uses GPIO18 for the touch controller interrupt.
    if (motor_pin < 0) {
        initialized = true;
        Serial.println("[BENCH] Motor output disabled; GPIO18 reserved for touch");
        return;
    }

    // Preload the output latch LOW before enabling the pad or peripheral.
    gpio_set_level(static_cast<gpio_num_t>(motor_pin), 0);
    gpio_set_direction(static_cast<gpio_num_t>(motor_pin), GPIO_MODE_INPUT_OUTPUT);
    gpio_pullup_dis(static_cast<gpio_num_t>(motor_pin));
    gpio_pulldown_en(static_cast<gpio_num_t>(motor_pin));

    // Initialize RMT for all motor control (both continuous and pulse)
    rmt_tx_channel_config_t tx_chan_config = {
        .gpio_num = (gpio_num_t)motor_pin,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 1000000, // 1MHz resolution = 1µs per tick
        .mem_block_symbols = 64,
        .trans_queue_depth = 4,
    };
    tx_chan_config.flags.init_level = 0;
    tx_chan_config.flags.io_loop_back = 1; // Permit pad-level diagnostic readback.
    
    if (rmt_new_tx_channel(&tx_chan_config, &rmt_channel) == ESP_OK) {
        rmt_tx_event_callbacks_t callbacks = {};
        callbacks.on_trans_done = &Grinder::on_rmt_done;
        if (rmt_tx_register_event_callbacks(rmt_channel, &callbacks, this) == ESP_OK &&
            rmt_enable(rmt_channel) == ESP_OK) {
            rmt_initialized = true;
            initialized = true;
            Serial.printf("[MOTOR] GPIO%d initialized LOW; active HIGH\n", motor_pin);
        } else {
            rmt_del_channel(rmt_channel);
            rmt_channel = nullptr;
        }
    }
}

void Grinder::start() {
#if DEBUG_ENABLE_LOADCELL_MOCK
    if (!initialized) return;
    MockHX711Driver::notify_grinder_start();
    pulse_active = false;
    grinding = true;
    motor_start_time = millis();
    emit_background_change(true);
    return;
#endif
    if (!initialized || !rmt_initialized) return;

    // Terminate any previous transfer before retiring its encoder/payload.
    stop();
    if (!initialized || !rmt_initialized) return;

    // Reset any active pulse state when using continuous mode
    pulse_active = false;
    motor_start_time = millis();
    
    // Clean up any existing encoder
    if (current_encoder) {
        rmt_del_encoder(current_encoder);
        current_encoder = nullptr;
    }
    
    // Create copy encoder for raw symbol data
    rmt_copy_encoder_config_t encoder_config = {};
    
    if (rmt_new_copy_encoder(&encoder_config, &current_encoder) != ESP_OK) {
        return;
    }
    
    // Use RMT infinite loop for continuous grinding
    continuous_data[0] = {};
    continuous_data[0].duration0 = 32767; // Maximum 15-bit duration per symbol (~32ms at 1MHz)
    continuous_data[0].level0 = 1; // HIGH
    continuous_data[0].duration1 = 32767;
    continuous_data[0].level1 = 1; // No EOF/LOW slot inside the hardware loop.
    
    rmt_transmit_config_t tx_config = {
        .loop_count = -1, // Infinite loop
    };
    tx_config.flags.eot_level = 0;
    
    rmt_transfer_done_.store(false, std::memory_order_relaxed);
    if (rmt_transmit(rmt_channel, current_encoder, continuous_data, sizeof(continuous_data), &tx_config) != ESP_OK) {
        stop();
        return;
    }
    grinding = true;
    emit_background_change(true);
}

void Grinder::stop() {
#if DEBUG_ENABLE_LOADCELL_MOCK
    if (!initialized) return;
    MockHX711Driver::notify_grinder_stop();
    grinding = false;
    pulse_active = false;
    emit_background_change(false);
    return;
#endif
    if (!initialized || !rmt_initialized) return;
    
    // Stop RMT transmission (works for both infinite loop and finite pulses)
    rmt_disable(rmt_channel);
    rmt_transfer_done_.store(true, std::memory_order_relaxed);
    gpio_set_level(static_cast<gpio_num_t>(motor_pin), 0);
    if (rmt_enable(rmt_channel) != ESP_OK) {
        initialized = false;
        rmt_initialized = false;
    }
    
    // Clean up current encoder
    if (current_encoder) {
        rmt_del_encoder(current_encoder);
        current_encoder = nullptr;
    }
    
    grinding = false;
    pulse_active = false;
    emit_background_change(false);
}

void Grinder::start_pulse_rmt(uint32_t duration_ms) {
#if DEBUG_ENABLE_LOADCELL_MOCK
    if (!initialized) return;
    MockHX711Driver::notify_pulse(duration_ms);
    pulse_active = true;
    grinding = true;
    motor_start_time = millis();
    emit_background_change(true);
    return;
#endif
    if (!initialized || !rmt_initialized) return;

    stop();
    if (!initialized || !rmt_initialized || duration_ms == 0) return;

    motor_start_time = millis();

    // Clean up any existing encoder
    if (current_encoder) {
        rmt_del_encoder(current_encoder);
        current_encoder = nullptr;
    }
    
    // Create copy encoder for raw symbol data
    rmt_copy_encoder_config_t encoder_config = {};
    
    if (rmt_new_copy_encoder(&encoder_config, &current_encoder) != ESP_OK) {
        return;
    }
    
    // A finite, non-looping waveform gives the requested HIGH duration exactly.
    // All current call sites request <= 1000ms; reject longer-than-2s requests.
    if (duration_ms > 2000) return;
    uint32_t remaining_us = duration_ms * 1000;
    size_t count = 0;
    while (remaining_us > 0) {
        auto& symbol = pulse_symbols[count++];
        symbol = {};
        const uint32_t first = remaining_us > 32767 ? 32767 : remaining_us;
        symbol.duration0 = first;
        symbol.level0 = 1;
        remaining_us -= first;
        if (remaining_us > 0) {
            const uint32_t second = remaining_us > 32767 ? 32767 : remaining_us;
            symbol.duration1 = second;
            symbol.level1 = 1;
            remaining_us -= second;
        } else {
            symbol.duration1 = 1;
            symbol.level1 = 0;
        }
    }

    rmt_transmit_config_t tx_config = {};
    tx_config.flags.eot_level = 0;
    rmt_transfer_done_.store(false, std::memory_order_relaxed);
    if (rmt_transmit(rmt_channel, current_encoder, pulse_symbols,
                     count * sizeof(rmt_symbol_word_t), &tx_config) != ESP_OK) {
        stop();
        return;
    }
    pulse_active = true;
    grinding = true;
    emit_background_change(true);
}

bool Grinder::is_pulse_complete() {
#if DEBUG_ENABLE_LOADCELL_MOCK
    if (!pulse_active) return true;
    if (!MockHX711Driver::is_pulse_active()) {
        pulse_active = false;
        grinding = false;
        emit_background_change(false);
        return true;
    }
    return false;
#endif
    if (!pulse_active) return true;
    
    // A queued transfer may not have raised the pad yet; LOW alone is not completion.
    if (rmt_transfer_done_.load(std::memory_order_relaxed)) {
        pulse_active = false;
        grinding = false;
        emit_background_change(false);
        return true;
    }
    
    return false;
}

bool Grinder::is_motor_settled() const {
    // Return true if sufficient time has passed since motor start
    if (motor_start_time == 0) {
        return false;  // Motor has never started
    }
    return (millis() - motor_start_time) >= HW_GRINDER_SETTLING_TIME_MS;
}

void Grinder::set_ui_event_callback(const std::function<void(const GrindEventData&)>& callback) {
    ui_event_callback = callback;
}

void Grinder::emit_background_change(bool active) {
    if (background_active == active) {
        return; // No change
    }
    
    background_active = active;
    
    if (ui_event_callback) {
        // Properly initialize all required fields to prevent null pointer crashes
        GrindEventData event_data = {};
        event_data.event = UIGrindEvent::BACKGROUND_CHANGE;
        event_data.phase = GrindPhase::IDLE;  // Safe default
        event_data.current_weight = 0.0f;
        event_data.progress_percent = 0;
        event_data.phase_display_text = "BACKGROUND";  // Safe string for logging
        event_data.show_taring_text = false;
        event_data.background_active = active;
        
        ui_event_callback(event_data);
        
        LOG_BLE("[Grinder] Background change: %s\n", active ? "ACTIVE" : "INACTIVE");
    }
}
