# Frontend Kickoff Checklist

Date: 2026-04-18

Frontend can start now. Backend contracts needed for customer and admin surfaces are available.

## 1) Customer flow endpoints

1. Upload PDF:
   - `POST /api/v1/print-jobs/upload`
2. Create quote:
   - `POST /api/v1/print-jobs`
   - Supports `upload_id` from upload response.
3. Create payment:
   - `POST /api/v1/payments/create`
4. Retry-safe payment action for delayed incidents:
   - `POST /api/v1/payments/retry-safe?reconcile_limit=25`
5. Poll customer status:
   - `GET /api/v1/print-jobs/{job_id}/customer-status`
6. Fetch customer receipt:
   - `GET /api/v1/print-jobs/{job_id}/customer-receipt`

## 2) Admin flow endpoints

1. Device list:
   - `GET /api/v1/admin/devices`
2. Payments:
   - `GET /api/v1/admin/payments`
3. Pending incidents:
   - `GET /api/v1/admin/payments/pending-incidents`
4. Dashboard snapshot:
   - `GET /api/v1/admin/dashboard/snapshot`
5. Daily report:
   - `GET /api/v1/admin/reports/today`
6. Alerts:
   - `GET /api/v1/alerts`

## 3) Frontend build order (recommended)

1. Customer upload + quote + pay page.
2. Customer status/receipt page.
3. Admin dashboard from snapshot endpoint.
4. Admin payments + pending incidents tables with retry-safe action button.

## 4) Contracts to pin in frontend

1. Customer status contract:
   - `docs/customer-api-contract-v1.md`
2. Admin smoke command pack:
   - `backend/scripts/check-admin-customer-api-pack.ps1`

## 5) Ready-to-use local smoke command

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\scripts\check-admin-customer-api-pack.ps1 `
  -ApiBaseUrl "http://hph-pi01.local:8000/api/v1" `
  -Limit 5
```
