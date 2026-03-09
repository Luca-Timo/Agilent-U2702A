#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "usb/usb_host.h"

/* Agilent/Keysight VID and U2702A PIDs */
#define VID_AGILENT         0x0957
#define PID_BOOT            0x2818
#define PID_OPERATIONAL     0x2918

/* USBTMC class codes (USB_CLASS_APP_SPEC already in usb_types_ch9.h) */
#define USB_SUBCLASS_USBTMC 0x03
#define USB_PROTO_USB488    0x01

/* Device state */
typedef enum {
    DEV_STATE_IDLE = 0,
    DEV_STATE_CONNECTED,
    DEV_STATE_BOOT_MODE,
    DEV_STATE_BOOTING,
    DEV_STATE_OPERATIONAL,
    DEV_STATE_READY,
    DEV_STATE_ERROR,
} dev_state_t;

/* Endpoint info extracted from config descriptor */
typedef struct {
    uint8_t bulk_out_ep;    /* e.g. 0x01 */
    uint8_t bulk_in_ep;     /* e.g. 0x82 */
    uint16_t bulk_out_mps;  /* max packet size */
    uint16_t bulk_in_mps;
    uint8_t iface_num;
} usbtmc_endpoints_t;

/* Current device handle and state (shared with other modules) */
extern usb_device_handle_t g_dev_handle;
extern dev_state_t g_dev_state;
extern usbtmc_endpoints_t g_endpoints;

/** Get the USB Host client handle (for USBTMC init). */
usb_host_client_handle_t usb_host_get_client_handle(void);

/**
 * Start the USB Host library daemon task.
 * Runs usb_host_lib_handle_events() in a loop.
 */
void usb_host_daemon_task(void *arg);

/**
 * USB client task — registers a client, handles device connect/disconnect,
 * triggers boot sequence or claims USBTMC interface.
 */
void usb_client_task(void *arg);
