// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Grace Ledger"] = {
    hide_new_doc: 1,
    onload(listview) {
        listview.page.remove_action_item(__("Delete"));
    },
};
