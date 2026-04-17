# Hosting Boundary: Pi vs Cloud

This document defines what runs on Raspberry Pi today and what must remain cloud-hosted/external.

## 1. Hosted On Raspberry Pi (Current Kiosk Runtime)

1. Backend API service (`hasnet-printhub-api` via `systemd`)
2. PostgreSQL database for kiosk transactions
3. Edge agent service (`hasnet-printhub-agent` via `systemd`)
4. CUPS + printer drivers + local printer queue execution
5. Local payment reconciliation job execution (inside backend process)
6. Local intranet customer flow endpoint (`http://hph-pi01.local:8000/api/v1`)
7. Local job dispatch gate (`no successful payment => no printing`)

## 2. Requires Cloud/External Hosting (Even In Pi-Local Mode)

1. Payment provider infrastructure:
   - Snippe APIs
   - Mixx APIs (if activated later)
2. Mobile network operator infrastructure (USSD/push delivery path)
3. Email/support channels:
   - SMTP or provider email relay
   - Snippe support portal/email
4. Source code backup/collaboration:
   - GitHub repository remote (`origin`)

## 3. Cloud Needed Only If You Want Public Callback/Admin Access

1. Public HTTPS endpoint for payment webhooks:
   - `/api/v1/payments/webhook/snippe`
   - `/api/v1/payments/webhook/mixx`
2. Public DNS + TLS termination (`api.hasnet.co.tz`, wildcard domains)
3. Reverse proxy/WAF and public ingress security
4. Remote admin access pattern (VPN/tunnel/proxy)

Note:
- In strict Pi-local mode without public webhook ingress, status sync is still possible through reconcile polling.

## 4. Recommended Split (Now vs Later)

1. Now (prototype/field rollout):
   - Keep customer transaction runtime on Pi.
   - Keep printer and edge agent local.
   - Use outbound calls to Snippe/Mixx only.
2. Later (multi-site scale):
   - Move central backend/admin to VPS or cloud.
   - Keep one edge agent + printer stack per site on Pi.
   - Optionally centralize observability and reporting.
