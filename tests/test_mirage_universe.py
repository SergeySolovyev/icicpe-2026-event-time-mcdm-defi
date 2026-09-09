"""Offline lifecycle checks: fake collection, real committed raw-evidence replay."""
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from mirage.chain.cache import CachingRpcClient
from mirage.chain.rpc import BlockAnchor, RpcClient
from mirage.discovery.subgraph import Discovery
from mirage.scan import load_snapshot, report_from_snapshot, save_snapshot
from scripts import mirage_capture_universe as runner
from scripts import mirage_summarize_universe as summary


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "mirage/snapshots/mainnet-full-25938082-routes-v2.json.gz"


class Harness:
    def __init__(self, directory):
        fixture = load_snapshot(FIXTURE)
        self.anchor = BlockAnchor(**fixture["anchor"])
        # Both rows have factory-oracle observations; no scientific/ML imports needed.
        self.rows = {r["market_id"]: r for r in fixture["rows"]
                     if r["market_id"].startswith(("0x94b823", "0xbd1ad3"))}
        assert len(self.rows) == 2
        self.ids = sorted(self.rows)
        self.source = {"kind": "the-graph", "deployment": runner.DEPLOYMENT,
                       "indexed_block": self.anchor.number, "query_block": self.anchor.number,
                       "query_block_hash": self.anchor.hash, "market_count": len(self.ids)}
        self.directory = directory
        self.attempts, self.discovery_calls, self.anchor_calls = [], [], []
        self.errors = {}
        self.beginnings = 0
        self.current_anchor = self.anchor

    def client(self, endpoints, **options):
        assert endpoints == runner.ENDPOINTS
        assert options == {"tries": 2, "timeout": 10}
        return self

    def anchor_read(self, block):
        assert block in ("finalized", self.anchor.number)
        self.anchor_calls.append(block)
        return self.current_anchor

    def begin_market(self):
        self.beginnings += 1

    def discover(self, block, *, block_hash, url):
        self.discovery_calls.append((block, block_hash, url))
        assert (block, block_hash, url) == (self.anchor.number, self.anchor.hash, runner.GRAPH)
        return Discovery(tuple(self.ids), deepcopy(self.source))

    def capture(self, client, anchor, ids, source, *, full_checks, scenario_notional_loan):
        assert client is self
        assert anchor == self.anchor
        assert source == self.source
        assert scenario_notional_loan == "10000"
        assert len(ids) == 1 and ids[0] in self.rows
        phase = "full" if full_checks else "accounting"
        key = (phase, ids[0])
        self.attempts.append(key)
        if key in self.errors:
            raise self.errors.pop(key)
        row = deepcopy(self.rows[ids[0]])
        if not full_checks:
            for name in ("oracle", "reference", "rate"):
                row.pop(name)
        return {"schema": "mirage-snapshot/1", "anchor": asdict(anchor),
                "source": deepcopy(source), "rows": [row],
                "scenario_notional_loan": "10000" if full_checks else None}

    def run(self, phase="accounting", *, log_progress=False):
        return runner.run(argparse.Namespace(run_dir=self.directory, phase=phase,
                                             log_progress=log_progress))

    def status(self):
        return json.loads((self.directory / "status.json").read_text(encoding="utf-8"))

    def checkpoint(self, market, phase="accounting"):
        return self.directory / phase / (market + ".json.gz")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    # An accidental transport invocation must fail rather than make a live request.
    def forbidden(*args, **kwargs):
        raise AssertionError("Network is forbidden in universe lifecycle tests")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    h = Harness(tmp_path / "run")
    # Keep h.anchor as fixture data; the client facade exposes anchor() separately.
    class Client:
        def anchor(self, block):
            return h.anchor_read(block)

        def begin_market(self):
            h.begin_market()

    client = Client()

    def make_client(endpoints, **options):
        h.client(endpoints, **options)
        return client

    def collect(actual_client, *args, **kwargs):
        assert actual_client is client
        return h.capture(h, *args, **kwargs)

    monkeypatch.setattr(runner, "CachingRpcClient", make_client)
    monkeypatch.setattr(runner, "discover_markets", h.discover)
    monkeypatch.setattr(runner, "capture", collect)
    return h


