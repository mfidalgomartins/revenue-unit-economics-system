# Decision Brief — Synthetic Revenue Analytics Case

## Executive Summary
- Total revenue: $54,595,966.54
- Contribution margin: $16,564,030.67 (30.3%)
- Growth quality is assessed via margin trend, cohort activation and retention, and channel unit economics.

## Channel Unit Economics (Observed)
- Best channel: organic (LTV/CAC 20.33, payback 0.0m)
- Weakest channel: social_ads (LTV/CAC 0.43, payback >24m (not recovered))

## Randomized Incrementality Evidence
- paid_search: $29.35 incremental contribution per treated customer (95% CI $17.58 to $41.11)
- social_ads: $13.03 incremental contribution per treated customer (95% CI $1.54 to $24.52)

## Observed Price Response
- Add-on: elasticity -1.58 (95% CI -1.72 to -1.43)
- Core: elasticity -1.23 (95% CI -1.36 to -1.10)
- Premium: elasticity -0.80 (95% CI -1.01 to -0.59)
- Services: elasticity -0.59 (95% CI -0.79 to -0.40)

### Bounded Pricing Decisions
- Add-on: test price index 1.05 ($96.60); predicted weekly contribution change $18.39
- Core: test price index 1.05 ($173.25); predicted weekly contribution change $513.19
- Premium: test price index 1.05 ($320.25); predicted weekly contribution change $749.73
- Services: test price index 1.05 ($407.40); predicted weekly contribution change $717.37

## Multi-Touch Attribution (Descriptive)
- Position-based channel credits reconcile $16,564,030.67 of observed contribution.
- Attribution allocates observed value across touches; randomized holdouts identify incremental impact.

## Scenario Summary (Policy Simulation)
- Baseline contribution: $16,564,030.67
- Scenario contribution: $24,477,398.57
- Estimated uplift: $7,913,367.90
- Unallocated budget holdback: $0.00
- Same-process seed sensitivity: 100% of 5 deterministic draws produced positive modeled uplift

## Stress Cases
- Best case: $29,372,878.28
- Base case: $24,477,398.57
- Worst case: $18,730,531.08

## Recommendations
1. Pilot staged reallocation toward organic, referral, partners, with LTV/CAC and payback guardrails.
2. Test reductions in paid_search, social_ads with randomized holdouts before broader cuts.
3. Diagnose activation and retention separately before changing lifecycle investment.
4. Use the randomized price-response estimates for bounded product tests; do not extrapolate outside the observed 0.90–1.10 index.
5. Decompose remaining low-margin pockets into mix, discount, scope, and cost-to-serve before intervention.

## Assumptions and Caveats
- Data is synthetic and intended for methodology demonstration, not forecasting.
- LTV is observed contribution margin per customer during the available window.
- CAC is period-level spend divided by customers acquired in the channel.
- Payback is the first acquisition-age month when cumulative contribution per mature customer recovers CAC; unrecovered channels are right-censored at 24 months.
- Complete payback curves use 19% to 22% of acquired customers by channel; younger customers are excluded from that curve only.
- Scenario outputs apply illustrative, bounded CAC/LTV elasticities and cap channel-level scale-up at 100%; excess budget is held back when capacity is exhausted.
- Seed sensitivity repeats the same synthetic data-generating process; it measures stability, not external validity.
- Marketing lift and price elasticity use explicit randomized synthetic assignments; real deployment requires a power calculation, interference review, and external-validity check.
- Multi-touch attribution is a descriptive reconciliation and is not used as a causal lift estimate.
- 258 transactions have cost above revenue. These are retained as intentional cost-to-serve exceptions.
