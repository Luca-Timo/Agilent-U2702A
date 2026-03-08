/*
 * U2702A USB Boot Helper — Native IOKit implementation
 *
 * Boots the Agilent U2702A from firmware-update mode (PID 0x2818)
 * to operational USBTMC mode (PID 0x2918) using macOS IOKit USB API.
 *
 * Unlike libusb, this uses Apple's native USB framework directly,
 * which properly handles the device's "not ready" transitional state
 * by retrying USBDeviceOpen on the same interface handle.
 *
 * Build: cc -framework IOKit -framework CoreFoundation \
 *        -o u2702a_boot_helper u2702a_boot_helper.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <syslog.h>
#include <stdarg.h>
#include <mach/mach_port.h>

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>

/* --- Constants --- */

#define VID_AGILENT     0x0957
#define PID_BOOT        0x2818
#define PID_OPERATIONAL 0x2918

#define OPEN_RETRY_MAX      30      /* retries for USBDeviceOpen */
#define OPEN_RETRY_DELAY_US 500000  /* 0.5s between retries */
#define ENUM_RETRY_MAX      20      /* retries for finding the device */
#define ENUM_RETRY_DELAY_US 1000000 /* 1.0s between retries */
#define INITIAL_DELAY_S     2       /* wait for USB enumeration */
#define POLL_MAX            40      /* re-enumeration poll attempts */
#define POLL_DELAY_US       500000  /* 0.5s between poll attempts */

/* Boot sequence: 6 vendor-specific USB control transfers */
static const uint8_t boot_cmd[8] = {
    0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x08, 0x01
};

typedef struct {
    uint8_t  bmRequestType;
    uint8_t  bRequest;
    uint16_t wValue;
    uint16_t wIndex;
    uint16_t wLength;
    int      is_write;  /* 1 = write boot_cmd, 0 = read into buffer */
} boot_step_t;

static const boot_step_t boot_sequence[] = {
    { 0xC0, 0x0C, 0x0000, 0x047E,  1, 0 },  /* Read 1 byte  */
    { 0xC0, 0x0C, 0x0000, 0x047D,  6, 0 },  /* Read 6 bytes */
    { 0xC0, 0x0C, 0x0000, 0x0484,  5, 0 },  /* Read 5 bytes */
    { 0xC0, 0x0C, 0x0000, 0x0472, 12, 0 },  /* Read 12 bytes */
    { 0xC0, 0x0C, 0x0000, 0x047A,  1, 0 },  /* Read 1 byte  */
    { 0x40, 0x0C, 0x0000, 0x0475,  8, 1 },  /* Write 8 bytes: BOOT */
};

#define NUM_BOOT_STEPS (sizeof(boot_sequence) / sizeof(boot_sequence[0]))


/* --- Logging --- */

static void logmsg(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    syslog(LOG_NOTICE, "u2702a-boot: %s", buf);
    fprintf(stderr, "[u2702a-boot] %s\n", buf);
}


/* --- IOKit USB helpers --- */

/*
 * Find a USB device by VID/PID and return its IOUSBDeviceInterface.
 * Returns NULL if not found.
 *
 * Tries both "IOUSBHostDevice" (macOS 13+) and legacy "IOUSBDevice" classes.
 */
static IOUSBDeviceInterface **find_device_interface(uint16_t vid, uint16_t pid) {
    /* Try modern class name first, then legacy */
    const char *class_names[] = { "IOUSBHostDevice", "IOUSBDevice", NULL };

    for (int c = 0; class_names[c] != NULL; c++) {
        CFMutableDictionaryRef matchDict = IOServiceMatching(class_names[c]);
        if (!matchDict) continue;

        /* Add VID/PID to matching dictionary */
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
        /* matchDict is consumed by IOServiceGetMatchingServices */

        if (kr != KERN_SUCCESS || !iter) continue;

        io_service_t service = IOIteratorNext(iter);
        IOObjectRelease(iter);

        if (!service) continue;

        logmsg("Found device via %s (VID=0x%04X PID=0x%04X)",
               class_names[c], vid, pid);

        /* Create plugin interface */
        IOCFPlugInInterface **plugIn = NULL;
        SInt32 score = 0;
        kr = IOCreatePlugInInterfaceForService(
            service,
            kIOUSBDeviceUserClientTypeID,
            kIOCFPlugInInterfaceID,
            &plugIn, &score);
        IOObjectRelease(service);

        if (kr != kIOReturnSuccess || !plugIn) {
            logmsg("IOCreatePlugInInterfaceForService failed: 0x%08x", kr);
            continue;
        }

        /* Query for USB device interface */
        IOUSBDeviceInterface **dev = NULL;
        HRESULT hr = (*plugIn)->QueryInterface(
            plugIn,
            CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID),
            (LPVOID *)&dev);
        (*plugIn)->Release(plugIn);

        if (hr != S_OK || !dev) {
            logmsg("QueryInterface failed: 0x%lx", (long)hr);
            continue;
        }

        return dev;
    }

    return NULL;
}


/*
 * Open a USB device interface with retry.
 *
 * macOS returns kIOReturnNotReady (0xe00002d8) when the device
 * is still initializing. We retry on the SAME interface handle
 * (unlike libusb which recreates everything).
 */
