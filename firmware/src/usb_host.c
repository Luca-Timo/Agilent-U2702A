#include "usb_host.h"
#include "usbtmc.h"
#include "led.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "usb/usb_host.h"

static const char *TAG = "usb_host";

/* Globals */
usb_device_handle_t g_dev_handle = NULL;
dev_state_t g_dev_state = DEV_STATE_IDLE;
usbtmc_endpoints_t g_endpoints = {0};

static usb_host_client_handle_t s_client_handle = NULL;
static SemaphoreHandle_t s_device_sem = NULL;

usb_host_client_handle_t usb_host_get_client_handle(void)
{
    return s_client_handle;
}

/* ------------------------------------------------------------------ */
/* USB Host library daemon — pumps the event loop                     */
/* ------------------------------------------------------------------ */

void usb_host_daemon_task(void *arg)
{
    ESP_LOGI(TAG, "USB Host daemon started");

    while (1) {
        uint32_t event_flags;
        usb_host_lib_handle_events(portMAX_DELAY, &event_flags);

        if (event_flags & USB_HOST_LIB_EVENT_FLAGS_NO_CLIENTS) {
            ESP_LOGW(TAG, "No USB clients registered");
        }
        if (event_flags & USB_HOST_LIB_EVENT_FLAGS_ALL_FREE) {
            ESP_LOGI(TAG, "All USB devices freed");
        }
    }
}

/* ------------------------------------------------------------------ */
/* Parse config descriptor to find USBTMC bulk endpoints              */
/* ------------------------------------------------------------------ */

static bool parse_usbtmc_endpoints(const usb_config_desc_t *config_desc,
                                   usbtmc_endpoints_t *ep_out)
{
    int offset = 0;
    const uint8_t *p = (const uint8_t *)config_desc;
    int total_len = config_desc->wTotalLength;
    bool in_usbtmc_iface = false;

    while (offset < total_len) {
        uint8_t bLength = p[offset];
        uint8_t bDescType = p[offset + 1];

        if (bLength == 0) break;

        /* Interface descriptor */
        if (bDescType == USB_B_DESCRIPTOR_TYPE_INTERFACE && bLength >= 9) {
            uint8_t iface_class    = p[offset + 5];
            uint8_t iface_subclass = p[offset + 6];

            if (iface_class == USB_CLASS_APP_SPEC &&
                iface_subclass == USB_SUBCLASS_USBTMC) {
                in_usbtmc_iface = true;
                ep_out->iface_num = p[offset + 2];
                ESP_LOGI(TAG, "Found USBTMC interface %d", ep_out->iface_num);
            } else {
                in_usbtmc_iface = false;
            }
        }

        /* Endpoint descriptor inside USBTMC interface */
        if (bDescType == USB_B_DESCRIPTOR_TYPE_ENDPOINT &&
            bLength >= 7 && in_usbtmc_iface) {
            uint8_t ep_addr = p[offset + 2];
            uint8_t ep_attr = p[offset + 3];
            uint16_t mps = p[offset + 4] | (p[offset + 5] << 8);

            /* Bulk endpoints only */
            if ((ep_attr & 0x03) == USB_TRANSFER_TYPE_BULK) {
                if (ep_addr & 0x80) {
                    ep_out->bulk_in_ep = ep_addr;
                    ep_out->bulk_in_mps = mps;
                    ESP_LOGI(TAG, "  Bulk IN  EP 0x%02X, MPS %d", ep_addr, mps);
                } else {
                    ep_out->bulk_out_ep = ep_addr;
                    ep_out->bulk_out_mps = mps;
                    ESP_LOGI(TAG, "  Bulk OUT EP 0x%02X, MPS %d", ep_addr, mps);
                }
            }
        }

        offset += bLength;
    }

    return (ep_out->bulk_in_ep != 0 && ep_out->bulk_out_ep != 0);
}

/* ------------------------------------------------------------------ */
/* Handle a newly connected device                                    */
/* ------------------------------------------------------------------ */

