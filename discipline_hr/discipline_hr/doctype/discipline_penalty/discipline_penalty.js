frappe.listview_settings["Discipline Penalty"] = {
    get_indicator(doc) {
        const colors = {
            "Auto Processed": "green",
            Processed: "green",
            Pending: "orange",
            Rejected: "red",
        };
        return [__(doc.status), colors[doc.status] || "grey", `status,=,${doc.status}`];
    },
    formatters: {
        penalty_amount(value) {
            if (!value) return "";
            return `<strong>${format_currency(value)}</strong>`;
        },
    },
};
frappe.ui.form.on("Discipline Penalty", {
    refresh(frm) {
        if (frm.doc.error_log) {
            frm.add_custom_button(__("Retry"), () => {
                frm.call("retry").then(() => {
                    frm.reload_doc();
                });
            });
        }
        if (frm.doc.employee && frm.doc.attendance) {
            frm.add_custom_button(__("View Ledger"), () => {
                frappe.db.get_value("Attendance", frm.doc.attendance, "shift").then((r) => {
                    const shift = (r.message || {}).shift;
                    const route = {
                        employee: frm.doc.employee,
                        discipline_penalty: frm.doc.name,
                    };
                    if (shift) route.shift = shift;
                    frappe.set_route("query-report", "Employee Grace Ledger", route);
                });
            });
        }
    },
});
