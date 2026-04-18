# QR Entry Flow (Customer)

Date: 2026-04-18

## Goal

Allow customer to scan one QR code and land directly on first customer page (upload screen).

## Implemented Entry URL

1. `http://<kiosk-host>:8000/customer-start`
2. `http://<kiosk-host>:8000/customer` (short alias)

Both URLs redirect to:

`/customer-app/?entry=qr`

## How To Use

1. Open admin app:
   - `http://<kiosk-host>:8000/admin-app`
2. Go to **Kiosk Controls** -> **Per-Device QR Pack**.
3. Set/confirm the kiosk `device_code`.
4. Copy the `Customer Entry URL` and `Wi-Fi QR Payload` (if hotspot enabled).
4. Generate/print QR from that URL and place it near kiosk.
5. Customer scans QR and lands directly on customer upload screen.

## Notes

1. QR payload is local kiosk URL; customer does not need internet if device is on same local network.
2. If hotspot mode is enabled, QR entry host should be hotspot gateway (for example `10.55.0.1`) so customers are forced to join kiosk hotspot first.
3. Admin QR preview currently uses online QR rendering service for convenience.
4. For strict offline printing of QR image, generate once and print/store physically at kiosk.
