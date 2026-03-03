### Discipline Hr

Smart time compliance, grace tracking and automated deductions for ERPNext HR.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app discipline_hr
```

### Configuration

**Shift Type** — set these custom fields per shift:

| Field | Description |
|---|---|
| Period Start / End Date | Date range in which penalties apply |
| Total Allowed Grace Minutes | Grace minute pool shared across the whole period |
| Minimum Grace Minutes | Minimum minutes recorded per permission |
| Enable Permissions | Require HR approval before a penalty is created |
| Attendance Penalty Policy | Overrides the global policy from Discipline HR Settings |

**Discipline HR Settings** — global defaults applied to all shifts:

- **Attendance Penalty Policy** — fallback policy when the shift doesn't set one
- **Salary Component** — component used when creating an Additional Salary deduction
- **Ignore Grace Ledger Duplicates** — prevents double-counting if a permission is re-processed

---

### How It Works

1. When an Attendance record is submitted, a hook calculates late-entry and early-exit minutes against the shift's grace periods and writes them as custom fields on the Attendance doc.
2. If penalisable minutes remain after grace, an **Attendance Permissions** record is created in the background.
   - Status is **Auto Processed** when no HR approval is needed.
   - Status is **Pending** when `Enable Permissions` is on — an HR manager must accept or reject it.
3. On acceptance (or auto-processing), an **Employee Grace Ledger** entry is inserted, summing consumed grace for the period. Any overflow becomes `penalty_minutes`.
4. If `penalty_minutes > 0`, an **Attendance Penalty** record is created with a computed `penalty_amount` based on the configured penalty type.

---

### Penalty Types

| Type | Formula |
|---|---|
| Fixed Per Hour | `penalty_minutes × (rate_per_hour ÷ 60)` |
| Factor | `penalty_minutes × factor × (daily_rate ÷ shift_hours ÷ 60)` |
| Penalty Matrix | Looks up `violation_number` in a table; each row maps a violation count to a % of daily rate. The last row applies to all subsequent violations. |

---

### Workflow Statuses

**Attendance Permissions**

| Status | Meaning |
|---|---|
| Auto Processed | Processed without HR approval |
| Pending | Waiting for HR/manager action |
| Accepted | Approved — penalty proceeds |
| Rejected | Waived — no penalty created |

**Attendance Penalty**

| Status | Meaning |
|---|---|
| Pending | Awaiting HR review |
| Approved | Confirmed, ready for payroll |
| Rejected | Waived by HR |

---

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/discipline_hr
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
