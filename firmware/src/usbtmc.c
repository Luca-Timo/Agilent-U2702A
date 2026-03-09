#include "usbtmc.h"

#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "usb/usb_host.h"

static const char *TAG = "usbtmc";

/* Transfer buffer size: 12-byte header + up to 4096 data + alignment */
#define XFER_BUF_SIZE 4096

/* Timeout for bulk transfers */
#define BULK_TIMEOUT_MS 5000

/* Internal state */
static usb_host_client_handle_t s_client = NULL;
static usb_device_handle_t s_dev = NULL;
static uint8_t s_ep_out = 0;
static uint8_t s_ep_in = 0;
static uint16_t s_mps_out = 0;
static uint16_t s_mps_in = 0;

static usb_transfer_t *s_xfer_out = NULL;
static usb_transfer_t *s_xfer_in = NULL;
static SemaphoreHandle_t s_xfer_sem = NULL;
static int s_xfer_status = 0;

/* bTag counter: 1-255, wrapping (skip 0) */
static uint8_t s_btag = 0;

static uint8_t next_btag(void)
{
    s_btag++;
    if (s_btag == 0) s_btag = 1;
    return s_btag;
}

/* Async callback for bulk transfers */
static void bulk_xfer_cb(usb_transfer_t *transfer)
{
    s_xfer_status = (transfer->status == USB_TRANSFER_STATUS_COMPLETED) ? 0 : -1;
    if (transfer->status != USB_TRANSFER_STATUS_COMPLETED) {
        ESP_LOGE(TAG, "Bulk transfer failed, status=%d", transfer->status);
    }
    xSemaphoreGive(s_xfer_sem);
}

/* ------------------------------------------------------------------ */
/* Init / cleanup                                                     */
/* ------------------------------------------------------------------ */

int usbtmc_init(usb_host_client_handle_t client_handle,
                usb_device_handle_t dev_handle,
                uint8_t bulk_out_ep, uint8_t bulk_in_ep,
                uint16_t bulk_out_mps, uint16_t bulk_in_mps)
{
    if (bulk_out_mps == 0 || bulk_in_mps == 0) {
        ESP_LOGE(TAG, "Invalid MPS (0) on bulk endpoint");
        return -1;
    }

    s_client = client_handle;
    s_dev = dev_handle;
    s_ep_out = bulk_out_ep;
    s_ep_in = bulk_in_ep;
    s_mps_out = bulk_out_mps;
    s_mps_in = bulk_in_mps;
    s_btag = 0;

    s_xfer_sem = xSemaphoreCreateBinary();
    if (!s_xfer_sem) return -1;

    /* Allocate transfer buffers */
    esp_err_t err;
    err = usb_host_transfer_alloc(XFER_BUF_SIZE, 0, &s_xfer_out);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to alloc OUT transfer");
        return -1;
    }

    err = usb_host_transfer_alloc(XFER_BUF_SIZE, 0, &s_xfer_in);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to alloc IN transfer");
        usb_host_transfer_free(s_xfer_out);
        return -1;
    }

    ESP_LOGI(TAG, "USBTMC initialized (OUT=0x%02X IN=0x%02X)", s_ep_out, s_ep_in);
    return 0;
}

/* ------------------------------------------------------------------ */
/* Build USBTMC headers                                               */
/* ------------------------------------------------------------------ */

static void build_dev_dep_msg_out(uint8_t *buf, uint8_t btag,
                                  uint32_t transfer_size, bool eom)
{
    memset(buf, 0, USBTMC_HEADER_SIZE);
    buf[0] = USBTMC_MSGID_DEV_DEP_MSG_OUT;
    buf[1] = btag;
    buf[2] = ~btag;
    buf[3] = 0;  /* reserved */
    /* TransferSize (little-endian 32-bit) */
    buf[4] = (transfer_size >>  0) & 0xFF;
    buf[5] = (transfer_size >>  8) & 0xFF;
    buf[6] = (transfer_size >> 16) & 0xFF;
    buf[7] = (transfer_size >> 24) & 0xFF;
    /* bmTransferAttributes: bit 0 = EOM */
    buf[8] = eom ? 0x01 : 0x00;
    buf[9] = 0;
    buf[10] = 0;
    buf[11] = 0;
}

static void build_request_dev_dep_msg_in(uint8_t *buf, uint8_t btag,
                                          uint32_t max_transfer_size)
{
    memset(buf, 0, USBTMC_HEADER_SIZE);
    buf[0] = USBTMC_MSGID_REQUEST_DEV_DEP_MSG_IN;
    buf[1] = btag;
    buf[2] = ~btag;
    buf[3] = 0;
    /* MaxTransferSize (little-endian 32-bit) */
    buf[4] = (max_transfer_size >>  0) & 0xFF;
    buf[5] = (max_transfer_size >>  8) & 0xFF;
    buf[6] = (max_transfer_size >> 16) & 0xFF;
    buf[7] = (max_transfer_size >> 24) & 0xFF;
    /* bmTransferAttributes */
    buf[8] = 0;
    buf[9] = 0;  /* TermChar */
    buf[10] = 0;
    buf[11] = 0;
}

