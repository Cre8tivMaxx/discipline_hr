# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**Discipline HR** is a Frappe/ERPNext app that adds smart time-compliance enforcement on top of the HRMS module. It tracks late entries and early exits against configurable grace periods, applies grace ledger accounting, and auto-creates monetary penalties linked to employee salary.

This app requires `hrms` as a dependency (`required_apps = ["hrms"]` in `hooks.py`).

## Commands

All commands are run from the bench root (`/home/frappe/frappe-bench`), not from within this app directory.

### Development

```bash
# Run all tests for this app
bench run-tests --app discipline_hr

# Run tests for a specific doctype
bench run-tests --app discipline_hr --doctype "Attendance Penalty"

# Run a single test module
bench run-tests --app discipline_hr --module discipline_hr.discipline_hr.doctype.attendance_penalty.test_attendance_penalty

# Apply database migrations after changing a DocType JSON
bench migrate

# Build assets
bench build --app discipline_hr

# Watch for JS/CSS changes during development
bench watch
```

### Linting & Formatting

Pre-commit hooks handle all linting. Install once per checkout:

```bash
cd apps/discipline_hr
pre-commit install
```

Run manually:

```bash
pre-commit run --all-files
```

Tools configured: `ruff` (linting + import sorting + formatting), `eslint`, `prettier`, `pyupgrade`.

Ruff line length is 110; `ruff-format` uses double quotes and spaces.

## Architecture

### Data Flow (Happy Path)

```
Attendance (before_submit)
  → calculate_attendance_penalty_minutes()   [events/attendance.py]
      Computes raw late/early minutes, subtracts shift grace period
      Sets custom fields on Attendance doc:
        custom_late_entry_minutes, custom_early_exist_minutes
        custom_late_after_grace_minutes, custom_early_after_grace_minutes
        custom_penalty_minutes
      If penalty_minutes > 0 → enqueues create_attendance_permissions()

  → Attendance Permissions (created via queue, after_insert)
      status = "Auto Processed"  (if Discipline HR Settings.auto_process_attendance_permission == 1)
      status = "Pending"         (if auto_process_attendance_permission == 0, requires HR approval)

  → process_submitted_attendance_permission()  [services/attendance_permission.py]
      Runs on after_insert of AttendancePermissions when status ∈ {Auto Processed, Accepted}
      Creates Employee Grace Ledger entry:
        Reads total consumed minutes for the period
        Computes remaining_minutes_before_consume, remaining_minutes, penalty_minutes

  → Attendance Penalty (created if penalty_minutes > 0)
      Reads Attendance Penalty Policy (from Shift Type or global config)
      Calculates penalty_amount via one of three strategies:
        - Fixed Per Hour: rate_per_hour / 60 × penalty_minutes
        - Factor: deducted_minutes_factor × minute_rate × penalty_minutes
        - Penalty Matrix: escalating daily-rate % per violation number in the period
```

### Custom Fields on Shift Type

The app extends `Shift Type` with custom fields (prefix `custom_`):

| Field | Purpose |
|---|---|
| `custom_period_start_date` / `custom_period_end_date` | Grace period window; penalties only apply inside this range |
| `custom_total_allowed_grace_minutes` | Pool of grace minutes per employee per period |
| `custom_minimum_grace_minutes` | Floor applied to `AttendancePermissions.minutes` |
| `custom_enable_permissions` | 1 = require HR approval before processing; 0 = auto-process |
| `custom_attendance_penalty_policy` | Overrides global policy from `Discipline HR Settings` |

### Key DocTypes

| DocType | Purpose |
|---|---|
| `Attendance Permissions` | Bridge between submitted Attendance and penalty processing; holds status workflow |
| `Employee Grace Ledger` | Ledger entry per attendance event; tracks allowed vs consumed minutes |
| `Attendance Penalty` | Final penalty record with computed `penalty_amount` |
| `Attendance Penalty Policy` | Defines calculation method (Factor / Fixed Per Hour / Penalty Matrix) |
| `Penalty Matrix` | Child table of Policy; defines % of daily rate per violation number |
| `Discipline HR Settings` | Global singleton: default policy, salary component, duplicate-guard toggle |

### Services Layer (`discipline_hr/services/`)

- `grace.py` – pure helpers to extract grace minutes from a shift doc and calculate consumed grace
- `attendance_permission.py` – orchestrates ledger creation and penalty creation after a permission is processed
- `utils.py` – shared `logger` instance (`frappe.logger("discipline_hr")`)

### Events (`discipline_hr/events/`)

- `attendance.py` – single hook `calculate_attendance_penalty_minutes` wired to `Attendance.before_submit`

### DocType Controllers (`discipline_hr/discipline_hr/doctype/`)

Business logic lives in the service layer; controllers are thin:
- `AttendancePermissions.after_insert` → calls `process_submitted_attendance_permission`
- `AttendancePenalty.validate` → calls `get_penalty_amount()` to populate `penalty_amount`

## Skills to Load

At the start of each session, load these skills using the Skill tool:

- `erpnext-syntax-controllers` – DocType lifecycle hooks, submittable docs, autoname, override patterns
- `erpnext-syntax-hooks` – `doc_events`, `scheduler_events`, fixtures, permission hooks
- `erpnext-syntax-scheduler` – `frappe.enqueue`, queue types, job deduplication, background jobs
- `erpnext-syntax-whitelisted` – `@frappe.whitelist()`, permission patterns, error handling, client calls

### Important Conventions

- Use `frappe.get_cached_doc()` for frequently read master data (Shift Type, Attendance, etc.).
- Background jobs are enqueued on the `"short"` queue for attendance permission creation.
- `ignore_if_duplicate=True` and `ignore_permissions=True` are used on auto-inserted docs.
- The `# begin: auto-generated types` / `# end: auto-generated types` block in each DocType controller is managed automatically by Frappe; do not edit it manually.
- DocType JSON files are the source of truth for schema; always run `bench migrate` after editing them.
