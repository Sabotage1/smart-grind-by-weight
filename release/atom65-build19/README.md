# Atom65 build19 installation bundle

Exact installed firmware for Waveshare ESP32-S3 Touch AMOLED1.64 V1.1, 16 MB flash / 8 MB PSRAM, GPIO1 active-high motor interface, HX711 DOUT3/SCK2.

Read the full wiring and installation guide before use:
https://github.com/Sabotage1/smart-grind-by-weight/blob/atom65/docs/atom65/FIRMWARE.md

Source and licenses:
https://github.com/Sabotage1/smart-grind-by-weight/tree/atom65

Verify SHA256SUMS after extraction (macOS: shasum -a 256 -c SHA256SUMS; Linux: sha256sum -c SHA256SUMS). Firmware is GPL-3.0-or-later. Hardware is CERN-OHL-S-2.0. The separately bundled Decaid plugin is MIT with its license inside that ZIP.

## Bluetooth update from a compatible custom GPIO1 installation

Requires Python 3.10+ on the updating computer. Enable Bluetooth, stop the motor and leave the grinder on the main weight screen. Release the Decaid connection first. Keep the computer beside the display. After creating/activating a Python environment:

    python -m pip install -r requirements-ble.txt
    python install_ble.py --inspect
    python install_ble.py --install --idle-confirmed

Inspection is read-only. Installation restarts the controller and verifies build19 after reconnecting. No remote motor/tare/calibration/dose command is sent. This updater rejects an unsupported source family. The local commissioning JSON includes the device address; keep it private.

## First USB installation

Use only with the controller disconnected from all grinder power/control wiring. See the online guide for the four explicit offsets and hardware commissioning sequence. Do not use the raw application alone with a generic ESP32 offset. USB first-install files were assembled/checked, but a blank-controller first flash was not physically repeated for this release.

The bundled STL/STEP ZIP and per-profile Decaid driver are also offered as separate release downloads. Original firmware metadata and exact source hashes are in source-metadata/. Rebuilds generate new Git/date/build metadata; they are not byte-identical release binaries.
