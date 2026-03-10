/**
 * U2702A boot sequence using HCD (Host Controller Driver) directly.
 *
 * The boot-mode firmware (PID 0x2818) has an invalid USB config descriptor,
 * which causes ESP-IDF's standard USB Host enumeration to fail. We bypass
 * enumeration entirely by using the low-level HCD API to open a control pipe
 * and send the 6 vendor boot transfers directly.
 */

#include "u2702a_boot.h"

#include <string.h>
#include "esp_log.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "hal/usb_phy_types.h"
#include "esp_private/usb_phy.h"
#include "hcd.h"
#include "usb_private.h"

static const char *TAG = "u2702a_boot";

/* Boot command payload for step 6 (write) */
static const uint8_t BOOT_CMD[8] = {
    0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x08, 0x01
};

/* Boot sequence definition */
typedef struct {
    uint8_t  bmRequestType;
    uint8_t  bRequest;
    uint16_t wValue;
    uint16_t wIndex;
    uint16_t wLength;
    bool     is_write;
} boot_step_t;

static const boot_step_t BOOT_SEQUENCE[] = {
    { 0xC0, 0x0C, 0x0000, 0x047E,  1, false },  /* Read 1 byte  */
    { 0xC0, 0x0C, 0x0000, 0x047D,  6, false },  /* Read 6 bytes */
    { 0xC0, 0x0C, 0x0000, 0x0484,  5, false },  /* Read 5 bytes */
    { 0xC0, 0x0C, 0x0000, 0x0472, 12, false },  /* Read 12 bytes */
    { 0xC0, 0x0C, 0x0000, 0x047A,  1, false },  /* Read 1 byte  */
    { 0x40, 0x0C, 0x0000, 0x0475,  8, true  },  /* Write 8 bytes */
};
#define NUM_BOOT_STEPS 6

/* Queue sizes */
#define PORT_EVENT_QUEUE_LEN  5
#define PIPE_EVENT_QUEUE_LEN  5

/* EP0 descriptor for control pipe */
static const usb_ep_desc_t ep0_desc = {
    .bLength = sizeof(usb_ep_desc_t),
    .bDescriptorType = USB_B_DESCRIPTOR_TYPE_ENDPOINT,
    .bEndpointAddress = 0x00,
    .bmAttributes = USB_TRANSFER_TYPE_CTRL,
    .wMaxPacketSize = 64,  /* Full Speed default MPS */
    .bInterval = 0,
};

/* URB data buffer size: setup packet (8) + max data (12) */
#define URB_DATA_SIZE  64

/* USB PHY handle */
static usb_phy_handle_t s_phy_handle = NULL;

/* ------------------------------------------------------------------ */
/* HCD callbacks                                                      */
/* ------------------------------------------------------------------ */

typedef struct {
    hcd_port_handle_t port_hdl;
    hcd_port_event_t event;
} port_event_msg_t;

typedef struct {
    hcd_pipe_handle_t pipe_hdl;
    hcd_pipe_event_t event;
} pipe_event_msg_t;

static bool port_callback(hcd_port_handle_t port_hdl, hcd_port_event_t event,
                           void *user_arg, bool in_isr)
{
    QueueHandle_t queue = (QueueHandle_t)user_arg;
    port_event_msg_t msg = { .port_hdl = port_hdl, .event = event };
    BaseType_t woken = pdFALSE;
    if (in_isr) {
        xQueueSendFromISR(queue, &msg, &woken);
    } else {
        xQueueSend(queue, &msg, 0);
    }
    return (woken == pdTRUE);
}

static bool pipe_callback(hcd_pipe_handle_t pipe_hdl, hcd_pipe_event_t event,
                           void *user_arg, bool in_isr)
{
    QueueHandle_t queue = (QueueHandle_t)user_arg;
    pipe_event_msg_t msg = { .pipe_hdl = pipe_hdl, .event = event };
    BaseType_t woken = pdFALSE;
    if (in_isr) {
        xQueueSendFromISR(queue, &msg, &woken);
    } else {
        xQueueSend(queue, &msg, 0);
    }
    return (woken == pdTRUE);
}

/* ------------------------------------------------------------------ */
/* URB allocation (simplified from ESP-IDF test helpers)              */
/* ------------------------------------------------------------------ */

