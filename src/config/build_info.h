#pragma once

#include <cstdio>
#include "../../include/git_info.h"

// Build information - BUILD_FIRMWARE_VERSION is automatically updated by release scripts
#ifdef ATOM_GPIO1_MOTOR_TEST
#define BUILD_FIRMWARE_VERSION "1.4.0-atom65-decaid-oled"
#elif defined(ATOM_BENCH_USB_TELEMETRY)
#define BUILD_FIRMWARE_VERSION "1.4.0-atom-v11-bench-usb-log"
#else
#define BUILD_FIRMWARE_VERSION "1.4.0-atom-v11-bench"                                          // Firmware version string (updated by release automation)
#endif
// BUILD_NUMBER is now defined in git_info.h as an auto-incrementing integer
#define BUILD_DATE __DATE__                                                // Compiler-provided build date
#define BUILD_TIME __TIME__                                                // Compiler-provided build time

inline const char* get_git_commit_id() {
    return GIT_COMMIT_ID;
}

inline const char* get_git_branch() {
    return GIT_BRANCH;
}

inline const char* get_build_datetime() {
    static char datetime[32];
    snprintf(datetime, sizeof(datetime), "%s %s", __DATE__, __TIME__);
    return datetime;
}
