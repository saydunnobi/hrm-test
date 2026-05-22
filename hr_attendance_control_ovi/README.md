# HR Attendance Control — Odoo 16 Module

## Features

### 1. Force Check-out on New Check-in
If an employee already has an **open attendance** (checked-in, not yet checked-out) and tries to check-in again, the module **automatically closes the previous attendance** at the current time before recording the new one.

### 2. Auto Checkout for Previous Days
If any employee forgot to check-out on a **previous day**, the nightly cron job will close those attendances at **23:59:59 of that day** (not today's date — each day's attendance gets its own end-of-day checkout).

### 3. Daily Auto Check-out at 23:59
A **scheduled cron** runs every night at **23:59 server time**.  
It checks out everyone who is still clocked-in for the day, at `23:59:59` of that day.

### 4. Restricted Login / Check-in Time
From **Settings → Attendance**, you can:
- Enable the time restriction toggle
- Set a **From** and **To** time (24-hour float format, e.g. `23:00` – `05:00`)
- The range **supports spanning midnight** (e.g. 23:00 to 05:00 next morning)
- During this window, **Odoo login is blocked** for non-admin users
- **Check-in via kiosk or web** is also blocked
- The **Administrator account is never blocked**

---

## Installation

1. Copy the `hr_attendance_control_ovi` folder into your Odoo `addons` path.
2. Restart the Odoo server.
3. Activate **Developer Mode**.
4. Go to **Apps**, search for `HR Attendance Control Ovi`, and click **Install**.

---

## Configuration

Go to **Settings → Attendance** (scroll down to the **Attendance Control** section):

| Setting | Description |
|---|---|
| Force Checkout on New Check-in | Auto close open attendance on new check-in |
| Auto Checkout Previous Unclosed Attendances | Close forgotten check-ins from past days during nightly cron |
| Restrict Login / Check-in Time | Enable time-based login block |
| Restricted From | Start of blocked period (e.g. 23:00) |
| Restricted Until | End of blocked period (e.g. 05:00) |

---

## Technical Notes

- Tested on **Odoo 16 Community / Enterprise**
- Timezone-aware: uses the **company's timezone** for all local time calculations
- Cron stores time in **UTC** internally; local time is computed per company tz
- `ir.config_parameter` is used to persist all settings
