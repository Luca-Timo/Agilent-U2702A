#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

/**
 * Serial bridge task — reads SCPI commands from UART, forwards to USBTMC,
 * returns responses over UART.
 *
 * Protocol (Mac <-> ESP32 over UART at 2 Mbps):
 *   Text commands:  "SCPI COMMAND\n"
 *   Text responses: "response data\n"
 *   Binary data:    "#" + 4-byte LE length + raw bytes  (for WAV:DATA?)
 *   Status msgs:    "!STATUS:READY\n", "!STATUS:BOOTING\n", etc.
 *
 * @param arg  SemaphoreHandle_t — taken before starting to wait for device ready
 */
void serial_bridge_task(void *arg);