/* ------------------------------------------------------------------ */
/* Submit a bulk transfer and wait for completion                     */
/* ------------------------------------------------------------------ */

static int submit_and_wait(usb_transfer_t *xfer)
{
    s_xfer_status = 0;
    esp_err_t err = usb_host_transfer_submit(xfer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Transfer submit failed: %s", esp_err_to_name(err));
        return -1;
    }

    if (xSemaphoreTake(s_xfer_sem, pdMS_TO_TICKS(BULK_TIMEOUT_MS)) != pdTRUE) {
        ESP_LOGE(TAG, "Transfer timeout");
        return -1;
    }

    return s_xfer_status;
}

/* ------------------------------------------------------------------ */
/* Public API                                                         */
/* ------------------------------------------------------------------ */

int usbtmc_write(const char *cmd, size_t len)
{
    if (!s_xfer_out || !s_dev) return -1;

    uint8_t btag = next_btag();

    /* Pad to 4-byte boundary */
    size_t padded_len = (USBTMC_HEADER_SIZE + len + 3) & ~3;
    if (padded_len > XFER_BUF_SIZE) {
        ESP_LOGE(TAG, "Command too long (%d bytes)", (int)len);
        return -1;
    }

    /* Build header + payload */
    build_dev_dep_msg_out(s_xfer_out->data_buffer, btag, len, true);
    memcpy(s_xfer_out->data_buffer + USBTMC_HEADER_SIZE, cmd, len);

    /* Zero padding bytes */
    for (size_t i = USBTMC_HEADER_SIZE + len; i < padded_len; i++) {
        s_xfer_out->data_buffer[i] = 0;
    }

    s_xfer_out->device_handle = s_dev;
    s_xfer_out->bEndpointAddress = s_ep_out;
    s_xfer_out->callback = bulk_xfer_cb;
    s_xfer_out->context = NULL;
    s_xfer_out->num_bytes = padded_len;

    return submit_and_wait(s_xfer_out);
}

int usbtmc_read(uint8_t *buf, size_t max_len)
{
    if (!s_xfer_out || !s_xfer_in || !s_dev) return -1;

    uint8_t btag = next_btag();

    /* Send REQUEST_DEV_DEP_MSG_IN via bulk OUT */
    build_request_dev_dep_msg_in(s_xfer_out->data_buffer, btag, max_len);

    s_xfer_out->device_handle = s_dev;
    s_xfer_out->bEndpointAddress = s_ep_out;
    s_xfer_out->callback = bulk_xfer_cb;
    s_xfer_out->context = NULL;
    s_xfer_out->num_bytes = USBTMC_HEADER_SIZE;

    if (submit_and_wait(s_xfer_out) != 0) {
        return -1;
    }

    /* Read response via bulk IN */
    size_t read_size = USBTMC_HEADER_SIZE + max_len;
    if (read_size > XFER_BUF_SIZE) read_size = XFER_BUF_SIZE;
    /* Round up to MPS boundary for bulk reads, clamp to buffer */
    read_size = ((read_size + s_mps_in - 1) / s_mps_in) * s_mps_in;
    if (read_size > XFER_BUF_SIZE) read_size = XFER_BUF_SIZE;

    s_xfer_in->device_handle = s_dev;
    s_xfer_in->bEndpointAddress = s_ep_in;
    s_xfer_in->callback = bulk_xfer_cb;
    s_xfer_in->context = NULL;
    s_xfer_in->num_bytes = read_size;

    if (submit_and_wait(s_xfer_in) != 0) {
        return -1;
    }

    /* Parse DEV_DEP_MSG_IN response header */
    if (s_xfer_in->actual_num_bytes < USBTMC_HEADER_SIZE) {
        ESP_LOGE(TAG, "Short response (%d bytes)", s_xfer_in->actual_num_bytes);
        return -1;
    }

    uint8_t *resp = s_xfer_in->data_buffer;
    if (resp[0] != USBTMC_MSGID_DEV_DEP_MSG_IN) {
        ESP_LOGE(TAG, "Unexpected MsgID: 0x%02X", resp[0]);
        return -1;
    }

    /* Extract TransferSize from header */
    uint32_t transfer_size = resp[4] | (resp[5] << 8) |
                             (resp[6] << 16) | (resp[7] << 24);

    if (transfer_size > max_len) transfer_size = max_len;

    int avail = s_xfer_in->actual_num_bytes - USBTMC_HEADER_SIZE;
    if ((int)transfer_size > avail) transfer_size = avail;

    memcpy(buf, resp + USBTMC_HEADER_SIZE, transfer_size);
    return (int)transfer_size;
}

int usbtmc_query(const char *cmd, uint8_t *response_buf, size_t max_len)
{
    int ret = usbtmc_write(cmd, strlen(cmd));
    if (ret != 0) return -1;
    return usbtmc_read(response_buf, max_len);
}
