# <Concise PR title>

## Summary

<1-3 sentences. What does this PR do and why is it scoped this way?>

## Motivation

<Why now? Link to the strategic plan section (PROJECT_2_PLAN.md §N) or
research note (DEEP_RESEARCH.md §N) that motivates the change. If this
PR closes an ERRATA item from README.md, link that too.>

## Design notes

<Key design decisions — the things a reviewer would otherwise ask about.
Cover: alternatives considered, trade-offs, why the chosen approach.
Mention any hard constraints from CLAUDE.md this PR has to honour
(sign convention, torch DLL order, loader contract, PARAMS_CLS, etc.).>

## Files

```
<path/to/file>            ← NEW / MODIFIED / DELETED — one-line purpose
...
```

## Tests

- <Test file added / extended, and what invariant it locks in.>
- <Regression test reference, if this PR fixes a bug.>
- Offline suite passes: `pytest tests/ -v -m "not network"`
- <Network suite if relevant: `pytest -m network` — note any new API key.>

## Out of scope

<Bullet list of related work intentionally deferred. Helps reviewer not
ask "why didn't you also...".>

## Checklist

- [ ] `make verify-imports` passes
- [ ] `pytest tests/ -v -m "not network"` passes (offline suite)
- [ ] Updated `CLAUDE.md` if a new hard constraint or convention was discovered
- [ ] Updated `README.md` / `ERRATA` if user-visible behaviour changed
- [ ] Whitepaper still compiles (`make whitepaper`) if any LaTeX touched
- [ ] No accidental commit of `fractal_data/`, `mlruns/`, or `.env`
- [ ] Sign convention preserved: `borrowing_rate >= lending_rate` everywhere
- [ ] Co-authored-by trailer kept in commits
