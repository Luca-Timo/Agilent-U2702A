#pragma once

#include <stdint.h>
#include <stddef.h>
#include "usb/usb_host.h"

/* USBTMC Message IDs */
#define USBTMC_MSGID_DEV_DEP_MSG_OUT   1
#define USBTMC_MSGID_REQUEST_DEV_DEP_MSG_IN 2
#define USBTMC_MSGID_DEV_DEP_MSG_IN    2

/* USBTMC header size */
#define USBTMC_HEADER_SIZE 12

/**
 * Initialize the USBTMC layer.
 * Must be called after USB Host has claimed the USBTMC interface.
 *
 * @param client_handle  USB Host client handle
 * @param dev_handle     Open USB device handle
 * @param bulk_out_ep    Bulk OUT endpoint address
 * @param bulk_in_ep     Bulk IN endpoint address
 * @param bulk_out_mps   Bulk OUT max packet size
 * @param bulk_in_mps    Bulk IN max packet size
 * @return 0 on success
 */
int usbtmc_init(usb_host_client_handle_t client_handle,
                usb_device_handle_t dev_handle,
                uint8_t bulk_out_ep, uint8_t bulk_in_ep,
                uint16_t bulk_out_mps, uint16_t bulk_in_mps);

/**
 * Send a SCPI command to the device (DEV_DEP_MSG_OUT).
 *
 * @param cmd   SCPI command string (null-terminated)
 * @param len   Length of command (excluding null terminator)
 * @return 0 on success, -1 on error
 */
int usbtmc_write(const char *cmd, size_t len);

/**
 * Read a response from the device.
 * Sends REQUEST_DEV_DEP_MSG_IN, then reads bulk-IN.
 *
 * @param buf       Buffer to receive response data
 * @param max_len   Maximum bytes to read
 * @return Number of bytes read, or -1 on error
 */
int usbtmc_read(uint8_t *buf, size_t max_len);

/**
 * Send a SCPI query and read the response.
 * Convenience wrapper: usbtmc_write() + usbtmc_read().
 *
 * @param cmd           SCPI command (null-terminated)
 * @param response_buf  Buffer for response
 * @param max_len       Max response length
 * @return Number of response bytes, or -1 on error
 */
int usbtmc_query(const char *cmd, uint8_t *response_buf, size_t max_len);
