"""Local evidence workbench. Read-only Ethereum RPC; no signing or wallet hooks."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .allocator import compare, scenario_amount
from .chain.cache import CachingRpcClient
from .chain.codec import enc_b32
from .discovery.subgraph import discover_markets
from .scan import capture, load_snapshot, report_from_snapshot, save_snapshot

GRAPH_URL = "https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1"
DEMO_MARKETS = (
    "0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9",
    "0xbd1ad3b968f5f0552dbd8cf1989a62881407c5cccf9e49fb3657c8731caf0c1f",
    "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc",
    "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd",
)


def default_snapshot():
    directory = Path(__file__).parent / "snapshots"
    manifest = directory / "demo.json"
    if manifest.exists():
        name = json.loads(manifest.read_text(encoding="utf-8"))["snapshot"]
        if Path(name).name != name:
            raise ValueError("Invalid demo snapshot name")
        return directory / name
    return directory / "mainnet-25937912.json.gz"


class Application:
    def __init__(self, snapshot_path=None, *, graph_url=None, cache_dir=None):
        self.lock = threading.Lock()
        self.snapshot = load_snapshot(Path(snapshot_path or default_snapshot()))
        report_from_snapshot(self.snapshot)
        self.graph_url = graph_url or GRAPH_URL
        self.cache_dir = Path(cache_dir or "data/cached/mirage")
        self.status = {"state": "idle", "mode": "saved", "message": "Saved chain evidence; refresh for live checks"}

    def get_status(self):
        with self.lock:
            return dict(self.status)

    def get_report(self):
        with self.lock:
            snapshot = self.snapshot
        result = report_from_snapshot(snapshot).to_dict()
        result["block_timestamp"] = snapshot["anchor"]["timestamp"]
        result["scenario_notional_loan"] = snapshot.get("scenario_notional_loan")
        return result

    def get_comparison(self, amount, market):
        with self.lock:
            snapshot = self.snapshot
        return compare(snapshot, amount_usdc=amount, market_id=market)

    def start_scan(self, amount="10000", market_id=None):
        amount = scenario_amount(amount)
        if market_id is not None:
            market_id = "0x" + enc_b32(market_id)
        with self.lock:
            if self.status["state"] == "running":
                return dict(self.status)
            self.status = {"state": "running", "mode": "saved", "message": "Discovering USDC markets through The Graph",
                           "progress": {"done": 0, "total": 0}}
        threading.Thread(target=self._scan, args=(amount, market_id), daemon=True).start()
        return self.get_status()

    def _scan(self, amount, market_id):
        try:
            client = CachingRpcClient(tries=3, timeout=8)
            anchor = client.anchor("finalized")
            discovery = discover_markets(anchor.number, block_hash=anchor.hash, url=self.graph_url)
            ids = (market_id,) if market_id else DEMO_MARKETS
            if not set(ids).issubset(discovery.market_ids):
                raise ValueError("Selected market is absent from Graph's USDC discovery at this block")
            source = {**discovery.source, "discovery_market_count": len(discovery.market_ids),
                      "inspected_market_count": len(ids), "selection": "explicit user selection" if market_id else "documented demo shortlist"}

            def progress(done, total, market):
                with self.lock:
                    self.status.update(progress={"done": done, "total": total},
                                       message="Reading accounting, oracle and exact-size Uniswap evidence" if market else "Validating captured evidence")

            snapshot = capture(client, anchor, ids, source, full_checks=True,
                               scenario_notional_loan=amount, progress=progress)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target = self.cache_dir / f"live-{anchor.number}-{time.time_ns()}.json.gz"
            save_snapshot(target, snapshot)
            with self.lock:
                self.snapshot = snapshot
                self.status = {"state": "complete", "mode": "live", "updated_at": int(time.time()),
                               "message": "Live Graph discovery and block-pinned RPC checks complete",
                               "progress": {"done": len(ids), "total": len(ids)}}
        except Exception as error:
            # Avoid surfacing any URL/key from third-party transport exceptions.
            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
            with self.lock:
                self.status = {"state": "error", "mode": "saved", "message": message,
                               "updated_at": int(time.time())}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, code, payload, content_type="application/json; charset=utf-8"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _local(self):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in allowed:
                self._send(403, {"error": "Local workbench host required"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{h}" for h in allowed}:
                self._send(403, {"error": "Same-origin request required"})
                return False
            return True

        def do_GET(self):
            if not self._local():
                return
            route = urlsplit(self.path)
            try:
                if route.path == "/api/status":
                    return self._send(200, app.get_status())
                if route.path == "/api/report":
                    return self._send(200, app.get_report())
                if route.path == "/api/allocator":
                    args = parse_qs(route.query)
                    return self._send(200, app.get_comparison(args.get("amount", ["10000"])[0], args.get("market", [None])[0]))
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/index.html": ("index.html", "text/html; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8")}
                if route.path in static:
                    name, content_type = static[route.path]
                    return self._send(200, (Path(__file__).parent / "web" / name).read_bytes(), content_type)
                self._send(404, {"error": "Not found"})
            except (ValueError, KeyError) as error:
                self._send(400, {"error": str(error)})
            except Exception:
                self._send(500, {"error": "Unable to render evidence"})

        def do_POST(self):
            if not self._local():
                return
            if self.path != "/api/scan":
                return self._send(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096:
                    raise ValueError("Request body too large")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                self._send(202, app.start_scan(body.get("amount_usdc", "10000"), body.get("market_id")))
            except (ValueError, TypeError) as error:
                self._send(400, {"error": str(error)})
    return Handler


def serve(*, port=8765, snapshot=None, graph_url=None):
    app = Application(snapshot, graph_url=graph_url)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(app))
    print(f"MIRAGE workbench: http://127.0.0.1:{server.server_port}", flush=True)
    print("Saved evidence loaded. Refresh performs read-only mainnet calls and live Graph discovery.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
