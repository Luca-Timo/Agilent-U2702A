#include "u2702a_boot.h"

#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "usb/usb_host.h"

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

/* Synchronous wrapper around async control transfer */
static SemaphoreHandle_t s_xfer_sem = NULL;
static int s_xfer_result = 0;

static void ctrl_xfer_cb(usb_transfer_t *transfer)
{
    s_xfer_result = (transfer->status == USB_TRANSFER_STATUS_COMPLETED) ? 0 : -1;
    if (transfer->status != USB_TRANSFER_STATUS_COMPLETED) {
        ESP_LOGE(TAG, "Control transfer failed, status=%d", transfer->status);
    }
    xSemaphoreGive(s_xfer_sem);
}

int u2702a_boot(usb_host_client_handle_t client_handle,
                usb_device_handle_t dev_handle)
{
    ESP_LOGI(TAG, "Starting boot sequence (6 steps)");

    /* Allocate transfer buffer */
    usb_transfer_t *xfer = NULL;
    esp_err_t err = usb_host_transfer_alloc(64 + USB_SETUP_PACKET_SIZE, 0, &xfer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to allocate transfer: %s", esp_err_to_name(err));
        return -1;
    }

    s_xfer_sem = xSemaphoreCreateBinary();
    if (!s_xfer_sem) {
        usb_host_transfer_free(xfer);
        return -1;
    }

    int result = 0;

    for (int i = 0; i < NUM_BOOT_STEPS; i++) {
        const boot_step_t *step = &BOOT_SEQUENCE[i];

        /* Build setup packet (8 bytes at start of transfer data buffer) */
        usb_setup_packet_t *setup = (usb_setup_packet_t *)xfer->data_buffer;
        setup->bmRequestType = step->bmRequestType;
        setup->bRequest = step->bRequest;
        setup->wValue = step->wValue;
        setup->wIndex = step->wIndex;
        setup->wLength = step->wLength;

        /* For write transfers, copy payload after setup packet */
        if (step->is_write) {
            memcpy(xfer->data_buffer + USB_SETUP_PACKET_SIZE, BOOT_CMD, step->wLength);
        }

        xfer->device_handle = dev_handle;
        xfer->bEndpointAddress = 0;  /* Control EP */
        xfer->callback = ctrl_xfer_cb;
        xfer->context = NULL;
        xfer->num_bytes = USB_SETUP_PACKET_SIZE + step->wLength;

        /* Submit and wait */
        err = usb_host_transfer_submit_control(client_handle, xfer);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Step %d: submit failed: %s", i + 1, esp_err_to_name(err));
            result = -1;
            break;
        }

        /* Wait up to 5 seconds for completion */
        if (xSemaphoreTake(s_xfer_sem, pdMS_TO_TICKS(5000)) != pdTRUE) {
            ESP_LOGE(TAG, "Step %d: timeout", i + 1);
            result = -1;
            break;
        }

        if (s_xfer_result != 0) {
            ESP_LOGE(TAG, "Step %d: transfer error", i + 1);
            result = -1;
            break;
        }

        /* Log response data for read transfers */
        if (!step->is_write) {
            int actual = xfer->actual_num_bytes - USB_SETUP_PACKET_SIZE;
            if (actual > 0) {
                char hex[64] = {0};
                uint8_t *data = xfer->data_buffer + USB_SETUP_PACKET_SIZE;
                for (int j = 0; j < actual && j < 20; j++) {
                    sprintf(hex + j * 3, "%02X ", data[j]);
                }
                ESP_LOGI(TAG, "Step %d/6: READ  wIdx=0x%04X -> %s(%d bytes)",
                         i + 1, step->wIndex, hex, actual);
            }
        } else {
            ESP_LOGI(TAG, "Step %d/6: WRITE wIdx=0x%04X -> OK", i + 1, step->wIndex);
        }
    }

    vSemaphoreDelete(s_xfer_sem);
    s_xfer_sem = NULL;
    usb_host_transfer_free(xfer);

    if (result == 0) {
        ESP_LOGI(TAG, "Boot sequence complete! Device will re-enumerate.");
    }
    return result;
}
