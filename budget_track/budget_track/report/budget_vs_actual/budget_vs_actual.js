// Copyright (c) 2025, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Budget Vs Actual"] = {
	"filters": [
		{
			"fieldname": "company",
			"label":__("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1
		},
		{
			fieldname: "project_budget",
			label: __("Project Budget"),
			fieldtype: "MultiSelectList",
			options: "Project Budget",
			"reqd": 1,
			get_data: function (txt) {
				return frappe.db.get_link_options("Project Budget", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
			on_change: function (query_report) {
				var project_budget = query_report.get_values().project_budget;
				if (!project_budget) {
					return;
				}
				console.log(project_budget,"---")
				frappe.call('budget_track.budget_track.report.budget_vs_actual.budget_vs_actual.fetch_project_start_date_from_project_budget', {
						project_budget: project_budget
					}).then(r => {
						console.log(r.message)
						if (r.message,"message") {
							frappe.query_report.set_filter_value({
								from_date: r.message
							});
						}
					})
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today()
		}
	],

	onload: create_show_consolidate_button,

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		if (data && column.fieldname.includes("spent_as_percent_against_budget")) {
			let percent_value = data[column.fieldname]
			if (percent_value > 100) {
				value = "<span style='color:red'>" + value+ "</span>"
			}
		}
		// return value;

		if (data && column.fieldname.includes("spent_as_percent_against_receipt")) {
			let percent_value = data[column.fieldname]
			if (percent_value > 100) {
				value = "<span style='color:red'>" + value+ "</span>"
			}
		}
		return value;
    }
};

function create_show_consolidate_button(report) {
    report.page.add_inner_button(
		__("Show Consolidated"),
        () => go_to_consolidated_report(report)
    );
}

function go_to_consolidated_report(report) {
	frappe.open_in_new_tab = false;
	frappe.route_options = {
		company: report.get_values().company,
		project_budget: report.get_values().project_budget,
	};                    
	frappe.set_route("query-report", "Budget Vs Actual ( Consolidated )");
	console.log("go_to_consolidated_report")
	console.log(report.get_values().company, "-------report", report.get_values().project_budget,  "-------member")
}