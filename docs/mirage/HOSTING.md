# Hosting the MIRAGE workbench

The real Python workbench is deployed at **https://mirage-workbench.onrender.com**.
It serves saved mainnet evidence and allocator replay, with user-triggered read-only
Graph/RPC checks. On 9 September 2026, the Render dashboard reported the release live,
and the public browser loaded the four-market saved-evidence workbench.

## Confirmed release

| Item | Observed value |
|---|---|
| Service URL | https://mirage-workbench.onrender.com |
| Platform | Existing Render Docker web service, free plan, Frankfurt |
| Release commit | `9aeb01c46d26865e95f95ac190168692d87bbf64` |
| Deployment ID | `dep-dagks5740ujc73fl7img` |
| Dashboard timestamp | 9 September 2026, 15:16:20 Moscow |
| Runtime live time | 9 September 2026, 15:17:34 Moscow |
| Build/deploy duration | 1 minute 14 seconds |
| Deployment and service state | Deploy succeeded; Live |
| Service automatic deploys | Disabled |
| Blueprint Auto Sync | No; service configuration and free plan unchanged |
| Published code | Exact release commit is published on `master` and `mirage-diagnostics-replay` |
| Default saved snapshot | Unchanged: `mainnet-full-25938082-diagnostics-v2.json.gz`, SHA-256 `3df5fa7330740453cf64464ff992e541b2095b01c952f34cd8c262afe888ed7b` |

This release corrects the explanation returned when a supplied sale scenario cannot
be evaluated because a token address is zero or token decimals are unavailable.
New observations use `quote_reason_version: 2`; the affected exit finding remains
`INSUFFICIENT`. Unversioned/version-0 and version-1 observations retain their exact
legacy replay. A missing historical raw amount is not reconstructed.

The default snapshot still records quote-reason version **1**. Its filename's
`diagnostics-v2` describes the earlier diagnostic artifact, not this new quote-reason
version. Its saved calls, four markets and block `25938082` were not changed.
The release operator loaded all four saved markets in the public browser after
deployment.

One new public inspection through **Check another market** completed for market
`0x54efdee08e272e929034a8f26f7ca34b1ebe364b275391169b28c6d7db24dbc8`
at `10000` USDC. The browser showed **Live capture complete**, 697 Graph-discovered
IDs and **one inspected market**, at block `25939677`, hash
`0x24eaeb91bd0576a6c8b62fa370614e1b8febdf5528c476361e09f5d6412ba132`.
The displayed evidence time was 9 September 2026, **12:00 UTC**, with minute precision.
This is the evidence time, not a measured request completion timestamp.

The expanded exit metrics retained `scenario_notional_loan: 10000` and showed
`quote_status: insufficient`, `reason: zero_token_address`; input, output and token
decimals remained **Unknown**. The overall market remained **INSUFFICIENT**:
`oracle_code_unavailable`, `reference_unavailable` and `exit_depth_unavailable`
were insufficient, while `accounting_observed` passed its accounting check.
The release operator inspected the actual public DOM, screenshot and visible raw
JSON containing the block hash. No funds moved. This one fresh capture has not been
independently reread through two providers.

The operator then clicked **Load demo**. At 12:22 UTC, the public DOM confirmed
**Saved evidence**, block `25938082`, 697 discovered IDs and four inspected markets:
PAXG BLOCK, deUSD INSUFFICIENT, wstETH INSUFFICIENT and WETH PASS. The amount was
10000 USDC; **Waiting for a preview** and **Evidence required** confirmed the cleared
preview state. The custom market ID was cleared and **Check another market** collapsed.
This reset made no additional live inspection.

[Clean Linux CI for the exact release](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34349726175)
passed **221 tests with 2 warnings in 9.30 seconds**. The official SDK stdio example
returned PAXG 10000 `switch` → `hold`, WETH 10000 `switch` → `switch`, and WETH
20000 `switch` → `hold`, then shut down normally. The Docker build and offline
four-market container replay passed. The CI image ID was
`sha256:2e76c7fde0580e758d525ebedfa5ed801c894776510be9c9ff5f22eb8af98c6a`;
this is not the digest of Render's separately built image. A separate local focused
run passed 51 tests in 116.54 seconds. See the
[quote-reason v2 release proof](QUOTE_REASON_V2_VERIFICATION_2026-09-09.json).

## Historical deployments and browser checks

These records describe earlier releases and captures. Their observations remain
bound to the specified release, block and saved artifact.

### Earlier 66198ad deployment

| Item | Observed value |
|---|---|
| Service URL | https://mirage-workbench.onrender.com |
| Platform | Existing Render Docker web service, free plan, Frankfurt |
| Release commit | `66198ad3e97d647cc5bafad818bb83a00e3d668c` |
| Deployment ID | `dep-dagjrku1egvs73bdmmlg` |
| Dashboard timestamp | 9 September 2026, 14:06:59 Moscow |
| Runtime live time | 9 September 2026, 14:08:12 Moscow |
| Build/deploy duration | 1 minute 13 seconds |
| Service state | Live |
| Service automatic deploys | Disabled |
| Blueprint Auto Sync | No; configuration unchanged |
| Release selection | Manual deploy of the specific published commit on `mirage-diagnostics-replay` |
| Default saved snapshot | `mainnet-full-25938082-diagnostics-v2.json.gz`, SHA-256 `3df5fa7330740453cf64464ff992e541b2095b01c952f34cd8c262afe888ed7b` |

