# MIRAGE Morpho market discovery

This subgraph discovers Ethereum Morpho Blue markets from their creation logs.
MIRAGE uses those market identifiers to read contract state and make admission
decisions. No asset amounts, TVL, prices, or admission verdicts are stored here.

Local code generation and compilation passed on 9 September 2026 with Node
24.11.0, Graph CLI 0.98.1 and graph-ts 0.38.2. This is a build result; a live
Studio deployment and successful queries are recorded in [DEPLOYMENT.json](DEPLOYMENT.json).
Full synchronization and discovery of 697 USDC market IDs were verified on
9 September. Four markets were inspected in the committed demo, not all 697.

## Source contract

- Network: Ethereum mainnet.
- Contract: `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb`.
- Start block: `18883124`.
- Event in [subgraph.yaml](subgraph.yaml):
  `CreateMarket(indexed bytes32,(address,address,address,address,uint256))`.
- Canonical topic0:
  `0xac4b2400f169220b0c0afdde7a0b32e775ba727ea1cb30b35f935cdaab8683ac`.

Preserve the tuple signature. Flattening its five fields changes topic0 and
would silently index the wrong event. The single handler in
[src/morpho-blue.ts](src/morpho-blue.ts) writes one immutable `Market` entity
using only the event and transaction data. It makes no contract calls.
`creator` records `transaction.from`, which can differ from an internal caller.

Keep state events such as Supply, Borrow and AccrueInterest out of this
discovery deployment. MIRAGE reads state separately at an explicit block.
The schema and mapping intentionally contain no TVL conversion.

## Build and deploy from PowerShell

From the repository root:

```powershell
Set-Location .\subgraph
npm ci
.\deploy.ps1
```

The helper runs the pinned CLI at `bin/run.js`, generates types and builds the
WASM. It disables manifest migrations and checks that the manifest did not
change. Without `-Deploy`, it only prepares local artifacts.

Sergey first signs into [Subgraph Studio](https://thegraph.com/studio/), creates
the `mirage-morpho-markets` subgraph, and obtains its deploy key. Use the actual
Studio slug if it differs. Load the key into the current terminal without
typing it as a literal command or saving it in the repository:

```powershell
$graphSecret = Read-Host 'Studio deploy key' -AsSecureString
$env:MIRAGE_GRAPH_DEPLOY_KEY = [System.Net.NetworkCredential]::new('', $graphSecret).Password
try {
    .\deploy.ps1 -Deploy -SubgraphName mirage-morpho-markets -VersionLabel v0.0.1
}
finally {
    Remove-Item Env:MIRAGE_GRAPH_DEPLOY_KEY -ErrorAction SilentlyContinue
    $graphSecret.Dispose()
}
```

The helper passes the key inside the Node process, without placing its value
in OS command-line arguments or writing a Graph CLI authentication file.
The deployment branch was exercised successfully for `mirage-morpho-markets`
version `v0.0.1` on 9 September 2026.

Deployment to Studio does not publish the subgraph onchain. The official
[Studio guide](https://thegraph.com/docs/en/subgraphs/developing/deploying-publishing/using-subgraph-studio/)
currently states 3,000 development-URL queries per day and a limit of three
deployed unpublished subgraphs per account. Check the account dashboard if a
limit prevents deployment. Synchronization time is not guaranteed.

## Verify the live deployment

Copy the deployment query URL from Studio. Its deploy key and query API key
have different purposes; never use the deploy key as a query credential.
Run this query in the Studio playground or against that authenticated URL:

```graphql
query DiscoveryPage($after: Bytes!) {
  _meta {
    deployment
    hasIndexingErrors
    block { number hash }
  }
  markets(
    first: 1000
    orderBy: id
    orderDirection: asc
    where: {
      loanToken: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
      id_gt: $after
    }
  ) {
    id
    loanToken
    collateralToken
    oracle
    irm
    lltv
    blockNumber
    blockTimestamp
    txHash
  }
}
```

Start with `{"after":"0x0000000000000000000000000000000000000000000000000000000000000000"}`.
Continue with the last returned ID until a page contains fewer than 1,000
entities. Check `hasIndexingErrors == false`, a plausible indexed block, and
nonempty market results; a green synchronization indicator alone is insufficient.
For a reproducible scan, pin all pages to the same indexed block using GraphQL
`block: {hash: ...}` with the finalized hash resolved by RPC, and read the
corresponding contract state at its numeric block. Historical `_meta` queries
by number can legitimately return `hash: null`; the hash-based query returns
the resolved hash and binds every page to the same chain state.
Compare a returned market ID and parameters with one direct
`idToMarketParams(bytes32)` call before treating the deployment as verified.

Record the deployment identifier, query time, indexed block/hash and market
count with the MIRAGE report. Do not substitute the historical market count
from the handoff for a live query. Never derive a monetary total from this
discovery response.

The manifest already uses `prune: auto`. Old indexed blocks can become
unavailable, particularly while the first synchronization advances quickly.
An observed error on 9 September rejected block `19972938` after the retained
range had moved to `21191522`. Wait for synchronization, then use a recent
indexed/finalized block. Historical offline evidence remains in the chain
snapshots; it is not guaranteed to be queryable from this pruned subgraph.

## ETHOnline evidence

The [official The Graph prize page](https://ethglobal.com/events/ethonline2026/prizes/the-graph)
lists a Continuity AI tooling/use-case pool of $5,000, split into $2,500,
$1,500 and $1,000. It requires a substantive Graph dependency, live provider
data, meaningful processing or decisions, a runnable open-source repository,
and a two-to-four-minute demo. Show Graph discovery feeding MIRAGE's decision
path in the running agent/application. A local build or offline snapshot alone
does not establish eligibility.

The separate composability prize requires composition or meaningful use of a
standardized schema; a single custom discovery subgraph does not satisfy that
requirement by itself. Whether unlabelled prizes admit Continuity projects
still requires clarification from the organizers.

## Version control

Commit the manifest, schema, mapping, ABI, package files, this guide and helper.
[.gitignore](.gitignore) excludes `node_modules/`, `generated/`, `build/` and
`.graph/`; they can be regenerated. Never commit credentials or authenticated
query URLs containing keys.
