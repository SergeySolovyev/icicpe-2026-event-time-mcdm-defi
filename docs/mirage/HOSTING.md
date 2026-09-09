# Hosting the MIRAGE workbench

The hosted product is the real Python workbench: saved mainnet evidence, allocator replay,
and user-triggered read-only Graph/RPC checks. `Dockerfile.mirage` and `render.yaml` prepare
deployment; their presence does not mean that a public service has been deployed or verified.

## Render: stable service address, free instance

Use the repository's `render.yaml` as a Render Blueprint. It defines one Docker web service,
explicitly on the `free` plan, in Frankfurt, with deploys on ordinary code commits disabled.
There is no database or persistent disk. Render uses
the repository containing the Blueprint and its default branch unless configured otherwise.
See the [official Blueprint fields](https://render.com/docs/blueprint-spec).

After the intended commit is available in the repository, the account owner can select
**New > Blueprint**, connect that repository, review the one free service, and apply it.
Existing GitHub login can be used with Render; account creation, GitHub authorization, and
applying the Blueprint are separate actions that this preparation does not perform.
See [Render login settings](https://render.com/docs/login-settings) and
[Blueprint setup](https://render.com/docs/infrastructure-as-code).

Blueprint **Auto Sync is a separate setting**: Render enables it by default, so later changes
to `render.yaml` can still update resources. To keep all subsequent updates manual, set the
Blueprint's **Settings > Auto Sync > No**, then use **Manual Sync** for configuration changes
and the service's manual deploy action for application releases.
See [disabling automatic Blueprint sync](https://render.com/docs/infrastructure-as-code#disabling-automatic-sync).

Render supplies `RENDER_EXTERNAL_URL`, for example `https://mirage-workbench.onrender.com`.
The actual assigned hostname must be read from the service dashboard; the example is not a
claimed deployment. `scripts/mirage_host.py` uses that exact origin and binds to `0.0.0.0`
on `PORT` (default `10000`). `MIRAGE_PUBLIC_ORIGIN`, if set, overrides the Render URL and must
be one canonical HTTPS origin with no trailing slash, path, credentials, query, fragment,
wildcard, or explicit default port. Missing or invalid configuration stops startup.
See [Render environment variables](https://render.com/docs/environment-variables) and
[port binding](https://render.com/docs/web-services#port-binding).

Render terminates public HTTPS and forwards HTTP to the container. The server accepts the
configured public Host and exact browser Origin, in addition to its local origin policy.
The `/style.css` health check avoids creating visitor sessions. Startup validates the frozen
snapshot before accepting connections; the health check verifies HTTP readiness, not live
RPC availability. Render sends its public hostname as the health check Host; introducing a
custom domain requires updating the exact public origin and checking health again.
See [Render health checks](https://render.com/docs/health-checks).

The free service sleeps after 15 minutes without inbound traffic; waking takes about a
minute. Its filesystem is ephemeral. Redeploys, restarts, or spin-downs discard captures in
`data/cached/mirage/` and in-memory visitor sessions. Frozen snapshots under
`mirage/snapshots/` are part of the image and survive those events. A stable service URL is
not an uptime guarantee or permanent storage. See [Render's free-instance limits](https://render.com/docs/free).

## Image contents and local verification

The image explicitly copies MIRAGE's UI, detectors, chain readers, frozen snapshots,
the original revert.pro extractor with its license/provenance, and the existing allocator's
T1 policy plus its base types. It installs `requirements-mirage.txt`: pyevmasm and the
NumPy/Pandas/SciPy/scikit-learn/joblib dependencies required by the unchanged extractor.
It does not install the paper/research requirements, training models, or the optional MCP
server. No Graph deploy key, RPC credential, local environment file, or research dataset
is copied. The process runs as an unprivileged user; only the capture directory is writable
under `/app`. Package constraints and the Python image tag allow upstream patch updates;
retain the built image digest when recording a release. The Docker build runs a saved-evidence
and allocator replay without network calls; incompatible decoder or numerical dependencies
fail that build before an image is deployed.

Preparation check on 9 September 2026: 23 helper configuration cases passed. Docker CLI is
installed locally, but its Linux engine pipe was unavailable; no image build or container
smoke test has been completed in this preparation. No Render deployment was performed.

Build from a clean checkout when using an external builder: explicit `COPY` controls image
contents, while Docker build-context transfer is a separate concern.

```powershell
docker build --file Dockerfile.mirage --tag mirage-workbench:local .
docker run --rm --name mirage-host-check -p 127.0.0.1:18767:10000 -e MIRAGE_PUBLIC_ORIGIN=https://mirage.example mirage-workbench:local
```

The placeholder origin is for this local proxy-header check only. In a second terminal:

```powershell
curl.exe --fail -H "Host: mirage.example" http://127.0.0.1:18767/style.css
curl.exe --fail -H "Host: mirage.example" http://127.0.0.1:18767/api/report
```

Expect CSS and a JSON report with the committed block/hash and `capture_mode: saved`.
An attacker Origin on an otherwise valid Host must return 403. A public browser smoke check
must then confirm that two independent cookie jars retain separate reports, an exact-size
live check completes, and **Load demo** restores the saved evidence. The free instance's
live RPC response times and memory use must be measured on the deployed service; a successful
local test does not establish those properties. Stop only the named test container when done.

## Quick Tunnel: temporary access to a running local workbench

Quick Tunnel is useful for an immediate demo while the PC, workbench process, and cloudflared
remain running. Its random `trycloudflare.com` URL is temporary. It needs no Cloudflare account
or domain, but has no SLA, supports at most 200 in-flight requests, and does not support SSE.
The workbench's polling is compatible with that limitation. An existing cloudflared
`config.yaml` can prevent Quick Tunnel startup; do not change another tunnel's configuration
without first identifying it. See [Cloudflare Quick Tunnel documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

Before exposing a port, check that it has no existing listener, start MIRAGE with its exclusive
bind protection, and verify **both** its HTML and `/api/report` locally. On Windows, a reused
port previously served a different Python server's directory listing: a bind or an HTTP 200
alone was insufficient verification. Do not terminate an unrelated listener. Select a free
port and check the product-specific response instead.

For example, after confirming port 18766 is unused, start the local workbench on that port and
verify its content. Start cloudflared with:

```powershell
cloudflared.exe tunnel --protocol http2 --url http://127.0.0.1:18766 --http-host-header 127.0.0.1:18766 --loglevel info --logfile "$env:TEMP\mirage-cloudflared.log"
```

The generated HTTPS URL is logged at INFO to **stderr** and the specified logfile. Configure
the workbench with that exact `--public-origin` and the same loopback port before testing its
public actions. Restart only the owned workbench process when updating the origin; keep the
tunnel process running to retain that assigned URL. Verify the public HTML and saved report
again before sharing it. Public cookie isolation requires public-origin configuration.

The Host override rewrites the local HTTP Host and preserves the original in
`X-Forwarded-Host`; the browser's public Origin is forwarded unchanged. `--protocol http2`
uses TCP 7844 between cloudflared and Cloudflare, avoiding a dependency on UDP/QUIC. It does
not enable HTTP/2 on the Python origin and does not solve a blocked TCP connection. INFO is
sufficient; DEBUG can record request headers. These flags were checked against installed
cloudflared 2026.7.3. See [run parameters](https://developers.cloudflare.com/tunnel/advanced/run-parameters/),
[network requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/),
and [Host forwarding in that release](https://github.com/cloudflare/cloudflared/blob/2026.7.3/ingress/origin_proxy.go#L32-L54).
