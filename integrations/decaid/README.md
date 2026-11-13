# Atom65 Profile Sync for Decaid

Version 0.1.1 — dose-only Bluetooth driver for the custom ESP32-S3 Atom65 GBW conversion.
This does not support an unmodified Eureka Atom65.

## Profile choices

Each profile starts with **Leave grinder unchanged**. Choosing a different profile
does not change the grinder unless you explicitly enabled that profile for that
physical Atom65. In the driver's Device settings, choose:

| Choice | Result |
| --- | --- |
| Leave grinder unchanged | Sends nothing, including on reconnect. |
| Use Decaid's dose | Sends `workflow.context.targetDoseWeight` when this profile is selected; follows dose edits while selected. |
| Use a fixed grind weight | Sends your chosen weight whenever this profile is selected, regardless of Decaid's dose. |

The same rule applies on reconnect and plugin reload: only the currently selected,
explicitly enabled profile can sync. Pending unsent work is canceled on selection
of an unconfigured profile, disabling sync, disconnect, or unload. An update
already transmitted/accepted cannot be recalled; changing to an excluded profile
leaves that last accepted target unchanged. No previous dose is restored.

Profile choices survive app restarts. Rules are scoped to the physical grinder,
using a SHA-256 digest of the profile's canonical content, including its title.
Same-title recipes remain distinct. Renaming or changing recipe execution requires
a new opt-in; changing notes, author, or format version does not. Workflow IDs,
brew yield, temperature overrides outside the profile, coffee changes, and JSON
object key order do not accidentally select another rule. No profile library or
espresso-machine settings are modified.

## Install

1. Use a Decaid version with BLE Grinder bindings, `events.workflow`, plugin HTTP
   endpoints, and device settings surfaces. This implementation is verified against
   Decaid 0.9.1 on the installed controller.
2. Install this fork's Atom65 build19 firmware first. See [firmware setup](../../docs/atom65/FIRMWARE.md). Existing GPIO1 build12 has no dose service.
3. In Decaid, open **Plugins → cogwheel → Install plugin → ZIP file**, and choose
   the release’s `atom65-profile-sync-0.1.1.zip` (or build it locally with `npm run build`).
   If using the REST source installer, send `manifest.json` and `plugin.js` to
   `PUT /api/v1/plugins/atom65.reaplugin/source`, then enable/load the plugin.
4. Enable Bluetooth on the grinder. Scan in Decaid and connect **GrindByWeight**
   as your preferred connected Grinder. The matcher requires the new dose service;
   stock/old firmware is intentionally not claimed by this driver.
5. Select an espresso profile in Decaid, then open **Device Management → Atom65 →
   Device settings** (or the Atom65 skin button on skins supporting plugin surfaces).
6. Select a sync mode and save. Repeat for the profiles that should change dose.
   Leave other profiles at the default. You can pause syncing per Atom65 or via
   the global **Enable profile dose syncing** setting.

The settings page shows the selected profile, Decaid dose, grinder target,
confirmation/error status, and saved enabled profiles. With several Atom65s,
open settings from the specific device rather than the skin shortcut.

### WorkFlow Skin integration (0.1.1)

In WorkFlow Skin 0.4.5, open **Profiles → Grinder dose** next to any recipe.
Choose **Leave grinder unchanged**, **Use Brew dose**, or **Use a fixed grind weight**,
then **Save grinder choice**. This uses the same driver-owned rules as Device settings;
existing choices and per-device pauses are preserved. Editing an inactive recipe
does not select it or send its dose. Selecting an enabled recipe applies its rule.
Install the updated plugin ZIP as well as the skin ZIP; no controller firmware
change is needed when upgrading from the working Profile Sync driver.

The new `POST profile-settings?deviceId=<encoded device id>` endpoint accepts
`{profile:<Decaid profile JSON>}` to read a rule. To save it, add
`choice:{profileKey:<returned key>,mode:"leave"|"workflow"|"fixed",weight:<grams>}`.
Weight is required only for fixed mode. The driver verifies the canonical recipe
key, validates the dose, and acknowledges storage before returning success.
This endpoint never changes the workflow or overrides a device's paused state.

