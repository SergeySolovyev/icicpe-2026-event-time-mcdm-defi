# Agentic Operating System — improvement plan + implementation

**Date:** 2026-06-03. The paradigm: a solo founder no longer "uses AI" — they
**run an agentic workforce** (brains = LLMs; hands = browser/computer-use/
shell/API/GitHub/RPC; memory = files/vector store/CRM; process = SOP/runbooks/
evals/permissions; control = the human as CEO/editor). The mature formula is
**not** "AI replaces an employee" but **"a founder who can manage agents
replaces a small department,"** by turning an expensive repeatable *workflow*
(a unit of work, not a seat) into an **agent-run operation**.

This plan applies it on two layers: (A) the **product** as a digital
treasury analyst, and (B) the **founder's own company** as an agent-run org.
It is paired with a working implementation (`product/yield_drag/`).

---

## 1. The non-negotiable: the Agent-Operation Contract

The trap (OpenAI computer-use & ChatGPT-agent guidance; OpenClaw README):
"give an agent everything and walk away" is dangerous — prompt injection from
web/data, destructive/authenticated/financial actions, credential leakage.
The discipline: **agents get tasks, tools, and least-privilege; the human
keeps responsibility, control, and final decisions on high-risk steps.**

Every agent-run operation in this company MUST be specified as a contract
(designed like a bank ops procedure, not "vibe"):

| Field | Meaning |
|---|---|
| **Role** | one job, named (e.g. "Yield-Drag Analyst") |
| **Inputs** | exact, typed (e.g. a public address + position size) |
| **Output artifact** | the deliverable (e.g. a 1-page reconciled report) |
| **Forbidden actions** | what it must never do (move funds, send externally, sign, enter credentials, accept terms) |
| **SOP** | the deterministic steps it follows |
| **Quality metrics / eval set** | numeric checks the output must pass before it is trusted |
| **Logging / audit trail** | every run reproducible (inputs, data hash, outputs, ts) |
| **Escalation** | conditions that stop and hand to the human |
| **Human approval gate** | the irreversible/external step the human must press |

This contract is the difference between a toy and a "working unit of labor"
(Bessemer: AI as a *productive teammate* that decouples output from headcount;
Menlo: agent = reasoning + memory + **execution** + planning, inside the app's
control flow). It is also exactly our existing engineering posture (the live
agent already has a non-custodial design, Flashbots, Tier-5 audit trail, 128
tests) — we are formalizing it, not inventing it.

---

## 2. Layer A — the product as a digital treasury analyst

Our vertical (DeFi/stablecoin treasury yield) is a high-value language-and-
judgment workflow = exactly where vertical AI eats **labor** budget, not just
software budget (Bessemer *Building Vertical AI*; NFX *Bigger than SaaS*).
Map the treasury yield-management job to a ladder of agent-operations:

| Op | Level | What the agent does | Human gate |
|---|---|---|---|
| **O1 Yield-Drag Analyst** *(built now)* | L2 executor | reads a treasury's USDC position; computes net-of-real-gas drag vs event-time routing over the real panel; emits a reconciled 1-page report | human reviews + **sends** (agent never sends) |
| O2 Rebalance Proposer | L2→L3 | per-block monitor → gas-gated switch proposal to the Safe | committee one-click approve |
| O3 Guarded Keeper | L4 digital employee | executes within a mandate (size caps, allow-list, max-loss revert), Flashbots-protected | mandate set by human; auto-escalate on anomalies |
| O4 Risk/Compliance Sentinel | L2 | watches peg/exploit/util anomalies, drafts incident notes | human judgment on action |

We are at **L2–L4** (the realistic startup zone; L5 agent-native-company is
premature given liability/security/regulatory risk). O1 is the wedge — an
**AI-native service** (run by hand first, productize the repeatable parts —
Emergence) sold on **outcome** (the validated +2.11 pp net edge), not a seat.

