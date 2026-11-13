# Firmware installation and building

## Match the hardware

Build19 targets Waveshare ESP32-S3-Touch-AMOLED-1.64 **V1.1**, 16 MB flash / 8 MB PSRAM, LCD CS46, HX711 DOUT3/SCK2 and an active-high GPIO1 RL interface. The [revision and wiring checks](WIRING.md) are part of choosing this image. This is not a stock Atom, Atom W, V1 display or other ESP32 image.

The release contains the exact application installed on 13 November 2026. Its device version is `1.4.0-atom65-decaid-oled`, build **19**. The GitHub release tag is `v1.4.0-atom65-build19`.

## Existing custom controller: Bluetooth update

Use `atom65-build19-install.zip` from the [release](https://github.com/Sabotage1/smart-grind-by-weight/releases/tag/v1.4.0-atom65-build19). Extract it, verify `SHA256SUMS`, use Python 3.10+ and install `bleak` on the updating computer and run:

```sh
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-ble.txt
python install_ble.py --inspect
python install_ble.py --install --idle-confirmed
```

Leave the motor stopped and the grinder on its main weight screen. Enable Bluetooth. Release Decaid’s grinder connection while the computer updates; pause only the Atom65 driver if automatic reconnection competes for the link, then restore it afterwards. Keep the computer beside the display with little metal between the antennae. The controller restarts during installation.

The updater is read-only unless `--install --idle-confirmed` is provided. It verifies the compatible source family, validates release hashes, transfers the full OTA patch, bounds the END-response wait across reboot, then reconnects and checks build19 and the dose service. It addresses coherent service-specific ATT handles because duplicate OTA-service UUIDs were observed after Bluetooth re-enabling. You can specify `--address` if more than one matching controller is nearby.

The existing NVS/calibration and partition map are retained. The updater does not send motor, tare, calibration or dose commands. It is for the custom GPIO1/Atom65 family; it intentionally rejects a stock upstream/factory image. Reconnect Decaid after it finishes.

## First installation: USB, controller isolated from grinder

Use the USB files only for first commissioning/recovery with the controller disconnected from the Atom harness. Do this before internal grinder power/control wiring. Install esptool 5.x and choose your actual serial port:

```sh
python -m pip install 'esptool>=5,<6'
python -m esptool --chip esp32s3 --port YOUR_PORT write-flash --flash-size 16MB \
  0x0 usb/bootloader.bin \
  0x8000 usb/partitions.bin \
  0xe000 usb/blank-8kb.bin \
  0x320000 firmware.bin
```

This follows the upstream v1.4.0 four-part USB layout with the custom V1.1 application. Writing `blank-8kb.bin` resets OTA selection; this is **not** the routine update method for an existing installation. No whole-chip erase is needed. The USB bootstrap package has been assembled and checked against the partition layout; a new blank-controller USB installation was not physically retested for this community release. The installed build19 was delivered through Bluetooth.

The layout includes NVS at 0x9000, OTA metadata at 0xe000, a factory slot at 0x20000, ota_0 at 0x320000 and ota_1 at 0x620000, with 3 MB application slots and a 2 MB patch region. Do not guess an application offset from a generic ESP32 tutorial.

After first flash, tare/calibrate on USB alone and verify known masses before proceeding with the [wiring stages](WIRING.md).

## Controls added in this fork

| Menu/feature | Behavior |
|---|---|
| Bluetooth → Enabled | Manual radio on/off |
| Bluetooth → Startup | Enable radio when the grinder boots |
| Bluetooth → Auto-off | Off by default: keep advertising available indefinitely while powered. On: legacy 5-minute boot / 30-minute disconnected timeout. Connected clients never expire |
| Grind Settings → Automation → Auto select | Off/SINGLE/DOUBLE/CUSTOM at boot and idle screen wake; saved separately from the current profile |
| OLED pixel shift | Automatic; no menu switch. Up to two pixels every minute on stable idle screens, paused during touch/grinding/OTA |
| Decaid dose | Valid weight-mode request selects/opens CUSTOM and wakes the display, including an unchanged weight. New intent takes priority over the saved wake default |

The first wake gesture is consumed when Auto select is enabled, preventing it from also pressing Grind. Active operations cannot be interrupted by automatic profile selection. Cup auto-start is forced off; start grinding locally.

## Build from source

Install PlatformIO, then from the repository root:

```sh
python -m pip install platformio
pio run -e atom-v11-gpio1-motor-test
```

The default environment also selects this Atom configuration. Keep `-DATOM_GPIO1_MOTOR_TEST=1` and the IPC task-stack linker wrapper. The environment name is historical; it is the production configuration used in this owner's conversion. The `atom-v11-bench-usb-log` environment disables motor output for scale-only work.

The build scripts generate local Git/date metadata and increment `.build_number`. For subsequent local numbering, initialize that file to `19` before building; the next local build is 20. The release’s original metadata and source hashes are under `release/atom65-build19/source-metadata`. A rebuild is a source/feature check, not a claim of bit-identical timestamped binary reproduction.
