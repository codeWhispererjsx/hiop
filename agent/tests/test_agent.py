import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from hiop_agent.collectors import execute
from hiop_agent.config import AgentConfig
from hiop_agent.queue import DurableQueue

class AgentTests(unittest.TestCase):
    def test_windows_powershell_config_accepts_bom(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"agent.json"
            path.write_text(json.dumps({"backend_url":"https://example.com","data_dir":root}),encoding="utf-8-sig")
            self.assertEqual(AgentConfig.load(path).backend_url,"https://example.com")

    @patch("hiop_agent.collectors.socket.create_connection")
    @patch("hiop_agent.collectors.ping",side_effect=OSError("ICMP unavailable"))
    def test_discovery_falls_back_to_tcp_when_ping_unavailable(self,ping,connection):
        from hiop_agent.collectors import discover_host
        result=discover_host("192.168.1.1",1)
        self.assertTrue(result["reachable"])
        self.assertEqual(result["reachability_source"],"tcp")

    def test_large_network_rejected_before_probing(self):
        from hiop_agent.collectors import discover
        with patch("hiop_agent.collectors.discover_host") as probe:
            with self.assertRaises(ValueError):discover("10.0.0.0/8")
            probe.assert_not_called()

    @patch("hiop_agent.collectors.discover_host",return_value={"target":"192.168.1.1","reachable":True})
    def test_single_host_scan_reports_progress_and_final_result(self,probe):
        from hiop_agent.collectors import discover
        updates=[]
        result=discover("192.168.1.1/32",progress=updates.append)
        self.assertEqual(result["scanned"],1)
        self.assertEqual(len(result["devices"]),1)
        self.assertEqual(updates[0]["scanned"],1)
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

    @patch("hiop_agent.collectors.socket.create_connection")
    @patch("hiop_agent.collectors.ping",return_value={"target":"10.50.21.10","reachable":False,"latency_ms":None,"error":"unreachable"})
    def test_monitoring_uses_same_tcp_fallback_as_discovery(self,ping,connection):
        source,result=execute({"type":"MONITORING","payload":{"target":"10.50.21.10","timeout":1}})
        self.assertEqual(source,"monitoring")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["reachability_source"],"tcp")
    def test_arbitrary_commands_are_rejected(self):
        with self.assertRaises(ValueError):execute({"type":"EXECUTE_COMMAND","payload":{"command":"whoami"}})
    @patch("hiop_agent.collectors.ping",return_value={"target":"127.0.0.1","reachable":True})
    def test_allowlisted_ping(self,_):
        source,result=execute({"type":"PING","payload":{"target":"127.0.0.1"}});self.assertEqual(source,"monitoring");self.assertTrue(result["reachable"])
if __name__=="__main__":unittest.main()
