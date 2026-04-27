// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Grace Ledger"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Link",
            options: "Shift Type",
            on_change() {
                const shift = frappe.query_report.get_filter_value("shift");
                if (!shift) {
                    frappe.query_report.set_filter_value("period_start", null);
                    frappe.query_report.set_filter_value("period_end", null);
                    return;
                }
                frappe.db
                    .get_value("Shift Type", shift, [
                        "custom_period_start_date",
                        "custom_period_end_date",
                    ])
                    .then((r) => {
                        const v = r.message || {};
                        frappe.query_report.set_filter_value(
                            "period_start",
                            v.custom_period_start_date || null
                        );
                        frappe.query_report.set_filter_value(
                            "period_end",
                            v.custom_period_end_date || null
                        );
                    });
            },
        },
        {
            fieldname: "period_start",
            label: __("Period Start"),
            fieldtype: "Date",
        },
        {
            fieldname: "period_end",
            label: __("Period End"),
            fieldtype: "Date",
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: ["", "Auto Processed", "Processed", "Pending", "Rejected"].join("\n"),
        },
        {
            fieldname: "voucher_no",
            label: __("Attendance Permission"),
            fieldtype: "Link",
            options: "Attendance Permissions",
        },
        {
            fieldname: "attendance",
            label: __("Attendance"),
            fieldtype: "Link",
            options: "Attendance",
        },
        {
            fieldname: "discipline_penalty",
            label: __("Discipline Penalty"),
            fieldtype: "Link",
            options: "Discipline Penalty",
        },
    ],

    formatter(value, row, column, data, default_formatter) {
        let formatted = default_formatter(value, row, column, data);
        if (!data) return formatted;

        const styleKey = `_style_${column.fieldname}`;
        if (data[styleKey]) {
            formatted = `<span style="${data[styleKey]}">${formatted}</span>`;
        }
        if (data._bold) {
            formatted = `<strong>${formatted}</strong>`;
        }
        return formatted;
    },
};
