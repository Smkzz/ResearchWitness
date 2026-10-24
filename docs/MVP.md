# MVP definition

This describes the current narrow product contract. Future priority/order is defined
only by [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md), not by the historical milestone
list formerly on this page. Agents start with [AGENTS.md](../AGENTS.md).

## User story

A research agent prepares a compact structured case and asks: does this explicit
witness contradict this explicit mathematical formalization? ResearchWitness returns
a reproducible answer and source-linked evidence, not a verdict on an entire paper.

## Existing MVP criteria

One-command intake/bundle creation; deterministic checker routing; exact bounded
replay; fail-closed unsupported input; source quote anchors/hashes; JSON and offline
HTML reports; deterministic private evidence export; conservative contact readiness;
local author-inquiry drafting; no runtime API-key or paid-model requirement; and
historical corrected-paper replay fixtures. Availability is tracked in
[PROJECT_STATUS.md](PROJECT_STATUS.md), not inferred from this criteria list.

## Next product milestone

RW-01/RW-02/RW-09 consolidate the existing audit implementations into one installed,
source-to-report workflow with explicit coverage, failures and abstentions. Reuse
#12's local UI only after separating custody authority and reviewing its attack
surface. Ship a scoped engineering preview when its gates pass; independent
research performance is a separate milestone.

## Non-goals and authority

No arbitrary theorem prover, whole-paper accusations, automatic email/public posting,
misconduct detection or researcher scoring. Multiple agents are not independent
human experts. A local draft can be created autonomously; the runtime never sends
it, and external contact needs a separate safety decision. Ordinary engineering
choices, review and qualified merges do not require routine human approval.