static IOReturn open_device_with_retry(IOUSBDeviceInterface **dev) {
    IOReturn kr;

    for (int attempt = 1; attempt <= OPEN_RETRY_MAX; attempt++) {
        kr = (*dev)->USBDeviceOpen(dev);
        if (kr == kIOReturnSuccess) {
            logmsg("USBDeviceOpen succeeded on attempt %d", attempt);
            return kIOReturnSuccess;
        }

        if (kr == (IOReturn)0xe00002d8) {
            /* kIOReturnNotReady — device still initializing */
            logmsg("Attempt %d/%d: device not ready (0x%08x), retrying...",
                   attempt, OPEN_RETRY_MAX, kr);
        } else if (kr == kIOReturnExclusiveAccess) {
            /* Another client has the device — try seize */
            logmsg("Attempt %d: exclusive access error, trying seize...",
                   attempt);
            kr = (*dev)->USBDeviceOpenSeize(dev);
            if (kr == kIOReturnSuccess) {
                logmsg("USBDeviceOpenSeize succeeded");
                return kIOReturnSuccess;
            }
            logmsg("USBDeviceOpenSeize failed: 0x%08x", kr);
        } else {
            logmsg("USBDeviceOpen failed: 0x%08x (attempt %d)",
                   kr, attempt);
        }

        usleep(OPEN_RETRY_DELAY_US);
    }

    logmsg("USBDeviceOpen failed after %d attempts, last error: 0x%08x",
           OPEN_RETRY_MAX, kr);
    return kr;
}


/*
 * Send the 6-step boot sequence via vendor control transfers.
 */
static int send_boot_sequence(IOUSBDeviceInterface **dev) {
    uint8_t buf[64];

    for (int i = 0; i < NUM_BOOT_STEPS; i++) {
        const boot_step_t *step = &boot_sequence[i];
        memset(buf, 0, sizeof(buf));

        IOUSBDevRequest req;
        req.bmRequestType = step->bmRequestType;
        req.bRequest      = step->bRequest;
        req.wValue        = step->wValue;
        req.wIndex        = step->wIndex;
        req.wLength       = step->wLength;

        if (step->is_write) {
            memcpy(buf, boot_cmd, step->wLength);
        }
        req.pData = buf;

        IOReturn kr = (*dev)->DeviceRequest(dev, &req);
        if (kr != kIOReturnSuccess) {
            logmsg("Boot step %d/%d FAILED: 0x%08x (wIndex=0x%04X)",
                   i + 1, (int)NUM_BOOT_STEPS, kr, step->wIndex);
            return -1;
        }

        logmsg("Boot step %d/%d OK (wIndex=0x%04X)",
               i + 1, (int)NUM_BOOT_STEPS, step->wIndex);
    }

    return 0;
}


/* --- Main --- */

int main(int argc, char **argv) {
    openlog("u2702a-boot", LOG_PID, LOG_DAEMON);
    logmsg("Starting U2702A boot (IOKit native)");

    /* Wait for USB bus enumeration after plug-in */
    logmsg("Waiting %ds for USB enumeration...", INITIAL_DELAY_S);
    sleep(INITIAL_DELAY_S);

    /* Check if device is already operational */
    IOUSBDeviceInterface **dev = find_device_interface(
        VID_AGILENT, PID_OPERATIONAL);
    if (dev) {
        logmsg("Device already operational (PID 0x%04X)", PID_OPERATIONAL);
        (*dev)->Release(dev);
        return 0;
    }

    /* Find boot-mode device with retries */
    dev = NULL;
    for (int attempt = 1; attempt <= ENUM_RETRY_MAX; attempt++) {
        dev = find_device_interface(VID_AGILENT, PID_BOOT);
        if (dev) break;
        logmsg("Enum attempt %d/%d: device not found, retrying...",
               attempt, ENUM_RETRY_MAX);
        usleep(ENUM_RETRY_DELAY_US);
    }

    if (!dev) {
        logmsg("No U2702A boot-mode device found");
        return 1;
    }

    /* Open the device (with retry for kIOReturnNotReady) */
    IOReturn kr = open_device_with_retry(dev);
    if (kr != kIOReturnSuccess) {
        logmsg("Cannot open device, giving up");
        (*dev)->Release(dev);
        return 1;
    }

    /* Send the 6-step boot sequence */
    int result = send_boot_sequence(dev);

    /* Close and release */
    (*dev)->USBDeviceClose(dev);
    (*dev)->Release(dev);

    if (result != 0) {
        logmsg("Boot sequence failed");
        return 1;
    }

    logmsg("Boot sequence sent. Waiting for re-enumeration...");

    /* Poll for operational device */
    for (int i = 0; i < POLL_MAX; i++) {
        usleep(POLL_DELAY_US);
        IOUSBDeviceInterface **oper = find_device_interface(
            VID_AGILENT, PID_OPERATIONAL);
        if (oper) {
            double elapsed = (i + 1) * 0.5;
            logmsg("Device operational (PID 0x%04X) after %.1fs",
                   PID_OPERATIONAL, elapsed);
            (*oper)->Release(oper);
            logmsg("Boot complete — device ready");
            return 0;
        }
    }

    logmsg("TIMEOUT: device did not re-enumerate within 20s");
    return 1;
}
