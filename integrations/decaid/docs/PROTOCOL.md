# Atom65 dose-only protocol v1

Custom protocol for the ESP32-S3 Atom65 conversion. Unrelated to Eureka factory
firmware and the existing GBW OTA, diagnostic, or data-export services.

| Attribute | UUID | Properties |
| --- | --- | --- |
| Service | `5e5d6500-3f45-4b8c-9a65-28b4858d23d4` | Advertised |
| Command | `5e5d6501-3f45-4b8c-9a65-28b4858d23d4` | Write with response |
| Status | `5e5d6502-3f45-4b8c-9a65-28b4858d23d4` | Read, notify, CCCD |

Advertising carries the service UUID; the scan response carries `GrindByWeight`.
Each packet fits within the default 20-byte ATT application payload. Integers
are unsigned little-endian. Weight units are decigrams (0.1 g).

## SET_DOSE command (8 bytes)

| Offset | Value |
| --- | --- |
| 0 | Magic `A6` |
| 1 | Protocol version `01` |
| 2 | Opcode `01` (the only opcode) |
| 3–4 | Nonzero sequence, 1–65535 |
| 5–6 | Requested target in decigrams |
| 7 | XOR of bytes 0–6 |

An ATT write response means the request was enqueued, not applied. Application
confirmation uses a status packet with the same sequence and nonzero result.
Malformed packets, unknown opcodes, and zero sequences do not
change settings. The mailbox holds one request; extra writes can time out rather
than accumulating delayed targets. The driver serializes commands.

## Status (15 bytes)

| Offset | Value |
| --- | --- |
| 0–1 | `A6 01` |
| 2 | Result: 0 snapshot, 1 applied, 2 busy, 3 invalid, 4 wrong mode, 5 expired |
| 3 | Flags: bit 0 ready, bit 1 active grind, bit 2 OTA, bit 3 other busy UI |
| 4–5 | Sequence; 0 on periodic snapshots |
| 6–7 | Current target in decigrams |
| 8 | Current preset: 0 SINGLE, 1 DOUBLE, 2 CUSTOM |
| 9 | Mode: 0 weight, 1 time |
| 10–11 | Minimum supported dose (50 = 5 g) |
| 12–13 | Maximum supported dose (10000 = 1000 g) |
| 14 | XOR of bytes 0–13 |

Status is updated about twice per second and immediately for command responses.
The driver disconnects a silent status stream after four seconds.

## Application rules

Only the UI task mutates preset data and LVGL; callbacks enqueue a request.
Application requires READY, no active grind, no OTA, and weight mode. The
controller checks the current state again when consuming the queue; it rejects
requests older than 750 ms. Successful updates select CUSTOM and persist its
weight/selection without changing SINGLE/DOUBLE weights or grind mode.

Disconnect/reconnect invalidates queued commands and response generations. Busy
requests are consumed and rejected immediately, never retained until idle. A
packet cannot trigger motor start, motor test, tare, calibration, or OTA. The
existing independent grinding/scale interlocks remain in force.

The application checksum detects malformed frames; it is not authentication.
The controller retains the existing BLE access model.
