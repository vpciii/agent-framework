# ADR 0006: License the framework under the MIT License

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Vince Ciganik

## Context

The repository went public (to let adopted repos' CI install it —
project-portability pilot, opn-mcp) with no `LICENSE`. For an unlicensed
work the legal default is **all rights reserved**: others may view it but
may not legally copy, run, modify, or contribute. A framework whose
adoption doc tells other repos to `uvx --from git+…` install it defeats
its own purpose without a grant. Licensing is a decision that is
expensive to reverse once anyone depends on it — ADR territory.

## Decision

License under the **MIT License** — consistent with `opn-mcp` (its ADR
0009), maximally permissive, no copyleft obligations for repos that
embed or install the framework, and universally understood.
`pyproject.toml` declares `license = "MIT"` with `license-files`.

## Alternatives considered

- **Apache-2.0** — adds an explicit patent grant and NOTICE mechanics;
  more ceremony than a small personal framework warrants, and it would
  diverge from the household default (opn-mcp is MIT).
- **No license (status quo)** — rejected: contradicts the adoption story
  outright.
- **Copyleft (GPL/AGPL)** — rejected: would impose obligations on every
  adopting repo, the opposite of the friction-free adoption goal.

## Consequences

- Anyone may use, modify, and redistribute with attribution; no warranty.
- Contributions arrive under the same terms (inbound = outbound).
- Consistent licensing across vpciii's public repos; adopting repos need
  no license review to install the framework in CI.

## Adoption impact

Project ADR. Rollout: `LICENSE` at the root and the `pyproject.toml`
license fields, this PR. None for consuming repos.

## References

- opn-mcp ADR 0009 (the precedent this mirrors).
- `docs/adoption.md` (the install path this decision unblocks).
