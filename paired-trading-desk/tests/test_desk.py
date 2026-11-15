import json
import os
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path

from desk.config import load_config
from desk.engine import launch_return, plan_launch_exit, run_cycle
from desk.handoff import (
    HandoffError,
    aihf_mandate,
    assert_live_allowed,
    hummingbot_argv,
    pump_yaml,
    write_handoff,
)
from desk.ledger import append_events, verify
from desk.market import load_fixture_book, load_launches
from desk.agent_api import main as agent_api_main
from desk.session import halt, run_paper
from desk.web import make_server


ROOT = Path(__file__).resolve().parents[1]


class ResearchAndRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(ROOT / "desk.json")
        self.series = load_fixture_book(ROOT / "fixtures" / "bars")
        self.launches = load_launches(ROOT / "fixtures" / "launches.json")

    def test_routes_each_repo_to_its_venue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_cycle(self.cfg, self.series, self.launches, Path(tmp))
        venues = {fill["symbol"]: fill["venue"] for fill in report["fills"]}
        self.assertEqual(venues["AAPL"], "ai_hedge_fund")
        self.assertEqual(venues["BTC-USDT"], "hummingbot")
        self.assertNotIn("CHOP", venues)
        self.assertFalse(report["research"]["CHOP"]["passed"])
        self.assertGreater(report["scores"]["BTC-USDT"], self.cfg.min_vote)
        reasons = {row["symbol"]: row["reason"] for row in report["launches"]}
        self.assertEqual(reasons["DEMO"], "take_profit")
        self.assertEqual(reasons["WAVE"], "stop_loss")
        self.assertEqual(reasons["OLD"], "umur token melewati batas")
        self.assertEqual(reasons["STNK"], "platform di luar daftar")
        self.assertGreater(report["cash_sol"], 1.0)
        self.assertLess(report["cash_usd"], self.cfg.capital_usd)
        self.assertTrue(any(item["symbol"] == "AAPL" for item in report["positions"]))

    def test_kill_switch_blocks_fills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            halt(path, "uji")
            report = run_cycle(self.cfg, self.series, self.launches, path)
        self.assertEqual(report["fills"], [])
        self.assertEqual(report["cash_usd"], self.cfg.capital_usd)
        self.assertEqual(report["cash_sol"], self.cfg.capital_sol)
        self.assertTrue(all(row["status"] == "skipped" for row in report["launches"]))

    def test_order_cap(self) -> None:
        cfg = replace(self.cfg, max_order_usd=100)
        with tempfile.TemporaryDirectory() as tmp:
            report = run_cycle(cfg, self.series, self.launches, Path(tmp))
        for fill in report["fills"]:
            self.assertLessEqual(fill["notional"], 100.01)

    def test_launch_math(self) -> None:
        self.assertAlmostEqual(launch_return(1.4, 0.01), 1.4 * 0.99**2 - 1)
        reason, relative, step = plan_launch_exit([1, 1.1, 1.4, 1.15], 0.01, 0.25, 0.15, 4)
        self.assertEqual((reason, relative, step), ("take_profit", 1.4, 2))
        reason, relative, _step = plan_launch_exit([1, 0.7, 0.5], 0.01, 0.25, 0.15, 4)
        self.assertEqual((reason, relative), ("stop_loss", 0.7))


class LedgerTest(unittest.TestCase):
    def test_chain_detects_a_tampered_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            append_events(path, [{"type": "session", "equity_usd": 1}])
            self.assertEqual(verify(path), 1)
            lines = path.read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            record["event"]["equity_usd"] = 999
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(path)


class HandoffTest(unittest.TestCase):
    def test_paper_files_do_not_carry_a_wallet_key(self) -> None:
        cfg = load_config(ROOT / "desk.json")
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_handoff(Path(tmp), cfg, enable_pump=False)
            pump = paths["pump"].read_text(encoding="utf-8")
            commands = paths["commands"].read_text(encoding="utf-8")
        self.assertIn("enabled: false", pump)
        self.assertIn("extreme_fast_mode: false", pump)
        self.assertIn("${SOLANA_PRIVATE_KEY}", pump)
        self.assertNotIn("5K", pump)
        self.assertIn("binance_paper_trade", commands)
        self.assertIn("schema_version: 2", aihf_mandate(cfg))
        argv = hummingbot_argv(cfg, "BTC-USDT", live=False)
        self.assertIn("exchange=binance_paper_trade", argv)
        self.assertIn("trading_pair=BTC-USDT", argv)

    def test_live_is_refused_without_the_flag_and_without_an_exchange(self) -> None:
        os.environ.pop("PAIRED_DESK_LIVE", None)
        with self.assertRaises(HandoffError):
            assert_live_allowed()
        cfg = replace(load_config(ROOT / "desk.json"), mode="live", live_exchange="")
        with self.assertRaises(HandoffError):
            hummingbot_argv(cfg, "BTC-USDT", live=True)
        with self.assertRaises(HandoffError):
            pump_yaml(replace(cfg, live_pump_buy=1), enabled=False)


class AgentApiTest(unittest.TestCase):
    def test_cycle_halt_and_resume_are_paper_only(self) -> None:
        agent_json(["resume"])
        out = io_cycle()
        self.assertEqual(out["mode"], "paper")
        self.assertGreater(out["equity_usd"], 0)
        self.assertGreater(len(out["fills"]), 0)
        halted = agent_json(["halt", "uji"])
        self.assertEqual(halted["killed"], "uji")
        blocked = io_cycle()
        self.assertEqual(blocked["fills"], [])
        self.assertTrue(agent_json(["resume"])["resumed"])


def agent_json(args: list[str]) -> dict:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = agent_api_main(args)
    if code != 0:
        raise AssertionError(buffer.getvalue())
    return json.loads(buffer.getvalue())


def io_cycle() -> dict:
    return agent_json(["cycle"])


class SessionTest(unittest.TestCase):
    def test_paper_session_writes_a_valid_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_paper(
                Path(tmp),
                cfg=load_config(ROOT / "desk.json"),
                series=load_fixture_book(ROOT / "fixtures" / "bars"),
                launches=load_launches(ROOT / "fixtures" / "launches.json"),
                reset=True,
            )
            self.assertGreater(report["equity_usd"], 0)
            self.assertTrue((Path(tmp) / "ledger.jsonl").exists())


class WebTest(unittest.TestCase):
    def test_dashboard_runs_a_paper_cycle(self) -> None:
        server = make_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
                page = response.read().decode("utf-8")
            self.assertIn("Paired desk", page)
            self.assertIn("Vibe-Trading", page)
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/cycle",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["mode"], "paper")
            self.assertEqual(payload["launches"][0]["reason"], "take_profit")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
                again = response.read().decode("utf-8")
            self.assertIn("take_profit", again)
            self.assertIn("<svg", again)
            halt_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/halt",
                data=b"",
                method="POST",
            )
            urllib.request.urlopen(halt_request).read()
            with urllib.request.urlopen(request) as response:
                halted = json.loads(response.read().decode("utf-8"))
            self.assertEqual(halted["fills"], [])
            self.assertTrue(halted["killed"])
            resume_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/resume",
                data=b"",
                method="POST",
            )
            urllib.request.urlopen(resume_request).read()
            with urllib.request.urlopen(request) as response:
                resumed = json.loads(response.read().decode("utf-8"))
            self.assertIsNone(resumed["killed"])
            self.assertGreater(len(resumed["fills"]), 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
