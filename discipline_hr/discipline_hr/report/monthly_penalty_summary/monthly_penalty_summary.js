// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Penalty Summary"] = {
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
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Link",
            options: "Shift Type",
            on_change() {
                const shift = frappe.query_report.get_filter_value("shift");
                if (!shift) return;
                frappe.db
                    .get_value("Shift Type", shift, [
                        "custom_period_start_date",
                        "custom_period_end_date",
                    ])
                    .then((r) => {
                        const v = r.message || {};
                        if (v.custom_period_start_date) {
                            frappe.query_report.set_filter_value(
                                "period_start",
                                v.custom_period_start_date
                            );
                        }
                        if (v.custom_period_end_date) {
                            frappe.query_report.set_filter_value(
                                "period_end",
                                v.custom_period_end_date
                            );
                        }
                    });
            },
        },
        {
            fieldname: "period_start",
            label: __("Period Start"),
            fieldtype: "Date",
            reqd: 1,
        },
        {
            fieldname: "period_end",
            label: __("Period End"),
            fieldtype: "Date",
            reqd: 1,
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "salary_component",
            label: __("Salary Component"),
            fieldtype: "Link",
            options: "Salary Component",
        },
        {
            fieldname: "docstatus",
            label: __("Docstatus"),
            fieldtype: "Select",
            options: [
                { value: "", label: __("Draft + Submitted (default)") },
                { value: "0", label: __("Draft only") },
                { value: "1", label: __("Submitted only") },
                { value: "2", label: __("Cancelled only") },
            ],
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
