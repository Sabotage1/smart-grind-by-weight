#pragma once
#include <cstddef>
#include <cstdint>

// Atom65 dose-only protocol v1. All words are little endian; units are 0.1 g.
// No opcode in this protocol can start/stop the motor, tare, calibrate, or OTA.
namespace atom_dose {
constexpr uint8_t magic = 0xa6;
constexpr uint8_t version = 1;
constexpr size_t command_size = 8;
constexpr size_t status_size = 15;
enum Result : uint8_t { snapshot = 0, applied = 1, busy = 2, invalid = 3, wrong_mode = 4, expired = 5 };
enum Flags : uint8_t { ready = 1, grinding = 2, updating = 4, editing = 8 };
struct Command { uint16_t sequence = 0; uint16_t dose = 0; };
struct Status {
    Result result = snapshot;
    uint8_t flags = 0;
    uint16_t sequence = 0;
    uint16_t dose = 0;
    uint8_t slot = 2;
    uint8_t mode = 0;
    uint16_t minimum = 50;
    uint16_t maximum = 10000;
};
inline uint16_t word(const uint8_t* p) { return p[0] | (uint16_t(p[1]) << 8); }
inline void put(uint8_t* p, uint16_t n) { p[0] = n & 255; p[1] = n >> 8; }
inline uint8_t checksum(const uint8_t* p, size_t n) {
    uint8_t value = 0; while (n--) value ^= *p++; return value;
}
inline bool decode(const uint8_t* p, size_t n, Command& out) {
    if (n != command_size || p[0] != magic || p[1] != version || p[2] != 1 ||
        checksum(p, command_size - 1) != p[command_size - 1]) return false;
    out.sequence = word(p + 3); out.dose = word(p + 5);
    return out.sequence != 0;
}
inline Result validate(const Command& command, const Status& status, uint32_t age) {
    if (command.sequence == 0 || command.dose < status.minimum || command.dose > status.maximum) return invalid;
    if (age > 750) return expired;
    if (status.mode != 0) return wrong_mode;
    if (!(status.flags & ready) || (status.flags & (grinding | updating | editing))) return busy;
    return applied;
}
inline void encode(const Status& s, uint8_t* p) {
    p[0] = magic; p[1] = version; p[2] = s.result; p[3] = s.flags;
    put(p + 4, s.sequence); put(p + 6, s.dose); p[8] = s.slot; p[9] = s.mode;
    put(p + 10, s.minimum); put(p + 12, s.maximum); p[14] = checksum(p, 14);
}
}
