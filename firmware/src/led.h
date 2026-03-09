#pragma once

typedef enum {
    LED_NO_DEVICE = 0,  /* Red */
    LED_BOOTING,        /* Yellow */
    LED_READY,          /* Green */
    LED_DATA,           /* Blue (during transfer) */
    LED_ERROR,          /* Red blinking */
} led_state_t;

/** Initialize the RGB LED on GPIO48 (WS2812 on DevKitC-1). */
void led_init(void);

/** Set the LED to a state color. */
void led_set_state(led_state_t state);
