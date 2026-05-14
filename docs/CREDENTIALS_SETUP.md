# Credentials Setup — `D:\DeFi\predictive-mcdm-defi\.env`

Filled-in `.env` is **NEVER committed** (`.gitignore` rule). Local file only.

Priority is **TheGraph** > **Ethereum RPC** > **Dune** (the first is mandatory,
the next two refine quality).

---

## 1. `THE_GRAPH_API_KEY`  *(mandatory)*

**Used for:** Aave V3 protocol-subgraph (hourly USDC rates + utilization +
TVL) and Compound V3 Messari subgraph. Single key serves both.

**Free tier:** 100,000 queries / month — we consume ~30 in a full data
pull, ~100/month over a 4-week development cycle. Plenty of headroom.

**Steps (3 minutes):**
1. Go to https://thegraph.com/studio/apikeys/
2. Click "Connect Wallet" — MetaMask works, no on-chain tx required, just
   a signature to authenticate.
3. Click "Create API Key". Name it `predictive-mcdm-defi`.
4. Copy the 32-char hex string.
5. Paste into `.env`:
   ```
   THE_GRAPH_API_KEY=<paste here, no quotes>
   ```

**Verification:** `make verify-imports` should pass. After Compound loader
implementation, `python -m data.fetch_compound` will exercise the key.

---

## 2. `ETHEREUM_RPC_URL`  *(highly recommended)*

**Used for:** one-shot reads of (a) Aave PoolDataProvider for kink
parameters (slope1, slope2, optimalUsageRatio, reserveFactor) and (b)
Compound Comet getSupplyRate/getBorrowRate for ground-truth validation of
our kink-subtraction. Tiny query budget — ~20 calls total over the
project.

**Recommended provider — Alchemy** (free tier most generous):

**Steps (4 minutes):**
1. Go to https://dashboard.alchemy.com/signup
2. Sign up (email, no card).
3. Create an "App" with Network = "Ethereum Mainnet".
4. From the app's dashboard, copy the HTTPS URL — looks like
   `https://eth-mainnet.g.alchemy.com/v2/AbC123...`
5. Paste into `.env`:
   ```
   ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/...
   ```

**Free tier limits:** 300 million compute units / month. Our entire usage
fits in ~1 thousand compute units. Effectively unlimited.

Alternatives if you already have one: Infura, QuickNode, Ankr, llamarpc
(free public — slower but works for our 20-query budget).

---

## 3. `DUNE_API_KEY`  *(optional fallback)*

**Used for:** historical gas-price series (hourly median 2024-11 → 2026-04).
Dune's `gas.gas_price` table is the canonical source.

**Free tier limits API access:** Dune's free tier does NOT include API
access — API requires the $390/mo "Plus" plan. **For our case the
alternative is:**
- Etherscan's free API for gas history (rate-limited but free), or
- llama.fi gas price endpoint (free, no key needed), or
- Skip historical-gas accuracy and use a flat $30 gas-cost assumption
  (acceptable per plan §6.2 "Transaction cost" — ablation #12 reports
  break-even gas anyway, so exact historical gas matters only at the
  margin).

**If you already have a Dune Plus account, paste the key:**
```
DUNE_API_KEY=<paste here>
```

**If not:** leave blank; `data/fetch_gas_eth.py` falls back to Etherscan
free tier transparently.

---

## 4. `COINGECKO_API_KEY`  *(not needed — free public API works)*

ETH/USD hourly close. Public endpoint is rate-limited to 10-30
calls/minute, which is fine for a one-off pull of 13,000 hourly bars
(~22 minutes wall-clock with the loader's built-in throttle).

If you want to speed it up, a Demo Pro key (free, requires email signup)
raises the limit:
```
COINGECKO_API_KEY=<optional>
```

---

## Final `.env` template

```sh
# ===== MANDATORY =====
THE_GRAPH_API_KEY=...

# ===== HIGHLY RECOMMENDED =====
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/...

# ===== OPTIONAL =====
DUNE_API_KEY=
COINGECKO_API_KEY=

# ===== Local config =====
DATA_PATH=D:/DeFi/predictive-mcdm-defi/data/cached
MLFLOW_TRACKING_URI=file:./mlruns
```

Copy this to `.env` (not committed — `.gitignore` rule). Test with:
```
.venv/Scripts/python.exe -m data.fetch_aave_subgraph --dry-run
```
(coming in next session — needs the key first.)
