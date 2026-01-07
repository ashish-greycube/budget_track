// Copyright (c) 2025, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Check Budget Allocation"] = {
	"filters": [
		{
			"fieldname": "project_budget",
			"label":__("Project Budget"),
			"fieldtype": "Link",
			"options": "Project Budget",
			"reqd": 1
		},
	],
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		if (data && data.variance_in_allocation && data.variance_in_allocation != 0 && column.fieldname == "variance_in_allocation") {
			value = "<span style='color:red'>" + value.bold() + "</span>"
		}
		return value;
    }
};
