# Chainlink: the decision, recorded onchain

MIRAGE decides offchain. Until this addition, that decision stayed inside our own
process: whatever executed next had no way to see it, and nothing independent checked
the price our reasoning rested on.

`MirageGate` closes both gaps with the smallest contract that can honestly do it. It
records one finished verdict for one market at one exact sale size, and it consults a
Chainlink price feed itself before storing anything.

## What each part does

| Part | File | Responsibility |
|---|---|---|
| `MirageGate` | [contracts/src/MirageGate.sol](../../contracts/src/MirageGate.sol) | Reads the Chainlink feed, measures the disagreement with MIRAGE's reference price, stores the verdict |
| `ExecutionGuard` | [contracts/src/ExecutionGuard.sol](../../contracts/src/ExecutionGuard.sol) | Reverts an entry unless the gate holds a fresh `Allow` for that exact market and amount |
| Publisher | [scripts/mirage_chainlink_publish.py](../../scripts/mirage_chainlink_publish.py) | Turns a MIRAGE decision into a ready-to-send transaction. Holds no key, signs nothing |
| Deploy script | [contracts/script/Deploy.s.sol](../../contracts/script/Deploy.s.sol) | Deploys both contracts with the operator's own key |

## The one design decision that matters

Chainlink can only make the outcome stricter.

`submitDecision` takes the verdict the offchain pipeline produced and the reference price
it used. It then reads `latestRoundData()` itself and computes the deviation between that
reference and the live answer. If a proposed `Allow` disagrees beyond `maxDeviationBps`,
it is stored as `Blocked` and the record is flagged `vetoedByFeed`. A proposed `Blocked`
is always stored as `Blocked`.

There is no path in which the feed turns a `Blocked` into an `Allow`. That direction is
deliberate and matches the rest of the product: a check may cancel an entry, never
authorise one. A stale feed is not treated as agreement either — if `updatedAt` is older
than `maxFeedAge`, the whole call reverts rather than recording a decision on a price of
unknown age.

## Why this is a state change and not logging

A flag nobody reads is a log line. `ExecutionGuard.enter` reverts with `EntryNotAllowed`
unless `MirageGate.isAllowed(marketId, amountUsdc, maxAge)` is true. The amount is part
of the storage key, so a decision taken for one sale size cannot authorise a larger one —
the same property the offchain gate enforces, carried into the contract.

The guard moves no funds and custodies nothing. It demonstrates the control flow, which
is what can be honestly demonstrated at prototype scale.

## The refusal that keeps the comparison meaningful

A Chainlink ETH/USD feed describes ether. Publishing a wstETH decision against it would
report a "deviation" that is really the wstETH/ETH exchange rate, around twenty percent,
and would veto every entry for a reason unrelated to risk.

The publisher refuses. `FEED_COVERAGE` declares which collateral each feed actually
describes, and a market outside that set is rejected with an explanation rather than
published with a meaningless number:

```console
$ python scripts/mirage_chainlink_publish.py --market wstETH
Refusing to publish.

Feed 'ETH / USD' describes ['ETH', 'WETH'], not WSTETH.
Publishing a WSTETH decision against it would report a deviation that reflects the
difference between two different assets, not a disagreement about price. Refusing.
```

Extending this to more markets is a matter of adding the right feed per collateral, not
of relaxing the check.

## The two decisions worth publishing

Both come from the same market and the same recorded evidence. Only the size differs,
and that is the whole point.

| Amount | Original policy | MIRAGE gate | Admission | Stored verdict |
|---|---|---|---|---|
| 10,000 USDC | switch | switch | pass | `Allow` |
| 20,000 USDC | switch | hold | insufficient | `Blocked` |

The second row is not a different market behaving differently. It is the same market
where the saved sale quote does not cover the proposed size, so the evidence does not
authorise the entry. After both are published, `ExecutionGuard.enter` succeeds for
10,000 and reverts for 20,000.

## Tests

```console
cd contracts && forge test
```

21 tests cover the feed veto in both directions, stale and non-positive answers, access
control, the size binding, decision ageing, and each guard path. A fuzz test asserts the
invariant directly: for any feed answer, a stored `Allow` implies the measured deviation
was within the bound.

