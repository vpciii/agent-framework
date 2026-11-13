# Architecture Decision Records

Numbered, append-only records of significant decisions for this project.
See `$METHODOLOGY_HOME/methodology.md` §1 for when an ADR is required, and
`$METHODOLOGY_HOME/templates/adr/_template.md` for the format.

Newest first when browsing. Never edit an accepted ADR — supersede it with a
new one and mark the old one `Superseded by NNNN`.

- **0009** — The validator is bound by what the eval set measures; lineage is a preference and a paid API is allowed. *Proposed.* Replaces in part: 0001 decision 4, 0004's validator row, 0008 decision 5.
- **0008** — The validator judges conformance to the contract; it does not hunt for unstated defects. Supersedes 0005.
- **0007** — The worker session is confined; the orchestrator holds the credentials and checks what comes back.
- **0006** — License the framework under the MIT License.
- **0005** — One per-PR gate: conformance and refutation in a single validator. *Superseded by 0008.*
- **0004** — Role execution surfaces (subscription-backed interactive roles, API-backed programmatic roles).
- **0003** — Adopt the methodology's reference spec-coverage checker.
- **0002** — Python implementation stack.
- **0001** — Model-agnostic roles, bound by a roster.