## Grinder behavior

- Dose changes update and select **CUSTOM**, preserving SINGLE and DOUBLE weights.
  CUSTOM's last synced dose and selection are saved on the controller. Excluded
  profiles leave its existing preset/weight untouched.
- The controller must be idle and in **weight mode**. Build19 accepts safe ready/menu/completion/timeout screens and opens CUSTOM. It rejects active grinding, calibration, profile editing, confirmation dialogs, auto-tune and OTA. Rejected requests are not
  silently deferred. Return to the ready weight screen and tap **Sync now**.
- Only numeric doses in 0.1 g steps are accepted. The driver defaults to 5–40 g;
  **Maximum synced dose** can adjust the upper bound within the controller's
  advertised 5–1000 g range. Invalid/missing doses are rejected; yield and
  `profile.target_weight` are never used as dose fallbacks.
- The driver waits for a matching sequence-numbered application acknowledgment,
  not merely a successful Bluetooth write. A missing confirmation is shown as
  uncertain and is not automatically retried.
- There is no remote motor start/stop, burr-gap, RPM, tare, calibration, or OTA
  control in this driver. Start grinding on the controller. Its existing GPIO1,
  stale-scale stop, forced-off auto-start, and OTA motor-stop behavior are retained.

## Development

No npm dependencies are needed. Node 20+, Python 3, and a C++17 compiler are used
for the behavioral suite. `npm test` exercises the real plugin sources and
compiles the firmware protocol/mailbox against a fake RTOS/backend. `npm run build`
bundles the QuickJS script and creates a validated ZIP with a SHA-256 checksum.
The separate firmware build uses the already installed PlatformIO environment.

The [public validation record](../../docs/atom65/VALIDATION.md) distinguishes automated checks and physical evidence. Version 0.1.1 passed 34 driver/protocol tests. On 13 November 2026 the owner reported testing the 0.1.1 driver and skin integration successfully. This release keeps the prepared runtime code unchanged and updates the packaged documentation. Firmware build19 remains unchanged.

Download [driver 0.1.1](https://github.com/Sabotage1/smart-grind-by-weight/releases/tag/atom65-profile-sync-v0.1.1). The original build19 release retains its historical 0.1.0 package; use the separate 0.1.1 release for the latest driver.

The real Decaid QuickJS integration harness is `test/host_harness.dart`; copy it
to `test/plugins/atom65_external_test.dart` in a Decaid source checkout and run
it with `ATOM65_PLUGIN_DIR` set to this project's `atom65.reaplugin` directory.
It exercises the host's actual manifest parser, BLE Grinder lifecycle, HTTP
dispatcher, workflow event delivery, KV acknowledgments, and four-binding quota.
The local validation used Flutter 3.44.1 / Dart 3.12.1 with only the disposable
checkout's SDK floor relaxed from 3.13 to 3.12; its runtime source was unchanged.
The upstream checkout's missing optional bundled assets emitted asset warnings.
This is not a full upstream Flutter suite or a production tablet test.

## Upstream contracts

- [Decaid plugin API](https://github.com/decentespresso/decaid/blob/main/doc/Plugins.md)
- [Workflow serialization](https://github.com/decentespresso/decaid/blob/main/lib/src/models/data/workflow.dart)
- [Grinder model](https://github.com/decentespresso/decaid/blob/main/lib/src/models/device/grinder_device.dart)
- [Original GBW firmware](https://github.com/jaapp/smart-grind-by-weight)

The custom dose service/protocol is documented in [docs/PROTOCOL.md](docs/PROTOCOL.md) and is not
an upstream Eureka or Smart Grind-by-Weight protocol. New plugin code is MIT;
the companion firmware retains its existing upstream license.
