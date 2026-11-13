# Atom65 Grind by Weight

[![Atom65 validation](https://github.com/Sabotage1/smart-grind-by-weight/actions/workflows/atom65.yml/badge.svg?branch=atom65)](https://github.com/Sabotage1/smart-grind-by-weight/actions/workflows/atom65.yml)

A community fork of [jaapp/smart-grind-by-weight](https://github.com/jaapp/smart-grind-by-weight) for the **Eureka Atom Speciality 65**, using a **Waveshare ESP32-S3-Touch-AMOLED-1.64 V1.1**, HX711 and T70 1 kg load cell.

The owner’s 220 V unit, purchased in 2022, runs **firmware build19**. This branch includes the installed firmware source, printable panel/cradle parts, a per-profile Decaid driver, and the build guide. Other Atom models and board revisions need their own electrical and mechanical checks.

**Start here:** [owner’s parts list and shopping links](docs/atom65/PARTS.md) · [parts and assembly](3d_files/atom65/README.md) · [wiring and board photos](docs/atom65/WIRING.md) · [firmware installation](docs/atom65/FIRMWARE.md) · [Decaid setup](docs/atom65/DECAID.md) · [test evidence and limits](docs/atom65/VALIDATION.md).

## Downloads

[Atom65 build19 release](https://github.com/Sabotage1/smart-grind-by-weight/releases/tag/v1.4.0-atom65-build19)

| Download | Purpose |
|---|---|
| `atom65-build19-install.zip` | Exact installed application, full Bluetooth OTA patch, USB bootstrap files, portable updater and checksums |
| `ATOM65_PRINT_AND_ASSEMBLY_v0_43.zip` | Front panel v0.43, fixed adapter v0.9 and moving 73 mm cradle v0.8; STL + editable STEP; optional two-piece panel |
| `atom65-profile-sync-0.1.0.zip` | Per-profile opt-in Decaid grinder driver |

Use the Atom65 files in this branch. Its default PlatformIO environment is `atom-v11-gpio1-motor-test` (the historical environment name; it is the installed GPIO1 build). On V1.1, **GPIO18 belongs to touch** and **LCD CS is GPIO46**. GPIO1 controls the verified RL interface in this build.

## What the firmware adds

- Weighing and local grind-by-weight through the original Atom relay/power board.
- Early GPIO1 LOW/off initialization, forced-off cup auto-start, fresh-scale checks and motor stop before OTA work.
- Automatic OLED pixel shift: nine positions, up to two pixels, once per minute on stable idle screens; touch mapping follows the image.
- Saved **Auto select**: Off/SINGLE/DOUBLE/CUSTOM at boot or idle dim-screen wake, with wake-touch protection.
- Acknowledged Bluetooth coffee-dose updates that select/open CUSTOM without starting the motor.
- **Menu → Bluetooth → Auto-off** defaults Off, keeping Bluetooth available for Decaid reconnection while the grinder is powered. Startup controls boot activation.
- A separate Decaid driver lets each profile choose **Leave grinder unchanged** (default), **Use Decaid’s dose**, or **Use a fixed grind weight**. Enable only the profiles that should change the grinder.

## Suggested build order

1. Identify the exact grinder/power board and V1.1 display. Read the [wiring scope and checks](docs/atom65/WIRING.md).
2. Print one panel, one fixed adapter and one moving cradle. Trial-fit before wiring. [Assembly and screws](3d_files/atom65/README.md).
3. Flash and test the scale on USB alone, with the grinder harness disconnected. Tare/calibrate using a known mass.
4. With all power removed, assemble the verified low-voltage harness, common ground and capacitor. GPIO1 → RL is specific to the checked interface. Keep the factory display’s output disconnected.
5. Test power, scale and then the one-second local motor test. Check the displayed target before a local test grind.
6. Connect Decaid as a **grinder** and enable one chosen profile. Leave other profiles unchanged.

## Status and provenance

On 13 November 2026, build19 was installed over Bluetooth, verified after reboot and reconnected to Decaid 0.9.1. A live **12.5 g → CUSTOM** synchronization was confirmed. Earlier, the owner reported **12.4 g delivered for a 12.5 g target** on build12. This is one reported dose, not a repeatability study. CAD v0.43 is geometrically checked; each newest exported refinement has not been independently reprinted and fit-confirmed. [Detailed evidence](docs/atom65/VALIDATION.md).

The upstream `main` and existing contribution branches remain separate. [Original project README](README.upstream.md). This branch is a hardware-specific community build, not an upstream universal Atom firmware release.

Firmware is GPL-3.0-or-later; hardware follows the upstream CERN-OHL-S-2.0 terms; the standalone Decaid driver is MIT. See [license notes](docs/atom65/LICENSES.md) and the retained [upstream notice](LICENSE).
