import ipaddress, os, re, socket, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed

def ping(target,timeout=3):
    started=time.perf_counter()
    command=["ping","-n","1","-w",str(int(timeout*1000)),str(target)] if os.name=="nt" else ["ping","-c","1","-W",str(max(1,int(timeout))),str(target)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=timeout+2,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    latency=round((time.perf_counter()-started)*1000,2)
    return {"target":str(target),"reachable":result.returncode==0,"latency_ms":latency if result.returncode==0 else None,"error":None if result.returncode==0 else "unreachable"}

def dns_lookup(target,timeout=5):
    previous=socket.getdefaulttimeout();socket.setdefaulttimeout(timeout)
    try:return {"target":target,"hostname":socket.gethostbyaddr(target)[0]}
    except (OSError,socket.error) as exc:return {"target":target,"hostname":None,"error":type(exc).__name__}
    finally:socket.setdefaulttimeout(previous)

def arp_snapshot():
    result=subprocess.run(["arp","-a"],capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    entries=[]
    for line in result.stdout.splitlines():
        match=re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})\s+(\w+)",line,re.I)
        if match:entries.append({"ip":match.group(1),"mac":match.group(2).replace("-",":").lower(),"state":match.group(3)})
    return {"entries":entries,"authoritative":False}

def discover_host(host,timeout):
    try: observation=ping(host,timeout)
    except (OSError,subprocess.TimeoutExpired):
        observation={"target":str(host),"reachable":False,"latency_ms":None,"error":"no_response"}
    observation["reachability_source"]="icmp" if observation["reachable"] else None
    if not observation["reachable"]:
        for port in (443,80,445):
            try:
                with socket.create_connection((str(host),port),timeout=min(timeout,0.5)):
                    observation.update(reachable=True,error=None,reachability_source="tcp",port=port)
                    break
            except OSError: pass
    if not observation["reachable"]: observation["error"]="no_response"
    return observation

def discover(cidr,max_hosts=1024,concurrency=32,timeout=2,progress=None):
    network=ipaddress.ip_network(cidr,strict=False)
    if network.num_addresses>max_hosts+2:raise ValueError("Discovery range exceeds approved job limit")
    hosts=list(network.hosts())
    if len(hosts)>max_hosts:raise ValueError("Discovery range exceeds approved job limit")
    devices=[];batch=[];completed=0
    with ThreadPoolExecutor(max_workers=max(1,min(concurrency,64))) as pool:
        futures=[pool.submit(discover_host,host,timeout) for host in hosts]
        for future in as_completed(futures):
            item=future.result();completed+=1
            if item["reachable"]:devices.append(item);batch.append(item)
            if progress and (completed%16==0 or completed==len(hosts)):
                progress({"network":str(network),"devices":batch,"scanned":completed});batch=[]
    return {"network":str(network),"devices":devices,"scanned":completed,"unresponsive":completed-len(devices)}


def execute(job,progress=None):
    kind=job["type"];payload=job.get("payload") or {}
    if kind in {"PING","MONITORING"}:return "monitoring",ping(payload["target"],min(float(payload.get("timeout",3)),10))
    if kind=="DNS_LOOKUP":return "dns",dns_lookup(payload["target"])
    if kind=="ARP_SNAPSHOT":return "arp",arp_snapshot()
    if kind=="DISCOVERY":return "discovery",discover(payload["cidr"],min(int(payload.get("max_hosts",1024)),4096),min(int(payload.get("concurrency",32)),64),min(float(payload.get("timeout",2)),10),progress=progress)
    if kind=="SNMP_POLL":raise RuntimeError("SNMP polling requires a configured scoped credential adapter")
    if kind=="AD_ENRICHMENT":raise RuntimeError("Active Directory collection requires a configured scoped connection adapter")
    raise ValueError("Unsupported job type")
