#include "led.h"

#include "esp_log.h"
#include "driver/rmt_tx.h"
#include "led_strip.h"
#include "led_strip_rmt.h"

static const char *TAG = "led";

/* DevKitC-1 has addressable RGB LED on GPIO48 */
#define LED_GPIO 48

static led_strip_handle_t s_strip = NULL;

void led_init(void)
{
    led_strip_config_t strip_config = {
        .strip_gpio_num = LED_GPIO,
        .max_leds = 1,
        .led_model = LED_MODEL_WS2812,
        .flags.invert_out = false,
    };

    led_strip_rmt_config_t rmt_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,  /* 10 MHz */
        .flags.with_dma = false,
    };

    esp_err_t err = led_strip_new_rmt_device(&strip_config, &rmt_config, &s_strip);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init LED strip: %s", esp_err_to_name(err));
        return;
    }

    led_set_state(LED_NO_DEVICE);
    ESP_LOGI(TAG, "LED initialized on GPIO%d", LED_GPIO);
}

void led_set_state(led_state_t state)
{
    if (!s_strip) return;

    uint8_t r = 0, g = 0, b = 0;

    switch (state) {
    case LED_NO_DEVICE: r = 20; g = 0;  b = 0;  break;  /* Dim red */
    case LED_BOOTING:   r = 20; g = 15; b = 0;  break;  /* Yellow */
    case LED_READY:     r = 0;  g = 20; b = 0;  break;  /* Green */
    case LED_DATA:      r = 0;  g = 0;  b = 20; break;  /* Blue */
    case LED_ERROR:     r = 30; g = 0;  b = 0;  break;  /* Bright red */
    }

    led_strip_set_pixel(s_strip, 0, r, g, b);
    led_strip_refresh(s_strip);
}
