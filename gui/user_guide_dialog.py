"""
In-app user guide.

A dialog with the key things a new user needs to know to get going —
plus pointers to the detailed docs in the repo (README, SCPI_COMMANDS,
ARCHITECTURE). Kept inside the bundle so it's available offline and
survives if the GitHub repo goes away.

The content is a single HTML string. Edits go in ``_GUIDE_HTML``
below. Links to external docs are clickable (opened via the default
browser); internal links (e.g. jumps within this dialog) use anchor
navigation.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
    QLabel,
)


_GUIDE_HTML = """
<h2>LabTestBench — User Guide</h2>

<p><em>Multi-instrument lab bench app for oscilloscopes, DMMs, and
function generators. Built around an ESP32-S3 USB bridge so Mac users
can drive instruments macOS's USB stack can't natively talk to.</em></p>

<h3>Getting started</h3>

<ol>
<li><b>Plug in the ESP32-S3 bridge</b> to your Mac's USB. A
    <code>/dev/cu.usbserial-…</code> port will appear.</li>
<li><b>Connect the instrument</b> to the ESP32's second USB port (for
    the Agilent U2702A) or via the instrument's RS-232 port with a
    USB-to-RS232 adapter (for the Agilent 33120A). See
    <code>README.md</code> for the VCC wire-wrap detail required for
    U2702A.</li>
<li><b>Launch LabTestBench.</b> The launcher window lists every
    instrument that responded to <code>*IDN?</code>, plus a "Demo
    mode" section with every registered model for hardware-free
    testing.</li>
<li><b>Click Open</b> on the row you want. The matching window
    opens — scope, DMM, or function generator. Multiple windows
    can be open at once.</li>
</ol>

<h3>Oscilloscope window basics</h3>

<ul>
<li><b>Channels</b> — toggle CH buttons in the right panel. Each
    channel has its own V/div knob (drag or click to type), offset
    knob, coupling (DC/AC), and probe factor.</li>
<li><b>Timebase</b> — T/div and horizontal position knobs at the
    top of the right panel.</li>
<li><b>Trigger</b> — level knob + source/slope/sweep/coupling. Use
    Mode: Pulse Width to switch to glitch (pulse-width) trigger;
    the pulse-width panel appears below with polarity / qualifier
    / threshold controls.</li>
<li><b>Run / Stop / Single</b> — top toolbar. Run for continuous
    acquisition, Single for one shot.</li>
<li><b>Measurements</b> — toggle buttons below the waveform.
    Click a measurement value to set cursors at the relevant
    positions; hover over a value to highlight the regions on
    the waveform.</li>
<li><b>Cursors</b> — the Cursor Mode carousel in the Utility
    panel cycles through Off / Time / Voltage / Both. Drag the
    cursor lines on the plot; the readout bar below shows ΔT,
    1/ΔT, ΔV.</li>
<li><b>FFT</b> — toggle in the FFT panel. A dedicated FFT pane
    appears below the waveform area (resizable via the splitter)
    and works in both combined and split view. Hover over the
    FFT for a live frequency + magnitude readout.</li>
<li><b>Math</b> — CH1+CH2 / CH1−CH2 / CH1×CH2 / CH1÷CH2 in the
    Math panel. Result is a virtual channel with its own
    V/div and offset knobs.</li>
<li><b>Reference waveforms</b> — View menu → Save Reference CH1 /
    CH2 to snapshot the current trace; Clear References removes
    the snapshots.</li>
</ul>

<h3>Function generator window basics</h3>

<ul>
<li><b>Waveform shape</b> — Sine / Square / Triangle / Ramp /
    Noise / DC. Pick from the grid.</li>
<li><b>Frequency / Amplitude / Offset</b> — big knobs in their
    own panels. Frequency panel has SI-decade preset buttons
    (1 Hz through 10 MHz) for quick jumps.</li>
<li><b>Duty cycle</b> — only active for square waves; grayed
    out otherwise. 20%–80% range on the 33120A.</li>
<li><b>Output load</b> — 50 Ω or HiZ (INF). Affects the
    displayed amplitude correction (the instrument's output
    impedance is always 50 Ω).</li>
<li><b>OUTPUT button</b> — big red when on, gray when off.
    Always starts off on window open for safety — the driver
    enforces <code>OUTP OFF</code> on every connection.</li>
</ul>

