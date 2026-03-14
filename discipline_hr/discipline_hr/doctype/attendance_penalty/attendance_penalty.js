// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.listview_settings["Attendance Penalty"] = {
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
