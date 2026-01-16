# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr, today
from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_execute


def execute(filters=None):
	columns, data = [], []

	columns = get_columns(filters)
	data = get_data(filters)

	return columns, data

def get_columns(filters):
	return [
		{
			"fieldname": "description",
			"label":_("Description"),
			"fieldtype": "Data",
			"width": 400
		},
		{
			"fieldname": "project_budget",
			"label":_("Project Budget"),
			"fieldtype": "Data",
			"options":"Project Budget",
			"width": 200
		},
		{
			"fieldname": "budget",
			"label":_("Budget"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "total_receipt",
			"label":_("Total Receipt"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "actual_expense",
			"label":_("Actual Expense"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "budget_variance",
			"label":_("Budget Variance"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "receipt_variance",
			"label":_("Receipt Variance"),
			"fieldtype": "Currency",
			"width": 200
		},
		{
			"fieldname": "spent_as_percent_against_budget",
			"label":_("Spent as % against Budget"),
			"fieldtype": "Percent",
			"width": 200
		},
		{
			"fieldname": "spent_as_percent_against_receipt",
			"label":_("Spent as % against Receipt"),
			"fieldtype": "Percent",
			"width": 200
		},	
	]

def get_data(filters):
	project_budget = filters.get("project_budget")

	total_operational_expense_budget = 0
	total_operational_expense_receipt = 0
	total_operational_expense_actual = 0
	total_consumption = 0

	report_data = []
	expense_data = []
	investment_data = []
	capex_data = []
	income_data = []
	overhead_data = []
	advances_data = []

	# Fetch Data for Operational Expenses 
	expense_data.append({"description":"<b>Operational Expenses</b>"})
	if len(project_budget)>0:
		for project in project_budget:
			project_budget_details = frappe.db.sql(f"""
							SELECT
								tpb.name,
								tpb.company,
								tpb.project_start_date,
								tpb.grant_ledger_account,
								tpb.capex,
								tpb.startup_investment,
								tpb.total_expenses,
								tpb.expense_percentage,
								tpb.total_budget,
								tpfe.description,
								tpfe.amount,
								tpfe.percentage_allocation,
								tpfe.cost_center as cost_center_for_expense 
							FROM
								`tabProject Budget` tpb
							INNER JOIN `tabParticulars for Expenses` tpfe ON
								tpb.name = tpfe.parent
							WHERE tpb.name = '{project}'
						""",as_dict= True)
			if len(project_budget_details)>0:
				total_operational_expense_budget = total_operational_expense_budget + project_budget_details[0].total_expenses

				group_by = "Group by Voucher (Consolidated)"
				include_dimensions = 1
				include_default_book_entries = 1

				total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_details[0].company,project_budget_details[0].project_start_date,project_budget_details[0].grant_ledger_account,project_budget_details[0].name)
				
				expense_receipt_amount = ( total_receipt * project_budget_details[0].expense_percentage) / 100
				total_operational_expense_receipt = total_operational_expense_receipt + expense_receipt_amount
				
				for row in project_budget_details:
					report_row = {}
					report_row["description"] = row.description
					report_row["indent"] = 1
					report_row["project_budget"] = row.name
					report_row["budget"] = row.amount
					report_row["project_start_date"] = row.project_start_date

					# Calculating Total Receipt For Operational Expense Cost Center Wise

					cost_center_wise_receipt = expense_receipt_amount * (row.percentage_allocation / 100)
					report_row["total_receipt"] = cost_center_wise_receipt

					# Calculating Actual Expense For Operational Expense Cost Center Wise

					company_default_expense_account = frappe.db.get_value("Company", row.company, "custom_default_budget_expense_account")
					filters_of_expenses_for_general_ledger = frappe._dict({
						"company": row.company,
						"from_date": row.project_start_date,
						"to_date": getdate(today()),
						"account":[company_default_expense_account],
						"cost_center":[row.cost_center_for_expense],
						"group_by": group_by,
						"include_dimensions": include_dimensions,
						"include_default_book_entries": include_default_book_entries
					})

					gl_report_data_for_expenses = gl_execute(filters_of_expenses_for_general_ledger)
					if len(gl_report_data_for_expenses)>0:
						total_debit = 0
						total_credit = 0
						for expense_row in gl_report_data_for_expenses[1]:
							if expense_row.get("account") and expense_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
								if expense_row.get("voucher_type") and expense_row.get("voucher_type") != "Period Closing Voucher":
									total_debit += expense_row.get("debit")
									total_credit += expense_row.get("credit")
						total_expense = total_debit - total_credit
					else:
						total_expense = 0
					report_row["actual_expense"] = total_expense
					total_operational_expense_actual = total_operational_expense_actual + total_expense

					# Calculating Variance and Percentages 

					budget_variance = report_row["budget"] - report_row["actual_expense"]
					receipt_variance = report_row["total_receipt"] - report_row["actual_expense"]
					report_row["budget_variance"] = budget_variance
					report_row["receipt_variance"] = receipt_variance

					if report_row["budget"] > 0:
						spent_as_percent_against_budget = (report_row["actual_expense"] * 100) / report_row["budget"]
					else:
						spent_as_percent_against_budget = 0
					report_row["spent_as_percent_against_budget"] = spent_as_percent_against_budget

					if report_row["total_receipt"] > 0:
						spent_as_percent_against_receipt = (report_row["actual_expense"] * 100) / report_row["total_receipt"]
					else:
						spent_as_percent_against_receipt = 0
					report_row["spent_as_percent_against_receipt"] = spent_as_percent_against_receipt

					expense_data.append(report_row)


	for row in expense_data:
		if row.get("description") == "<b>Operational Expenses</b>":
			row["budget"] = total_operational_expense_budget
			row["total_receipt"] = total_operational_expense_receipt
			row["actual_expense"] = total_operational_expense_actual
			row["budget_variance"] = total_operational_expense_budget - total_operational_expense_actual
			row["receipt_variance"] = total_operational_expense_receipt - total_operational_expense_actual
			total_consumption = total_consumption + total_operational_expense_actual
			if total_operational_expense_budget > 0:
				row["spent_as_percent_against_budget"] = (total_operational_expense_actual * 100) / total_operational_expense_budget
			else:
				row["spent_as_percent_against_budget"] = 0
			if total_operational_expense_receipt > 0:
				row["spent_as_percent_against_receipt"] = (total_operational_expense_actual * 100) / total_operational_expense_receipt
			else:
				row["spent_as_percent_against_receipt"] = 0

	
	# Calculations for Investments 

	investment_data.append({"description":"<b>Investments</b>"})
	
	investment_group_ledger_accounts = []

	company = frappe.get_doc("Company", filters.get("company"))
	if len(company.custom_default_budget_group_ledger_for_investment)>0:
		for account in company.custom_default_budget_group_ledger_for_investment:
			investment_group_ledger_accounts.append(cstr(account.account))
	
	total_investment_budget = 0
	total_investment_receipt = 0
	total_investment_actual = 0

	if len(project_budget)>0:
		for project in project_budget:
			project_budget_details = frappe.db.sql("""
							SELECT
								tpb.name,
								tpb.company,
								tpb.project_start_date,
								tpb.grant_ledger_account,
								tpb.startup_investment,
								tpb.startup_investment_percentage,
								tpb.total_budget,
								tpb.capex
							FROM
								`tabProject Budget` tpb
							WHERE tpb.name = '{0}'
						""".format(project),as_dict= True)
			if len(project_budget_details)>0:
				total_investment_budget = total_investment_budget + project_budget_details[0].startup_investment

				total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_details[0].company,project_budget_details[0].project_start_date,project_budget_details[0].grant_ledger_account,project_budget_details[0].name)
				receipt_amount_for_investment = ( total_receipt * project_budget_details[0].startup_investment_percentage ) / 100
				total_investment_receipt = total_investment_receipt + receipt_amount_for_investment

				group_by = "Group by Account"
				include_dimensions = 1
				include_default_book_entries = 1

				filters_of_investment_expense_for_general_ledger = frappe._dict({
					"company": project_budget_details[0].company,
					"from_date": project_budget_details[0].project_start_date,
					"to_date": getdate(today()),
					"account":investment_group_ledger_accounts,
					"cost_center":[project_budget_details[0].name],
					"group_by": group_by,
					"include_dimensions": include_dimensions,
					"include_default_book_entries": include_default_book_entries
				})

				gl_report_data_for_investments = gl_execute(filters_of_investment_expense_for_general_ledger)
				if len(gl_report_data_for_investments[1]) >0:
					account_list = []
					for investment_row in gl_report_data_for_investments[1]:
						if investment_row.get("account") and investment_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
							if row.get("account") not in account_list:
								report_row = {}
								expense = investment_row.get("debit") - investment_row.get("credit")
								report_row["description"] = investment_row.get("account")
								report_row["indent"] = 1
								report_row["project_budget"] = project_budget_details[0].name
								report_row["actual_expense"] = expense
								report_row["budget"] = 0
								report_row["total_receipt"] = 0
								total_investment_actual = total_investment_actual + expense
								# Calculating Variance and Percentages 

								budget_variance = report_row["budget"] - report_row["actual_expense"]
								report_row["budget_variance"] = budget_variance

								if report_row["budget"] > 0:
									spent_as_percent_against_budget = (report_row["actual_expense"] * 100) / report_row["budget"]
								else:
									spent_as_percent_against_budget = 0

								report_row["spent_as_percent_against_budget"] = spent_as_percent_against_budget

								investment_data.append(report_row)
								account_list.append(investment_row.get("account"))
							else :
								for existing_investment_row in investment_data:
									if existing_investment_row.get("description") == investment_row.get("account"):
										expense = existing_investment_row.get("actual_expense") + (investment_row.get("debit") - investment_row.get("credit"))
										existing_investment_row["actual_expense"] = expense
										existing_investment_row["budget_variance"] = existing_investment_row["budget"] - existing_investment_row["actual_expense"]
										if existing_investment_row["budget"] > 0:
											existing_investment_row["spent_as_percent_against_budget"] = (existing_investment_row["actual_expense"] * 100) / existing_investment_row["budget"]
										else:
											existing_investment_row["spent_as_percent_against_budget"] = 0


										total_investment_actual = total_investment_actual + (investment_row.get("debit") - investment_row.get("credit"))

							

	for row in investment_data:
		if row.get("description") == "<b>Investments</b>":
			row["budget"] = total_investment_budget
			row["actual_expense"] = total_investment_actual
			row["total_receipt"] = total_investment_receipt
			row["budget_variance"] = total_investment_budget - total_investment_actual
			row["receipt_variance"] = total_investment_receipt - total_investment_actual
			total_consumption = total_consumption + total_investment_actual
			if total_investment_budget > 0:
				row["spent_as_percent_against_budget"] = (total_investment_actual * 100) / total_investment_budget
			else:
				row["spent_as_percent_against_budget"] = 0
			if total_investment_receipt > 0:
				row["spent_as_percent_against_receipt"] = (total_investment_actual * 100) / total_investment_receipt
			else:
				row["spent_as_percent_against_receipt"] = 0
	

	# Calculations for Capex

	capex_data.append({"description":"<b>Capex</b>"})
	project_budget_list = []
	account_list = []
	company_default_capex_account = company.custom_default_budget_capex_account

	total_capex_budget = 0
	total_capex_receipt = 0
	total_capex_actual = 0

	if len(project_budget)>0:
		for project in project_budget:
			project_budget_details = frappe.db.sql("""
							SELECT
								tpb.name,
								tpb.company,
								tpb.project_start_date,
								tpb.grant_ledger_account,
								tpb.total_budget,
								tpb.capex,
								tpb.capex_percentage
							FROM
								`tabProject Budget` tpb
							WHERE tpb.name = '{0}'
						""".format(project),as_dict= True)
			if len(project_budget_details)>0:
				total_capex_budget = total_capex_budget + project_budget_details[0].capex

				total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_details[0].company,project_budget_details[0].project_start_date,project_budget_details[0].grant_ledger_account,project_budget_details[0].name)
				receipt_amount_for_capex = ( total_receipt * project_budget_details[0].capex_percentage ) / 100
				total_capex_receipt = total_capex_receipt + receipt_amount_for_capex

				capex_report_row = {}
				capex_expense = 0

				gl_list = frappe.db.get_all("GL Entry",
							 filters={"posting_date":["between",[project_budget_details[0].project_start_date,today()]],"account":["descendants of (inclusive)",company_default_capex_account],"cost_center":["descendants of (inclusive)",project_budget_details[0].name]},
							 fields=["sum(debit) as total_debit", "sum(credit) as total_credit", "account"],group_by="account")

				if len(gl_list)>0:
					for capex_row in gl_list:
						account_type = frappe.db.get_value("Account",capex_row.get("account"),"account_type")
						if account_type and account_type == "Fixed Asset":
							if capex_row.get("account") and capex_row.get("account") not in account_list:
								capex_report_row = {}	
								capex_expense = 0
								capex_expense = capex_row.total_debit - capex_row.total_credit
								if capex_expense > 0 and project not in project_budget_list:
									project_budget_list.append(project)
								capex_report_row["description"] = capex_row.get("account")
								capex_report_row["indent"] = 1
								capex_report_row["project_budget"] = project_budget_details[0].name
								capex_report_row["budget"] = 0
								capex_report_row["actual_expense"] = capex_expense

								# Calculating Variance and Percentages 

								budget_variance = capex_report_row["budget"] - capex_report_row["actual_expense"]
								capex_report_row["budget_variance"] = budget_variance

								if capex_report_row["budget"] > 0:
									spent_as_percent_against_budget = (capex_report_row["actual_expense"] * 100) / capex_report_row["budget"]
								else:
									spent_as_percent_against_budget = 0
								capex_report_row["spent_as_percent_against_budget"] = spent_as_percent_against_budget

								capex_data.append(capex_report_row)
								total_capex_actual = total_capex_actual + capex_expense

							else :
								for existing_capex_row in capex_data:
									if existing_capex_row.get("description") == capex_row.get("account"):
										capex_expense = existing_capex_row.get("actual_expense") + (capex_row.total_debit - capex_row.total_credit)
										if capex_expense > 0 and project not in project_budget_list:
											project_budget_list.append(project)
										existing_capex_row["actual_expense"] = capex_expense
										existing_capex_row["project_budget"] = ", ".join(project_budget_list)
										existing_capex_row["budget_variance"] = existing_capex_row["budget"] - existing_capex_row["actual_expense"]
										if existing_capex_row["budget"] > 0:
											existing_capex_row["spent_as_percent_against_budget"] = (existing_capex_row["actual_expense"] * 100) / existing_capex_row["budget"]
										else:
											existing_capex_row["spent_as_percent_against_budget"] = 0

										total_capex_actual = total_capex_actual + (capex_row.total_debit - capex_row.total_credit)
				else:
					capex_expense = 0


	for row in capex_data:
		if row.get("description") == "<b>Capex</b>":
			row["budget"] = total_capex_budget
			row["actual_expense"] = total_capex_actual
			row["total_receipt"] = total_capex_receipt
			row["budget_variance"] = total_capex_budget - total_capex_actual
			row["receipt_variance"] = total_capex_receipt - total_capex_actual
			total_consumption = total_consumption + total_capex_actual
			if total_capex_budget > 0:
				row["spent_as_percent_against_budget"] = (total_capex_actual * 100) / total_capex_budget
			else:
				row["spent_as_percent_against_budget"] = 0
			if total_capex_receipt > 0:
				row["spent_as_percent_against_receipt"] = (total_capex_actual * 100) / total_capex_receipt
			else:
				row["spent_as_percent_against_receipt"] = 0


	# Advances Calculations

	advance_accounts = [company.custom_advance_to_employee, company.custom_advance_to_vendor]
	project_budget_list = []

	advances_data.append({"description":"<b>Advances</b>"})

	if len(project_budget)>0:
		if len(advance_accounts)>0:
			for account in advance_accounts:
				total_debit = 0
				total_credit = 0
				advance_expense = 0
				for project in project_budget:
					project_budget_details = frappe.db.sql("""
									SELECT
										tpb.name,
										tpb.company,
										tpb.project_start_date
									FROM
										`tabProject Budget` tpb
									WHERE tpb.name = '{0}'
								""".format(project),as_dict= True)
					if len(project_budget_details)>0:
						group_by = "Group by Voucher (Consolidated)"
						include_dimensions = 1
						include_default_book_entries = 1

						filters_of_advances_for_general_ledger = frappe._dict({
							"company": project_budget_details[0].company,
							"from_date": project_budget_details[0].project_start_date,
							"to_date": getdate(today()),
							"account":[account],
							"cost_center":[project_budget_details[0].name],
							"group_by": group_by,
							"include_dimensions": include_dimensions,
							"include_default_book_entries": include_default_book_entries
						})

						gl_report_data_for_advances = gl_execute(filters_of_advances_for_general_ledger)
						if len(gl_report_data_for_advances)>0:
							for d in gl_report_data_for_advances[1]:
								if d.get("account") and d.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
									total_debit += d.get("debit")
									total_credit += d.get("credit")
							advance_expense = advance_expense + (total_debit - total_credit)
							if advance_expense > 0 and project not in project_budget_list:
								project_budget_list.append(project)

						else:
							advance_expense = 0
						
				advance_report_row = {}
				advance_report_row["description"] = account
				advance_report_row["indent"] = 1
				advance_report_row["project_budget"] = ", ".join(project_budget_list)
				advance_report_row["budget"] = 0
				advance_report_row["actual_expense"] = advance_expense
				advance_report_row["total_receipt"] = 0

				# Calculating Variance and Percentages 

				budget_variance = advance_report_row["budget"] - advance_report_row["actual_expense"]
				advance_report_row["budget_variance"] = budget_variance

				if advance_report_row["budget"] > 0:
					spent_as_percent_against_budget = (advance_report_row["actual_expense"] * 100) / advance_report_row["budget"]
				else:
					spent_as_percent_against_budget = 0
				advance_report_row["spent_as_percent_against_budget"] = spent_as_percent_against_budget

				advances_data.append(advance_report_row)

	
	# Overhead Calcultions

	overhead_data.append({"description":"<b>Overhead</b>"})
	# overhead_calculation_based_on = filters.get("overhead_calculation_based_on")
	company_default_expense_account = company.custom_default_budget_expense_account
	total_overhead_budget = 0
	total_overhead_receipt = 0
	# total_overhead_actual = 0
	overhead_expense = 0
	project_budget_list = []
	account_list = []
	total_debit = 0
	total_credit = 0

	if len(project_budget)>0:
		for project in project_budget:
			project_budget_details = frappe.db.sql("""
							SELECT
								tpb.name,
								tpb.company,
								tpb.project_start_date,
								tpb.grant_ledger_account,
								tpb.overhead_cost_center,
								tpb.overhead_percentage,
								tpb.overhead_amount
							FROM
								`tabProject Budget` tpb
							WHERE tpb.name = '{0}'
						""".format(project),as_dict= True)
			if len(project_budget_details)>0:
				total_overhead_budget = total_overhead_budget + project_budget_details[0].overhead_amount
				total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_details[0].company,project_budget_details[0].project_start_date,project_budget_details[0].grant_ledger_account,project_budget_details[0].name)
				receipt_amount_for_overhead = ( total_receipt * project_budget_details[0].overhead_percentage ) / 100
				total_overhead_receipt = total_overhead_receipt + receipt_amount_for_overhead

				overhead_expense = overhead_expense + project_budget_details[0].overhead_amount
				project_budget_list.append(project_budget_details[0].name)
				# total_overhead_actual = total_overhead_actual + overhead_expense
		overhead_report_row = {}
		overhead_report_row["description"] = ""
		overhead_report_row["indent"] = 1
		overhead_report_row["project_budget"] = ",".join(project_budget_list if len(project_budget_list) > 0 else "")
		overhead_report_row["budget"] = 0
		overhead_report_row["actual_expense"] = overhead_expense
		overhead_data.append(overhead_report_row)

	for row in overhead_data:
		if row.get("description") == "<b>Overhead</b>":
			row["budget"] = total_overhead_budget
			row["actual_expense"] = overhead_expense
			row["total_receipt"] = total_overhead_receipt
			row["budget_variance"] = total_overhead_budget - overhead_expense
			row["receipt_variance"] = total_overhead_receipt - overhead_expense
			if total_overhead_budget > 0:
				row["spent_as_percent_against_budget"] = (overhead_expense * 100) / total_overhead_budget
			else:
				row["spent_as_percent_against_budget"] = 0
			if total_overhead_receipt > 0:
				row["spent_as_percent_against_receipt"] = (overhead_expense * 100) / total_overhead_receipt
			else:
				row["spent_as_percent_against_receipt"] = 0

	# Income Calculations
	income_data.append({"description":"<b>Income</b>"})

	company_default_income_account = company.custom_default_budget_income_account
	account_list = []

	total_income = 0

	if len(project_budget)>0:
		for project in project_budget:
			project_budget_details = frappe.db.sql("""
							SELECT
								tpb.name,
								tpb.company,
								tpb.project_start_date
							FROM
								`tabProject Budget` tpb
							WHERE tpb.name = '{0}'
						""".format(project),as_dict= True)
			if len(project_budget_details)>0:
				group_by = "Group by Account"
				include_dimensions = 1
				include_default_book_entries = 1

				filters_of_income_for_general_ledger = frappe._dict({
					"company": project_budget_details[0].company,
					"from_date": project_budget_details[0].project_start_date,
					"to_date": getdate(today()),
					"account":[company_default_income_account],
					"cost_center":[project_budget_details[0].name],
					"group_by": group_by,
					"include_dimensions": include_dimensions,
					"include_default_book_entries": include_default_book_entries
				})

				gl_report_data_for_income = gl_execute(filters_of_income_for_general_ledger)
				if len(gl_report_data_for_income)>0:
					for income_row in gl_report_data_for_income[1]:
						if income_row.get("account") and income_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
							if income_row.get("account") not in account_list:
								total_income = 0
								income = income_row.get("credit") - income_row.get("debit")
								total_income = total_income + income
								income_report_row = {}
								income_report_row["description"] = income_row.get("account")
								income_report_row["indent"] = 1
								income_report_row["project_budget"] = project_budget_details[0].name
								income_report_row["budget"] = 0
								income_report_row["total_receipt"] = income

								income_data.append(income_report_row)
								account_list.append(income_row.get("account"))
							else :
								for existing_income_row in income_data:
									if existing_income_row.get("description") == income_row.get("account"):
										income = existing_income_row.get("total_receipt") + (income_row.get("credit") - income_row.get("debit"))
										existing_income_row["total_receipt"] = income
										total_income = total_income + (income_row.get("credit") - income_row.get("debit"))

				else:
					income = 0


	report_data = expense_data + investment_data + capex_data + advances_data + overhead_data + income_data
	return report_data

def get_total_receipt_amount_from_general_ledger(company,start_date,grant_ledger_account,cost_center):
	group_by = "Group by Voucher (Consolidated)"
	include_dimensions = 1
	include_default_book_entries = 1

	filters_of_receipt_for_general_ledger = frappe._dict({
		"company": company,
		"from_date": getdate(start_date),
		"to_date": getdate(today()),
		"account":[grant_ledger_account],
		"cost_center":[cost_center],
		"group_by": group_by,
		"include_dimensions": include_dimensions,
		"include_default_book_entries": include_default_book_entries
	})

	gl_report_data_for_receipt = gl_execute(filters_of_receipt_for_general_ledger)

	if len(gl_report_data_for_receipt)>0:
		total_debit = 0
		total_credit = 0
		for d in gl_report_data_for_receipt[1]:
			total_debit += d.get("debit") if d.get("voucher_subtype") == "Bank Entry" else 0
			total_credit += d.get("credit") if d.get("voucher_subtype") == "Bank Entry" else 0
		total_receipt = total_credit - total_debit
	else:
		total_receipt = 0
	
	return total_receipt