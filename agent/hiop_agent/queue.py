import json, sqlite3, time, uuid
from datetime import datetime, timezone
from pathlib import Path

class DurableQueue:
    def __init__(self,path:Path,max_items:int=10000,retention_days:int=7):
        path.parent.mkdir(parents=True,exist_ok=True);self.max_items=max_items;self.retention_seconds=retention_days*86400
        self.db=sqlite3.connect(path);self.db.execute("PRAGMA journal_mode=WAL");self.db.execute("CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,source TEXT NOT NULL,observed_at TEXT NOT NULL,payload TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,created REAL NOT NULL)");self.db.commit();self.prune()
    def add(self,source,payload,observation_id=None):
        now=time.time();oid=observation_id or str(uuid.uuid4());self.prune()
        while self.count()>=self.max_items:self.db.execute("DELETE FROM observations WHERE id=(SELECT id FROM observations ORDER BY created LIMIT 1)")
        self.db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,0,0,?)",(oid,source,datetime.now(timezone.utc).isoformat(),json.dumps(payload,separators=(",",":")),now));self.db.commit();return oid
    def ready(self,limit=50):
        rows=self.db.execute("SELECT id,source,observed_at,payload,attempts FROM observations WHERE next_attempt<=? ORDER BY created LIMIT ?",(time.time(),limit)).fetchall()
        return [{"observation_id":r[0],"source":r[1],"observed_at":r[2],"schema_version":1,"payload":json.loads(r[3]),"attempts":r[4]} for r in rows]
    def ack(self,oid):self.db.execute("DELETE FROM observations WHERE id=?",(oid,));self.db.commit()
    def retry(self,oid,attempts):
        delay=min(300,2**min(attempts+1,8));self.db.execute("UPDATE observations SET attempts=?,next_attempt=? WHERE id=?",(attempts+1,time.time()+delay,oid));self.db.commit()
    def count(self):return self.db.execute("SELECT count(*) FROM observations").fetchone()[0]
    def prune(self):self.db.execute("DELETE FROM observations WHERE created<?",(time.time()-self.retention_seconds,));self.db.commit()
    def close(self):self.db.close()
