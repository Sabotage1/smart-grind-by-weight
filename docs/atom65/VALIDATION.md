# Validation record and limits

## Installed-device evidence — 13 November 2026

- Firmware build19 (`1.4.0-atom65-decaid-oled`) installed over full Bluetooth OTA from build18.
- Source and post-reboot build/version were read over BLE; the dose service returned READY, weight mode and the retained 12.5g target.
- Decaid 0.9.1 loaded the per-profile driver 0.1.0, auto-load enabled, and connected the native grinder. Status notifications remained healthy beyond its watchdog interval.
- A live 12.5g acknowledgement and CUSTOM selection were observed after a profile rule was enabled. No remote motor-start command exists in the dose protocol/driver.
- Existing maximum-dose, scale/skin preferences and profile choices were retained through the update. Device addresses, home-network IPs, profile names and raw settings are omitted from the public report.
- Earlier owner-reported build12 result: Atom 5V power and RL start/stop worked; 12.5g target delivered 12.4g on one weighed grind. This is not a measured repeatability dataset.

## Automated checks

The host tests compile actual firmware method bodies with controlled I/O and address/undefined-behavior sanitizers where applicable. They cover pixel flush/touch mapping, dose framing/mailbox/expiry/disconnect fencing, CUSTOM-only updates and preference preservation, boot/wake/default priority and touch guarding, motor/RMT and IPC fixes, OTA motor stop, and Bluetooth policy persistence/expiry/rollover/UI text. The per-profile driver suite covers opt-in rules, identity, invalid doses, acknowledgements, storage, busy/timeout, unload and independent devices; its C++ checks use this fork’s protocol/controller.

A separate targeted Decaid QuickJS fixture previously exercised native BLE Grinder/workflow/HTTP/KV integration. This was not a complete upstream test suite. The release firmware and full OTA package were reconstructed/compared byte-for-byte and hashed. `release/atom65-build19/verification.json` records public artifact details.

The five provided STL alternatives are watertight positive-volume single bodies; editable STEP solids and the CAD validation report are included. Panel v0.43, adapter v0.9 and cradle v0.8 are distinct part revisions. The overall owner-confirmed working conversion does not separately validate every newest exported refinement or all Atom variants.

## Still requires the builder’s checks

Electrical isolation and supply margin on the actual board, latest-print fit/retention, installed OLED/touch appearance and burn-in behavior, prolonged disconnected radio behavior, power/crash/sensor-fault motor-off behavior on the assembled grinder, and repeatable delivered-dose accuracy require physical acceptance. Pixel shift reduces static placement but does not guarantee prevention of OLED burn-in.

The USB first-install bundle is checked against the upstream layout and toolchain files. Its first flash onto an entirely blank controller was not physically repeated for this release; the observed build19 installation used Bluetooth.

## Driver 0.1.1 — 13 November 2026

Adds the profile-settings API for WorkFlow Skin 0.4.5’s **Profiles → Grinder dose** editor. The 34 driver/protocol tests cover inactive-recipe editing without workflow changes or dose transmission, rule identity validation, invalid weight rejection and preserving device pause state. The owner reported testing the 0.1.1 driver/skin integration successfully. This is an owner report, not an independently repeated hardware test. Controller firmware remains build19; the original build19 installation evidence and 0.1.0 archive remain historical snapshots.
