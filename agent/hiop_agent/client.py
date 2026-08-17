import json, socket, time, urllib.error, urllib.request
from datetime import datetime, timezone
from . import __version__
from .collectors import execute
from .credential_store import load_credential, save_credential
from .queue import DurableQueue

class AgentClient:
    def __init__(self,config):
        self.config=config;self.started=time.monotonic();self.credential_path=config.data_dir/"credential.dpapi";self.queue=DurableQueue(config.data_dir/"queue.db",config.queue_max_items,config.queue_retention_days);self.last_job=None
    def request(self,method,path,body=None,authenticated=True):
        headers={"Content-Type":"application/json","User-Agent":f"HIOP-Agent/{__version__}"}
        if authenticated:headers["Authorization"]="Agent "+load_credential(self.credential_path)
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.config.backend_url+"/api/v1"+path,data=data,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=self.config.request_timeout_seconds) as response:return json.loads(response.read() or b"{}")
    def enroll(self,token):
        result=self.request("POST","/agent/enroll",{"enrollment_token":token,"hostname":socket.gethostname(),"version":__version__,"api_version":1},False);save_credential(self.credential_path,result["credential"]);return result
    def heartbeat(self):
        return self.request("POST","/agent/heartbeat",{"version":__version__,"hostname":socket.gethostname(),"uptime_seconds":int(time.monotonic()-self.started),"pending_queue":self.queue.count(),"queue_capacity":self.config.queue_max_items,"last_successful_job":self.last_job})
    def flush(self):
        for item in self.queue.ready():
            attempts=item.pop("attempts")
            try:self.request("POST","/agent/observations",item);self.queue.ack(item["observation_id"])
            except (OSError,urllib.error.HTTPError):self.queue.retry(item["observation_id"],attempts)
    def poll_jobs(self):
        for job in self.request("GET","/agent/jobs"):
            self.request("POST",f"/agent/jobs/{job['id']}",{"status":"started"})
            try:
                source,payload=execute(job);self.queue.add(source,{"job_id":str(job["id"]),"result":payload});self.last_job=str(job["id"]);self.request("POST",f"/agent/jobs/{job['id']}",{"status":"completed"})
            except Exception as exc:self.request("POST",f"/agent/jobs/{job['id']}",{"status":"failed","error":str(exc)[:1000]})
