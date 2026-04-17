# Customer API Contract v1 (Frozen For Frontend)

Date frozen: 2026-04-17

This document freezes the customer payload contract for frontend integration.

## Endpoints

1. `GET /api/v1/print-jobs/{job_id}/customer-status`
2. `GET /api/v1/print-jobs/{job_id}/customer-receipt`

## Contract Version Fields

1. `customer-status` always returns: `contract_version = "customer-status-v1"`
2. `customer-receipt` always returns: `contract_version = "customer-receipt-v1"`

## Stable Core Fields (Both Endpoints)

1. `job_id`
2. `stage`
3. `message`
4. `next_action`
5. `job_status`
6. `payment_status`
7. `total_cost`
8. `currency`
9. `pages`
10. `copies`
11. `color`
12. `timeline[]` (ordered events)
13. `receipt` (nullable when no payment record exists yet)

## Stable Stage Values (Customer Status/Receipt)

1. `awaiting_payment`
2. `payment_pending`
3. `provider_delay_escalated` (pending beyond escalation window; operator reconciliation expected)
4. `payment_confirmed`
5. `processing`
6. `completed`
7. `payment_failed`

## Timeline Event Shape

Each item in `timeline`:

1. `code` (`job_created`, `payment_requested`, `payment_confirmed`, `print_dispatched`, `print_completed`)
2. `label`
3. `state` (`pending`, `current`, `done`, `blocked`)
4. `at` (nullable timestamp)
5. `detail` (nullable text)

## Receipt Object Shape

When present:

1. `payment_id`
2. `provider`
3. `provider_request_id`
4. `provider_transaction_ref`
5. `payment_status`
6. `amount`
7. `currency`
8. `requested_at`
9. `confirmed_at`
10. `webhook_received_at`
11. `updated_at`

## Change Policy

1. No removals or renames inside v1.
2. New fields may only be additive.
3. Breaking changes require a new version key (`customer-status-v2` / `customer-receipt-v2`) and dual-support window.
