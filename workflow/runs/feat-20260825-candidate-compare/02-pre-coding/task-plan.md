# Task plan — feat-20260825-candidate-compare (attempt 2)

## Status

**BLOCKED — prerequisite work only.** This is not a coding work order because the configured checkout is the Lantern control plane rather than the hiring product.

## Prerequisite

1. **Correct the run's product target — HITL: required**
   - Set the hiring-product repository URL and base branch, assign the developer, and rerun stage 2.
   - End state: pre-coding can open product conventions/schema and name exact paths.

## Required order once rerun

1. Characterize existing finalist, scoring, evidence, status-transition, outreach, authorization, and analytics contracts; add tests first where coverage is thin (≤0.5 day).
2. Finalize persistence strategy; **HITL: required** for any schema migration (≤0.5 day).
3. Build/test an authorized comparison read model using existing judgments and weights, including 2/3 finalists, tie, provisional evidence, stale weights, and row errors (≤0.5 day).
4. Build/test idempotent advance/hold commands with required rationale and existing OUTREACH handoff (≤0.5 day).
5. Implement approved `verdict` UI in existing shell/components behind the product's feature-flag pattern, default off (≤0.5 day).
6. Add rationale, rebalance-return, conversation focus, and all non-happy states (≤0.5 day).
7. Add `compare_opened`, `compare_decision`, and `compare_rebalanced` through the existing analytics wrapper without rationale/evidence text (≤0.5 day).
8. Run product-required checks and self-review full diff (≤0.5 day).

## Coding principles most at risk

- Imitate a named product exemplar before inventing style; none can be selected from this checkout.
- Handle errors at boundaries and degrade row-by-row rather than collapsing comparison.
- Include behavior tests with each commit, especially scoring, stale weights, rationale validation, and candidate transitions.

## Packages

No new package planned. Any proposal requires developer sign-off and a full dependency justification.

## Definition of code-complete

- [ ] Correct product repository/base and assigned developer are recorded.
- [ ] Exact paths, exemplars, consumers, and tests replace this scaffold.
- [ ] Schema decision is final; migrations/packages have recorded approval where applicable.
- [ ] Comparison is authorized and uses existing judgments/weights only.
- [ ] Required rationale is validated and durably feeds calibration.
- [ ] Advance creates/opens the established outreach draft; hold remains visible in CALIBRATE.
- [ ] 2/3-finalist, `<2`, tie, sourcing, stale-weight, and row-error states pass tests.
- [ ] Analytics properties match the flow spec and exclude free text/evidence.
- [ ] Product test/type/lint/e2e commands pass; deviations and confidence map are recorded.
