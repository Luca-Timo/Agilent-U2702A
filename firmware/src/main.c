/*
 * ESP32-S3 USB Bridge for Agilent U2702A Oscilloscope
 *
 * Architecture:
 *   Mac <-- UART/CP2102N (2Mbps) --> ESP32-S3 <-- USB OTG Host --> U2702A
 *
 * Two-phase approach:
 *   Phase 1: HCD direct boot (bypass broken enumeration of PID 0x2818)
 *   Phase 2: USB Host library for USBTMC communication with PID 0x2918
 *
 * Three FreeRTOS tasks (Phase 2):
 *   1. USB Host daemon  — pumps usb_host_lib_handle_events()
 *   2. USB client       — device connect/disconnect, USBTMC interface claim
 *   3. Serial bridge    — UART RX/TX, SCPI command dispatch
 */

#include <stdio.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "usb/usb_host.h"

#include "u2702a_boot.h"
#include "usb_host.h"
#include "usbtmc.h"
#include "serial_bridge.h"
#include "led.h"

static const char *TAG = "main";

/* Stack sizes */
#define USB_DAEMON_STACK  4096
#define USB_CLIENT_STACK  6144
#define SERIAL_STACK      6144

void app_main(void)
{
    ESP_LOGI(TAG, "U2702A USB Bridge starting...");

    /* Initialize LED */
    led_init();
    led_set_state(LED_NO_DEVICE);

    /*
     * Phase 1: Boot the oscilloscope using HCD directly.
     * The boot-mode firmware (PID 0x2818) has an invalid config descriptor,
     * so we can't use the USB Host library for this phase.
     */
    ESP_LOGI(TAG, "Phase 1: Booting U2702A via HCD...");
    led_set_state(LED_BOOTING);

    int boot_ret = u2702a_hcd_boot(15000);  /* 15s timeout */
    if (boot_ret != 0) {
        ESP_LOGE(TAG, "Boot failed! Device may already be operational or not connected.");
        /* Continue anyway — the device might already be in operational mode */
    } else {
        ESP_LOGI(TAG, "Boot succeeded, waiting for re-enumeration...");
        vTaskDelay(pdMS_TO_TICKS(2000));  /* Give device time to re-enumerate */
    }

    /*
     * Phase 2: Install USB Host library for USBTMC communication.
     * The device should now be operational (PID 0x2918) with valid descriptors.
     */
    ESP_LOGI(TAG, "Phase 2: Starting USB Host for USBTMC...");

    SemaphoreHandle_t device_ready_sem = xSemaphoreCreateBinary();

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

    ESP_LOGI(TAG, "All tasks started. Waiting for U2702A operational device...");
}