<h3>Session save and restore</h3>

<p>File → Save Session (Ctrl+S) writes a JSON file with all
channel, timebase, trigger, cursor, and measurement settings.
Load Session (Ctrl+O) restores them. The app auto-saves the
last session on exit and restores it on startup, so picking
up where you left off "just works" in the usual case.</p>

<h3>Export</h3>

<p>File → Export (Ctrl+E) opens the unified export dialog:</p>

<ul>
<li><b>Data tab</b> — CSV, JSON, or NumPy (.npz). Includes
    settings metadata and computed measurements per channel.</li>
<li><b>Graph tab</b> — PNG or PDF. Configurable elements
    (measurements, cursors, trigger overlay, V/div and T/div
    labels, GND markers). Dark or light theme independent of
    the app theme.</li>
</ul>

<p>Ctrl+Shift+E is the quick-export CSV shortcut (skips the
dialog).</p>

<h3>Headless scripting</h3>

<p>The same driver objects the GUI uses are scriptable without
Qt:</p>

<pre>from automation import LabSession

with LabSession() as lab:
    scope = lab.open("U2702A", demo=True)
    scope.apply_setting("channel.1.vdiv", 0.5)
    scope.apply_setting("trigger.level", 1.0)
    result = scope.acquire()
    print(result.waveforms[0].measurements["vpp"])

    # Multiple instruments in one session — the lab-bench case.
    dmm = lab.open("Generic-DMM", demo=True)
    gen = lab.open("33120A",      demo=True)</pre>

<p>Use <code>ActionRecorder</code> to capture a sequence of
driver calls to JSON and replay it later.</p>

<h3>Settings (Ctrl+,)</h3>

<ul>
<li><b>Controls tab</b> — knob scroll-wheel toggle, auto-discovery
    toggle (for the connection dialog's <code>*IDN?</code> probe),
    theme (Dark / Light; restart required).</li>
<li><b>Channel Colors tab</b> — per-channel trace color.</li>
<li><b>Probes tab</b> — per-channel probe attenuation factor.</li>
</ul>

<h3>Troubleshooting</h3>

<ul>
<li><b>Scope doesn't appear in the launcher's Detected list</b> —
    the U2702A's boot-mode firmware (PID 0x2818) doesn't answer
    <code>*IDN?</code>; the ESP32 bridge boots it into operational
    mode (PID 0x2918) first. Wait a few seconds after plugging in
    and Refresh.</li>
<li><b>"OUTPUT: OFF" on function generator but signal is live</b> —
    shouldn't happen with our driver (safety invariant), but if
    the instrument was set externally, Refresh / re-open the
    window to re-read state.</li>
<li><b>Port appears but <code>*IDN?</code> times out</b> — try
    Settings → Controls → disable Auto-discovery, then pick the
    model manually from the Demo section and set the port in the
    bridge config.</li>
<li><b>Logs</b> — <code>~/.config/U2702A/oscilloscope.log</code>
    captures everything from INFO up. Useful for debugging
    acquisition or connection issues.</li>
</ul>

<h3>More</h3>

<ul>
<li><a href="https://github.com/">README.md</a> — full install
    guide and architecture overview</li>
<li><code>SCPI_COMMANDS.md</code> — every SCPI command we issue
    to the U2702A, with Wireshark-verified formats</li>
<li><code>ARCHITECTURE.md</code> — the three-layer design
    (instrument / processing / gui) and the lab-bench framework</li>
<li><code>VERSIONING.md</code> — roadmap and feature staging</li>
</ul>
"""


class UserGuideDialog(QDialog):
    """Offline user guide — bundles the key usage notes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Guide — LabTestBench")
        self.setMinimumSize(640, 720)
        self.resize(720, 820)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        header = QLabel("User Guide")
        hf = QFont()
        hf.setPointSize(16)
        hf.setBold(True)
        header.setFont(hf)
        root.addWidget(header)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        # External URLs open in the system browser; internal anchors
        # stay in the widget.
        browser.anchorClicked.connect(self._on_anchor_clicked)
        browser.setHtml(_GUIDE_HTML)
        root.addWidget(browser, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _on_anchor_clicked(self, url: QUrl):
        # Hand http(s) URLs to the OS default browser; ignore empty
        # / internal anchors (QTextBrowser handles those on its own
        # when setSource is used — we keep setHtml so no-op).
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
