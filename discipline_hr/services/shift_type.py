import frappe
from frappe.utils import add_days, add_months, add_years, cint, getdate, today

from discipline_hr.services.utils import _log


def _calculate_end_date(interval, n_interval, start_date):
    """Return the period end date given an interval, count, and start date."""
    n_interval = cint(n_interval)
    start_date = getdate(start_date)

    if interval == "Week":
        return add_days(start_date, n_interval * 7)
    elif interval == "Month":
        return add_months(start_date, n_interval)
    elif interval == "Year":
        return add_years(start_date, n_interval)
    else:
        frappe.throw(frappe._("Invalid interval: {0}").format(interval))


@frappe.whitelist()
def calculate_end_date(interval, n_interval, start_date):
    _log(
        "debug",
        "calculate_end_date_called",
        interval=interval,
        n_interval=n_interval,
        start_date=str(start_date),
    )
    if not interval:
        return ""

    end_date = _calculate_end_date(interval, n_interval, start_date)
    _log("debug", "calculate_end_date_returned", end_date=str(end_date))
    return getdate(end_date)


def rollover_grace_periods():
    """Daily task: roll over grace period on Shift Types whose period ends today."""
    shift_types = frappe.get_all(
        "Shift Type",
        filters=[["custom_period_end_date", "<=", today()]],
        fields=["name", "custom_period_end_date", "custom_grace_interval", "custom_grace_count"],
    )

    current_today = getdate(today())
    for st in shift_types:
        if not st.custom_grace_interval or not st.custom_grace_count:
            _log("warning", "rollover_skipped_missing_config", shift=st.name)
            continue

        end_date = getdate(st.custom_period_end_date)
        while end_date <= current_today:
            new_start = end_date
            end_date = _calculate_end_date(st.custom_grace_interval, st.custom_grace_count, new_start)

        frappe.db.set_value(
            "Shift Type",
            st.name,
            {"custom_period_start_date": new_start, "custom_period_end_date": end_date},
        )
        _log(
            "info",
            "grace_period_rolled_over",
            shift=st.name,
            new_start=str(new_start),
            end_date=str(end_date),
        )
