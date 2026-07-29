from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "v2" / "scripts" / "fetch_private_funds.py"
SPEC = importlib.util.spec_from_file_location("fetch_private_funds", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrivateAmacTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE._AMAC_IPS = ["1.1.1.1", "2.2.2.2"]
        MODULE._AMAC_PREFERRED_IP = None

    def tearDown(self) -> None:
        MODULE._AMAC_IPS = None
        MODULE._AMAC_PREFERRED_IP = None

    def test_system_dns_and_pinned_ips_are_all_rotated(self) -> None:
        self.assertIsNone(MODULE.amac_ip_for_attempt(0))
        self.assertEqual(MODULE.amac_ip_for_attempt(1), "1.1.1.1")
        self.assertEqual(MODULE.amac_ip_for_attempt(2), "2.2.2.2")
        self.assertIsNone(MODULE.amac_ip_for_attempt(3))

    def test_post_json_recovers_on_alternate_transport(self) -> None:
        transports: list[str | None] = []

        def fake_fetch(url, headers, body=None, ip=None):
            transports.append(ip)
            if len(transports) < 3:
                raise RuntimeError("empty reply")
            return json.dumps({"content": [{"managerName": "测试管理人"}], "last": True})

        with (
            mock.patch.object(MODULE, "curl_fetch", side_effect=fake_fetch),
            mock.patch.object(MODULE.time, "sleep"),
        ):
            result = MODULE.post_json(
                "/pof/manager/query",
                {"officeProvince": "陕西省"},
                page=0,
                referer=MODULE.MANAGER_REFERER,
            )

        self.assertEqual(result["content"][0]["managerName"], "测试管理人")
        self.assertEqual(transports, [None, "1.1.1.1", "2.2.2.2"])

    def test_curl_uses_http1_and_retries_empty_responses(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b"{}"
            run.return_value.stderr = b""
            MODULE.curl_fetch(
                "https://gs.amac.org.cn/example",
                {"User-Agent": "test"},
                body=b"{}",
                ip="1.1.1.1",
            )
        command = run.call_args.args[0]
        self.assertIn("--http1.1", command)
        self.assertIn("--retry-all-errors", command)
        self.assertIn("--resolve", command)


if __name__ == "__main__":
    unittest.main()
