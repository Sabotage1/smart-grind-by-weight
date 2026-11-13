#pragma once
#include "dose_protocol.h"
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// Cross-task mailbox: BLE callbacks only enqueue; the UI task owns profile writes.
class AtomDoseSync {
    struct Request {
        atom_dose::Command command;
        uint32_t generation;
        uint32_t received;
        bool valid;
    };
    struct Reply { atom_dose::Status status; uint32_t generation; };
    QueueHandle_t requests_ = nullptr;
    QueueHandle_t replies_ = nullptr;
    QueueHandle_t snapshots_ = nullptr;
    std::atomic<uint32_t> generation_{0};
    std::atomic<bool> connected_{false};
    atom_dose::Status last_; // BLE task/callback side; snapshots arrive through a queue.
public:
    void init() {
        requests_ = xQueueCreate(1, sizeof(Request));
        replies_ = xQueueCreate(4, sizeof(Reply));
        snapshots_ = xQueueCreate(1, sizeof(atom_dose::Status));
    }
    bool available() const { return requests_ && replies_ && snapshots_; }
    void connected(bool value) {
        connected_.store(false);
        generation_.fetch_add(1);
        if (requests_) xQueueReset(requests_);
        if (replies_) xQueueReset(replies_);
        connected_.store(value);
    }
    void receive(const uint8_t* bytes, size_t count, uint32_t now) {
        if (!available() || !connected_.load()) return;
        Request r{};
        r.valid = atom_dose::decode(bytes, count, r.command);
        r.generation = generation_.load(); r.received = now;
        // Queue depth one prevents a backlog of doses being applied later.
        // A full queue is left unchanged; the sender times out and must retry explicitly.
        xQueueSend(requests_, &r, 0);
    }
    template<class Apply>
    bool process(atom_dose::Status status, uint32_t now, Apply apply) {
        if (!available()) return false;
        bool changed = false;
        Request r{};
        if (xQueueReceive(requests_, &r, 0) == pdPASS && connected_.load() && r.generation == generation_.load()) {
            status.sequence = r.command.sequence;
            status.result = r.valid ? atom_dose::validate(r.command, status, now - r.received) : atom_dose::invalid;
            if (status.result == atom_dose::applied && connected_.load() && r.generation == generation_.load()) {
                apply(r.command.dose / 10.0f);
                status.dose = r.command.dose; status.slot = 2;
                changed = true;
            }
            Reply reply{status, r.generation};
            xQueueSend(replies_, &reply, 0);
        }
        status.result = atom_dose::snapshot; status.sequence = 0;
        xQueueOverwrite(snapshots_, &status);
        return changed;
    }
    bool next(atom_dose::Status& status) {
        if (!available()) return false;
        atom_dose::Status fresh;
        if (xQueuePeek(snapshots_, &fresh, 0) == pdPASS) last_ = fresh;
        Reply r;
        while (xQueueReceive(replies_, &r, 0) == pdPASS) {
            if (r.generation == generation_.load() && connected_.load()) { status = r.status; return true; }
        }
        status = last_; return false;
    }
};
