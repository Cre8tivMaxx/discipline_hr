// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Grace Ledger"] = {
    hide_new_doc: 1,
    onload(listview) {
        listview.page.remove_action_item(__("Delete"));
    },
};

frappe.ui.form.on("Employee Grace Ledger", {
    refresh(frm) {
        if (frm.doc.error_log) {
            frm.add_custom_button(__("Retry"), () => {
                frm.call("retry").then(() => {
                    frm.reload_doc();
                });
            });
        }
        if (frm.doc.discipline_penalty) {
            frm.add_custom_button(__("View Penalty"), () => {
                frappe.set_route("Form", "Discipline Penalty", frm.doc.discipline_penalty);
            });
        }
    },
});
