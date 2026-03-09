/*
 * U2702A Boot — Raw IOKit UserClient approach
 *
 * Bypasses USBDeviceOpen entirely and sends control transfers
 * directly through IOConnectCallStructMethod on the IOUSBHostDevice
 * user client.
 *
 * The U2702A boot-mode firmware doesn't provide a config descriptor,
 * which causes macOS to mark it as a USB compliance violation and
 * block USBDeviceOpen (kIOReturnNotReady). This approach works around
 * that by sending vendor control transfers without opening the device.
 *
 * Build: cc -framework IOKit -framework CoreFoundation \
 *        -Wall -O2 -o u2702a_boot_raw u2702a_boot_raw.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <mach/mach.h>

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>

/* --- Constants --- */

#define VID_AGILENT     0x0957
#define PID_BOOT        0x2818
#define PID_OPERATIONAL 0x2918

#define INITIAL_DELAY_S     3
#define ENUM_RETRY_MAX      30
#define ENUM_RETRY_DELAY_US 1000000
#define OPEN_RETRY_MAX      60
#define OPEN_RETRY_DELAY_US 500000
#define POLL_MAX            40
#define POLL_DELAY_US       500000

/* Boot sequence */
static const uint8_t boot_cmd[8] = {
    0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x08, 0x01
};

typedef struct {
    uint8_t  bmRequestType;
    uint8_t  bRequest;
    uint16_t wValue;
    uint16_t wIndex;
    uint16_t wLength;
    int      is_write;
} boot_step_t;

static const boot_step_t boot_sequence[] = {
    { 0xC0, 0x0C, 0x0000, 0x047E,  1, 0 },
    { 0xC0, 0x0C, 0x0000, 0x047D,  6, 0 },
    { 0xC0, 0x0C, 0x0000, 0x0484,  5, 0 },
    { 0xC0, 0x0C, 0x0000, 0x0472, 12, 0 },
    { 0xC0, 0x0C, 0x0000, 0x047A,  1, 0 },
    { 0x40, 0x0C, 0x0000, 0x0475,  8, 1 },
};
#define NUM_BOOT_STEPS 6


static void logmsg(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    fprintf(stderr, "[u2702a-boot-raw] %s\n", buf);
}


/*
 * Find the IOService for a USB device by VID/PID.
 */
static io_service_t find_usb_service(uint16_t vid, uint16_t pid) {
    const char *class_names[] = { "IOUSBHostDevice", "IOUSBDevice", NULL };

    for (int c = 0; class_names[c]; c++) {
        CFMutableDictionaryRef matchDict = IOServiceMatching(class_names[c]);
        if (!matchDict) continue;

        int32_t vid32 = vid, pid32 = pid;
        CFNumberRef vidRef = CFNumberCreate(kCFAllocatorDefault,
                                            kCFNumberSInt32Type, &vid32);
        CFNumberRef pidRef = CFNumberCreate(kCFAllocatorDefault,
                                            kCFNumberSInt32Type, &pid32);
        CFDictionarySetValue(matchDict, CFSTR("idVendor"), vidRef);
        CFDictionarySetValue(matchDict, CFSTR("idProduct"), pidRef);
        CFRelease(vidRef);
        CFRelease(pidRef);

        io_iterator_t iter = 0;
        kern_return_t kr = IOServiceGetMatchingServices(
            kIOMainPortDefault, matchDict, &iter);

        if (kr != KERN_SUCCESS || !iter) continue;

        io_service_t service = IOIteratorNext(iter);
        IOObjectRelease(iter);

        if (service) {
            logmsg("Found device via %s", class_names[c]);
            return service;
        }
    }
    return 0;
}


/*
 * Approach 1: Standard IOUSBDeviceInterface with extended retry
 * and USBDeviceOpenSeize fallback.
 */
static int try_standard_approach(io_service_t service) {
    logmsg("--- Approach 1: Standard IOKit with extended retry ---");

    IOCFPlugInInterface **plugIn = NULL;
    SInt32 score = 0;
    kern_return_t kr = IOCreatePlugInInterfaceForService(
        service, kIOUSBDeviceUserClientTypeID,
        kIOCFPlugInInterfaceID, &plugIn, &score);

    if (kr != kIOReturnSuccess || !plugIn) {
        logmsg("  IOCreatePlugInInterface failed: 0x%08x", kr);
        return -1;
    }

    IOUSBDeviceInterface **dev = NULL;
    HRESULT hr = (*plugIn)->QueryInterface(
        plugIn, CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID),
        (LPVOID *)&dev);
    (*plugIn)->Release(plugIn);

    if (hr != S_OK || !dev) {
        logmsg("  QueryInterface failed");
        return -1;
    }

    /* Try USBDeviceOpen with extended retry */
    IOReturn result = kIOReturnError;
    for (int attempt = 1; attempt <= OPEN_RETRY_MAX; attempt++) {
        result = (*dev)->USBDeviceOpen(dev);
        if (result == kIOReturnSuccess) {
            logmsg("  USBDeviceOpen succeeded on attempt %d!", attempt);
            goto send_boot;
        }

        /* Try seize on any error, not just exclusive access */
        if (attempt % 10 == 0) {
            logmsg("  Attempt %d: trying USBDeviceOpenSeize...", attempt);
            result = (*dev)->USBDeviceOpenSeize(dev);
            if (result == kIOReturnSuccess) {
                logmsg("  USBDeviceOpenSeize succeeded on attempt %d!", attempt);
                goto send_boot;
            }
        }

        if (attempt <= 5 || attempt % 10 == 0) {
            logmsg("  Attempt %d/%d: 0x%08x, retrying...",
                   attempt, OPEN_RETRY_MAX, result);
        }
        usleep(OPEN_RETRY_DELAY_US);
    }

    logmsg("  All open attempts failed (last: 0x%08x)", result);
    (*dev)->Release(dev);
    return -1;

