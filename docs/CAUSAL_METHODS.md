# Causal measurement and attribution

The system separates causal effects from descriptive allocation. Randomized assignments support incrementality and price-response claims; multi-touch attribution only reconciles observed value.

## Marketing incrementality

`marketing_experiments.csv` contains customer-level randomized control and treatment assignments, a fixed 90-day outcome window, pre-period contribution, conversion, and observed contribution.

For each experiment:

1. Estimate the CUPED coefficient from pre-period contribution and the outcome.
2. Center and remove the pre-period component from both arms.
3. Report the adjusted treatment-minus-control contribution per customer.
4. Calculate a Welch standard error, two-sided p-value, and 95% confidence interval.
5. Report sample-ratio mismatch and pre-period standardized-difference diagnostics.
6. Multiply per-customer lift by treated customers only to report realized experiment-scale incremental contribution.

The published diagnostic passes when the balanced-allocation sample-ratio mismatch test has `p >= 0.01` and the absolute pre-period standardized difference is at most `0.10`. These checks do not replace prospective power, exposure, attrition, interference, or outcome-window reviews in a real experiment.

## Price elasticity

`pricing_interventions.csv` randomizes weekly product-region cells to price indices `0.90`, `1.00`, or `1.10`. The model estimates:

```text
log(units) = intercept + elasticity × log(price) + product FE + region FE + week-of-year FE + error
```

Product models omit product fixed effects. Published uncertainty uses a CR1 covariance matrix clustered by intervention week to allow shared weekly shocks; HC1 is retained as a diagnostic. The output also records cluster count, residual degrees of freedom, and the design-matrix condition number. The coefficient is interpreted causally only inside the randomized design and tested price range.

Pricing recommendations evaluate price indices `0.95`, `1.00`, and `1.05` using the estimated product coefficient, observed control units, and observed variable cost per unit. The selected candidate maximizes predicted weekly contribution and cannot leave the randomized `0.90–1.10` support.

## Multi-touch attribution

Pre-signup journeys receive position-based weights:

- one touch: 100%;
- two touches: 50% first / 50% last;
- three or more: 40% first / 40% last / 20% equally across middle touches.

Customer contribution is allocated using those weights. Customer-equivalent credit sums to the customer population and attributed contribution reconciles to observed customer contribution. This is a descriptive allocation model. It does not estimate what would have happened without a channel and is never substituted for randomized lift.

Governed outputs are `marketing_incrementality.csv`, `multi_touch_attribution.csv`, `pricing_elasticity.csv`, and `pricing_recommendations.csv` under `outputs/tables/`.
