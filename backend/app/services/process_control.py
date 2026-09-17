"""Terminate only the isolated scan worker and its child commands."""
import os
import signal
import subprocess

def terminate_process(process):
    if process.is_alive():
        if os.name == "nt":
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        else:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: process.kill()
        process.join(timeout=5)
        if process.is_alive(): process.kill();process.join(timeout=5)
    else: process.join(timeout=1)
