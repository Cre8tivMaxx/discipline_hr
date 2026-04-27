# Discipline HR

Smart time tracking, grace minutes, and salary penalties for ERPNext HR.

Frappe HRMS already tracks attendance, leaves, and late entries. **Discipline HR** adds three things on top: a pool of grace minutes per employee, a clear record of how many minutes are left, and an automatic salary penalty when an employee goes over the limit or is absent without permission.

---

## Quickstart

Get a working penalty in under 10 minutes.

### 1. Install

Run from your bench folder:

Discipline HR needs Frappe HRMS. Install it first if it is not already on your bench:

```bash
cd ~/frappe-bench
bench get-app hrms
bench --site $SITE_NAME install-app hrms
```

Then install Discipline HR:

```bash
bench get-app https://github.com/Cre8tivMaxx/discipline_hr --branch develop
bench --site $SITE_NAME install-app discipline_hr
bench --site $SITE_NAME migrate
```

### 2. Set a default policy

Open **Discipline HR Settings** and pick:

- A default **Attendance Penalty Policy** (for late entry and early exit).
- A **Salary Component** to use for the deduction.

![Discipline HR Settings](imgs/discipline_hr_settings.png)

### 3. Give one shift a grace pool

Open any **Shift Type** and set:

- **Total Allowed Grace Minutes** — for example, `120` (2 hours per period).
- **Grace Reset Interval** — `Monthly`.
- **Period Start Date** and **Period End Date** — the first month.

![Shift Type grace settings](imgs/shift_type_grace_settings.png)

### 4. Submit a late Attendance

Submit an Attendance for an employee on this shift, with a late entry larger than 120 minutes.

You will see:

- An **Attendance Permission** is created.
- An **Employee Grace Ledger** entry shows the minutes used.
- A **Discipline Penalty** is created with the deduction amount.

That's it, keep exploring different policies.

---

## How it works

When an employee submits an Attendance, the app:

1. Reads the shift's grace pool and the minutes already used in this period.
2. Saves the late and early minutes on the Attendance.
3. Creates an **Attendance Permission**. If auto-process is on, it goes straight through. If not, HR must approve it.
4. Adds a row to the **Employee Grace Ledger** to track minutes used.
5. Creates a **Discipline Penalty** with the amount to deduct from salary.

![How permitted graces work](imgs/permitted_graces.png)

If any step fails, the Attendance, Permission, or Penalty shows the reason in its **Error Log** field, and a **Retry** button appears on the document so HR can run that step again. While an Attendance has an unresolved error or a pending Permission or Penalty in the payroll period, the app blocks the Salary Slip from submitting — so a broken step never silently turns into a wrong paycheck.

---

## Configuration reference

### Shift Type fields

![Shift Type custom fields](imgs/shift_type_custom_fields.png)

| Field                       | Description                                                                                                       |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Period Start / End Date     | The date range when penalties apply. The app rolls these forward when the period ends.                            |
| Total Allowed Grace Minutes | The grace pool shared across the whole period.                                                                    |
| Minimum Grace Minutes       | The smallest minutes saved per permission. If an employee is 20 minutes late but the minimum is 60, they get 60.  |
| Grace Reset Interval        | How often the pool resets: Weekly, Monthly, or Yearly.                                                            |
| Reset After (Intervals)     | How many intervals before reset. For example, reset every 2 months.                                               |
| Enable Permissions          | If on, HR must approve the permission before a penalty is created.                                                |
| Attendance Penalty Policy   | Replaces the default attendance policy for this shift.                                                            |
| Absence Penalty Policy      | Replaces the default absence policy for this shift.                                                               |
| Salary Component            | Replaces the default salary component for this shift.                                                             |

### Attendance fields (filled by the app)

![Attendance calculated fields](imgs/attendance_calculated_fields.png)

| Field              | Description                                                                  |
| ------------------ | ---------------------------------------------------------------------------- |
| Late Entry Minutes | The actual minutes late.                                                     |
| Late After Grace   | Minutes left to penalize after using the grace pool.                         |
| Early Exit Minutes | The actual minutes early.                                                    |
| Early After Grace  | Minutes left to penalize after using the grace pool.                         |
| Penalty Minutes    | Total minutes to penalize (Late After Grace + Early After Grace).            |
| Error Log          | Any errors raised during the background calculation.                         |

### Discipline HR Settings

- **Default Policies** — used when a Shift Type does not set its own.
- **Salary Component** — the component for the Additional Salary deduction.
- **Salary Basis** — use `Base` salary or `Total` salary for the daily rate.
- **Month Days** — days in a month for the daily rate (default `30`).
- **Automation** — turn auto-process on or off for Permissions, Penalties, and Additional Salary.
- **Split Permissions & Penalties** — if on, extra minutes past an existing permission are penalized on their own.

---

## Penalty policies

### Attendance Penalty Policy (late and early)

Pick one:

1. **Factor** — `penalty_minutes × factor × (daily_rate ÷ shift_hours ÷ 60)`
2. **Fixed Per Hour** — a flat rate per hour of penalty.
3. **Penalty Matrix** — a growing percent of daily rate per violation in the period (day 1 a warning, day 2 a `25%` deduction, and so on).

![Penalty Matrix policy](imgs/penalty_matrix_policy.png)
![Factor policy](imgs/factor_policy.png)
![Fixed Per Hour policy](imgs/fixed_per_hour_policy.png)

### Absence Penalty Policy (unpermitted absence)

Pick one:

1. **Penalty Matrix** — percent of daily rate based on number of absences.
2. **Special Days** — different percent for some weekdays. For example, `200%` deduction on Sundays.
3. **Matrix & Special Days** — uses both rules together.

---

## Workflow statuses

Both **Attendance Permissions** and **Discipline Penalty** share these statuses:

| Status         | Meaning                                |
| -------------- | -------------------------------------- |
| Auto Processed | Processed without HR approval.         |
| Pending        | Waiting for HR or manager action.      |
| Accepted       | Approved — the penalty is created.     |
| Rejected       | Waived — no penalty is created.        |

---

## Reports

The app ships four script reports under the **Discipline HR** workspace:

| Report                          | Purpose                                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Employee Grace Ledger Report    | Drill-down of every grace-pool movement for one employee in a shift period — investigate how the pool was consumed.    |
| Monthly Penalty Summary         | Payroll roll-up: one row per (employee, period, salary component) with total minutes and amount. Run before payroll.   |
| Discipline Penalty Register     | Line-level audit log of every penalty (Draft, Submitted, Cancelled), filterable by department, policy, error state.    |
| Attendance Permissions Pipeline | Operational triage view — Pending vs Auto Processed, oldest-first, with error and stuck-item flags.                    |

---

## Scheduled jobs and guards

- **Daily Grace Rollover** — a daily scheduled job moves the **Period Start** and **Period End** dates on Shift Types when the current period ends.
- **Salary Slip Guard** — the app blocks Salary Slip submission if the employee has Attendances with errors or penalties that are still pending in the payroll period.

---

## Contributing

This app uses `pre-commit` for formatting and linting. [Install pre-commit](https://pre-commit.com/#installation), then enable it for this repo:

```bash
cd apps/discipline_hr
pre-commit install
```

Run all checks at any time with:

```bash
pre-commit run --all-files
```
