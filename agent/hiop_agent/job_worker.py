"""Isolated collector process; its entire process tree can be stopped."""
import os
from .collectors import execute

def collect(job, output):
    if os.name != "nt": os.setsid()
    try:
        source, result = execute(job,progress=lambda result:output.send({"progress":True,"source":"discovery","result":result}))
        output.send({"source":source,"result":result})
    except Exception as exc:
        output.send({"error":str(exc)[:1000]})
    finally:
        output.close()
