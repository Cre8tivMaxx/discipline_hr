frappe.ui.form.on("Shift Type", {
    custom_period_start_date(frm) {
        update_end_period(frm);
    },
    custom_grace_interval(frm) {
        update_end_period(frm);
    },
    custom_grace_count(frm) {
        update_end_period(frm);
    },
});

function update_end_period(frm) {
    const start_date = frm.doc.custom_period_start_date;
    if (!start_date) return;

    frappe
        .call({
            method: "discipline_hr.services.shift_type.calculate_end_date",
            args: {
                interval: frm.doc.custom_grace_interval,
                n_interval: frm.doc.custom_grace_count,
                start_date: start_date,
            },
        })
        .then((r) => {
            if (r.message) {
                frm.set_value("custom_period_end_date", r.message);
            }
        });
}
