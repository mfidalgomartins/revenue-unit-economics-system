# Metric Registry

This registry is the single source of truth for unit-economics policy thresholds and risk-scoring defaults.

## Efficiency Classification Policy
- Efficient: `LTV/CAC >= 3.0` and `payback <= 12.0 months`
- Inefficient: `LTV/CAC < 1.0` or `payback > 24.0 months`
- Borderline: all remaining finite cases
- Undefined: missing or invalid denominator states

## Risk Scoring Defaults
- Overall margin quality floor: `30%`
- Low-efficiency base score: `90.0`
- Borderline base score: `60.0`
- Payback contribution cap: `40.0` points
- Segment margin floor reference: `35%`
- Segment base score: `60.0`
- Cohort base score: `55.0`

## Change Control
- Thresholds are used by analysis, dashboard classification, and validation checks.
- Any threshold change should update affected tests, recommendation guardrails, and published outputs.