def test_partial_accounting_resume_preserves_checkpoints(harness):
    h = harness
    failed = h.ids[1]
    h.errors[("accounting", failed)] = RuntimeError("Transient read unavailable")
    assert h.run(log_progress=True) == 2
    status = h.status()
    assert status["state"] == "partial"
    assert status["counts"] == {"discovered": 2, "included": 1, "full_checked": 0,
                                "accounting_only": 1, "failed_this_phase": 1, "missing": 1}
    original = h.checkpoint(h.ids[0]).read_bytes()
    manifest = (h.directory / "manifest.json").read_bytes()
    assert not h.checkpoint(failed).exists()
    assert not (h.directory / ".running.lock").exists()
    ledger = (h.directory / "failures.jsonl").read_text(encoding="utf-8")
    assert json.loads(ledger)["anchor_reverified"] is True
    assert h.run(log_progress=True) == 0
    assert h.attempts == [("accounting", h.ids[0]), ("accounting", failed), ("accounting", failed)]
    assert h.checkpoint(h.ids[0]).read_bytes() == original
    assert (h.directory / "manifest.json").read_bytes() == manifest
    assert (h.directory / "failures.jsonl").read_text(encoding="utf-8") == ledger
    assert h.status()["resumed"] == 1 and h.status()["new_attempts"] == 1
    assert h.status()["failed_market_ids"] == []
    assert len(h.discovery_calls) == 1 and h.beginnings == 3
    progress = [json.loads(line) for line in (h.directory / "progress.jsonl").read_text().splitlines()]
    assert progress[-1]["state"] == "complete"


def test_partial_full_keeps_accounting_coverage_and_resume_is_full_only(harness):
    h = harness
    assert h.run() == 0
    accounting_bytes = {m: h.checkpoint(m).read_bytes() for m in h.ids}
    h.errors[("full", h.ids[1])] = RuntimeError("RPC response unavailable")
    assert h.run("full") == 2
    assert h.status()["counts"] == {"discovered": 2, "included": 2, "full_checked": 1,
                                    "accounting_only": 1, "failed_this_phase": 1, "missing": 0}
    mixed = summary.summarize(Path(h.status()["snapshot"]))
    assert mixed["coverage"]["all_discovered_markets_included"] is True
    assert mixed["coverage"]["all_discovered_markets_have_three_checks"] is False
    assert mixed["coverage"]["accounting_only"] == 1
    first_full = h.checkpoint(h.ids[0], "full").read_bytes()
    assert h.run("full") == 0
    assert h.attempts[-1] == ("full", h.ids[1])
    assert h.status()["resumed"] == 1 and h.status()["new_attempts"] == 1
    assert h.checkpoint(h.ids[0], "full").read_bytes() == first_full
    assert {m: h.checkpoint(m).read_bytes() for m in h.ids} == accounting_bytes
    result = summary.summarize(Path(h.status()["snapshot"]))
    assert result["coverage"]["all_three_checks_recorded"] == 2
    assert result["coverage"]["all_discovered_markets_have_three_checks"] is True
    # Finished collection is not a promise of PASS; these are actual fixture findings.
    assert result["status_counts"]["pass"] < 2
    assert result["coverage"]["all_three_with_insufficient_findings"] > 0
    assert len(h.discovery_calls) == 1


def test_completed_run_does_not_recollect_and_publishes_new_merge(harness):
    h = harness
    assert h.run() == 0
    old_snapshot = Path(h.status()["snapshot"])
    old_bytes = old_snapshot.read_bytes()
    assert h.run() == 0
    assert h.status()["new_attempts"] == 0 and h.status()["resumed"] == 2
    assert len(h.attempts) == 2
    assert old_snapshot.read_bytes() == old_bytes
    assert Path(h.status()["snapshot"]) != old_snapshot