static urb_t *alloc_urb(size_t data_size)
{
    urb_t *urb = heap_caps_calloc(1, sizeof(urb_t), MALLOC_CAP_DEFAULT);
    if (!urb) return NULL;

    void *buf = heap_caps_calloc(1, data_size,
                                  MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!buf) {
        heap_caps_free(urb);
        return NULL;
    }

    /* Cast to dummy to set const fields */
    usb_transfer_dummy_t *dummy = (usb_transfer_dummy_t *)&urb->transfer;
    dummy->data_buffer = buf;
    dummy->data_buffer_size = data_size;
    dummy->num_isoc_packets = 0;
    return urb;
}

static void free_urb(urb_t *urb)
{
    if (urb) {
        heap_caps_free(urb->transfer.data_buffer);
        heap_caps_free(urb);
    }
}

/* ------------------------------------------------------------------ */
/* Send one control transfer and wait for completion                  */
/* ------------------------------------------------------------------ */

static int send_ctrl_xfer(hcd_pipe_handle_t pipe, QueueHandle_t pipe_queue,
                          urb_t *urb, const boot_step_t *step, int step_num)
{
    /* Build setup packet */
    usb_setup_packet_t *setup = (usb_setup_packet_t *)urb->transfer.data_buffer;
    setup->bmRequestType = step->bmRequestType;
    setup->bRequest = step->bRequest;
    setup->wValue = step->wValue;
    setup->wIndex = step->wIndex;
    setup->wLength = step->wLength;

    /* For write transfers, copy payload after setup packet */
    if (step->is_write) {
        memcpy(urb->transfer.data_buffer + sizeof(usb_setup_packet_t),
               BOOT_CMD, step->wLength);
        urb->transfer.num_bytes = sizeof(usb_setup_packet_t) + step->wLength;
    } else {
        /* For IN (read) transfers, use full buffer size. The DWC OTG
         * controller reads FIFO data in word-aligned chunks, so the
         * parsed length may exceed wLength. URB_DATA_SIZE provides
         * enough headroom to avoid the _buffer_parse_ctrl assertion. */
        urb->transfer.num_bytes = URB_DATA_SIZE;
    }

    /* Submit URB */
    esp_err_t err = hcd_urb_enqueue(pipe, urb);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step %d: enqueue failed: %s", step_num, esp_err_to_name(err));
        return -1;
    }

    /* Wait for pipe event */
    pipe_event_msg_t msg;
    if (xQueueReceive(pipe_queue, &msg, pdMS_TO_TICKS(5000)) != pdTRUE) {
        ESP_LOGE(TAG, "Step %d: timeout waiting for pipe event", step_num);
        return -1;
    }

    if (msg.event != HCD_PIPE_EVENT_URB_DONE) {
        ESP_LOGE(TAG, "Step %d: pipe error event %d", step_num, msg.event);
        return -1;
    }

    /* Dequeue completed URB */
    urb_t *done = hcd_urb_dequeue(pipe);
    if (!done) {
        ESP_LOGE(TAG, "Step %d: dequeue returned NULL", step_num);
        return -1;
    }

    if (done->transfer.status != USB_TRANSFER_STATUS_COMPLETED) {
        ESP_LOGE(TAG, "Step %d: transfer status %d", step_num, done->transfer.status);
        return -1;
    }

    /* Log result */
    if (!step->is_write) {
        int actual = done->transfer.actual_num_bytes - sizeof(usb_setup_packet_t);
        if (actual > 0) {
            char hex[64] = {0};
            uint8_t *data = done->transfer.data_buffer + sizeof(usb_setup_packet_t);
            for (int j = 0; j < actual && j < 20; j++) {
                sprintf(hex + j * 3, "%02X ", data[j]);
            }
            ESP_LOGI(TAG, "Step %d/6: READ  wIdx=0x%04X -> %s(%d bytes)",
                     step_num, step->wIndex, hex, actual);
        }
    } else {
        ESP_LOGI(TAG, "Step %d/6: WRITE wIdx=0x%04X -> OK", step_num, step->wIndex);
    }

    return 0;
}

/* ------------------------------------------------------------------ */
/* Main boot function                                                 */
/* ------------------------------------------------------------------ */

