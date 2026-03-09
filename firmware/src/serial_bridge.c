#include "serial_bridge.h"
#include "usbtmc.h"
#include "usb_host.h"
#include "led.h"

#include <string.h>
#include "esp_log.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "bridge";

/* UART config for serial bridge (UART1, separate from console UART0) */
#define BRIDGE_UART_NUM  UART_NUM_1
#define BRIDGE_BAUD      2000000
#define BRIDGE_TX_PIN    17
#define BRIDGE_RX_PIN    18
#define BRIDGE_BUF_SIZE  4096

/* Max SCPI command line length */
#define CMD_MAX_LEN      1024

/* Response buffer */
#define RESP_MAX_LEN     4096

/* IEEE 488.2 binary block prefix: #8NNNNNNNN */
#define IEEE_HEADER_LEN  10

static void send_status(const char *status)
{
    char msg[64];
    int len = snprintf(msg, sizeof(msg), "!STATUS:%s\n", status);
    uart_write_bytes(BRIDGE_UART_NUM, msg, len);
}

static void send_text_response(const uint8_t *data, int len)
{
    uart_write_bytes(BRIDGE_UART_NUM, data, len);
    /* Ensure newline termination */
    if (len == 0 || data[len - 1] != '\n') {
        uart_write_bytes(BRIDGE_UART_NUM, "\n", 1);
    }
}

static void send_binary_response(const uint8_t *data, int len)
{
    /* Binary frame: '#' + 4-byte little-endian length + raw data */
    uint8_t header[5];
    header[0] = '#';
    header[1] = (len >>  0) & 0xFF;
    header[2] = (len >>  8) & 0xFF;
    header[3] = (len >> 16) & 0xFF;
    header[4] = (len >> 24) & 0xFF;
    uart_write_bytes(BRIDGE_UART_NUM, header, 5);
    uart_write_bytes(BRIDGE_UART_NUM, data, len);
}

/**
 * Check if a SCPI response is an IEEE 488.2 binary block (starts with '#').
 * If so, strip the IEEE header and send as binary frame.
 * Otherwise send as text.
 */
static void send_response(const uint8_t *data, int len)
{
    if (len >= IEEE_HEADER_LEN && data[0] == '#' && data[1] >= '1' && data[1] <= '9') {
        /* Parse IEEE 488.2 header: #NDDDD...  where N=num digits, D=size digits */
        int n_digits = data[1] - '0';
        if (len >= 2 + n_digits) {
            /* Extract byte count */
            uint32_t byte_count = 0;
            for (int i = 0; i < n_digits; i++) {
                byte_count = byte_count * 10 + (data[2 + i] - '0');
            }
            int header_len = 2 + n_digits;
            int payload_len = len - header_len;
            if ((uint32_t)payload_len > byte_count) payload_len = byte_count;

            send_binary_response(data + header_len, payload_len);
            return;
        }
    }

    send_text_response(data, len);
}

static bool is_query(const char *cmd, size_t len)
{
    /* A SCPI query ends with '?' */
    for (int i = len - 1; i >= 0; i--) {
        if (cmd[i] == '?') return true;
        if (cmd[i] != ' ' && cmd[i] != '\n' && cmd[i] != '\r') break;
    }
    return false;
}

/* ------------------------------------------------------------------ */
/* Bridge task                                                        */
/* ------------------------------------------------------------------ */

void serial_bridge_task(void *arg)
{
    SemaphoreHandle_t device_ready_sem = (SemaphoreHandle_t)arg;

    /* Configure UART1 for bridge communication */
    uart_config_t uart_config = {
        .baud_rate = BRIDGE_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_driver_install(BRIDGE_UART_NUM, BRIDGE_BUF_SIZE,
                                         BRIDGE_BUF_SIZE, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(BRIDGE_UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(BRIDGE_UART_NUM, BRIDGE_TX_PIN, BRIDGE_RX_PIN,
                                  UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    ESP_LOGI(TAG, "Serial bridge started on UART%d (TX=%d RX=%d @ %d baud)",
             BRIDGE_UART_NUM, BRIDGE_TX_PIN, BRIDGE_RX_PIN, BRIDGE_BAUD);

    send_status("WAITING");

    /* Wait for device to be ready */
    while (1) {
        if (xSemaphoreTake(device_ready_sem, pdMS_TO_TICKS(1000)) == pdTRUE) {
            break;
        }
        /* Periodically send status while waiting */
        if (g_dev_state == DEV_STATE_BOOTING) {
            send_status("BOOTING");
        }
    }

    /* Initialize USBTMC layer */
    /* The USB host module has already set up g_endpoints at this point */
    /* We need the client handle — it's stored as a static in usb_host.c,
       so we pass it through a global or init function. For simplicity,
       we expose it via the usb_host module. */

    send_status("READY");
    ESP_LOGI(TAG, "Device ready, accepting SCPI commands");

    /* Command buffer */
    char cmd_buf[CMD_MAX_LEN];
    int cmd_pos = 0;
    uint8_t resp_buf[RESP_MAX_LEN];

    while (1) {
        /* Check if device is still connected */
        if (g_dev_state != DEV_STATE_READY) {
            send_status("DISCONNECTED");
            ESP_LOGW(TAG, "Device disconnected, waiting for reconnect...");

            /* Wait for device ready again */
            while (g_dev_state != DEV_STATE_READY) {
                if (xSemaphoreTake(device_ready_sem, pdMS_TO_TICKS(1000)) == pdTRUE) {
                    break;
                }
            }
            send_status("READY");
            cmd_pos = 0;  /* Reset command buffer */
            continue;
        }

        /* Read bytes from UART */
        uint8_t byte;
        int read = uart_read_bytes(BRIDGE_UART_NUM, &byte, 1, pdMS_TO_TICKS(50));
        if (read <= 0) continue;

        /* Build command line until newline */
        if (byte == '\n' || byte == '\r') {
            if (cmd_pos == 0) continue;  /* Ignore empty lines */
            if (cmd_pos < 0) {
                /* Command was too long, discard */
                send_text_response((const uint8_t *)"!ERROR:CMD_TOO_LONG", 19);
                cmd_pos = 0;
                continue;
            }

            cmd_buf[cmd_pos] = '\0';
            ESP_LOGD(TAG, "RX: %s", cmd_buf);

            /* Flash LED blue during transfer */
            led_set_state(LED_DATA);

            if (is_query(cmd_buf, cmd_pos)) {
                /* Query: write + read */
                int resp_len = usbtmc_query(cmd_buf, resp_buf, RESP_MAX_LEN);
                if (resp_len > 0) {
                    send_response(resp_buf, resp_len);
                } else {
                    /* Error or empty response */
                    send_text_response((const uint8_t *)"!ERROR:QUERY_FAILED", 19);
                }
            } else {
                /* Set command: write only */
                int ret = usbtmc_write(cmd_buf, cmd_pos);
                if (ret == 0) {
                    send_text_response((const uint8_t *)"OK", 2);
                } else {
                    send_text_response((const uint8_t *)"!ERROR:WRITE_FAILED", 19);
                }
            }

            led_set_state(LED_READY);
            cmd_pos = 0;

        } else if (cmd_pos < CMD_MAX_LEN - 1) {
            cmd_buf[cmd_pos++] = (char)byte;
        } else {
            /* Buffer full — discard until newline */
            cmd_pos = -1;  /* sentinel: discard mode */
        }
    }
}
