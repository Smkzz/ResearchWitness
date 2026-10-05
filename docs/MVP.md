# MVP definition

## User story

A research agent finds a potentially wrong objective claim in a paper. It should be able to hand ResearchWitness a compact structured case and receive a reproducible answer to the narrow question “does this explicit witness contradict this explicit formalization?” together with enough provenance to review or share the evidence.

## MVP success criteria

- One-command agent intake and bundle creation.
- Automatic deterministic checker routing.
- Exact/bounded replay with fail-closed unsupported inputs.
- Source quote anchoring and artifact hashes.
- Machine-readable JSON report.
- Human-readable offline HTML report.
- Private deterministic evidence export.
- Conservative contact-readiness state.
- Optional author-inquiry draft with user review required.
- No runtime API key or paid-model dependency.
- Real corrected-paper replay tests.

## Explicit non-goals

- General theorem proving.
- Autonomous claims that a whole paper is wrong.
- Automatic email sending or public posting.
- Misconduct detection.
- Researcher scoring.
- Pretending multiple agents are independent human experts.

## Next milestones after MVP

1. Expand graph coverage from chromatic lower-bound certificates to paths, connectivity, and graph mechanisms in the frozen screen.
2. Extend finite probability from explicit PMF event and expectation arithmetic to marginals, conditionals, and independence certificates.
3. Add recurrence and sequence certificates, then broaden exact modular and linear-algebra claims where historical cases justify them.
4. Run a frozen unseen-corrigenda benchmark before claiming increased real-paper coverage.
5. Add code-vs-paper consistency capsules in a sandboxed adapter.
6. Add optional paper retrieval and agent-harness integrations without putting model trust inside the verifier core.