## Deploying it

Nothing in this repository stores, reads or transmits a private key. The operator runs
these commands with their own key; `--interactive` makes `cast` and `forge` prompt for it
rather than reading a flag or the environment, so it never enters shell history.

```bash
export SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
export CHAINLINK_FEED=0x694AA1769357215DE4FAC081bf1f309aDC325306   # Sepolia ETH/USD

cd contracts
forge script script/Deploy.s.sol:Deploy \
  --rpc-url $SEPOLIA_RPC_URL --broadcast --interactives 1
```

The script prints both addresses. Then produce each transaction:

```bash
python scripts/mirage_chainlink_publish.py --market WETH --amount 10000 --gate <MIRAGE_GATE>
python scripts/mirage_chainlink_publish.py --market WETH --amount 20000 --gate <MIRAGE_GATE>
```

Each run prints the exact `cast send` to run, the values it will send, and a `cast call`
to read the stored decision back. Finally, show the guard actually gating:

```bash
cast send <EXECUTION_GUARD> "enter(bytes32,uint128)" <MARKET_ID> 10000000000 \
  --rpc-url $SEPOLIA_RPC_URL --interactive          # succeeds
cast send <EXECUTION_GUARD> "enter(bytes32,uint128)" <MARKET_ID> 20000000000 \
  --rpc-url $SEPOLIA_RPC_URL --interactive          # reverts: EntryNotAllowed
```

## Verified facts

The Sepolia ETH/USD aggregator was read directly on 12 September 2026:
`description()` returned `"ETH / USD"`, `decimals()` returned `8`, and
`latestRoundData()` returned a positive answer with a current `updatedAt`.

MIRAGE's recorded reference price for the WETH market at block 25938082 is
`2500.66364819905311430` USDC per WETH, which the publisher scales to `250066364819` at
the feed's eight decimals.

## The whole sequence, rehearsed end to end

Every step above was executed on 13 September 2026 against a local Anvil fork of Sepolia
at block 11691510, using Anvil's own published development key. The fork serves the real
aggregator at `0x694AA1769357215DE4FAC081bf1f309aDC325306`; `description()` returned
`ETH / USD` and the contract read the answer `252210000000` itself inside `submitDecision`.

| Step | Observed |
|---|---|
| Deploy both contracts | succeeded |
| Publish 10,000 USDC | stored `Allow`, deviation **84 bps**, `vetoedByFeed` false |
| Publish 20,000 USDC | stored `Blocked`, same evidence, same block |
| `enter(marketId, 10000000000)` | succeeded, `entryCount` 1 |
| `enter(marketId, 20000000000)` | reverted `EntryNotAllowed` |

84 bps is the gap between MIRAGE's recorded mainnet reference of 2500.66 USDC per WETH
and the live testnet answer of 2522.10 — ordinary movement between a recorded mainnet
block and a live testnet feed, comfortably inside the 500 bps bound, so the `Allow`
survived. The `Blocked` record carries `vetoedByFeed` false, which is the honest reading:
the offchain gate refused that size, the feed did not disagree. The contract keeps those
two reasons distinct rather than collapsing them into one flag.

Full record: [CHAINLINK_FORK_REHEARSAL_2026-09-13.json](CHAINLINK_FORK_REHEARSAL_2026-09-13.json).

This is a fork, not the live network: the addresses above are fork addresses and mean
nothing onchain. What it establishes is that the contracts compile, deploy, read the real
feed, and gate execution in the intended direction.

## Limits

- The contracts are deployed to Sepolia, not to Ethereum mainnet.
- MIRAGE's evidence is read from mainnet while the feed consulted is on Sepolia. The
  mechanism is real; the two sides of the comparison sit on different networks, and the
  deviation therefore includes ordinary price movement between them.
- `ExecutionGuard` proves control flow. It holds no funds, and no part of this prototype
  holds, transfers or swaps value.
- The MIRAGE engine itself is unchanged and remains read-only. Only the publisher, run by
  the operator, produces a transaction, and it signs nothing on its own.
