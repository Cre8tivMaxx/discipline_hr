// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.listview_settings["Attendance Permissions"] = {
    get_indicator(doc) {
        const colors = {
            "Auto Processed": "green",
            Processed: "green",
            Pending: "orange",
            Rejected: "red",
        };
        return [__(doc.status), colors[doc.status] || "grey", `status,=,${doc.status}`];
    },
};

frappe.ui.form.on("Attendance Permissions", {
    refresh(frm) {
        if (frm.doc.error_log) {
            frm.add_custom_button(__("Retry"), () => {
                frm.call("retry").then(() => {
                    frm.reload_doc();
                });
            });
        }
        if (frm.doc.employee && frm.doc.shift_type) {
            frm.add_custom_button(__("View Ledger"), () => {
                frappe.set_route("query-report", "Employee Grace Ledger", {
                    employee: frm.doc.employee,
                    shift: frm.doc.shift_type,
                    voucher_no: frm.doc.name,
                });
            });
        }
    },
});