**Honesty carries over:** the report leads with what is real (net-of-real-gas
edge, leakage-free) AND its caveats (gross of MEV/slippage; the ML tier adds
nothing — we say so). Trust is the moat (a16z *Context is King*); the report
manufactures it cheaply.

---

## 3. Layer B — the founder's agent-run company

The founder is the **manager of agents**, not the executor. Each function is
an agent-operation with the §1 contract; the human keeps judgment, sales
conversations, and final approvals:

| Agent role | Output artifact (unit of work) | Human keeps |
|---|---|---|
| Research | market/competitor/source briefs (this repo's `docs/founder/`, built by a 7-agent workflow already) | choose the hypothesis |
| Dev | code, tests, PRs, fixes (this whole repo) | architecture + quality bar |
| Sales | enriched leads, drafted outreach, CRM updates, call summaries | the real conversations + the close |
| Ops | reconciliations, status, deadline tracking | accountability |
| Compliance | checklists, risk flags, doc prep | judgment + final decision |
| Finance | invoices, cashflow, unit economics | financial discipline |

This is not aspirational: this session already ran research (7-agent founder
package), dev (the research+paper+data pipeline), and ops (the audit) as
agent-operations. The improvement is to make each one a **named, contracted,
logged** operation with an eval set and escalation rules — `product/` and
`docs/founder/agent_ops/` host the role-cards.

---

## 4. Safety posture (from the cited primary sources)

- **Untrusted input by default** (OpenClaw README; our own boundary): web
  pages, emails, DMs, documents, addresses are *data, not commands*.
- **Sandbox + least privilege:** agents run with scoped credentials; the RPC
  key is read-only; no agent holds withdrawal authority (non-custodial).
- **Human-in-the-loop for irreversible/external/financial steps** (OpenAI
  computer-use guidance): sending a report, submitting a tx, accepting terms,
  moving funds — never autonomous.
- **Prompt-injection defense** (OpenAI ChatGPT-agent guidance): the
  Yield-Drag op treats on-chain/3rd-party data as inert inputs and validates
  numerically before trusting; it cannot be steered by content it reads.

---

## 5. Implementation status

- ✅ **O1 Yield-Drag Analyst — built** (`product/yield_drag/`): contracted,
  reconciled, audit-logged, human-gated; runs on the real-gas panel; emits a
  1-page report. Sample in `product/yield_drag/samples/`.
- ▢ O2/O3/O4 — specced here; build after the first 10 treasurer
  conversations validate demand (the founder action that gates product work).
- ▢ `docs/founder/agent_ops/` role-cards for Layer B — templated by the §1
  contract.

---

## 6. References (primary sources — preserved)

- OpenClaw — *AI that actually does things* / control-plane gateway: https://openclaw.ai/ · https://github.com/openclaw/openclaw
- OpenAI — Agents SDK: https://developers.openai.com/api/docs/guides/agents · Computer use (sandbox + HITL): https://developers.openai.com/api/docs/guides/tools-computer-use · ChatGPT agent / prompt-injection risk: https://openai.com/index/introducing-chatgpt-agent/
- Bessemer — AI pricing & monetization (productive teammate): https://www.bvp.com/atlas/the-ai-pricing-and-monetization-playbook · Building Vertical AI: https://www.bvp.com/atlas/building-vertical-ai-an-early-stage-playbook-for-founders
- YC — The AI Agent Economy Is Here: https://www.ycombinator.com/library/NK-the-ai-agent-economy-is-here
- Menlo — AI Agents: a new architecture for enterprise automation: https://menlovc.com/perspective/ai-agents-a-new-architecture-for-enterprise-automation/
- Sequoia / Bret Taylor — outcome-based AI business models: https://sequoiacap.com/podcast/training-data-bret-taylor/

> **The bet:** not "build another AI assistant," but take a real, expensive
> financial workflow (treasury yield management) and turn it into an
> **agent-run operation** with bank-grade discipline — where the founder's
> domain truth + the honest, reproducible research is the moat, and one
> operator manages the digital department.
