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
							tpb.overhead_amount,
							tpb.total_expenses ,
							tpfe.propsoed_utilization ,
							tpfe.amount,
							tpfe.description
						FROM
							`tabProject Budget` tpb
						INNER JOIN `tabParticulars for Expenses` tpfe ON
							tpb.name = tpfe.parent
						WHERE tpb.name = %(project_budget)s
						GROUP BY tpfe.description
					""", {"project_budget": project_budget}, as_dict=True)
	
	company = frappe.db.get_value("Project Budget",filters.get("project_budget"),"company")
	company_doc = frappe.get_doc("Company",company)

	company_default_investments_account = company_doc.custom_default_budget_group_ledger_for_investment
	company_default_capex_account = frappe.db.get_value("Company",company_doc.name,"custom_default_budget_capex_account")

	all_investment_accounts_with_child = []
	for acc in company_default_investments_account:
		all_investment_accounts_with_child.append(acc.name)
		all_investment_accounts_with_child = all_investment_accounts_with_child + frappe.db.get_descendants("Account", acc.name)

	all_capex_accounts_with_child = []
	if company_default_capex_account:
		all_capex_accounts_with_child.append(company_default_capex_account)
		all_capex_accounts_with_child = all_capex_accounts_with_child + frappe.db.get_descendants("Account", company_default_capex_account)

	investment_particulars = []
	capex_particulars = []
	operational_particulars = []
	for row in project_budget_details:
		if row.description in all_investment_accounts_with_child:
			investment_particulars.append(row)
		elif row.description in all_capex_accounts_with_child:
			capex_particulars.append(row)
		else:
			operational_particulars.append(row)

	if len(project_budget_details)>0:
		investment_total = sum(row.amount or 0 for row in investment_particulars)
		capex_total = sum(row.amount or 0 for row in capex_particulars)
		operational_total = sum(row.amount or 0 for row in operational_particulars)

		report_data.append({
			"budget_description" : "<b>Investment</b>",
			"total_budget" : investment_total,
		})

		report_data.append({
			"budget_description" : "<b>Capex</b>",
			"total_budget" : capex_total,
		})

		report_data.append({
			"budget_description" : "<b>Overhead</b>",
			"total_budget" : project_budget_details[0].overhead_amount,
		})

		report_data.append({
			"budget_description" : "<b>Operational Expenses</b>",
			"total_budget" : operational_total,
			"indent": 0,
		})
		for row in operational_particulars:
			report_data.append({
				"budget_description": row.description,
				"total_budget": row.amount,
				"indent": 1,
			})

	year_wise_project_budget_allocation_list = frappe.db.get_all("Fiscal Year Wise Project Budget Allocation",
															  filters={"project_budget":project_budget},
															  fields=["name","fiscal_year"], order_by="fiscal_year Asc")
	
	if len(year_wise_project_budget_allocation_list)>0:
		for allocation in year_wise_project_budget_allocation_list:
			fiscal_year_wise_allocation_data = frappe.db.sql("""
						SELECT
							tfywpba.name,
							tfywpba.overhead_amount,
							tfywpba.total_expenses,
							SUM(tpfe.amount) AS amount,
							tpfe.propsoed_utilization,
							tpfe.description,
							tfywpba.fiscal_year
						FROM
							`tabFiscal Year Wise Project Budget Allocation` tfywpba
						INNER JOIN `tabParticulars for Expenses` tpfe
						ON
							tfywpba.name = tpfe.parent
						WHERE
							tfywpba.project_budget = %(project_budget)s and tfywpba.fiscal_year = %(fiscal_year)s
						GROUP BY tpfe.description

		""", {"project_budget": project_budget, "fiscal_year": allocation.fiscal_year}, as_dict=1)
			if len(fiscal_year_wise_allocation_data)>0:
				investment_year_amount = 0
				capex_year_amount = 0
				operational_year_amount = 0
				for row in fiscal_year_wise_allocation_data:
					if row.description in all_investment_accounts_with_child:
						investment_year_amount += row.amount or 0
					elif row.description in all_capex_accounts_with_child:
						capex_year_amount += row.amount or 0
					else:
						operational_year_amount += row.amount or 0

				for row in fiscal_year_wise_allocation_data:
					fiscal_year_field_name = cstr(row.fiscal_year).replace("-","_")
					for report_row in report_data:
						if report_row.get("budget_description") == "<b>Investment</b>":
							report_row[fiscal_year_field_name] = investment_year_amount
						elif report_row.get("budget_description") == "<b>Capex</b>":
							report_row[fiscal_year_field_name] = capex_year_amount
						elif report_row.get("budget_description") == "<b>Overhead</b>":
							report_row[fiscal_year_field_name] = row.overhead_amount
						elif report_row.get("budget_description") == "<b>Operational Expenses</b>":
							report_row[fiscal_year_field_name] = operational_year_amount
						elif report_row.get("budget_description") == row.description:
							report_row[fiscal_year_field_name] = row.amount

						if fiscal_year_field_name not in fiscal_year_list:
							fiscal_year_list.append(fiscal_year_field_name)

		for ele in report_data:
			total_allocated = 0
			for year in fiscal_year_list:
				if ele.get(year):
					total_allocated = total_allocated + ele.get(year)
			ele["total_allocated"] = total_allocated
			ele["variance_in_allocation"] = ele.get("total_budget") - total_allocated

		### Add total row
		total_row = {
			"budget_description": "<b>Total</b>",
			"total_budget": 0,
			"total_allocated": 0,
			"variance_in_allocation": 0
		}
		
		for year in fiscal_year_list:
			total_row[year] = 0

		for ele in report_data:
			# Skip child rows (where indent == 1) to only calculate main lines
			if ele.get("indent") != 1:
				total_row["total_budget"] += ele.get("total_budget") or 0
				total_row["total_allocated"] += ele.get("total_allocated") or 0
				total_row["variance_in_allocation"] += ele.get("variance_in_allocation") or 0
				for year in fiscal_year_list:
					total_row[year] += ele.get(year) or 0

		report_data.append(total_row)
		
	return report_data