def test_ctrl_c_releases_lock_and_keeps_last_checkpoint(harness):
    h = harness
    h.errors[("accounting", h.ids[1])] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        h.run()
    assert h.status()["state"] == "interrupted"
    assert h.checkpoint(h.ids[0]).exists()
    assert not (h.directory / ".running.lock").exists()
    assert h.run() == 0
    assert h.status()["resumed"] == 1


@pytest.mark.parametrize("change", ["manifest_source", "checkpoint_source", "checkpoint_raw", "checkpoint_phase", "ledger"])
def test_invalid_resume_aborts_before_capture(harness, change):
    h = harness
    assert h.run() == 0
    if change == "manifest_source":
        path = h.directory / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["source"]["deployment"] = "QmWrongDeployment"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    elif change == "ledger":
        (h.directory / "failures.jsonl").write_text('{"market_id":"unknown","phase":"full"}\n', encoding="utf-8")
    else:
        path = h.checkpoint(h.ids[0])
        snapshot = load_snapshot(path)
        if change == "checkpoint_source":
            snapshot["source"]["query_block_hash"] = "0x" + "00" * 32
        elif change == "checkpoint_raw":
            snapshot["rows"][0]["evidence"][1]["result"] = "0x"
        else:
            snapshot["rows"][0]["oracle"] = {}
        path.write_bytes(gzip.compress(json.dumps(snapshot).encode("utf-8"), mtime=0))
    attempted = list(h.attempts)
    with pytest.raises((ValueError, KeyError)):
        h.run()
    assert h.attempts == attempted
    assert h.status()["state"] == "aborted"
    assert not (h.directory / ".running.lock").exists()


def test_invalid_initial_discovery_is_not_published(harness):
    harness.source["deployment"] = "QmUntrusted"
    with pytest.raises(ValueError, match="manifest/source"):
        harness.run()
    assert not (harness.directory / "manifest.json").exists()
    assert harness.attempts == []


def test_other_size_full_observation_cannot_resume_as_fixed_ten_thousand(harness):
    h = harness
    assert h.run() == 0
    market = h.ids[1]
    snapshot = h.capture(h, h.anchor, (market,), h.source, full_checks=True,
                         scenario_notional_loan="10000")
    snapshot["rows"][0]["reference"]["scenario"]["notional_loan"] = "5000"
    # The product can replay this different scenario using genuine saved raw calls;
    # the universe runner must additionally bind it to its manifest's fixed size.
    assert report_from_snapshot(snapshot).markets[0].market_id == market
    save_snapshot(h.checkpoint(market, "full"), snapshot)
    attempted = list(h.attempts)
    with pytest.raises(ValueError, match="checkpoint scenario"):
        h.run("full")
    assert h.attempts == attempted
    assert h.status()["state"] == "aborted"


def test_changed_anchor_aborts_resume_without_capture(harness):
    h = harness
    assert h.run() == 0
    h.current_anchor = replace(h.anchor, hash="0x" + "00" * 32)
    attempts = list(h.attempts)
    with pytest.raises(ValueError, match="anchor/hash change"):
        h.run()
    assert h.attempts == attempts


def test_historical_hash_change_is_fatal_not_partial(harness):
    h = harness
    h.errors[("accounting", h.ids[0])] = ValueError("Historical block hash changed")
    with pytest.raises(ValueError, match="current/historical block hash change"):
        h.run()
    assert not (h.directory / "failures.jsonl").exists()
    assert h.status()["state"] == "aborted"


def test_orphan_pending_file_is_not_adopted_as_a_checkpoint(harness):
    h = harness
    assert h.run() == 0
    pending = h.directory / "accounting" / ".pending" / "interrupted.json.gz"
    pending.write_bytes(b"incomplete")
    assert h.run() == 0
    assert pending.read_bytes() == b"incomplete"
    assert h.status()["resumed"] == 2


