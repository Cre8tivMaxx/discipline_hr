// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.listview_settings["Attendance Pre-Authorization"] = {
    get_indicator(doc) {
        const colors = {
            Draft: "gray",
            "Pending Approval": "orange",
            Approved: "blue",
            Consumed: "green",
            Rejected: "red",
            Expired: "gray",
        };
        return [__(doc.status), colors[doc.status] || "grey", `status,=,${doc.status}`];
    },
};

frappe.ui.form.on("Attendance Pre-Authorization", {
    refresh(frm) {
        if (frm.doc.employee && frm.doc.shift_type) {
            frm.add_custom_button(__("View Ledger"), () => {
                frappe.set_route("query-report", "Employee Grace Ledger", {
                    employee: frm.doc.employee,
                    shift: frm.doc.shift_type,
                });
            });
        }
        if (frm.doc.name && !frm.is_new()) {
            frappe.db
                .get_value(
                    "Discipline Penalty",
                    { attendance_pre_authorization: frm.doc.name, docstatus: ["!=", 2] },
                    "name"
                )
                .then((r) => {
                    const penalty = (r.message || {}).name;
                    if (penalty) {
                        frm.add_custom_button(__("View Penalty"), () => {
                            frappe.set_route("Form", "Discipline Penalty", penalty);
                        });
                    }
                });
        }
    },
});
