"""Local evidence workbench. Read-only Ethereum RPC; no signing or wallet hooks."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
import secrets
import socket
from http.cookies import SimpleCookie
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


class WorkbenchHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits unrelated listeners to share a port. A
    # reverse proxy must never accidentally expose another local application.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


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
    def __init__(self, snapshot_path=None, *, graph_url=None, cache_dir=None, live_slots=None):
        self.lock = threading.Lock()
        self.snapshot = load_snapshot(Path(snapshot_path or default_snapshot()))
        report_from_snapshot(self.snapshot)
        self.seed_snapshot = self.snapshot
        self.snapshot_mode = "saved"
        self.live_slots = live_slots
        self.graph_url = graph_url or GRAPH_URL
        self.cache_dir = Path(cache_dir or "data/cached/mirage")
        self.status = {"state": "idle", "mode": "saved", "message": "Saved chain evidence; refresh for live checks"}

    def get_status(self):
        with self.lock:
            return dict(self.status)

    def get_report(self):
        with self.lock:
            snapshot = self.snapshot
            mode = self.snapshot_mode
        result = report_from_snapshot(snapshot).to_dict()
        result["block_timestamp"] = snapshot["anchor"]["timestamp"]
        result["scenario_notional_loan"] = snapshot.get("scenario_notional_loan")
        result["capture_mode"] = mode
        return result

    def get_comparison(self, amount, market):
        with self.lock:
            snapshot = self.snapshot
        return compare(snapshot, amount_usdc=amount, market_id=market)

    def reset_demo(self):
        with self.lock:
            if self.status["state"] == "running":
                raise ValueError("Wait for the current check to finish before loading the demo")
            self.snapshot = self.seed_snapshot
            self.snapshot_mode = "saved"
            self.status = {"state": "idle", "mode": "saved", "message": "Saved demo evidence loaded"}
            return dict(self.status)

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
        slot_acquired = False
        try:
            if self.live_slots is not None:
                slot_acquired = self.live_slots.acquire(blocking=False)
                if not slot_acquired:
                    raise RuntimeError("Live checks are busy; retry after the running checks finish")
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
                self.snapshot_mode = "live"
                self.status = {"state": "complete", "mode": "live", "updated_at": int(time.time()),
                               "message": "Live Graph discovery and block-pinned RPC checks complete",
                               "progress": {"done": len(ids), "total": len(ids)}}
        except Exception as error:
            # Avoid surfacing any URL/key from third-party transport exceptions.
            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
            with self.lock:
                self.status = {"state": "error", "mode": "saved", "message": message,
                               "updated_at": int(time.time())}
        finally:
            if slot_acquired:
                self.live_slots.release()


class Sessions:
    """Isolate public visitors' selected reports; retain only a bounded idle cache."""
    def __init__(self, factory, *, max_sessions=32):
        self.factory, self.max_sessions = factory, max_sessions
        self.lock, self.items = threading.Lock(), {}

    def get(self, token):
        with self.lock:
            now = time.monotonic()
            if token in self.items:
                app, _ = self.items[token]
                self.items[token] = (app, now)
                return token, app
            if len(self.items) >= self.max_sessions:
                idle = [(last, key) for key, (app, last) in self.items.items()
                        if app.get_status()["state"] != "running"]
                if not idle:
                    raise RuntimeError("All demo sessions are busy")
                del self.items[min(idle)[1]]
            token = secrets.token_urlsafe(24)
            app = self.factory()
            self.items[token] = (app, now)
            return token, app


def handler_for(app, *, public_origin=None, sessions=None):
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
            if getattr(self, "session_token", None):
                cookie = f"mirage_session={self.session_token}; Path=/; HttpOnly; SameSite=Strict"
                self.send_header("Set-Cookie", cookie + ("; Secure" if public_origin else ""))
            self.end_headers()
            self.wfile.write(data)

        def _local(self):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origins = {f"http://{h}" for h in allowed}
            if public_origin:
                allowed.add(urlsplit(public_origin).netloc)
                origins.add(public_origin)
            if self.headers.get("Host") not in allowed:
                self._send(403, {"error": "Configured workbench host required"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self._send(403, {"error": "Same-origin request required"})
                return False
            return True

        def _app(self):
            if sessions is None:
                return app
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except Exception:
                pass
            token = cookies["mirage_session"].value if "mirage_session" in cookies else None
            self.session_token, selected = sessions.get(token)
            return selected

        def do_GET(self):
            if not self._local():
                return
            route = urlsplit(self.path)
            try:
                if route.path == "/api/status":
                    return self._send(200, self._app().get_status())
                if route.path == "/api/report":
                    return self._send(200, self._app().get_report())
                if route.path == "/api/allocator":
                    args = parse_qs(route.query)
                    return self._send(200, self._app().get_comparison(args.get("amount", ["10000"])[0], args.get("market", [None])[0]))
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/index.html": ("index.html", "text/html; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8")}
                if route.path in static:
                    # Set the visitor cookie on the HTML before concurrent API
                    # requests; otherwise initial report/status can split sessions.
                    if route.path in ("/", "/index.html"):
                        self._app()
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
            if self.path not in ("/api/scan", "/api/demo"):
                return self._send(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096:
                    raise ValueError("Request body too large")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                selected = self._app()
                if self.path == "/api/demo":
                    return self._send(200, selected.reset_demo())
                self._send(202, selected.start_scan(body.get("amount_usdc", "10000"), body.get("market_id")))
            except (ValueError, TypeError) as error:
                self._send(400, {"error": str(error)})
            except RuntimeError:
                self._send(503, {"error": "All demo sessions are busy; retry shortly"})
            except Exception:
                self._send(500, {"error": "Unable to start evidence check"})
    return Handler


def serve(*, port=8765, snapshot=None, graph_url=None, public_origin=None, bind="127.0.0.1"):
    if bind not in ("127.0.0.1", "0.0.0.0") or (bind == "0.0.0.0" and not public_origin):
        raise ValueError("A public bind requires an exact HTTPS public-origin")
    if public_origin:
        parsed = urlsplit(public_origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("public-origin must be one exact HTTPS origin without path or credentials")
    slots = threading.BoundedSemaphore(2)
    factory = lambda: Application(snapshot, graph_url=graph_url, live_slots=slots)
    app = factory()
    sessions = Sessions(factory) if public_origin else None
    server = WorkbenchHTTPServer((bind, port), handler_for(app, public_origin=public_origin, sessions=sessions))
    print(f"MIRAGE workbench: http://127.0.0.1:{server.server_port}", flush=True)
    print("Saved evidence loaded. Refresh performs read-only mainnet calls and live Graph discovery.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
