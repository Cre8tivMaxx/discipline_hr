import frappe


class _LazyLogger:
    """Proxy that delegates to frappe.logger() on every attribute access.

    This ensures the logger is always fetched after frappe.log_level is set,
    so configure_log_level() takes effect even though the logger was created
    before the level was configured.
    """

    def __getattr__(self, name):
        return getattr(frappe.logger("discipline_hr", allow_site=True), name)


logger = _LazyLogger()


def count_prior_violations(employee: str, start_period: str, end_period: str, penalty_status: str) -> int:
    """Count non-rejected penalties in a period for violation number calculation."""
    return frappe.db.count(
        "Discipline Penalty",
        {
            "employee": employee,
            "start_period": start_period,
            "end_period": end_period,
            "penalty_status": penalty_status,
            "status": ("!=", "Rejected"),
        },
    )


_log_level_configured = False


def configure_log_level():
    """Apply log_level from site/common config to this app's logger.

    Called via before_request hook so frappe.conf is available.
    Runs the actual configuration only once per worker process.
    """
    global _log_level_configured
    if _log_level_configured:
        return

    level = frappe.conf.get("log_level")
    if level:
        from frappe.utils.logger import set_log_level

        set_log_level(level)

    _log_level_configured = True