int u2702a_hcd_boot(uint32_t timeout_ms)
{
    esp_err_t err;
    int result = -1;

    QueueHandle_t port_queue = NULL;
    QueueHandle_t pipe_queue = NULL;
    hcd_port_handle_t port_hdl = NULL;
    hcd_pipe_handle_t pipe_hdl = NULL;
    urb_t *urb = NULL;

    ESP_LOGI(TAG, "=== HCD Boot Phase ===");

    /* --- Step 1: Initialize USB PHY --- */
    usb_phy_config_t phy_config = {
        .controller = USB_PHY_CTRL_OTG,
        .target = USB_PHY_TARGET_INT,
        .otg_mode = USB_OTG_MODE_HOST,
        .otg_speed = USB_PHY_SPEED_UNDEFINED,  /* Determined by device */
    };
    err = usb_new_phy(&phy_config, &s_phy_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "PHY init failed: %s", esp_err_to_name(err));
        return -1;
    }
    ESP_LOGI(TAG, "USB PHY initialized");

    /* --- Step 2: Install HCD --- */
    hcd_config_t hcd_config = {
        .intr_flags = ESP_INTR_FLAG_LEVEL1,
        .peripheral_map = BIT0,  /* ESP32-S3 has one USB-OTG peripheral at index 0 */
    };
    err = hcd_install(&hcd_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HCD install failed: %s", esp_err_to_name(err));
        goto cleanup_phy;
    }

    /* --- Step 3: Initialize port --- */
    port_queue = xQueueCreate(PORT_EVENT_QUEUE_LEN, sizeof(port_event_msg_t));
    if (!port_queue) goto cleanup_hcd;

    hcd_port_config_t port_config = {
        .callback = port_callback,
        .callback_arg = (void *)port_queue,
        .context = (void *)port_queue,
    };
    err = hcd_port_init(0, &port_config, &port_hdl);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Port init failed: %s", esp_err_to_name(err));
        goto cleanup_hcd;
    }

    /* --- Step 4: Power on and wait for connection --- */
    err = hcd_port_command(port_hdl, HCD_PORT_CMD_POWER_ON);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Port power on failed: %s", esp_err_to_name(err));
        goto cleanup_port;
    }
    ESP_LOGI(TAG, "Port powered on, waiting for device...");

    /* Wait for connection event */
    port_event_msg_t port_msg;
    TickType_t wait_ticks = (timeout_ms == 0) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);
    if (xQueueReceive(port_queue, &port_msg, wait_ticks) != pdTRUE) {
        ESP_LOGW(TAG, "No device connected within timeout");
        goto cleanup_port;
    }
    if (port_msg.event != HCD_PORT_EVENT_CONNECTION) {
        ESP_LOGE(TAG, "Unexpected port event: %d", port_msg.event);
        goto cleanup_port;
    }

    /* Handle the connection event */
    hcd_port_handle_event(port_hdl);
    ESP_LOGI(TAG, "Device connected!");

    /* --- Step 5: Reset the port --- */
    err = hcd_port_command(port_hdl, HCD_PORT_CMD_RESET);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Port reset failed: %s", esp_err_to_name(err));
        goto cleanup_port;
    }
    ESP_LOGI(TAG, "Port reset complete");

    /* Get device speed */
    usb_speed_t dev_speed;
    hcd_port_get_speed(port_hdl, &dev_speed);
    ESP_LOGI(TAG, "Device speed: %s", dev_speed == USB_SPEED_FULL ? "Full" : "Low");

    /* Allow device to stabilize after reset (USB spec tRSTRECOV) */
    vTaskDelay(pdMS_TO_TICKS(100));

    /* --- Step 6: Open control pipe (EP0, address 0) --- */
    pipe_queue = xQueueCreate(PIPE_EVENT_QUEUE_LEN, sizeof(pipe_event_msg_t));
    if (!pipe_queue) goto cleanup_port;

    hcd_pipe_config_t pipe_config = {
        .callback = pipe_callback,
        .callback_arg = (void *)pipe_queue,
        .context = (void *)pipe_queue,
        .ep_desc = &ep0_desc,
        .dev_addr = 0,  /* Default address — device hasn't been assigned one */
        .dev_speed = dev_speed,
    };
    err = hcd_pipe_alloc(port_hdl, &pipe_config, &pipe_hdl);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Pipe alloc failed: %s", esp_err_to_name(err));
        goto cleanup_port;
    }
    ESP_LOGI(TAG, "Control pipe opened");

    /* --- Step 7: Minimal enumeration (GET_DESCRIPTOR + SET_ADDRESS) --- */
    urb = alloc_urb(URB_DATA_SIZE);
    if (!urb) {
        ESP_LOGE(TAG, "URB alloc failed");
        goto cleanup_pipe;
    }

    /* 7a: GET_DESCRIPTOR(device, 8 bytes) at address 0
     * We only need 8 bytes to read bMaxPacketSize0 (offset 7).
     * With pipe MPS=64, a short packet (<64) ends the transfer,
     * so requesting 8 bytes is safe regardless of actual MPS. */
    {
        usb_setup_packet_t *setup = (usb_setup_packet_t *)urb->transfer.data_buffer;
        setup->bmRequestType = 0x80;   /* Device-to-Host | Standard | Device */
        setup->bRequest      = 0x06;   /* GET_DESCRIPTOR */
        setup->wValue        = 0x0100; /* Type: Device (1), Index: 0 */
        setup->wIndex        = 0;
        setup->wLength       = 8;

        urb->transfer.num_bytes = sizeof(usb_setup_packet_t) + 8;

        err = hcd_urb_enqueue(pipe_hdl, urb);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "GET_DESCRIPTOR enqueue failed: %s", esp_err_to_name(err));
            goto cleanup_urb;
        }

        pipe_event_msg_t pmsg;
        if (xQueueReceive(pipe_queue, &pmsg, pdMS_TO_TICKS(5000)) != pdTRUE) {
            ESP_LOGE(TAG, "GET_DESCRIPTOR timeout");
            goto cleanup_urb;
        }

        if (pmsg.event != HCD_PIPE_EVENT_URB_DONE) {
            ESP_LOGE(TAG, "GET_DESCRIPTOR pipe error event: %d", pmsg.event);
            hcd_urb_dequeue(pipe_hdl);
            goto cleanup_urb;
        }

        urb_t *done = hcd_urb_dequeue(pipe_hdl);
        if (!done || done->transfer.status != USB_TRANSFER_STATUS_COMPLETED) {
            ESP_LOGE(TAG, "GET_DESCRIPTOR transfer status: %d",
                     done ? done->transfer.status : -1);
            goto cleanup_urb;
        }

        uint8_t *data = done->transfer.data_buffer + sizeof(usb_setup_packet_t);
        int actual = done->transfer.actual_num_bytes - sizeof(usb_setup_packet_t);
        if (actual >= 8) {
            uint8_t mps = data[7];
            ESP_LOGI(TAG, "Device bMaxPacketSize0=%d", mps);
            if (mps != 64 && mps > 0) {
                hcd_pipe_update_mps(pipe_hdl, mps);
            }
        }
        if (actual >= 4) {
            uint16_t vid = (actual >= 10) ? (data[8] | (data[9] << 8)) : 0;
            uint16_t pid = (actual >= 12) ? (data[10] | (data[11] << 8)) : 0;
            if (vid || pid) {
                ESP_LOGI(TAG, "Device VID=0x%04X PID=0x%04X", vid, pid);
            }
        }
    }

    /* 7b: SET_ADDRESS(1) — device must be at a proper address
     * before it will respond to vendor-specific requests */
    {
        usb_setup_packet_t *setup = (usb_setup_packet_t *)urb->transfer.data_buffer;
        setup->bmRequestType = 0x00;  /* Host-to-Device | Standard | Device */
        setup->bRequest      = 0x05;  /* SET_ADDRESS */
        setup->wValue        = 1;     /* New address: 1 */
        setup->wIndex        = 0;
        setup->wLength       = 0;

        urb->transfer.num_bytes = sizeof(usb_setup_packet_t); /* No data stage */

        err = hcd_urb_enqueue(pipe_hdl, urb);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "SET_ADDRESS enqueue failed: %s", esp_err_to_name(err));
            goto cleanup_urb;
        }

        pipe_event_msg_t pmsg;
        if (xQueueReceive(pipe_queue, &pmsg, pdMS_TO_TICKS(5000)) != pdTRUE) {
            ESP_LOGE(TAG, "SET_ADDRESS timeout");
            goto cleanup_urb;
        }

        if (pmsg.event != HCD_PIPE_EVENT_URB_DONE) {
            ESP_LOGE(TAG, "SET_ADDRESS pipe error event: %d", pmsg.event);
            hcd_urb_dequeue(pipe_hdl);
            goto cleanup_urb;
        }

        urb_t *done = hcd_urb_dequeue(pipe_hdl);
        if (!done || done->transfer.status != USB_TRANSFER_STATUS_COMPLETED) {
            ESP_LOGE(TAG, "SET_ADDRESS transfer failed (status=%d)",
                     done ? done->transfer.status : -1);
            goto cleanup_urb;
        }

        /* Update pipe to target the new device address */
        hcd_pipe_update_dev_addr(pipe_hdl, 1);
        ESP_LOGI(TAG, "Device address set to 1");

        /* USB spec: host must wait ≥2ms after SET_ADDRESS */
        vTaskDelay(pdMS_TO_TICKS(5));
    }

    /* 7c: SET_CONFIGURATION(1) — device must be in Configured state
     * before it will respond to vendor-specific requests */
    {
        usb_setup_packet_t *setup = (usb_setup_packet_t *)urb->transfer.data_buffer;
        setup->bmRequestType = 0x00;  /* Host-to-Device | Standard | Device */
        setup->bRequest      = 0x09;  /* SET_CONFIGURATION */
        setup->wValue        = 1;     /* Configuration value 1 */
        setup->wIndex        = 0;
        setup->wLength       = 0;

        urb->transfer.num_bytes = sizeof(usb_setup_packet_t);

        err = hcd_urb_enqueue(pipe_hdl, urb);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "SET_CONFIGURATION enqueue failed: %s", esp_err_to_name(err));
            goto cleanup_urb;
        }

        pipe_event_msg_t pmsg;
        if (xQueueReceive(pipe_queue, &pmsg, pdMS_TO_TICKS(5000)) != pdTRUE) {
            ESP_LOGE(TAG, "SET_CONFIGURATION timeout");
            goto cleanup_urb;
        }

        if (pmsg.event != HCD_PIPE_EVENT_URB_DONE) {
            ESP_LOGE(TAG, "SET_CONFIGURATION pipe error event: %d", pmsg.event);
            hcd_urb_dequeue(pipe_hdl);
            goto cleanup_urb;
        }

        urb_t *done = hcd_urb_dequeue(pipe_hdl);
        if (!done || done->transfer.status != USB_TRANSFER_STATUS_COMPLETED) {
            ESP_LOGE(TAG, "SET_CONFIGURATION failed (status=%d)",
                     done ? done->transfer.status : -1);
            goto cleanup_urb;
        }

        ESP_LOGI(TAG, "Configuration 1 set");
    }

    /* --- Step 8: Send boot sequence --- */
    ESP_LOGI(TAG, "Sending boot sequence (6 steps)...");
    for (int i = 0; i < NUM_BOOT_STEPS; i++) {
        if (send_ctrl_xfer(pipe_hdl, pipe_queue, urb, &BOOT_SEQUENCE[i], i + 1) != 0) {
            ESP_LOGE(TAG, "Boot sequence failed at step %d", i + 1);
            goto cleanup_urb;
        }
    }

    ESP_LOGI(TAG, "Boot sequence complete! Device will re-enumerate as PID 0x2918.");
    result = 0;

    /* --- Cleanup --- */
