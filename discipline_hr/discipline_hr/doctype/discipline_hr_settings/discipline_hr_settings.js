// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Discipline HR Settings", {
	refresh(frm) {
		render_status_indicators(frm);
	},
	attendance_penalty_policy: render_status_indicators,
	absence_penalty_policy: render_status_indicators,
	salary_component: render_status_indicators,
	auto_approve_pre_authorization: render_status_indicators,
});

function render_status_indicators(frm) {
	frm.dashboard.clear_headline();

	const missing = [];
	if (!frm.doc.attendance_penalty_policy) missing.push(__("Attendance Penalty Policy"));
	if (!frm.doc.absence_penalty_policy) missing.push(__("Absence Penalty Policy"));
	if (!frm.doc.salary_component) missing.push(__("Salary Component"));

	if (missing.length) {
		frm.dashboard.set_headline_alert(
			__("Set defaults before submitting Attendance: {0}", [missing.join(", ")]),
			"orange"
		);
		return;
	}

	if (frm.doc.auto_approve_pre_authorization) {
		frm.dashboard.set_headline_alert(
			__("Auto-Approve is on — every new Pre-Authorization skips HR review."),
			"yellow"
		);
	}
}