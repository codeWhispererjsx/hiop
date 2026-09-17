import json, socket, time, urllib.error, urllib.request
from datetime import datetime, timezone
from . import __version__
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
        import multiprocessing
        from .job_worker import collect
        context=multiprocessing.get_context("spawn")
        for job in self.request("GET","/agent/jobs"):
            # Do not claim work on servers that lack cancellable job support.
            self.request("GET",f"/agent/jobs/{job['id']}")
            state=self.request("POST",f"/agent/jobs/{job['id']}",{"status":"started"})
            if state["status"] != "started": continue
            parent, child=context.Pipe(duplex=False)
            process=context.Process(target=collect,args=(job,child))
            process.start();child.close()
            deadline=time.monotonic()+job.get("timeout_seconds",120)
            last_heartbeat=time.monotonic()
            try:
                while True:
                    state=self.request("GET",f"/agent/jobs/{job['id']}")["status"]
                    if state in {"cancelling","cancelled"}:
                        stop_process(process)
                        self.request("POST",f"/agent/jobs/{job['id']}",{"status":"cancelled"})
                        break
                    if time.monotonic()>=deadline:
                        stop_process(process)
                        self.request("POST",f"/agent/jobs/{job['id']}",{"status":"timed_out","error":"Scan exceeded its time limit"})
                        break
                    if time.monotonic()-last_heartbeat>=self.config.heartbeat_seconds:
                        self.heartbeat();last_heartbeat=time.monotonic()
                    if parent.poll(1):
                        result=parent.recv()
                        if result.get("error"): raise RuntimeError(result["error"])
                        oid=self.queue.add(result["source"],{"job_id":str(job["id"]),"result":result["result"]})
                        if result.get("progress"):
                            self.flush()
                            continue
                        # Final discovery results contain all hosts; require acknowledgement
                        # before reporting completion, even when earlier batches are delayed.
                        observation={"observation_id":oid,"source":result["source"],"observed_at":datetime.now(timezone.utc).isoformat(),"schema_version":1,"payload":{"job_id":str(job["id"]),"result":result["result"]}}
                        self.request("POST","/agent/observations",observation)
                        self.queue.ack(oid)
                        self.last_job=str(job["id"])
                        completion=self.request("POST",f"/agent/jobs/{job['id']}",{"status":"completed"})
                        if completion["status"]=="cancelling":
                            stop_process(process)
                            self.request("POST",f"/agent/jobs/{job['id']}",{"status":"cancelled"})
                        break
                    if not process.is_alive(): raise RuntimeError("Collector stopped without a result")
            except Exception as exc:
                stop_process(process)
                self.request("POST",f"/agent/jobs/{job['id']}",{"status":"failed","error":str(exc)[:1000]})
            finally:
                stop_process(process)
                parent.close()


def stop_process(process):
    import os, signal, subprocess
    if process.is_alive():
        if os.name == "nt":
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        else:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: process.kill()
        process.join(timeout=5)
        if process.is_alive(): process.kill();process.join(timeout=5)
    else: process.join(timeout=1)
