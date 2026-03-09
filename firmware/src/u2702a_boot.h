#pragma once

#include "usb/usb_host.h"

/**
 * Send the 6-step vendor boot sequence to the U2702A.
 *
 * The device must be in boot mode (PID 0x2818). After a successful boot,
 * the device disconnects and re-enumerates as PID 0x2918 (operational).
 *
 * @param client_handle  USB Host client handle (for submitting control transfers)
 * @param dev_handle     Open USB device handle
 * @return 0 on success, -1 on failure
 */
int u2702a_boot(usb_host_client_handle_t client_handle,
                usb_device_handle_t dev_handle);
