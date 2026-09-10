import argparse, logging, time
from pathlib import Path
from .client import AgentClient
from .config import AgentConfig

def run(config_path:Path,stop_event=None):
    config=AgentConfig.load(config_path);config.data_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=config.data_dir/"agent.log",level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
    client=AgentClient(config);last_heartbeat=0;delay=1
    while not (stop_event and stop_event.is_set()):
        try:
            if time.monotonic()-last_heartbeat>=config.heartbeat_seconds:client.heartbeat();last_heartbeat=time.monotonic()
            client.flush();client.poll_jobs();delay=1
        except Exception as exc:logging.warning("Agent cycle failed safely: %s",type(exc).__name__);delay=min(300,delay*2)
        if stop_event:stop_event.wait(max(config.poll_seconds,delay))
        else:time.sleep(max(config.poll_seconds,delay))

def main():
    parser=argparse.ArgumentParser(description="HIOP Local Agent");parser.add_argument("--config",type=Path,required=True);parser.add_argument("--enroll");parser.add_argument("--enroll-prompt",action="store_true");args=parser.parse_args()
    if args.enroll or args.enroll_prompt:
        token=input("Paste your HIOP connection code: ").strip() if args.enroll_prompt else args.enroll
        if not token:raise RuntimeError("Connection code is required.")
        print("Connecting...")
        config=AgentConfig.load(args.config);config.data_dir.mkdir(parents=True,exist_ok=True);AgentClient(config).enroll(token);print("Connected.")
    else:run(args.config)
if __name__=="__main__":main()
