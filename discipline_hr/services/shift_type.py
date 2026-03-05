import frappe
from frappe.utils import add_days, add_months, add_years, cint, getdate

from discipline_hr.services.utils import logger


@frappe.whitelist()
def calculate_end_date(interval, n_interval, start_date):
    logger.debug(
        "Accepted | Interval :%s | n_interval :%s | start_date :%s", interval, n_interval, start_date
    )
    if not interval:
        return ""

    n_interval = cint(n_interval)
    start_date = getdate(start_date)

    if interval == "Week":
        end_date = add_days(start_date, n_interval * 7)
    elif interval == "Month":
        end_date = add_months(start_date, n_interval)
    elif interval == "Year":
        end_date = add_years(start_date, n_interval)
    else:
        frappe.throw(frappe._("Invalid interval: {0}").format(interval))

    logger.debug("Returned | :%s", end_date)
    return getdate(end_date)