cleanup_urb:
    /* HALT pipe first (required before FLUSH), then flush pending URBs */
    hcd_pipe_command(pipe_hdl, HCD_PIPE_CMD_HALT);
    hcd_pipe_command(pipe_hdl, HCD_PIPE_CMD_FLUSH);
    while (hcd_urb_dequeue(pipe_hdl) != NULL) { /* drain */ }
    free_urb(urb);
cleanup_pipe:
    hcd_pipe_free(pipe_hdl);
cleanup_port:
    /* Wait briefly for device to disconnect after boot command */
    if (result == 0) {
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    /* Drain any pending port events */
    {
        port_event_msg_t evt;
        while (xQueueReceive(port_queue, &evt, 0) == pdTRUE) {
            hcd_port_handle_event(port_hdl);
        }
    }

    /* Transition port to NOT_POWERED so deinit succeeds */
    {
        hcd_port_state_t state = hcd_port_get_state(port_hdl);
        ESP_LOGI(TAG, "Cleanup: port state = %d", state);

        if (state == HCD_PORT_STATE_ENABLED) {
            hcd_port_command(port_hdl, HCD_PORT_CMD_DISABLE);
            state = hcd_port_get_state(port_hdl);
        }
        if (state == HCD_PORT_STATE_DISABLED || state == HCD_PORT_STATE_DISCONNECTED) {
            hcd_port_command(port_hdl, HCD_PORT_CMD_POWER_OFF);
            state = hcd_port_get_state(port_hdl);
        }
        if (state == HCD_PORT_STATE_RECOVERY) {
            hcd_port_recover(port_hdl);
            state = hcd_port_get_state(port_hdl);
        }
        ESP_LOGI(TAG, "Cleanup: port state after teardown = %d", state);
    }

    err = hcd_port_deinit(port_hdl);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Port deinit failed: %s", esp_err_to_name(err));
    }

cleanup_hcd:
    err = hcd_uninstall();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "HCD uninstall failed: %s", esp_err_to_name(err));
    }

cleanup_phy:
    usb_del_phy(s_phy_handle);
    s_phy_handle = NULL;

    if (port_queue) vQueueDelete(port_queue);
    if (pipe_queue) vQueueDelete(pipe_queue);

    if (result == 0) {
        ESP_LOGI(TAG, "=== Boot Phase Complete ===");
    }
    return result;
}