send_boot:
    logmsg("  Sending boot sequence...");
    {
        uint8_t buf[64];
        for (int i = 0; i < NUM_BOOT_STEPS; i++) {
            const boot_step_t *step = &boot_sequence[i];
            memset(buf, 0, sizeof(buf));

            IOUSBDevRequest req;
            req.bmRequestType = step->bmRequestType;
            req.bRequest = step->bRequest;
            req.wValue = step->wValue;
            req.wIndex = step->wIndex;
            req.wLength = step->wLength;

            if (step->is_write) memcpy(buf, boot_cmd, step->wLength);
            req.pData = buf;

            kr = (*dev)->DeviceRequest(dev, &req);
            if (kr != kIOReturnSuccess) {
                logmsg("  Boot step %d FAILED: 0x%08x", i + 1, kr);
                (*dev)->USBDeviceClose(dev);
                (*dev)->Release(dev);
                return -1;
            }
            logmsg("  Boot step %d/6 OK", i + 1);
        }
    }

    (*dev)->USBDeviceClose(dev);
    (*dev)->Release(dev);
    return 0;
}


/*
 * Approach 2: Direct IOServiceOpen + IOConnectCallStructMethod
 * Bypasses USBDeviceOpen entirely.
 */
static int try_raw_ioconnect(io_service_t service) {
    logmsg("--- Approach 2: Raw IOConnectCallStructMethod ---");

    io_connect_t connect = 0;
    kern_return_t kr;

    /* Try different user client types */
    for (uint32_t type = 0; type < 3; type++) {
        kr = IOServiceOpen(service, mach_task_self(), type, &connect);
        if (kr == kIOReturnSuccess && connect) {
            logmsg("  IOServiceOpen succeeded with type %u", type);
            break;
        }
        logmsg("  IOServiceOpen type %u: 0x%08x", type, kr);
        connect = 0;
    }

    if (!connect) {
        logmsg("  All IOServiceOpen attempts failed");
        return -1;
    }

    /*
     * Try to send a control transfer via IOConnectCallStructMethod.
     *
     * IOUSBHostDeviceUserClient external methods:
     *   Selector 0 = Open
     *   Selector 2 = DeviceRequest (varies by macOS version)
     *
     * The struct layout for DeviceRequest typically matches
     * IOUSBDevRequest (8 bytes header + data pointer).
     */

    /* First try: just send the control transfer on selector 2 */
    struct {
        uint8_t  bmRequestType;
        uint8_t  bRequest;
        uint16_t wValue;
        uint16_t wIndex;
        uint16_t wLength;
        uint16_t pad;
        uint8_t  data[64];
    } __attribute__((packed)) req;

    memset(&req, 0, sizeof(req));
    req.bmRequestType = 0xC0;  /* Vendor, device-to-host */
    req.bRequest = 0x0C;
    req.wValue = 0x0000;
    req.wIndex = 0x047E;
    req.wLength = 1;

    uint8_t output[64];
    size_t outputSize = sizeof(output);

    /* Try various selectors for DeviceRequest */
    for (uint32_t sel = 0; sel < 10; sel++) {
        outputSize = sizeof(output);
        kr = IOConnectCallStructMethod(
            connect, sel,
            &req, sizeof(req),
            output, &outputSize);

        if (kr == kIOReturnSuccess) {
            logmsg("  Selector %u SUCCESS! Output %zu bytes", sel, outputSize);
            if (outputSize > 0) {
                logmsg("  Data: %02x", output[0]);
            }
            /* Found working selector — send full boot sequence */
            logmsg("  Sending boot sequence via selector %u...", sel);
            for (int i = 0; i < NUM_BOOT_STEPS; i++) {
                const boot_step_t *step = &boot_sequence[i];
                memset(&req, 0, sizeof(req));
                req.bmRequestType = step->bmRequestType;
                req.bRequest = step->bRequest;
                req.wValue = step->wValue;
                req.wIndex = step->wIndex;
                req.wLength = step->wLength;
                if (step->is_write) memcpy(req.data, boot_cmd, step->wLength);

                outputSize = sizeof(output);
                kr = IOConnectCallStructMethod(
                    connect, sel,
                    &req, sizeof(req),
                    output, &outputSize);
                if (kr != kIOReturnSuccess) {
                    logmsg("  Boot step %d FAILED: 0x%08x", i + 1, kr);
                    IOServiceClose(connect);
                    return -1;
                }
                if (step->is_write) {
                    logmsg("  Boot step %d/6 OK (write)", i + 1);
                } else {
                    logmsg("  Boot step %d/6 OK (read %zu bytes)", i + 1, outputSize);
                }
            }
            IOServiceClose(connect);
            return 0;
        }

        if (kr != kIOReturnBadArgument && kr != kIOReturnUnsupported) {
            logmsg("  Selector %u: 0x%08x (%s)", sel, kr,
                   kr == (IOReturn)0xe00002d8 ? "not ready" :
                   kr == (IOReturn)0xe00002c5 ? "exclusive access" :
                   kr == (IOReturn)0xe00002bc ? "unsupported" :
                   kr == (IOReturn)0xe00002c2 ? "invalid arg" :
                   "other");
        }
    }

    logmsg("  No working selector found");
    IOServiceClose(connect);
    return -1;
}


