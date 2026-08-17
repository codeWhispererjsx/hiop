import os, threading
import win32event, win32service, win32serviceutil, servicemanager
from pathlib import Path
from .runner import run

class HIOPAgentService(win32serviceutil.ServiceFramework):
    _svc_name_="HIOPLocalAgent";_svc_display_name_="HIOP Local Hotel Agent";_svc_description_="Secure outbound observation and collection service for HIOP."
    def __init__(self,args):
        super().__init__(args);self.stop_handle=win32event.CreateEvent(None,0,0,None);self.stop_event=threading.Event()
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING);self.stop_event.set();win32event.SetEvent(self.stop_handle)
    def SvcDoRun(self):
        servicemanager.LogInfoMsg("HIOP Local Agent starting");run(Path(os.environ.get("HIOP_AGENT_CONFIG",r"C:\ProgramData\HIOP Agent\agent.json")),self.stop_event)
if __name__=="__main__":win32serviceutil.HandleCommandLine(HIOPAgentService)
