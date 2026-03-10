#pragma once

#include <stdint.h>

/**
 * Boot the U2702A using HCD (Host Controller Driver) directly.
 *
 * Bypasses ESP-IDF's USB Host enumeration, which fails because the boot-mode
 * firmware (PID 0x2818) has an invalid config descriptor.
 *
 * Flow:
 *   1. Init USB PHY + HCD
 *   2. Wait for device connection
 *   3. Port reset, open control pipe
 *   4. Send 6 vendor control transfers
 *   5. Tear down HCD + PHY
 *   6. Device re-enumerates as PID 0x2918 (operational)
 *
 * After this returns, the caller should install USB Host library normally.
 *
 * @param timeout_ms  Max time to wait for device connection (ms)
 * @return 0 on success, -1 on error
 */
int u2702a_hcd_boot(uint32_t timeout_ms);
