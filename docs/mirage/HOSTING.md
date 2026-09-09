# Hosting the MIRAGE workbench

The real Python workbench is deployed at **https://mirage-workbench.onrender.com**.
It serves saved mainnet evidence and allocator replay, with user-triggered read-only
Graph/RPC checks. On 9 September 2026, the Render dashboard reported the release live,
and the public browser loaded the four-market saved-evidence workbench.

## Confirmed release

| Item | Observed value |
|---|---|
| Service URL | https://mirage-workbench.onrender.com |
| Platform | Render Docker web service, free plan, Frankfurt |
| Release commit | `2212062662245a0c02d6d93b6d6e195d45371681` |
| Deployment ID | `dep-daghgg942hec73ccdi10` |
| Dashboard timestamp | 9 September 2026, 11:26:41 Moscow |
| Runtime live log | 9 September 2026, 11:27:53 Moscow |
| Build/deploy duration | 1 minute 12 seconds |
| Service state | Live |
| Service automatic deploys | Disabled |
| Blueprint Auto Sync | No; saved and verified |

The cloud Docker build completed its saved-evidence and allocator replay checks. The public
browser displayed the committed four-market demo and then completed a fresh Graph/RPC
inspection through the hosted service. The live WETH check below passed the implemented
checks, and both original T1 and the gated preview returned `switch` at its evidence block.
Subsequent release records should distinguish the deployed commit from later documentation
commits in the repository.

| Public browser live check | Observed value |
|---|---|
| Market | WETH/USDC, `0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd` |
| Scenario | 10000 USDC |
| Discovery and assessment | 697 Graph-discovered IDs; one market inspected |
| Verdict | PASS |
| Ethereum block | `25938497` |
| Block hash | `0x958420107c3cedc4adbfc1761ac367746156530b056bac903824147f46c3ab14` |
| Displayed evidence timestamp | 9 September 2026, 08:03 UTC |
| Request observation | Started approximately 08:21 UTC; complete by 08:22 UTC |

Exact request latency was not measured. This browser check verifies the deployed live path;
the new capture has not been independently reread through two providers. The two-provider
verification elsewhere in the repository applies to the frozen block `25938082` demo.
See [public browser verification](RENDER_BROWSER_VERIFICATION_2026-09-09.json).

The follow-up release above corrects a stale preview caption after a new report.
A second WETH check passed at block `25938561`; the preview used that block,
both policies proposed entry, and **Load demo** restored block `25938082` with
the new caption and cleared decisions. Backend detectors and the frozen fixture
were unchanged. The earlier full HTTP isolation check refers to the initial release.

[Clean Linux CI](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34329377252)
at commit `0e3a13f1a01e6f1728c49480343eb0ae395c3f4b` passed 176 tests and separately built
the same product inputs. The CI image ID was
`sha256:a7f5e23c335a763849fa383620543f64e15ede288e639d27a3459e141bebc960`;
it replayed four markets at block `25938082` with `--network=none`. This is the CI
image ID, not a claimed digest of Render's separately built image.

## Render: stable service address, free instance

The deployment uses the repository's `render.yaml` as a Render Blueprint. It defines one Docker web service,
explicitly on the `free` plan, in Frankfurt, with deploys on ordinary code commits disabled.
There is no database or persistent disk. Render uses
the repository containing the Blueprint and its default branch unless configured otherwise.
See the [official Blueprint fields](https://render.com/docs/blueprint-spec).

The repository connection and initial Blueprint application are complete for this service.
To reproduce it in another Render account, the account owner can select **New > Blueprint**,
connect the public repository, review the free service, and apply it. Account access and
repository authorization belong to that account owner.
See [Render login settings](https://render.com/docs/login-settings) and
[Blueprint setup](https://render.com/docs/infrastructure-as-code).

Blueprint **Auto Sync is a separate setting** from service automatic deploys. Both are
disabled on the confirmed service. Use **Manual Sync** for intentional Blueprint
configuration changes and the service's manual deploy action for application releases.
See [disabling automatic Blueprint sync](https://render.com/docs/infrastructure-as-code#disabling-automatic-sync).

Render supplies `RENDER_EXTERNAL_URL`; the confirmed assigned origin is
`https://mirage-workbench.onrender.com`. `scripts/mirage_host.py` uses that exact origin and binds to `0.0.0.0`
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

The preparation check on 9 September 2026 passed 23 helper configuration cases. Docker CLI
is installed locally, but its Linux engine pipe was unavailable, so the local Docker image
build and container smoke test could not run. Render subsequently built and deployed the
image successfully in the cloud, including the Dockerfile's saved-evidence replay step.
The successful cloud build does not change the status of that failed local-engine attempt.

`Dockerfile.mirage.dockerignore` also limits the build context to the product's
source, dependencies and saved evidence; unrelated research, Git history and local
configuration are excluded before transfer. It applies specifically to this Dockerfile,
as described in [Docker's build-context documentation](https://docs.docker.com/build/concepts/context/#filename-and-location).

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
An attacker Origin on an otherwise valid Host must return 403. The public page, saved-demo
load, exact-size live capture and **Load demo** restoration were verified in the browser.
Separate [HTTP checks](RENDER_HTTP_VERIFICATION_2026-09-09.json) passed for two independent
cookie jars: resetting one visitor preserved the other's report and status; a hostile Origin
received 403. Those 13 requests took 0.236–0.717 seconds each. They do not measure live-scan
latency or peak memory, and are not a load test. Stop only the named local test container when done.

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
