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
