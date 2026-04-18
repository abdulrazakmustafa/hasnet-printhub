# Payment Provider Cost Conclusion (2026-04-18)

## Inputs Used
- Mixx fee card from `docs/C2B Charges.xlsx` (C2B - Standard Charges column).
- Operational behavior already observed in PrintHub tests: Snippe minimum transaction is 500 TZS (100 TZS not accepted).

## Mixx Cost Snapshot (from current fee card)
- 100 TZS -> 50 TZS fee (50.0%)
- 500 TZS -> 80 TZS fee (16.0%)
- 1,000 TZS -> 120 TZS fee (12.0%)
- 1,500 TZS -> 120 TZS fee (8.0%)
- 2,000 TZS -> 210 TZS fee (10.5%)
- 5,000 TZS -> 450 TZS fee (9.0%)
- 10,000 TZS -> 600 TZS fee (6.0%)

## Conclusion
- If you must support low-value transactions below 500 TZS (for example 100 TZS), Mixx is required because Snippe minimum blocks those transactions.
- For the current kiosk test pricing (500 TZS per page), Mixx works, but fees are still meaningful at low amounts.
- We do not yet have a confirmed Snippe official fee card in the repo to do a strict fee-for-fee comparison by band.

## Recommended Decision Now
- Use Mixx when low-amount acceptance (below 500 TZS) is a hard requirement.
- Keep the provider switch feature in place (`PAYMENT_PROVIDER`) so you can move between Snippe and Mixx quickly.
- Before final production lock-in, request Snippe's official transaction fee bands and compare directly against this Mixx sheet.
