# Decaid: choose exactly which profiles change the grinder

Install `atom65-profile-sync-0.1.0.zip` from the [release](https://github.com/Sabotage1/smart-grind-by-weight/releases/tag/v1.4.0-atom65-build19). This is the **per-profile opt-in** driver `atom65.reaplugin`, verified on Decaid 0.9.1. Do not also load another Atom65 dose-sync driver for the same physical grinder.

1. In Decaid → Plugins → Install plugin → ZIP file, install the ZIP. Load it and enable auto-load.
2. On the grinder, enable Bluetooth. Leave Startup on and Auto-off off for continuous reconnection availability while powered.
3. Use Decaid’s normal device discovery and connect **GrindByWeight as a grinder**. Keep your espresso scale as the primary scale; this driver does not register a scale.
4. Select one of the espresso profiles that should control the grinder.
5. Open Decaid → Device Management → Atom65 → **Device settings**. Choose the behavior below, then **Save profile choice**.
6. Repeat only for the other profiles that should control the grinder. All unconfigured profiles send nothing and retain the grinder’s last selected setting/weight.

| When selecting this profile | What is sent |
|---|---|
| **Leave grinder unchanged** (default) | Nothing, including on reconnect |
| **Use Decaid's dose** | The current workflow’s coffee dose, `context.targetDoseWeight` |
| **Use a fixed grind weight** | Your saved weight for this profile and physical grinder |

For example, enable Profile A for the Decaid dose and Profile B for a fixed 12.5g; leave all other profiles unconfigured. Espresso yield (`targetYield` / a brew profile’s `target_weight`) is never substituted for coffee dose. If the workflow does not define a dose, supply one or use a fixed weight.

A valid dose opens **CUSTOM** on the grinder, even if the weight already matches. Start the motor locally after checking the displayed target. Unchanged workflow events do not repeatedly overwrite a local/default selection. Active grinding, calibration, edit/confirmation, OTA and time mode block dose writes. The settings page reports confirmation/errors; after a rejected request return to the ready weight screen and use **Sync now**.

Rules persist in plugin storage per physical grinder and profile content. Renaming/changing a recipe requires a new opt-in. The global **Maximum synced dose** defaults to 40g and can be reduced; supported bounds are further limited by the controller. These software bounds are not a load-cell capacity rating.

The settings page shows the current profile, workflow dose, grinder target, saved choices and acknowledgement state. Saving choices requires the plugin to finish loading storage. Missing, malformed or unconfirmed doses do not silently appear as success.

**No skin change is needed** to use Device settings. A skin can add a shortcut via the plugin’s declared settings surface; exposing choices inside a skin’s profile editor is an optional UI enhancement. Decaid remains responsible for BLE discovery, recovery and the primary espresso scale. The driver exposes no remote motor start/stop, burr-gap, RPM, tare, calibration or OTA controls.

[Driver source and API details](../../integrations/decaid/README.md).