static void handle_device_connected(uint8_t dev_addr)
{
    esp_err_t err;

    /* Open the device */
    err = usb_host_device_open(s_client_handle, dev_addr, &g_dev_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open device addr %d: %s", dev_addr, esp_err_to_name(err));
        return;
    }

    /* Get device descriptor */
    const usb_device_desc_t *dev_desc;
    err = usb_host_get_device_descriptor(g_dev_handle, &dev_desc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get device descriptor");
        usb_host_device_close(s_client_handle, g_dev_handle);
        g_dev_handle = NULL;
        return;
    }

    uint16_t vid = dev_desc->idVendor;
    uint16_t pid = dev_desc->idProduct;
    ESP_LOGI(TAG, "Device connected: VID=0x%04X PID=0x%04X", vid, pid);

    /* Check if it's our device */
    if (vid != VID_AGILENT) {
        ESP_LOGW(TAG, "Not an Agilent device, ignoring");
        usb_host_device_close(s_client_handle, g_dev_handle);
        g_dev_handle = NULL;
        return;
    }

    if (pid == PID_BOOT) {
        /* Boot-mode device should have been handled in Phase 1 (HCD boot).
         * If we see it here, something went wrong. */
        ESP_LOGW(TAG, "U2702A still in boot mode! HCD boot may have failed.");
        usb_host_device_close(s_client_handle, g_dev_handle);
        g_dev_handle = NULL;
        g_dev_state = DEV_STATE_ERROR;
        led_set_state(LED_ERROR);

    } else if (pid == PID_OPERATIONAL) {
        /* Operational device — claim USBTMC interface */
        ESP_LOGI(TAG, "U2702A operational (PID 0x2918)");
        g_dev_state = DEV_STATE_OPERATIONAL;

        /* Get config descriptor and parse endpoints */
        const usb_config_desc_t *config_desc;
        err = usb_host_get_active_config_descriptor(g_dev_handle, &config_desc);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to get config descriptor: %s", esp_err_to_name(err));
            g_dev_state = DEV_STATE_ERROR;
            led_set_state(LED_ERROR);
            return;
        }

        memset(&g_endpoints, 0, sizeof(g_endpoints));
        if (!parse_usbtmc_endpoints(config_desc, &g_endpoints)) {
            ESP_LOGE(TAG, "No USBTMC bulk endpoints found");
            g_dev_state = DEV_STATE_ERROR;
            led_set_state(LED_ERROR);
            return;
        }

        /* Claim the USBTMC interface */
        err = usb_host_interface_claim(s_client_handle, g_dev_handle,
                                       g_endpoints.iface_num, 0);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to claim interface %d: %s",
                     g_endpoints.iface_num, esp_err_to_name(err));
            g_dev_state = DEV_STATE_ERROR;
            led_set_state(LED_ERROR);
            return;
        }

        /* Initialize USBTMC protocol layer */
        if (usbtmc_init(s_client_handle, g_dev_handle,
                        g_endpoints.bulk_out_ep, g_endpoints.bulk_in_ep,
                        g_endpoints.bulk_out_mps, g_endpoints.bulk_in_mps) != 0) {
            ESP_LOGE(TAG, "USBTMC init failed");
            g_dev_state = DEV_STATE_ERROR;
            led_set_state(LED_ERROR);
            return;
        }

        ESP_LOGI(TAG, "USBTMC interface claimed, device ready");
        g_dev_state = DEV_STATE_READY;
        led_set_state(LED_READY);

        /* Signal serial bridge that device is ready */
        if (s_device_sem) {
            xSemaphoreGive(s_device_sem);
        }

    } else {
        ESP_LOGW(TAG, "Unknown Agilent PID 0x%04X, ignoring", pid);
        usb_host_device_close(s_client_handle, g_dev_handle);
        g_dev_handle = NULL;
    }
}

/* ------------------------------------------------------------------ */
/* Handle device disconnection                                        */
/* ------------------------------------------------------------------ */

static void handle_device_disconnected(void)
{
    ESP_LOGW(TAG, "Device disconnected");

    if (g_dev_handle) {
        /* Release interface if claimed */
        if (g_dev_state == DEV_STATE_READY) {
            usb_host_interface_release(s_client_handle, g_dev_handle,
                                       g_endpoints.iface_num);
        }
        usb_host_device_close(s_client_handle, g_dev_handle);
        g_dev_handle = NULL;
    }

    memset(&g_endpoints, 0, sizeof(g_endpoints));
    g_dev_state = DEV_STATE_IDLE;
    led_set_state(LED_NO_DEVICE);
}

/* ------------------------------------------------------------------ */
/* Client event callback                                              */
/* ------------------------------------------------------------------ */

static void client_event_cb(const usb_host_client_event_msg_t *event_msg, void *arg)
{
    switch (event_msg->event) {
    case USB_HOST_CLIENT_EVENT_NEW_DEV:
        ESP_LOGI(TAG, "New device (addr %d)", event_msg->new_dev.address);
        handle_device_connected(event_msg->new_dev.address);
        break;
    case USB_HOST_CLIENT_EVENT_DEV_GONE:
        ESP_LOGW(TAG, "Device gone");
        handle_device_disconnected();
        break;
    default:
        break;
    }
}

/* ------------------------------------------------------------------ */
/* USB client task                                                    */
/* ------------------------------------------------------------------ */

void usb_client_task(void *arg)
{
    s_device_sem = (SemaphoreHandle_t)arg;

    ESP_LOGI(TAG, "USB client task started");

    /* Register client */
    usb_host_client_config_t client_config = {
        .is_synchronous = false,
        .max_num_event_msg = 5,
        .async = {
            .client_event_callback = client_event_cb,
            .callback_arg = NULL,
        },
    };

    esp_err_t err = usb_host_client_register(&client_config, &s_client_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register USB client: %s", esp_err_to_name(err));
        vTaskDelete(NULL);
        return;
    }

    /* Event loop */
    while (1) {
        usb_host_client_handle_events(s_client_handle, pdMS_TO_TICKS(100));
    }
}
