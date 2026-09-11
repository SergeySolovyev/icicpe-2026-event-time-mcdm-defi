# Prompt and planning provenance

Prepared on 9 September 2026. This is a **selected public reconstruction**, assembled after implementation from the supplied user instructions, historical handoff and current implementation record. It is not a complete original prompt archive or an assertion that every planning artifact has been published.

## Source register

| ID | Source and dating | What is established / publication boundary |
| --- | --- | --- |
| U1 | User's continuation instructions supplied to this Codex task on 9 September 2026 | Direct human directions shown below. The message also pasted earlier agent narration; that narration is not treated as proof of personal human coding. The full private conversation is not reproduced. |
| H1 | `HANDOFF_v2.md`, dated in its header “08.09.2026 вечером”; read locally on 9 September | Original planning input outside this repository. The supplied history attributes its preparation to an earlier AI-assisted session. It contains withdrawn interpretations and operational context, so the raw document is not republished. |
| C1 | `CURRENT_STATE_2026-09-09.md`, latest section “08:32 UTC”, consulted on 9 September | Agent-maintained continuation record. Used to locate completed work and corrected decisions; private account/process state is omitted. Public claims are supported by linked repository artifacts below. |
| G1 | Repository history through `e757e91`, 9 September 2026. This register entry was not re-cut afterwards: `BUILD_SPEC.md` was later revised against `5488350` of 9 September, and further commits landed through `ba99254` of 10 September and the documentation work of 11 September. Read this row as the cutoff of this document, not of the repository | Public implementation and revision evidence; commit timestamps alone do not determine human versus AI authorship. [Commit history](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/commits/master/). |

H1 original-file SHA-256, computed from its exact local bytes on 9 September:

```text
a120a14c7d908eedb011ce60f47142e5958cdad3f610eea7d05be8911e94375b
```

This digest identifies the source consulted; it is not a public copy, a timestamp proof or evidence that the original statements were correct. The older `HANDOFF.md` and obsolete submission/design files were not used as authoritative submission text. No credentials or session transcripts are included here.

## Exact short directives from U1

Quotation text is preserved in Russian; explanatory text is an English summary of its implemented effect. The source/date for every quote is U1, 9 September 2026.

| Exact excerpt | Effect on the build |
| --- | --- |
| “Цель — выиграть, а не просто подать заявку.” | Prioritize a working, reviewable product and meaningful reuse for the hackathon. This does not imply eligibility or a predicted award. |
| “Подаёмся на трек Continuity: расширяем существующий открытый репозиторий, а не пишем с нуля.” | Preserve the allocator baseline and explicitly attribute both existing foundations. |
| “Каждую цифру для демо перепроверять одиночными вызовами.” | Preserve raw calls and block anchors; run independent single-call checks for captured demonstration evidence. |
| “Если найдёшь ошибку в числах — говори сразу.” | Challenge the supplied arithmetic; publish the [correction record](../CORRECTIONS_2026-09-09.md) instead of repeating the old financial interpretation. |
| “Начни с чтения документа и скажи, что вызывает сомнения, прежде чем писать код.” | Inspect the handoff and existing code before accepting the proposed causal claims. |
| “Если что-то не сделано — говори прямо, а не обходи молчанием.” | Label missing/unsupported evidence explicitly and distinguish saved replay, live capture and pending submission work. |

U1 also prioritized deployment of the Graph subgraph before detector 2 because synchronization was an external dependency, and reserved account-gated/final submission actions for the owner. These are paraphrases, not additional verbatim prompt excerpts.

## Public planning and revision trail

- [BUILD_SPEC.md](BUILD_SPEC.md) maps H1 sections to implemented, revised or superseded requirements. It is the corrected current specification, created after the work.
- [CORRECTIONS_2026-09-09.md](../CORRECTIONS_2026-09-09.md) withdraws the unsupported accounting, warning-label, oracle and TVL-to-policy interpretations without treating the initial plan as ground truth.
- [ARCHITECTURE.md](../ARCHITECTURE.md), [UI_DESIGN.md](../UI_DESIGN.md), [UNISWAP.md](../UNISWAP.md) and [MCP.md](../MCP.md) describe the implemented evidence flow, interface and integration constraints. They are working design/verification documents, not presented as untouched original prompts.
- [DEMO_SCRIPT.md](../DEMO_SCRIPT.md), [SUBMISSION_DRAFT.md](../SUBMISSION_DRAFT.md) and [UNISWAP_FORM_DRAFT.md](../UNISWAP_FORM_DRAFT.md) are AI-assisted preparation artifacts. Their presence does not establish that a human video or final submission has been completed.
- [AI_USE.md](../AI_USE.md) identifies affected files and separates observed Codex work, reported earlier Claude Code use and unconfirmed historical authorship.

## Completeness and confirmation

Selected excerpts and a corrected specification do not replace the full original archive required by the event's [spec-driven development rule](https://ethglobal.com/events/ethonline2026/info/details). The raw historical handoff contains withdrawn claims that the owner instructed us not to republish; private operational records are also excluded. This limitation is disclosed, not described as an approved exemption.

The owner must confirm the historical attribution and determine what additional original, appropriately sanitized planning material can be submitted, or obtain clarification from the organizers. Do not claim this reconstruction is complete or that attribution alone proves meaningful human participation.