def test_preconditions_and_existing_lock_are_preserved(harness):
    h = harness
    with pytest.raises(ValueError, match="accounting first"):
        h.run("full")
    h.directory.mkdir()
    sentinel = h.directory / "unrelated.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="nonempty"):
        h.run()
    assert sentinel.read_text() == "keep"
    sentinel.unlink()
    assert h.run() == 0
    lock = h.directory / ".running.lock"
    lock.write_text("owned by another process", encoding="utf-8")
    with pytest.raises(FileExistsError):
        h.run()
    assert lock.read_text() == "owned by another process"


def test_atomic_publish_never_overwrites_and_cleans_temporary(tmp_path):
    path = tmp_path / "immutable.json"
    runner.write_json(path, {"original": True}, immutable=True)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        runner.write_json(path, {"replaced": True}, immutable=True)
    assert path.read_bytes() == original
    assert list((tmp_path / ".pending").iterdir()) == []


def test_cache_failures_retry_at_next_market_and_successes_remain_cached(monkeypatch):
    responses = iter((RuntimeError("transient"), "0x1234"))
    requests = []

    def read(*args):
        requests.append(args)
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(RpcClient, "call", read)
    client = CachingRpcClient(("https://example.invalid",))
    call = ("0x" + "11" * 20, "0x12345678", 25938082)
    with pytest.raises(RuntimeError, match="transient"):
        client.call(*call)
    with pytest.raises(RuntimeError, match="earlier in this market"):
        client.call(*call)
    assert len(requests) == 1
    client.begin_market()
    assert client.call(*call) == "0x1234"
    client.begin_market()
    assert client.call(*call) == "0x1234"
    assert len(requests) == 2


def test_summary_replays_exact_raw_sums_hash_and_labels(harness):
    h = harness
    assert h.run() == 0
    path = Path(h.status()["snapshot"])
    result = summary.summarize(path)
    snapshot = load_snapshot(path)
    expected = sum(int(r["evidence"][1]["result"][2:66], 16) for r in snapshot["rows"])
    assert result["schema"] == "mirage-universe-summary/1"
    assert result["snapshot_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["accounting"]["stored_supply_assets"] == summary.amount(expected)
    assert result["accounting"]["markets_in_sums"] == 2
    assert "not recovered principal" in result["accounting"]["labels"]
    assert result["coverage"]["accounting_only"] == 2
    assert result["coverage"]["all_three_checks_recorded"] == 0
    assert sum(result["status_counts"].values()) == len(report_from_snapshot(snapshot).markets)
    assert summary.usdc(1000000000000000000000000000001) == "1000000000000000000000000.000001"
    assert summary.usdc(-1) == "-0.000001"


@pytest.mark.parametrize("change", ["raw", "conflicting_counts", "unknown_count", "half_observation"])
def test_summary_rejects_corruption_and_marks_unknown_universe(harness, change):
    h = harness
    assert h.run() == 0
    snapshot = load_snapshot(Path(h.status()["snapshot"]))
    if change == "raw":
        snapshot["rows"][0]["evidence"][0]["result"] = "0x"
    elif change == "conflicting_counts":
        snapshot["source"]["discovery_market_count"] = 3
    elif change == "half_observation":
        snapshot["rows"][0]["oracle"] = {}
    else:
        snapshot["source"].pop("discovery_market_count")
        snapshot["source"].pop("market_count")
    path = h.directory / "altered.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    if change == "unknown_count":
        coverage = summary.summarize(path)["coverage"]
        assert coverage["missing_from_snapshot"] is None
        assert coverage["all_discovered_markets_included"] is None
    else:
        with pytest.raises((ValueError, KeyError)):
            summary.summarize(path)


def test_summary_cli_new_output_only_and_no_transport(harness, capsys):
    h = harness
    assert h.run() == 0
    path = h.status()["snapshot"]
    destination = h.directory / "summary.json"
    summary.main(["--snapshot", path, "--output", str(destination)])
    original = destination.read_bytes()
    with pytest.raises(ValueError, match="never overwritten"):
        summary.main(["--snapshot", path, "--output", str(destination)])
    assert destination.read_bytes() == original
    capsys.readouterr()
    summary.main(["--snapshot", path, "--stdout"])
    assert json.loads(capsys.readouterr().out)["schema"] == "mirage-universe-summary/1"
