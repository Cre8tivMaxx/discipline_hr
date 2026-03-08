import frappe

logger = frappe.logger("discipline_hr", allow_site=True)

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
