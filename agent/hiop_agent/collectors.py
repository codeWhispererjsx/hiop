import ipaddress, re, socket, subprocess, time
from concurrent.futures import ThreadPoolExecutor

def ping(target,timeout=3):
    started=time.perf_counter()
    result=subprocess.run(["ping","-n","1","-w",str(int(timeout*1000)),str(target)],capture_output=True,text=True,timeout=timeout+2,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
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

def discover(cidr,max_hosts=1024,concurrency=32,timeout=2):
    network=ipaddress.ip_network(cidr,strict=False);hosts=list(network.hosts())
    if len(hosts)>max_hosts:raise ValueError("Discovery range exceeds approved job limit")
    with ThreadPoolExecutor(max_workers=min(concurrency,64)) as pool:results=list(pool.map(lambda host:ping(host,timeout),hosts))
    return {"network":str(network),"devices":[x for x in results if x["reachable"]],"scanned":len(results)}

def execute(job):
    kind=job["type"];payload=job.get("payload") or {}
    if kind in {"PING","MONITORING"}:return "monitoring",ping(payload["target"],min(float(payload.get("timeout",3)),10))
    if kind=="DNS_LOOKUP":return "dns",dns_lookup(payload["target"])
    if kind=="ARP_SNAPSHOT":return "arp",arp_snapshot()
    if kind=="DISCOVERY":return "discovery",discover(payload["cidr"],min(int(payload.get("max_hosts",1024)),4096),min(int(payload.get("concurrency",32)),64),min(float(payload.get("timeout",2)),10))
    if kind=="SNMP_POLL":raise RuntimeError("SNMP polling requires a configured scoped credential adapter")
    if kind=="AD_ENRICHMENT":raise RuntimeError("Active Directory collection requires a configured scoped connection adapter")
    raise ValueError("Unsupported job type")
