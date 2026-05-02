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
bench run-tests --app discipline_hr --doctype "Discipline Penalty"

# Run a single test module
bench run-tests --app discipline_hr --module discipline_hr.discipline_hr.doctype.discipline_penalty.test_discipline_penalty

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

The pipeline runs synchronously inside `Attendance.before_submit`. Two branches:

**Flow A — No matching pre-authorization**

```
Attendance.before_submit
  → calculate_attendance_penalty_minutes()      [events/attendance.py]
      Computes raw late/early minutes, subtracts shift grace period
      Sets custom fields on Attendance doc:
        custom_late_entry_minutes, custom_early_exist_minutes
        custom_late_after_grace_minutes, custom_early_after_grace_minutes
        custom_penalty_minutes

  → apply_pre_authorization_and_penalty()       [services/pre_authorization.py]
      No Approved pre-auth found for (employee, date, slice)
      → _create_grace_ledger(ctx_from_attendance)
          Inserts Employee Grace Ledger:
            Reads total consumed minutes for the period
            Computes remaining_minutes_before_consume, remaining_minutes, penalty_minutes
          If penalty_minutes > 0 → _create_attendance_penalty()
              Creates Discipline Penalty using main attendance_penalty_policy
```

**Flow B — Approved pre-authorization exists**

```
Attendance.before_submit
  → calculate_attendance_penalty_minutes()
  → apply_pre_authorization_and_penalty()
      Looks up Attendance Pre-Authorization where
        employee=X, date=Y, status="Approved"
        kind ∈ {Late, Both} for late_after_grace_minutes
        kind ∈ {Early, Both} for early_after_grace_minutes
      Atomic UPDATE: Approved → Consumed (guards against amend races)
      Sets custom_attendance_pre_authorization on Attendance
      If consumed minutes >= penalty minutes → done (no ledger, no penalty)
      If surplus > 0 → _create_surplus_penalty()
          Uses config.pre_authorization_surplus_policy (NOT the main policy)
          Skips the grace ledger entirely
```

**Penalty amount calculation** (Discipline Penalty controller):
- Fixed Per Hour: `rate_per_hour / 60 × penalty_minutes`
- Factor: `deducted_minutes_factor × minute_rate × penalty_minutes`
- Penalty Matrix: escalating daily-rate % per violation number in the period

**Cancellation**: `Attendance.on_cancel → cascade_cancel_attendance` reverts
Consumed pre-auths back to Approved (so an amended re-submit can re-consume),
deletes downstream Discipline Penalty, Employee Grace Ledger, Additional Salary,
and dev seeders.

### Custom Fields on Shift Type

The app extends `Shift Type` with custom fields (prefix `custom_`):

| Field | Purpose |
|---|---|
| `custom_period_start_date` / `custom_period_end_date` | Grace period window; penalties only apply inside this range |
| `custom_total_allowed_grace_minutes` | Pool of grace minutes per employee per period |
| `custom_minimum_grace_minutes` | Floor applied to recorded penalty minutes |
| `custom_salary_component` | Override deduction salary component (under Penalties and Deductions section) |
| `custom_attendance_penalty_policy` | Overrides global policy from `Discipline HR Settings` |

### Key DocTypes

| DocType | Purpose |
|---|---|
| `Attendance Pre-Authorization` | HR-managed excuse for a known late entry / early exit on a specific date. Statuses: Draft → Pending Approval → Approved → Consumed (or Rejected / Expired). |
| `Employee Grace Ledger` | Ledger entry per attendance event; tracks allowed vs consumed minutes |
| `Discipline Penalty` | Final penalty record with computed `penalty_amount` |
| `Attendance Penalty Policy` | Defines calculation method (Factor / Fixed Per Hour / Penalty Matrix) |
| `Penalty Matrix` | Child table of Policy; defines % of daily rate per violation number |
| `Discipline HR Settings` | Global singleton: main policy, surplus policy, salary component, auto-approve / auto-process toggles |

### Services Layer (`discipline_hr/services/`)

- `grace.py` – pure helpers to extract grace minutes from a shift doc and calculate consumed grace
- `pre_authorization.py` – orchestrates pre-auth resolution, grace ledger insertion, and penalty creation
- `utils.py` – shared `logger` instance (`frappe.logger("discipline_hr")`)

### Events (`discipline_hr/events/`)

- `attendance.py` – `calculate_attendance_penalty_minutes` and `apply_pre_authorization_and_penalty` chained on `Attendance.before_submit`; `cascade_cancel_attendance` on `on_cancel`
- `pre_authorization.py` – daily `expire_stale_pre_authorizations` scheduler entry

### DocType Controllers (`discipline_hr/discipline_hr/doctype/`)

Business logic lives in the service layer; controllers are thin:
- `AttendancePreAuthorization.validate` → enforces status transitions, no-overlap, and minimum-grace floor; `before_save` auto-approves Drafts when the global flag is on
- `DisciplinePenalty.validate` → calls `get_penalty_amount()` to populate `penalty_amount`

## Skills to Load

At the start of each session, load these skills using the Skill tool:

- `erpnext-syntax-controllers` – DocType lifecycle hooks, submittable docs, autoname, override patterns
- `erpnext-syntax-hooks` – `doc_events`, `scheduler_events`, fixtures, permission hooks
- `erpnext-syntax-scheduler` – `frappe.enqueue`, queue types, job deduplication, background jobs
- `erpnext-syntax-whitelisted` – `@frappe.whitelist()`, permission patterns, error handling, client calls

### Important Conventions

- Use `frappe.get_cached_doc()` for frequently read master data (Shift Type, Attendance, etc.).
- The pre-authorization pipeline runs synchronously in `Attendance.before_submit` — no background queue.
- `ignore_if_duplicate=True` and `ignore_permissions=True` are used on auto-inserted docs.
- The `# begin: auto-generated types` / `# end: auto-generated types` block in each DocType controller is managed automatically by Frappe; do not edit it manually.
- DocType JSON files are the source of truth for schema; always run `bench migrate` after editing them.
