## Rook: ✗ A business rule is broken

Repo `minishop` · run `run_fixture` · status **done** · 0.00 coins · exit 1

| Rule | Result |
|---|---|
| `refund_le_paid` | ✗ broken |

### Counterexample `cx_001`: rule `refund_le_paid`

Rule: `Total refunds never exceed the amount paid`

Minimal steps:

1. `customer: buy {"amount": 100}`
2. `customer: refund {"amount": 60}`
3. `customer: refund {"amount": 50}`

Replayed `10/10` on the real app.

Observed:

~~~
{
  "paid": 100,
  "refunded": 110
}
~~~

Expected: `refunded <= paid`
