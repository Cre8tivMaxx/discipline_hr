// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.query_reports["Discipline Penalty Register"] = {
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
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
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
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Link",
            options: "Shift Type",
        },
        {
            fieldname: "salary_component",
            label: __("Salary Component"),
            fieldtype: "Link",
            options: "Salary Component",
        },
        {
            fieldname: "penalty_status",
            label: __("Type"),
            fieldtype: "Select",
            options: ["", "Present", "Absent"].join("\n"),
        },
        {
            fieldname: "attendance_penalty_policy",
            label: __("Attendance Policy"),
            fieldtype: "Link",
            options: "Attendance Penalty Policy",
        },
        {
            fieldname: "docstatus",
            label: __("Docstatus"),
            fieldtype: "Select",
            options: [
                { value: "", label: __("All") },
                { value: "0", label: __("Draft") },
                { value: "1", label: __("Submitted") },
                { value: "2", label: __("Cancelled") },
            ],
        },
        {
            fieldname: "has_error",
            label: __("Has Error Only"),
            fieldtype: "Check",
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
