/*
 * ESP32-S3 USB Bridge for Agilent U2702A Oscilloscope
 *
 * Architecture:
 *   Mac <-- UART/CP2102N (2Mbps) --> ESP32-S3 <-- USB OTG Host --> U2702A
 *
 * Three FreeRTOS tasks:
 *   1. USB Host daemon  — pumps usb_host_lib_handle_events()
 *   2. USB client       — device connect/disconnect, boot sequence, USBTMC claim
 *   3. Serial bridge    — UART RX/TX, SCPI command dispatch
 */

#include <stdio.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "usb/usb_host.h"

#include "usb_host.h"
#include "usbtmc.h"
#include "serial_bridge.h"
#include "led.h"

static const char *TAG = "main";

/* Stack sizes */
#define USB_DAEMON_STACK  4096
#define USB_CLIENT_STACK  4096
#define SERIAL_STACK      4096

void app_main(void)
{
    ESP_LOGI(TAG, "U2702A USB Bridge starting...");

    /* Initialize LED */
    led_init();
    led_set_state(LED_NO_DEVICE);

    /* Semaphore: USB client signals serial bridge when device is ready */
    SemaphoreHandle_t device_ready_sem = xSemaphoreCreateBinary();

    /* Install USB Host library */
    usb_host_config_t host_config = {
        .skip_phy_setup = false,
        .intr_flags = ESP_INTR_FLAG_LEVEL1,
    };

    esp_err_t err = usb_host_install(&host_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "USB Host install failed: %s", esp_err_to_name(err));
        led_set_state(LED_ERROR);
        return;
    }
    ESP_LOGI(TAG, "USB Host library installed");

    /* Start tasks */
    xTaskCreatePinnedToCore(usb_host_daemon_task, "usb_daemon",
                            USB_DAEMON_STACK, NULL, 5, NULL, 0);

    xTaskCreatePinnedToCore(usb_client_task, "usb_client",
                            USB_CLIENT_STACK, device_ready_sem, 4, NULL, 0);

    xTaskCreatePinnedToCore(serial_bridge_task, "serial_bridge",
                            SERIAL_STACK, device_ready_sem, 3, NULL, 1);

    ESP_LOGI(TAG, "All tasks started. Waiting for U2702A...");
}
