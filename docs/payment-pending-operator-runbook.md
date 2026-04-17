# Payment Pending Operator Runbook

Use this when customer payment stays `pending` and the print is not released.

## 1. Non-Negotiable Rule

1. No successful payment means no printing.
2. Never print manually from CUPS as a workaround.
3. Never start a second payment attempt until the first reference is verified as not `completed`.

## 2. Standard Timeline

1. `T+0s`: Create payment and capture `provider_request_id` (`SN...`).
2. `T+60s`: Run one backend reconcile.
3. `T+120s`: Query provider status directly using the same `SN...` reference.
4. `T+180s`: Reconcile again.
5. `T+300s`: If still pending, treat as provider delay incident and follow escalation section.

## 3. Decision Tree

1. If provider returns `completed`:
   - Run reconcile.
   - Wait for edge-agent poll cycle.
   - Confirm job dispatch and print start.
2. If provider returns `failed` or `cancelled`:
   - Do not print.
   - Ask customer to retry payment (new transaction).
3. If provider remains `pending` after `T+300s`:
   - Do not print.
   - Escalate with evidence to support.
   - Optionally retry with a new payment only after confirming the first attempt did not complete.

## 4. Copy-Paste Commands (Windows)

### A) Reconcile pending payments

```powershell
curl.exe -X POST "http://hph-pi01.local:8000/api/v1/admin/payments/reconcile?limit=100"
```

### B) Open SSH session to Pi

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' -tt hasnet_pi@hph-pi01.local
```

### C) Query Snippe status on Pi

```bash
ENV=/home/hasnet_pi/hasnet-printhub/backend/.env
BASE=$(sed -n 's/^SNIPPE_BASE_URL=//p' "$ENV")
KEY=$(sed -n 's/^SNIPPE_API_KEY=//p' "$ENV")
REF=<SN_PROVIDER_REQUEST_ID>
curl -sS -H "Authorization: Bearer $KEY" "$BASE/v1/payments/$REF"
```

### D) Check recent API logs on Pi

```bash
sudo journalctl -u hasnet-printhub-api -n 120 --no-pager | egrep -i 'payment|snippe|confirm|dispatch|error|fail'
```

### E) Check recent edge-agent logs on Pi

```bash
sudo journalctl -u hasnet-printhub-agent -n 120 --no-pager | egrep -i 'next-job|assigned|dispatched|printed|error|fail|printer'
```

## 5. Evidence Template (Always Capture)

1. Date/time (local + UTC if possible)
2. Customer msisdn used
3. Method (`mpesa`, `tigo`, `airtel`)
4. Amount
5. Print job id
6. Provider request id (`SN...`)
7. Provider direct status response
8. Reconcile responses (`synced` count)
9. Whether print started or remained blocked

## 6. Support Escalation Trigger

Escalate when either is true:
1. `pending` is still unresolved after 5 minutes.
2. repeated failed/cancelled events on the same network window.

Escalation message must include:
1. account email (`abdulrazak.jmus@gmail.com`)
2. provider refs
3. timestamps
4. msisdn + method
5. exact symptom: create succeeds but approval/status is delayed/fails

## 7. Operator Outcome Codes

1. `OP-OK-COMPLETED`: provider completed and print dispatched.
2. `OP-BLOCK-PENDING`: still pending, print held, support escalated.
3. `OP-BLOCK-FAILED`: provider failed/cancelled, customer asked to retry.
