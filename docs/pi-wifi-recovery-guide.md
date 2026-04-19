# Hasnet PrintHub - Raspberry Pi Wi-Fi Recovery Guide (Non-Technical)

Date: 2026-04-19

## Goal

Connect your Raspberry Pi to a new Wi-Fi network when:
- the old Wi-Fi is no longer available
- you do not have Ethernet cable

This guide gives you 3 methods. Start with Method 1 because it is usually the fastest.

---

## Your Actual HPH Connection Details (Use These)

From your current PrintHub setup:
- Pi host name: `hph-pi01.local`
- Pi user: `hasnet_pi`
- Main SSH command (PowerShell):

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@hph-pi01.local
```

Password to enter:
- Use the Linux password for user `hasnet_pi` on that Pi.
- The repo does not store your real SSH password in plain text.

If you forgot this password:
1. Use Method 2 (HDMI + keyboard).
2. Log in locally on Pi.
3. Run:

```bash
passwd hasnet_pi
```

4. Set a new password and use it for SSH.

---

## Before You Start (Quick Checklist)

Prepare these items:
- Raspberry Pi power adapter
- Phone (for hotspot method)
- New Wi-Fi name and password
- Optional but useful: HDMI monitor + keyboard

Important:
- Wi-Fi names and passwords are case-sensitive
- Keep the Pi close to the Wi-Fi router for first connection
- Wait 1 to 3 minutes after boot before testing connection

---

## Method 1 (Fastest): Phone Hotspot With Same Name As Old Wi-Fi

Use this when you remember the old Wi-Fi name and password.

### Step 1: Create a phone hotspot that matches old Wi-Fi exactly

On your phone hotspot settings:
1. Set hotspot name (SSID) to the old Wi-Fi name exactly.
2. Set hotspot password to the old Wi-Fi password exactly.
3. Turn hotspot ON.

Example:
- old Wi-Fi name was `HomeNet123`
- old password was `MyPass2024`
- your hotspot must use the exact same values

### Step 2: Boot the Raspberry Pi

1. Power on the Pi.
2. Wait 1 to 3 minutes.
3. The Pi should auto-connect to your phone hotspot because it recognizes the same saved network.

### Step 3: Connect to Pi over SSH from your computer

Open PowerShell on your computer and run:

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@hph-pi01.local
```

When prompted:
- Username is already in command (`hasnet_pi`)
- Enter password for `hasnet_pi`

If `hph-pi01.local` does not work, find the Pi IP from phone hotspot connected devices list, then use:

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@<PI_IP_ADDRESS>
```

### Step 4: Switch Pi to the new real Wi-Fi

After SSH login:

```bash
sudo raspi-config
```

In the menu:
1. Select `System Options`
2. Select `Wireless LAN`
3. Enter new Wi-Fi SSID (name)
4. Enter new Wi-Fi password
5. Finish and exit

### Step 5: Reboot and test

Run:

```bash
sudo reboot
```

Then:
1. Turn OFF phone hotspot.
2. Wait for Pi to restart.
3. Test SSH again on new network:

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@hph-pi01.local
```

If it connects, you are done.

---

## Method 2: One-Time HDMI + Keyboard Setup

Use this when you do not remember old Wi-Fi credentials.

### Step 1: Connect peripherals

1. Connect Pi to monitor using HDMI.
2. Connect USB keyboard.
3. Power on Pi.

### Step 2: Open Wi-Fi setup menu

On Pi terminal:

```bash
sudo raspi-config
```

Then:
1. Go to `System Options`
2. Open `Wireless LAN`
3. Enter new Wi-Fi name
4. Enter new Wi-Fi password
5. Save and exit

### Step 3: Reboot

```bash
sudo reboot
```

### Step 4: Confirm from your computer

After reboot, try:

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@hph-pi01.local
```

If SSH connects, setup is successful.

---

## Method 3: Fully Headless (No Display) Using Raspberry Pi Imager

Use this when:
- you cannot access old Wi-Fi
- you do not have display/keyboard
- you can access the SD card

### Step 1: Prepare SD card in Raspberry Pi Imager

1. Insert SD card into your computer.
2. Open Raspberry Pi Imager.
3. Choose Raspberry Pi OS.
4. Click the advanced settings icon (gear).

### Step 2: Enter basic settings

In advanced settings:
1. Set hostname (example: `hph-pi01`).
2. Enable SSH.
3. Set username and password.
4. Configure Wi-Fi:
   - Wi-Fi SSID = new network name
   - Wi-Fi password = new network password
   - Wi-Fi country = your country code
5. Save settings.

### Step 3: Write image and boot

1. Write image to SD card.
2. Insert SD card into Pi.
3. Power on Pi.
4. Wait 2 to 5 minutes for first boot.

### Step 4: Test SSH

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@hph-pi01.local
```

If mDNS is blocked in your network, use Pi IP instead:

```powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' hasnet_pi@<PI_IP_ADDRESS>
```

If that fails, check router client list and SSH to Pi IP.

---

## Troubleshooting (Simple)

If Pi does not connect:
1. Re-check Wi-Fi name and password spelling.
2. Move Pi closer to router.
3. Reboot Pi and router.
4. Ensure router is 2.4 GHz compatible (many Pi setups use 2.4 GHz reliably).
5. Try Method 2 if Method 1 fails.
6. Try Method 3 if both fail.

If SSH says host not found:
1. Try Pi IP instead of `.local` name.
2. Confirm Pi and your computer are on the same network.

---

## Quick Decision Guide

Use this path:
1. Know old Wi-Fi details? Use Method 1.
2. Do not know old Wi-Fi details but have monitor/keyboard? Use Method 2.
3. No monitor/keyboard and no old Wi-Fi details? Use Method 3.

---

## Completion Check

You are done when all are true:
- Pi appears in your router connected devices
- SSH works from your computer
- Pi stays online after reboot
