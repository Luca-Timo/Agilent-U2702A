"""
Automation layer — headless scripting on top of the same drivers the GUI uses.

Scripts never import from ``gui/``. They go through :class:`LabSession`
to open drivers, :class:`ActionRecorder` to capture a sequence of
actions (for replay or to learn from a GUI session), and optionally
the drivers' ``apply_setting`` / ``read_setting`` generic API.

Example:

    from automation import LabSession

    with LabSession() as lab:
        scope = lab.open("U2702A", demo=True)    # pick real bridge when available
        scope.apply_setting("channel.1.vdiv", 0.5)
        scope.apply_setting("trigger.level", 1.0)
        result = scope.acquire()
        for wf in result.waveforms:
            print(wf.channel, wf.measurements["vpp"])
"""

from automation.session import LabSession
from automation.recorder import Action, ActionRecorder

__all__ = ["LabSession", "ActionRecorder", "Action"]
