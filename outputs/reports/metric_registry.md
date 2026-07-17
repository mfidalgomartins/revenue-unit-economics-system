# Metric Registry

This registry defines the unit-economics policy thresholds and risk-scoring defaults consumed by code and validation.

## Efficiency Classification Policy
- Efficient: `LTV/CAC >= 3.0` and `payback <= 12.0 months`
- Inefficient: `LTV/CAC < 1.0`, observed payback `> 24.0 months`, or CAC is not recovered within the governed horizon
- Borderline: all remaining finite cases
- Undefined: missing/invalid denominator states or insufficient cohort maturity

## Payback Evidence
- Horizon: `24 acquisition-age months`
- Population: customers with enough observation time to reach the full horizon, including mature customers with zero transactions
- Measure: first month where cumulative contribution per mature customer equals or exceeds channel CAC
- `not_recovered`: right-censored at the horizon and classified inefficient
- `insufficient_maturity`: no mature customer evidence and classified undefined

## Risk Scoring Defaults
- Overall margin quality floor: `30%`
- Low-efficiency base score: `90.0`
- Borderline base score: `60.0`
- Payback contribution cap: `40.0` points
- Segment margin floor reference: `35%`
- Segment base score: `60.0`
- Cohort base score: `55.0`

## Causal Measurement Contracts
- Marketing incrementality: CUPED-adjusted treatment-minus-control contribution from randomized customer holdouts, reported with a 95% confidence interval
- Price elasticity: log demand response to log price using randomized weekly price assignments, fixed effects, and CR1 uncertainty clustered by week
- Valid pricing range: recommendations remain inside the observed 0.90–1.10 price index and optimize predicted contribution over bounded candidates
- Multi-touch attribution: position-based 40/20/40 allocation that reconciles observed contribution; descriptive only and never labeled incremental

## Change Control
- Thresholds and causal claim boundaries are used by analysis, dashboard classification, API publication, and validation checks.
- Any threshold change should update affected tests, recommendation guardrails, and published outputs.
