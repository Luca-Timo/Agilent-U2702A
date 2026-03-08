#!/usr/bin/env python3
"""Parse USBTMC/SCPI commands from USB pcapng capture of Agilent U2702A."""

import subprocess
import sys
from collections import OrderedDict


def extract_usbtmc_data(pcapng_file, device_addr=6):
    """Extract USBTMC payloads from pcapng using tshark."""
    cmd = [
        "tshark", "-r", pcapng_file,
        "-Y", f"usb.device_address == {device_addr} && usb.capdata",
        "-T", "fields",
        "-e", "frame.number",
        "-e", "frame.time_relative",
        "-e", "usb.endpoint_address",
        "-e", "usb.capdata",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"tshark error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip().split("\n")


def decode_usbtmc_payload(hex_data):
    """Decode USBTMC header and extract SCPI payload.

    USBTMC header (12 bytes):
      Byte 0: MsgID (1=DEV_DEP_MSG_OUT, 2=REQUEST_DEV_DEP_MSG_IN)
      Byte 1: bTag
      Byte 2: bTagInverse
      Byte 3: Reserved
      Bytes 4-7: TransferSize (uint32 LE)
      Bytes 8-11: bmTransferAttributes + reserved
    """
    raw = bytes.fromhex(hex_data.replace(":", ""))
    if len(raw) < 12:
        return None, None, None

    msg_id = raw[0]
    transfer_size = int.from_bytes(raw[4:8], "little")
    payload = raw[12:12 + transfer_size]

    # msg_id 1 = DEV_DEP_MSG_OUT (command to device)
    # msg_id 2 = REQUEST_DEV_DEP_MSG_IN (request response)
    # Response data also uses msg_id 2 but comes on endpoint 0x82

    return msg_id, transfer_size, payload


def is_printable_scpi(data):
    """Check if payload looks like ASCII SCPI text."""
    try:
        text = data.decode("ascii", errors="strict")
        return all(c.isprintable() or c in "\r\n\t" for c in text.rstrip("\x00"))
    except (UnicodeDecodeError, AttributeError):
        return False


def main():
    pcapng_file = sys.argv[1] if len(sys.argv) > 1 else "/Users/lucabresch/Documents/GitHub/Agilent-U2702A/USB_dump_ch1_2_single.pcapng"

    print("=" * 80)
    print("U2702A USB/SCPI Protocol Extraction")
    print("=" * 80)

    lines = extract_usbtmc_data(pcapng_file)

    commands = []  # (timestamp, direction, scpi_text)
    command_set = OrderedDict()  # unique commands
    query_responses = []  # (query, response) pairs

    pending_query = None

    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        frame_num = parts[0]
        timestamp = float(parts[1])
        endpoint = int(parts[2], 16)
        hex_data = parts[3]

        msg_id, size, payload = decode_usbtmc_payload(hex_data)
        if payload is None or size == 0:
            continue

        # Endpoint 0x01 = Bulk OUT (host to device)
        # Endpoint 0x82 = Bulk IN (device to host)

        if endpoint == 0x01 and msg_id == 1:
            # Command sent to device
            if is_printable_scpi(payload):
                text = payload.decode("ascii").rstrip("\x00").strip()
                if text:
                    commands.append((timestamp, "OUT", text))

                    # Track unique commands (strip parameters for grouping)
                    base_cmd = text.split(" ")[0] if " " in text else text
                    if base_cmd not in command_set:
                        command_set[base_cmd] = []
                    command_set[base_cmd].append(text)

                    if text.endswith("?"):
                        pending_query = text

        elif endpoint == 0x82 and msg_id == 2:
            # Response from device
            if is_printable_scpi(payload):
                text = payload.decode("ascii").rstrip("\x00").strip()
                if text:
                    commands.append((timestamp, "IN", text))
                    if pending_query:
                        query_responses.append((pending_query, text))
                        pending_query = None
            else:
                # Binary data (likely waveform)
                commands.append((timestamp, "IN_BIN", f"[{len(payload)} bytes binary data]"))
                if pending_query:
                    query_responses.append((pending_query, f"[{len(payload)} bytes binary]"))
                    pending_query = None

    # Print chronological log
    print(f"\n{'='*80}")
    print("CHRONOLOGICAL COMMAND LOG")
    print(f"{'='*80}")
    print(f"Total packets with SCPI data: {len(commands)}")
    print(f"{'='*80}\n")

    for ts, direction, text in commands:
        arrow = "-->" if direction == "OUT" else "<--" if direction == "IN" else "<~="
        print(f"[{ts:10.3f}s] {arrow} {text}")

    # Print unique commands
    print(f"\n{'='*80}")
    print("UNIQUE SCPI COMMANDS (Queries)")
    print(f"{'='*80}\n")

    for cmd in sorted(command_set.keys()):
        if cmd.endswith("?"):
            examples = command_set[cmd][:3]
            print(f"  {cmd}")

    print(f"\n{'='*80}")
    print("UNIQUE SCPI COMMANDS (Set/Action)")
    print(f"{'='*80}\n")

    for cmd in sorted(command_set.keys()):
        if not cmd.endswith("?"):
            examples = command_set[cmd]
            unique_examples = list(OrderedDict.fromkeys(examples))[:5]
            if len(unique_examples) == 1:
                print(f"  {unique_examples[0]}")
            else:
                print(f"  {cmd}")
                for ex in unique_examples:
                    print(f"    -> {ex}")

    # Print query/response pairs
    print(f"\n{'='*80}")
    print("QUERY/RESPONSE PAIRS")
    print(f"{'='*80}\n")

    seen_pairs = OrderedDict()
    for query, response in query_responses:
        key = query
        if key not in seen_pairs:
            seen_pairs[key] = []
        if response not in [r for r in seen_pairs[key]]:
            seen_pairs[key].append(response)

    for query, responses in seen_pairs.items():
        if len(responses) == 1:
            print(f"  {query:45s} => {responses[0]}")
        else:
            print(f"  {query}")
            for r in responses[:10]:
                print(f"    => {r}")

    # Categorize commands
    print(f"\n{'='*80}")
    print("CATEGORIZED COMMANDS")
    print(f"{'='*80}\n")

    categories = {
        "System/IEEE488": [],
        "Channel": [],
        "Timebase": [],
        "Trigger": [],
        "Acquisition": [],
        "Waveform": [],
        "Measurement": [],
        "Function/Math": [],
        "Display": [],
        "Output": [],
        "Other": [],
    }

    for cmd in command_set.keys():
        upper = cmd.upper()
        if upper.startswith("*"):
            categories["System/IEEE488"].append(cmd)
        elif any(upper.startswith(p) for p in ["CHAN", ":CHAN"]):
            categories["Channel"].append(cmd)
        elif any(upper.startswith(p) for p in ["TIM", ":TIM", "TIMEBASE", ":TIMEBASE"]):
            categories["Timebase"].append(cmd)
        elif any(upper.startswith(p) for p in ["TRIG", ":TRIG"]):
            categories["Trigger"].append(cmd)
        elif any(upper.startswith(p) for p in ["ACQ", ":ACQ"]):
            categories["Acquisition"].append(cmd)
        elif any(upper.startswith(p) for p in ["WAV", ":WAV"]):
            categories["Waveform"].append(cmd)
        elif any(upper.startswith(p) for p in ["MEAS", ":MEAS"]):
            categories["Measurement"].append(cmd)
        elif any(upper.startswith(p) for p in ["FUNC", ":FUNC"]):
            categories["Function/Math"].append(cmd)
        elif any(upper.startswith(p) for p in ["DISP", ":DISP"]):
            categories["Display"].append(cmd)
        elif any(upper.startswith(p) for p in ["OUTP", ":OUTP"]):
            categories["Output"].append(cmd)
        else:
            categories["Other"].append(cmd)

    for cat, cmds in categories.items():
        if cmds:
            print(f"  [{cat}]")
            for cmd in sorted(cmds):
                examples = list(OrderedDict.fromkeys(command_set[cmd]))[:3]
                for ex in examples:
                    print(f"    {ex}")
            print()

    # Summary stats
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Total SCPI exchanges: {len(commands)}")
    print(f"  Unique base commands: {len(command_set)}")
    print(f"  Query commands:       {sum(1 for c in command_set if c.endswith('?'))}")
    print(f"  Set/action commands:  {sum(1 for c in command_set if not c.endswith('?'))}")
    print(f"  Capture duration:     {commands[-1][0]:.1f}s" if commands else "  No commands found")


if __name__ == "__main__":
    main()
