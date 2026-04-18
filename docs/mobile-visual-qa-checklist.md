# Customer App Mobile Visual QA Checklist

Date: 2026-04-18

Use this checklist to capture consistent screenshots for pixel-perfect UI polishing.

## 1) QA Mode URL

Open:

`http://hph-pi01.local:8000/customer-app/?qa=1`

QA mode shows a small badge at bottom-right with viewport size and current step.

## 2) Target Phone Screens

Capture on at least these 3 screen families:

1. Small phone (example 360 x 800)
2. Medium phone (example 390 x 844)
3. Large phone (example 412 x 915)

## 3) Screenshots Needed Per Phone

Take screenshots for:

1. Step 1 (Upload screen, no file selected)
2. Step 2 (Print options with page selection and copies)
3. Step 3 (Summary with totals visible)
4. Step 4 (Payment form with keyboard closed)
5. Step 5 (Final status/success screen)

## 4) Capture Rules

1. Keep portrait orientation.
2. Do not crop; include full screen.
3. Keep browser zoom at default 100%.
4. Use same brightness/theme mode while capturing all screens on one device.

## 5) File Naming Format

Use:

`<phone>-step-<n>.png`

Examples:

1. `small-360x800-step-1.png`
2. `small-360x800-step-2.png`
3. `medium-390x844-step-3.png`
4. `large-412x915-step-5.png`

## 6) Handoff

After capture, share all images in one batch so design fixes can be applied in one pass.