/*
 * Approach 3: Reset port via IOKit, then retry.
 */
static int try_port_reset(io_service_t service) {
    logmsg("--- Approach 3: IOKit port reset ---");

    /* Get parent (the port/hub) and try to reset */
    io_service_t parent = 0;
    kern_return_t kr = IORegistryEntryGetParentEntry(
        service, kIOServicePlane, &parent);
    if (kr != kIOReturnSuccess) {
        logmsg("  Can't get parent: 0x%08x", kr);
        return -1;
    }

    io_name_t className;
    IOObjectGetClass(parent, className);
    logmsg("  Parent class: %s", className);

    /* Try to open parent and reset */
    io_connect_t connect = 0;
    kr = IOServiceOpen(parent, mach_task_self(), 0, &connect);
    IOObjectRelease(parent);

    if (kr != kIOReturnSuccess) {
        logmsg("  Can't open parent: 0x%08x", kr);
        return -1;
    }

    /* Try reset via IOConnectCallMethod */
    for (uint32_t sel = 0; sel < 5; sel++) {
        kr = IOConnectCallMethod(connect, sel,
            NULL, 0, NULL, 0, NULL, NULL, NULL, NULL);
        logmsg("  Parent selector %u: 0x%08x", sel, kr);
    }

    IOServiceClose(connect);
    return -1;  /* This is exploratory */
}


/* --- Main --- */

int main(int argc, char **argv) {
    logmsg("Starting U2702A boot (raw IOKit)");
    logmsg("Running as uid %d", getuid());

    if (getuid() != 0) {
        logmsg("WARNING: Not running as root. Run with sudo.");
    }

    /* Wait for USB enumeration */
    logmsg("Waiting %ds for USB enumeration...", INITIAL_DELAY_S);
    sleep(INITIAL_DELAY_S);

    /* Check if already operational */
    io_service_t service = find_usb_service(VID_AGILENT, PID_OPERATIONAL);
    if (service) {
        logmsg("Device already operational!");
        IOObjectRelease(service);
        return 0;
    }

    /* Find boot-mode device with retries */
    service = 0;
    for (int attempt = 1; attempt <= ENUM_RETRY_MAX; attempt++) {
        service = find_usb_service(VID_AGILENT, PID_BOOT);
        if (service) break;
        if (attempt <= 3 || attempt % 5 == 0)
            logmsg("Enum attempt %d/%d: not found", attempt, ENUM_RETRY_MAX);
        usleep(ENUM_RETRY_DELAY_US);
    }

    if (!service) {
        logmsg("No boot-mode device found");
        return 1;
    }

    int result;

    /* Try Approach 2 first (raw IOConnect, bypasses USBDeviceOpen) */
    result = try_raw_ioconnect(service);
    if (result == 0) goto poll_operational;

    /* Try Approach 3 (port reset) */
    try_port_reset(service);

    /* Try Approach 1 (standard, with extended retry + seize) */
    result = try_standard_approach(service);
    if (result == 0) goto poll_operational;

    IOObjectRelease(service);
    logmsg("All approaches failed");
    return 1;

poll_operational:
    IOObjectRelease(service);
    logmsg("Boot sequence sent! Polling for operational device...");

    for (int i = 0; i < POLL_MAX; i++) {
        usleep(POLL_DELAY_US);
        io_service_t oper = find_usb_service(VID_AGILENT, PID_OPERATIONAL);
        if (oper) {
            logmsg("Device operational after %.1fs!", (i + 1) * 0.5);
            IOObjectRelease(oper);
            logmsg("Boot complete — device ready");
            return 0;
        }
    }

    logmsg("TIMEOUT: device did not re-enumerate");
    return 1;
}
