# Hasnet PrintHub Investor Brief
Date: April 18, 2026
Prepared by: Hasnet ICT Solution (Project Team)

## 1. Executive Summary
Hasnet PrintHub is a smart self-service printing platform designed for kiosk environments (schools, streets, campuses, offices, and service centers), where customers can upload documents, pay on mobile money, and print automatically without operator dependency.

The platform is built with a strict business rule:
No successful payment means no printing.

This eliminates revenue leakage, improves trust in transaction records, and creates a scalable model for multi-kiosk rollout.

## 2. Problem It Solves
Traditional printing points face recurring problems:
1. Payment disputes and unpaid prints.
2. Heavy operator dependency and inconsistent service.
3. Low visibility into daily transactions and printer/device health.
4. Difficulty scaling to multiple kiosks with consistent controls.
5. Weak audit trail for customer support and operations.

## 3. Solution Overview
Hasnet PrintHub combines:
1. Customer flow:
Upload PDF -> Quote -> Pay -> Status -> Receipt.
2. Mobile money integration:
Snippe active now, Mixx ready.
3. Automated print dispatch:
Print only after payment confirmation.
4. Admin operations APIs and dashboard-ready data:
devices, payments, incidents, pricing, and daily reports.
5. Edge agent on Raspberry Pi:
local printer monitoring, queue handling, and job execution.

## 4. How It Works (Operational Flow)
1. Customer uploads PDF on kiosk UI.
2. System auto-detects page count from uploaded PDF (not user-entered).
3. Customer selects:
   - print mode (Black & White or Color),
   - copies,
   - all pages or custom page range.
4. System calculates total cost using server-side pricing logic.
5. Customer submits mobile number and name, then payment request is created.
6. Payment is reconciled and verified with provider status.
7. Only confirmed payment unlocks print dispatch to edge agent.
8. Edge agent prints and reports completion back to backend.
9. Customer sees final status and receipt details.

## 5. Core Product Value
1. Revenue protection:
strict payment gate prevents unpaid printing.
2. Operational reliability:
daily operator command pack and retry-safe payment flow.
3. Customer clarity:
status timeline and receipt endpoints for frontend UX.
4. Local resilience:
Pi-local runtime keeps kiosk usable even without full cloud dependency.
5. Auditability:
transaction references, job states, and reports available for management.

## 6. Current Technical Architecture
1. Backend:
FastAPI + PostgreSQL.
2. Edge runtime:
Raspberry Pi + systemd services + CUPS printer integration.
3. Payment:
provider integration with reconcile support for delayed confirmations.
4. Customer and admin web apps:
served locally from backend (`/customer-app`, `/admin-app`).
5. Deployment model:
local-first kiosk operation with optional cloud/public webhook access.

## 7. Local-First Strategy (Important for Scale and Cost)
The system is intentionally designed to run as much as possible on each Pi:
1. API service on Pi.
2. Database on Pi.
3. Print agent on Pi.
4. Printer queue and driver layer on Pi.
5. Customer UI hosted on Pi local network.

Cloud/external services are used only where necessary:
1. Payment provider APIs (Snippe/Mixx).
2. Mobile network infrastructure.
3. Optional public webhook ingress and remote admin access.
4. Source backup/collaboration via GitHub.

## 8. Security and Control Principles
1. Non-negotiable gate:
No successful payment => no printing.
2. Retry-safe payment creation to avoid accidental duplicate charges.
3. Provider-reference based reconciliation and incident handling.
4. Customer contract versioning (`v1`) to keep frontend stable.
5. Controlled file handling:
uploaded files are temporary, with cleanup after print success and stale file TTL cleanup.

## 9. Multi-Kiosk Readiness
The platform already includes multi-kiosk provisioning foundation:
1. Kiosk profile template per site.
2. Validate-only preflight before deployment.
3. One-command provisioning pipeline.
4. Standard smoke checks post-provision.
5. Recommended canary-then-batch rollout approach.

This makes migration to new Pi units practical and repeatable.

## 10. Milestones Achieved (As of April 18, 2026)
1. Backend admin APIs delivered and smoke-tested:
   - `/admin/devices`
   - `/admin/payments`
   - `/admin/reports/today`
   - `/admin/pricing`
   - `/alerts`
2. Customer APIs delivered and contract-frozen:
   - `/print-jobs/{job_id}/customer-status`
   - `/print-jobs/{job_id}/customer-receipt`
3. Automated backend regression suite established and passing.
4. Payment retry-safe flow and provider reference snapshot checks implemented.
5. Customer flow UI implemented with:
   - auto page detection,
   - one-mode-at-a-time selection,
   - custom page range support,
   - default hidden payment method (M-Pesa),
   - server-side anti-cheat billing enforcement.
6. Local deployment and smoke validation on Pi completed.

## 11. Business Impact Potential
1. New unattended or low-attended print revenue channels.
2. Standardized customer experience across branches.
3. Reduced fraud/leakage from manual payment handling.
4. Better reporting for finance and decision-making.
5. Faster expansion to schools, institutions, and public service points.

## 12. Expansion Path
Phase 1:
single-kiosk hardening and production discipline.

Phase 2:
multi-kiosk rollout with centralized monitoring.

Phase 3:
optional central cloud control plane and analytics for cross-site intelligence.

## 13. Investor Perspective
Hasnet PrintHub is not only a software project; it is an operational platform for distributed revenue points.
Its strength is the combination of:
1. hard payment-control policy,
2. practical field operations tooling,
3. local-first reliability,
4. scalable kiosk deployment model.

This positions it as a practical infrastructure product for modern print-service digitization in Tanzania and similar markets.

## 14. Conclusion
Hasnet PrintHub is already demonstrating real transaction and print workflow execution.
The current stage is ideal for:
1. UI polish and customer adoption optimization,
2. controlled kiosk expansion,
3. investor-backed scale-out into multiple locations.
