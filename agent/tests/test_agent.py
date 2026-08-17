import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from hiop_agent.collectors import execute
from hiop_agent.config import AgentConfig
from hiop_agent.queue import DurableQueue

class AgentTests(unittest.TestCase):
    def test_production_config_requires_https(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"agent.json";path.write_text(json.dumps({"backend_url":"http://example.com","data_dir":root}))
            with self.assertRaises(ValueError):AgentConfig.load(path)
    def test_local_test_http_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"agent.json";path.write_text(json.dumps({"backend_url":"http://127.0.0.1:8000","data_dir":root,"allow_insecure_http":True}))
            self.assertEqual(AgentConfig.load(path).backend_url,"http://127.0.0.1:8000")
    def test_queue_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            queue=DurableQueue(Path(root)/"queue.db",max_items=2)
            queue.add("icmp",{"n":1},"same");queue.add("icmp",{"n":2},"same");queue.add("icmp",{"n":3},"third");queue.add("icmp",{"n":4},"fourth")
            self.assertEqual(queue.count(),2);self.assertEqual([x["observation_id"] for x in queue.ready()],["third","fourth"]);queue.close()
    def test_arbitrary_commands_are_rejected(self):
        with self.assertRaises(ValueError):execute({"type":"EXECUTE_COMMAND","payload":{"command":"whoami"}})
    @patch("hiop_agent.collectors.ping",return_value={"target":"127.0.0.1","reachable":True})
    def test_allowlisted_ping(self,_):
        source,result=execute({"type":"PING","payload":{"target":"127.0.0.1"}});self.assertEqual(source,"monitoring");self.assertTrue(result["reachable"])
if __name__=="__main__":unittest.main()
