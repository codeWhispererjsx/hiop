import json, os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

@dataclass(frozen=True)
class AgentConfig:
    backend_url:str;data_dir:Path;heartbeat_seconds:int=60;poll_seconds:int=15;queue_max_items:int=10000;queue_retention_days:int=7;request_timeout_seconds:int=30;allow_insecure_http:bool=False
    @classmethod
    def load(cls,path:Path):
        raw=json.loads(path.read_text(encoding="utf-8"));base=str(raw["backend_url"]).rstrip("/");parsed=urlparse(base)
        allow=bool(raw.get("allow_insecure_http",False))
        if parsed.scheme!="https" and not (allow and parsed.scheme=="http" and parsed.hostname in {"localhost","127.0.0.1"}):raise ValueError("Agent backend URL must use HTTPS; HTTP is allowed only for explicit local test mode")
        data=Path(os.path.expandvars(raw.get("data_dir",r"%ProgramData%\HIOP Agent")))
        return cls(base,data,int(raw.get("heartbeat_seconds",60)),int(raw.get("poll_seconds",15)),int(raw.get("queue_max_items",10000)),int(raw.get("queue_retention_days",7)),int(raw.get("request_timeout_seconds",30)),allow)
