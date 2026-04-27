// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.query_reports["Attendance Permissions Pipeline"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: ["", "Auto Processed", "Processed", "Pending", "Rejected"].join("\n"),
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Link",
            options: "Shift Type",
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "auto_created",
            label: __("Auto Created Only"),
            fieldtype: "Check",
        },
        {
            fieldname: "has_error",
            label: __("Has Error Only"),
            fieldtype: "Check",
        },
        {
            fieldname: "stuck_days",
            label: __("Stuck Pending ≥ N days"),
            fieldtype: "Int",
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