This release exposes the recorded direct and WETH-route quotes beside the exit verdict.
In the public browser, the wstETH table showed the same sale amount,
`3.220832145173417247` wstETH, for both candidates: `5927.556111` USDC through
the direct pool and `10007.772538` USDC through WETH, marked **Selected in report**.
The exit-size check passed; the aggregate market verdict remained insufficient.
These are saved quotes for the explicit 10000-USDC scenario at block `25938082`,
not a claim of maximum liquidation capacity or a comparison of every possible route.

The hosted browser also replayed three saved allocation scenarios. PAXG at 10000 USDC
showed **Allocate to destination** for the original allocator and **Keep capital unallocated**
with MIRAGE. WETH at 10000 showed **Allocate to destination** for both. At 20000,
the original allocator still proposed allocation, while MIRAGE kept capital unallocated
and displayed the missing-size warning beside the recorded 10000-USDC scope. Returning
the amount to 10000 cleared the previous preview. No **Check market** action or new
live capture was used in this release verification. See the separate
[route UI and release verification](ROUTE_UI_VERIFICATION_2026-09-09.json).

The snapshot is an offline diagnostic derivation of the original routes-v2 artifact,
SHA-256 `91aa45a2134eb8757ff4dcd9a4e651447067fa55ba20c40f700ac4840c2385fa`.
Its raw evidence, numerical inputs and math are unchanged. The original proof remains
historical evidence for those saved returns; the new artifact adds versioned diagnostic
explanations and explicit parent provenance. See
[diagnostic verification](DIAGNOSTIC_VERIFICATION_2026-09-09.json).

[Clean Linux CI for this exact release](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34343610011)
passed **218 tests with 2 warnings in 6.82 seconds** on Ubuntu 24 and Python 3.12.14.
Its official SDK stdio example returned PAXG 10000 `switch` → `hold`, WETH 10000
`switch` → `switch`, and WETH 20000 `switch` → `hold`. The Docker build and the
offline container replay of four saved markets passed. The CI image ID was
`sha256:d47676ec403a2ee46197a92c9d13357927019e51ce79873fef11224fa599e39f`;
it is not a digest of Render's separately built image.

Render's manual deployment selected the specific commit from the published branch.
The main `master` checkout remained at `6af7790` for the ongoing capture. The service
and free plan were retained, with automatic deploys disabled. Documentation commits
after this release must not be presented as the deployed product commit.

### Earlier c2ed741 deployment

| Item | Observed value |
|---|---|
| Service URL | https://mirage-workbench.onrender.com |
| Platform | Render Docker web service, free plan, Frankfurt |
| Release commit | `c2ed7413f3d184d611b476f5fac678a78c98ecee` |
| Deployment ID | `dep-dagig6v40ujc73fbk330` |
| Dashboard timestamp | 9 September 2026, 12:34:19 Moscow |
| Runtime live log | 9 September 2026, 12:35:32 Moscow |
| Build/deploy duration | 1 minute 13 seconds |
| Service state | Live |
| Service automatic deploys | Disabled |
| Blueprint Auto Sync | No; saved and verified |

This earlier deployment record is retained for provenance. The first public live
inspection below preceded it and is recorded separately.

### First public live inspection (historical)

The first cloud deployment completed its saved-evidence and allocator replay checks.
Its public browser displayed the committed four-market demo and then completed a fresh
Graph/RPC inspection through the hosted service. The historical WETH check below passed
the implemented checks, and both original T1 and the gated preview returned `switch`
at its evidence block.

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

Exact request latency was not measured. This historical browser check verified that release's live path;
the new capture has not been independently reread through two providers. The two-provider
verification elsewhere in the repository applies to the frozen block `25938082` demo.
See [public browser verification](RENDER_BROWSER_VERIFICATION_2026-09-09.json).

The earlier `2212062` release corrected a stale preview caption after a new report.
A second WETH check passed at block `25938561`; the preview used that block,
both policies proposed entry, and **Load demo** restored block `25938082` with
the new caption and cleared decisions. Backend detectors and the frozen fixture
were unchanged. The earlier full HTTP isolation check refers to the initial release.

The earlier `8278c65` release added the recorded sale size beside each verdict and the
allocation amount. The public browser verified the 10000 → 20000 → 10000 WETH
scenario: an immediate mismatch warning, an actual gate refusal for 20000, and
entry allowed again for the checked 10000. deUSD correctly shows that no completed
sale quote is available. This follow-up used saved evidence; it is not a new live
chain verification. That release left the backend and frozen observations unchanged.

The earlier `c2ed741` release bounded failed RPC reads to one market. If a shared
oracle read fails transiently, the next market can retry it; successful reads
remain reusable at their exact numeric block. The deployed public browser loaded
all four saved cases and replayed PAXG with original `switch` and gated `hold`.
This release smoke check used saved evidence, not a new live chain capture.
The frozen observations and UI are unchanged.

[Clean Linux CI](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34335127913)
at the same release commit passed 178 tests, ran the official SDK stdio example, and separately built
the same product inputs. The CI image ID was
`sha256:823e6aa069e20cfe808ebde7aea2cc13b0f65b085eec0d78c651bc3ebb4ec9dc`;
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
An attacker Origin on an otherwise valid Host must return 403. Earlier browser releases
verified the public page, saved-demo load, exact-size live capture and **Load demo** restoration.
Historical [HTTP checks](RENDER_HTTP_VERIFICATION_2026-09-09.json) on the initial release passed for two independent
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
