// Copyright (c) 2025, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Budget Vs Actual ( Consolidated )"] = {
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
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		if (data && data.spent_as_percent_against_budget && data.spent_as_percent_against_budget > 100 && column.fieldname == "spent_as_percent_against_budget") {
			value = "<span style='color:red'>" + value+ "</span>"
		}
		// return value;

		if (data && data.spent_as_percent_against_receipt && data.spent_as_percent_against_receipt > 100 && column.fieldname == "spent_as_percent_against_receipt") {
			value = "<span style='color:red'>" + value+ "</span>"
		}
		return value;
    }
};
