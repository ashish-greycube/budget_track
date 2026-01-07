# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr


def execute(filters=None):
	columns, data = [], []

	columns = get_columns(filters)
	data = get_data(filters)

	return columns, data

def get_columns(filters):
	columns = [
		{
			"fieldname": "budget_description",
			"label":_("Budget Description"),
			"fieldtype": "Data",
			"width": 400
		},
		{
			"fieldname": "total_budget",
			"label":_("Total Budget"),
			"fieldtype": "Currency",
			"width": 200
		}
	]

	project_budget = filters.get("project_budget")
	
	year_wise_project_budget_allocation_list = frappe.db.get_all("Fiscal Year Wise Project Budget Allocation",
															  filters={"project_budget":project_budget},
															  fields=["name","fiscal_year"], order_by="fiscal_year Asc")
	if len(year_wise_project_budget_allocation_list)>0:
		
		for allocation in year_wise_project_budget_allocation_list:
			first_year = getdate(frappe.db.get_value("Fiscal Year",allocation.fiscal_year,"year_start_date")).year
			second_year = getdate(frappe.db.get_value("Fiscal Year",allocation.fiscal_year,"year_end_date")).year
			if first_year != second_year:
				field_name = "{0}_{1}".format(first_year,second_year)
			else:
				field_name = "{0}".format(first_year)
			columns.append({
				"fieldname": field_name,
				"label":_("{0}").format(allocation.fiscal_year),
				"fieldtype": "Currency",
				"width": 200
			})
	
	columns.extend([
		{
			"fieldname": "total_allocated",
			"label":_("Total Allocated"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "variance_in_allocation",
			"label":_("Variance In Allocation"),
			"fieldtype": "Currency",
			"width": 200
		}
	])

	return columns

def get_data(filters):
	project_budget = filters.get("project_budget")
	report_data = []
	fiscal_year_list = []
	project_budget_details = frappe.db.sql("""
						SELECT
							tpb.name,
							tpb.capex ,
							tpb.startup_investment ,
							tpb.total_expenses ,
							tpfe.propsoed_utilization ,
							tpfe.amount,
							tpfe.description
						FROM
							`tabProject Budget` tpb
						INNER JOIN `tabParticulars for Expenses` tpfe ON
							tpb.name = tpfe.parent
						WHERE tpb.name = '{0}'
					""".format(project_budget),as_dict= True)
	if len(project_budget_details)>0:
		report_data.append({
			"budget_description" : "Investment",
			"total_budget" : project_budget_details[0].startup_investment,
		})
		report_data.append({
			"budget_description" : "Capex",
			"total_budget" : project_budget_details[0].capex,
		})
		report_data.append({
			"budget_description" : "Operational Expenses",
			"total_budget" : project_budget_details[0].total_expenses,
		})
		for row in project_budget_details:
			new_row={}
			new_row["budget_description"]=row.description
			new_row["total_budget"]=row.amount
			report_data.append(new_row)

	year_wise_project_budget_allocation_list = frappe.db.get_all("Fiscal Year Wise Project Budget Allocation",
															  filters={"project_budget":project_budget},
															  fields=["name","fiscal_year"], order_by="fiscal_year Asc")
	
	print(year_wise_project_budget_allocation_list,"---")
	if len(year_wise_project_budget_allocation_list)>0:
		for allocation in year_wise_project_budget_allocation_list:
			fiscal_year_wise_allocation_data = frappe.db.sql("""
						SELECT
							tfywpba.name,
							tfywpba.startup_investment ,
							tfywpba.capex,
							tfywpba.total_expenses,
							tpfe.amount,
							tpfe.propsoed_utilization,
							tpfe.description,
							tfywpba.fiscal_year
						FROM
							`tabFiscal Year Wise Project Budget Allocation` tfywpba
						INNER JOIN `tabParticulars for Expenses` tpfe 
						ON
							tfywpba.name = tpfe.parent
						WHERE
							tfywpba.project_budget = '{0}' and tfywpba.fiscal_year = '{1}'
			
		""".format(project_budget,allocation.fiscal_year),as_dict=1)
			if len(fiscal_year_wise_allocation_data)>0:
				for row in fiscal_year_wise_allocation_data:
					fiscal_year_field_name = cstr(row.fiscal_year).replace("-","_")
					for report_row in report_data:
						if report_row.get("budget_description") == "Investment":
							print(fiscal_year_field_name,"=======================fiscal_year_field_name")
							report_row[fiscal_year_field_name] = row.startup_investment
						elif report_row.get("budget_description") == "Capex":
							report_row[fiscal_year_field_name] = row.capex
						elif report_row.get("budget_description") == "Operational Expenses":
							report_row[fiscal_year_field_name] = row.total_expenses
						elif report_row.get("budget_description") == row.description:
							report_row[fiscal_year_field_name] = row.amount
						
						if fiscal_year_field_name not in fiscal_year_list:
							fiscal_year_list.append(fiscal_year_field_name)

		for ele in report_data:
			total_allocated = 0
			for year in fiscal_year_list:
				total_allocated = total_allocated + ele.get(year)
			ele["total_allocated"] = total_allocated
			ele["variance_in_allocation"] = ele.get("total_budget") - total_allocated
	return report_data