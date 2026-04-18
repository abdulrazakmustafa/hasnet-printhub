# Multi-Kiosk Provisioning Runbook

This runbook standardizes provisioning of additional Raspberry Pi kiosks so each kiosk is configured the same way.

## 1) What this gives you

1. One profile file per kiosk.
2. One provisioning command to install/update backend + edge-agent.
3. Validation-only mode before touching the remote Pi.
4. Reusable process for new kiosk rollout.

## 2) Files added for this flow

1. Provisioning orchestrator:
   - `scripts/provision-kiosk-from-profile.ps1`
2. Kiosk profile template:
   - `kiosk-profiles/template.kiosk-profile.json`

## 3) Create a kiosk profile

1. Copy template:
   - `Copy-Item .\kiosk-profiles\template.kiosk-profile.json .\kiosk-profiles\kiosk-001.local.json`
2. Edit the `.local.json` file:
   - Set `pi.host` and `pi.user`
   - Set `backend.postgres_password`
   - Set `agent.device_api_token`
   - Set `agent.device_code` and `agent.site_name`
3. Keep profile secrets out of git:
   - `kiosk-profiles/*.local.json` is ignored by `.gitignore`.

## 4) Validate profile (no remote changes)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\provision-kiosk-from-profile.ps1 `
  -ProfilePath .\kiosk-profiles\kiosk-001.local.json `
  -ValidateOnly
```

If you intentionally want to test with placeholders, add:

```powershell
-AllowInsecurePlaceholders
```

## 5) Provision a kiosk

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\provision-kiosk-from-profile.ps1 `
  -ProfilePath .\kiosk-profiles\kiosk-001.local.json
```

Optional flags:

1. Backend only:
   - `-SkipAgent`
2. Edge-agent only:
   - `-SkipBackend`

## 6) Post-provision smoke checks

1. Backend/admin/customer endpoints:
   - `powershell -ExecutionPolicy Bypass -File .\backend\scripts\check-admin-customer-api-pack.ps1 -ApiBaseUrl "http://<pi-host>:8000/api/v1" -Limit 5`
2. Daily operator payment flow:
   - `powershell -ExecutionPolicy Bypass -File .\backend\scripts\run-daily-operator-pack.ps1 -ProviderRequestId "<SN...>" -ApiBaseUrl "http://<pi-host>:8000/api/v1" -PiApiBaseUrl "http://127.0.0.1:8000/api/v1"`
3. Physical print verification:
   - Run one real paid print and confirm paper output.

## 7) Rollout recommendation for many kiosks

1. Build and test on one canary kiosk first.
2. Copy profile and update only kiosk-specific values (`host`, `device_code`, `site_name`, token).
3. Provision kiosks in small batches.
4. Run smoke checks after each kiosk before moving to next.
