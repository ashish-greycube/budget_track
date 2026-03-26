# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr, today, flt
from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_execute
from erpnext.accounts.utils import get_fiscal_year


def execute(filters=None):
	columns, data = [], []

	# columns = get_columns(filters)
	data, columns = get_data(filters)

	return columns, data

def get_columns(filters):
	columns = [
		{
			"fieldname": "description",
			"label":_("Description"),
			"fieldtype": "Data",
			"width": 400
		},
		# {
		# 	"fieldname": "project_budget",
		# 	"label":_("Project Budget"),
		# 	"fieldtype": "Data",
		# 	"options":"Project Budget",
		# 	"width": 200
		# }	
	]
	current_fy = None
	fiscal_year_list = frappe.db.get_all("Fiscal Year",
									or_filters={"year_start_date": ["between", [filters.get("from_date"),filters.get("to_date")]],
											 "year_end_date": ["between", [filters.get("from_date"),filters.get("to_date")]]},
									fields=["name"],
									order_by="year_start_date asc")
	print(fiscal_year_list,"=========>>>>>>")
	if len(fiscal_year_list)>0:
		for fy in fiscal_year_list:
			fy_field_name = (fy.name).replace("-","_")
			if current_fy == None:
				pass
			else :
				columns.append({
					"fieldname": "carry_forward_budget_from_last_year_{0}".format(fy_field_name),
					"label":_("Carry Forward Budget From Last Year ({0})".format(fy.name)),
					"fieldtype": "Currency",
					"width": 200
				})
			columns.append({
				"fieldname": "budget_{0}".format(fy_field_name),
				"label":_("Budget ({0})".format(fy.name)),
				"fieldtype": "Currency",
				"width": 200
			})

			if current_fy == None:
				pass
			else :
				columns.append({
					"fieldname": "balance_budget_{0}".format(fy_field_name),
					"label":_("Balance Budget ({0})".format(fy.name)),
					"fieldtype": "Currency",
					"width": 200
				})
				columns.append({
					"fieldname": "carry_forward_receipt_from_last_year_{0}".format(fy_field_name),
					"label":_("Carry Forward Receipt From Last Year ({0})".format(fy.name)),
					"fieldtype": "Currency",
					"width": 200
				})

			columns.append({
				"fieldname": "total_receipt_{0}".format(fy_field_name),
				"label":_("Total Receipt ({0})".format(fy.name)),
				"fieldtype": "Currency",
				"width": 200
			})

			if current_fy == None:
				pass
			else :
				columns.append({
					"fieldname": "balance_receipt_{0}".format(fy_field_name),
					"label":_("Total Available Fund ({0})".format(fy.name)),
					"fieldtype": "Currency",
					"width": 200
				})

			columns.append({
				"fieldname": "actual_expense_{0}".format(fy_field_name),
				"label":_("Actual Expense ({0})".format(fy.name)),
				"fieldtype": "Currency",
				"width": 200
			})
			columns.append({
				"fieldname": "budget_variance_{0}".format(fy_field_name),
				"label":_("Budget Variance ({0})".format(fy.name)),
				"fieldtype": "Currency",
				"width": 200
			})
			columns.append({
				"fieldname": "receipt_variance_{0}".format(fy_field_name),
				"label":_("Receipt Variance ({0})".format(fy.name)),
				"fieldtype": "Currency",
				"width": 200
			})
			columns.append({
				"fieldname": "spent_as_percent_against_budget_{0}".format(fy_field_name),
				"label":_("Spent as % against Budget ({0})".format(fy.name)),
				"fieldtype": "Percent",
				"width": 200
			})
			columns.append({
				"fieldname": "spent_as_percent_against_receipt_{0}".format(fy_field_name),
				"label":_("Spent as % against Receipt ({0})".format(fy.name)),
				"fieldtype": "Percent",
				"width": 200
			})
			current_fy = fy.name
	return columns

def get_data(filters):
	max_description_length = 0
	project_budget = filters.get("project_budget")

	total_consumption = 0
	fiscal_year_list = frappe.db.get_all("Fiscal Year",
									or_filters={"year_start_date": ["between", [filters.get("from_date"),filters.get("to_date")]],
											 "year_end_date": ["between", [filters.get("from_date"),filters.get("to_date")]]},
									fields=["name","year_start_date"],
									order_by="year_start_date asc")

	report_data = []
	expense_data = []
	investment_data = []
	capex_data = []
	income_data = []
	overhead_data = []
	advances_data = []
	cc_list = []
	pb_list = []

	data_for_overhead = []
	fy_wise_total_expenses_for_overhead = 0
	projects_used_in_overhead = []

	total_row = {"description":"<b>Total</b>"}

	# ==============================================================
	# 1. OPERATIONAL EXPENSES
	# ==============================================================
	expense_data.append({"description":"<b>Operational Expenses</b>"})
	total_carry_forward_budget = 0
	total_carry_forward_receipt = 0
	previous_fy = None
	
	if len(project_budget)>0:
		for project in project_budget:
			if len(fiscal_year_list)>0:
				for fy in fiscal_year_list:
					total_operational_expense_budget = 0
					total_operational_expense_receipt = 0
					total_operational_expense_actual = 0
					total_carry_forward_budget = 0
					total_carry_forward_receipt = 0
					total_balance_budget = 0
					total_available_fund = 0
					current_fy = fy.name
					fy_wise_total_expenses_for_overhead = 0
					# NEW: Track cost centers already processed in this specific FY
					processed_cc_in_current_fy = [] 

					fy_field_name = (fy.name).replace("-","_")
					project_budget_allocation_details = frappe.db.sql(f"""
									SELECT
										tpba.project_budget,
										tpba.name,
										tpba.company,
										tpba.fiscal_year,
										tpba.total_expenses,
										tpba.expense_percentage,
										tpfe.description,
										tpfe.amount,
										tpfe.percentage_allocation,
										tpfe.cost_center as cost_center_for_expense,
										tfy.year_start_date,
										tfy.year_end_date,
										tpb.grant_ledger_account,
										tpb.overhead_cost_center,
										tpb.project_start_date 
									FROM
										`tabFiscal Year Wise Project Budget Allocation` tpba
									INNER JOIN `tabParticulars for Expenses` tpfe ON
										tpba.name = tpfe.parent
									INNER JOIN `tabFiscal Year` tfy ON
										tfy.name = tpba.fiscal_year
									INNER JOIN `tabProject Budget` tpb ON
										tpb.name = tpba.project_budget
									WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
								""",as_dict= True,debug=1)
					
					if len(project_budget_allocation_details)>0:
						total_operational_expense_budget = total_operational_expense_budget + project_budget_allocation_details[0].total_expenses

						group_by = "Group by Voucher (Consolidated)"
						include_dimensions = 1
						include_default_book_entries = 1

						# select from date and to date to fetch data from General Ledger 
						if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
							print("IN FROM IFF",project_budget_allocation_details[0].name)
							report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
						else :
							print("IN FROM ELSE")
							report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
						
						if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
							print("IN TO IF")
							report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
						else:
							print("IN TO ELSE")
							report_to_date = getdate(filters.get("to_date"))
						
						# Calculating receipt
						total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_allocation_details[0].company, report_from_date, report_to_date, project_budget_allocation_details[0].grant_ledger_account, project_budget_allocation_details[0].project_budget)
						
						expense_receipt_amount = ( total_receipt * project_budget_allocation_details[0].expense_percentage) / 100
						total_operational_expense_receipt = total_operational_expense_receipt + expense_receipt_amount
						
						# calculation for expenses based on cost centers
						for row in project_budget_allocation_details:
							cc = row.cost_center_for_expense
							if cc not in cc_list:
								if cc not in processed_cc_in_current_fy:
									cc_list.append(cc)
									processed_cc_in_current_fy.append(cc)

									description_length = len(row.cost_center_for_expense)
									if description_length>max_description_length:
										max_description_length = description_length
									report_row = {}
									report_row["description"] = row.cost_center_for_expense
									report_row["indent"] = 1
									report_row["project_budget"] = row.project_budget
									report_row["budget_{0}".format(fy_field_name)] = row.amount

									# Calculating Total Receipt For Operational Expense Cost Center Wise

									cost_center_wise_receipt = expense_receipt_amount * (row.percentage_allocation / 100)
									report_row["total_receipt_{0}".format(fy_field_name)] = cost_center_wise_receipt

									# Calculating Actual Expense For Operational Expense Cost Center Wise

									company_default_expense_account = frappe.db.get_value("Company", row.company, "custom_default_budget_expense_account")
									filters_of_expenses_for_general_ledger = frappe._dict({
										"company": row.company,
										"from_date": report_from_date,
										"to_date": report_to_date,
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
												# if expense_row.get("account") == row.description:
													if expense_row.get("voucher_type") and expense_row.get("voucher_type") != "Period Closing Voucher":
														total_debit += expense_row.get("debit")
														total_credit += expense_row.get("credit")
										total_expense = total_debit - total_credit

									else:
										total_expense = 0

									report_row["actual_expense_{0}".format(fy_field_name)] = total_expense
									total_operational_expense_actual = total_operational_expense_actual + total_expense

									# Calculating Variance and Percentages 

									budget_variance = report_row["budget_{0}".format(fy_field_name)] - report_row["actual_expense_{0}".format(fy_field_name)]
									receipt_variance = report_row["total_receipt_{0}".format(fy_field_name)] - report_row["actual_expense_{0}".format(fy_field_name)]
									report_row["budget_variance_{0}".format(fy_field_name)] = budget_variance
									report_row["receipt_variance_{0}".format(fy_field_name)] = receipt_variance

									if report_row["budget_{0}".format(fy_field_name)] > 0:
										spent_as_percent_against_budget = (report_row["actual_expense_{0}".format(fy_field_name)] * 100) / report_row["budget_{0}".format(fy_field_name)]
									else:
										spent_as_percent_against_budget = 0
									report_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = spent_as_percent_against_budget

									if report_row["total_receipt_{0}".format(fy_field_name)] > 0:
										spent_as_percent_against_receipt = (report_row["actual_expense_{0}".format(fy_field_name)] * 100) / report_row["total_receipt_{0}".format(fy_field_name)]
									else:
										spent_as_percent_against_receipt = 0
									report_row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = spent_as_percent_against_receipt

									expense_data.append(report_row)
									cc_list.append(row.get("cost_center_for_expense"))
									report_row["previous_year_budget_variance"] = report_row.get("budget_variance_{0}".format(fy_field_name))
									report_row["previous_year_receipt_variance"] = report_row.get("receipt_variance_{0}".format(fy_field_name))
									total_balance_budget = total_balance_budget + report_row.get("budget_variance_{0}".format(fy_field_name))
									total_available_fund = total_available_fund + report_row.get("receipt_variance_{0}".format(fy_field_name))

									fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + total_expense

							else :
								for existing_expense_row in expense_data:
									if cc == existing_expense_row.get("description"):			
										if cc not in processed_cc_in_current_fy:
											# -----------------------------------------------------------
											# SCENARIO 2: Next FY, Existing Cost Center 
											# -----------------------------------------------------------
											processed_cc_in_current_fy.append(cc)
											
											# 1. Fetch the True Carry Forward from the PREVIOUS loop FIRST
											cf_budget = existing_expense_row.get("previous_year_budget_variance") or 0
											cf_receipt = existing_expense_row.get("previous_year_receipt_variance") or 0

											if previous_fy and current_fy != previous_fy:
												existing_expense_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = cf_budget
												existing_expense_row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = cf_receipt
												
												# ADD to the grand total for this FY safely
												total_carry_forward_budget += cf_budget
												total_carry_forward_receipt += cf_receipt

											if row.project_budget not in pb_list:
												pb_list.append(row.project_budget)

											if existing_expense_row.get("budget_{0}".format(fy_field_name)) :
												existing_expense_row["budget_{0}".format(fy_field_name)] = existing_expense_row.get("budget_{0}".format(fy_field_name)) + row.amount
												existing_expense_row["project_budget"] = ",".join(pb_list)
											else:
												existing_expense_row["budget_{0}".format(fy_field_name)] = row.amount

											# Calculate Balances
											existing_expense_row["balance_budget_{0}".format(fy_field_name)] = existing_expense_row.get("budget_{0}".format(fy_field_name)) + cf_budget
											total_balance_budget += existing_expense_row["balance_budget_{0}".format(fy_field_name)]

											# Calculating Total Receipt For Operational Expense Cost Center Wise
											cost_center_wise_receipt = expense_receipt_amount * (row.percentage_allocation / 100)
											existing_expense_row["total_receipt_{0}".format(fy_field_name)] = (existing_expense_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + cost_center_wise_receipt
											
											existing_expense_row["balance_receipt_{0}".format(fy_field_name)] = existing_expense_row.get("total_receipt_{0}".format(fy_field_name)) + cf_receipt
											total_available_fund += existing_expense_row["balance_receipt_{0}".format(fy_field_name)]

											# Calculating Actual Expense For Operational Expense Cost Center Wise
											company_default_expense_account = frappe.db.get_value("Company", row.company, "custom_default_budget_expense_account")
											filters_of_expenses_for_general_ledger = frappe._dict({
												"company": row.company, "from_date": report_from_date, "to_date": report_to_date,
												"account": [company_default_expense_account], "cost_center": [row.cost_center_for_expense],
												"group_by": group_by, "include_dimensions": include_dimensions, "include_default_book_entries": include_default_book_entries
											})

											gl_report_data_for_expenses = gl_execute(filters_of_expenses_for_general_ledger)

											total_expense = 0
											if len(gl_report_data_for_expenses)>0:
												total_debit = 0
												total_credit = 0
												for expense_row in gl_report_data_for_expenses[1]:
													if expense_row.get("account") and expense_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
														if expense_row.get("voucher_type") and expense_row.get("voucher_type") != "Period Closing Voucher":
															total_debit += expense_row.get("debit")
															total_credit += expense_row.get("credit")
												total_expense = total_debit - total_credit
												
											existing_expense_row["actual_expense_{0}".format(fy_field_name)] = (existing_expense_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_expense
											total_operational_expense_actual += total_expense
											fy_wise_total_expenses_for_overhead += total_expense

											# Calculating Variance and Percentages 
											budget_variance = existing_expense_row["balance_budget_{0}".format(fy_field_name)] - existing_expense_row["actual_expense_{0}".format(fy_field_name)]
											receipt_variance = existing_expense_row["balance_receipt_{0}".format(fy_field_name)] - existing_expense_row["actual_expense_{0}".format(fy_field_name)]
											
											existing_expense_row["budget_variance_{0}".format(fy_field_name)] = budget_variance
											existing_expense_row["receipt_variance_{0}".format(fy_field_name)] = receipt_variance

											if existing_expense_row["balance_budget_{0}".format(fy_field_name)] > 0:
												existing_expense_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (existing_expense_row["actual_expense_{0}".format(fy_field_name)] * 100) / existing_expense_row["balance_budget_{0}".format(fy_field_name)]
											else:
												existing_expense_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0

											if existing_expense_row["balance_receipt_{0}".format(fy_field_name)] > 0:
												existing_expense_row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = (existing_expense_row["actual_expense_{0}".format(fy_field_name)] * 100) / existing_expense_row["balance_receipt_{0}".format(fy_field_name)]
											else:
												existing_expense_row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = 0

											# 2. Store this NEW variance safely for the NEXT Fiscal Year
											existing_expense_row["previous_year_budget_variance"] = budget_variance
											existing_expense_row["previous_year_receipt_variance"] = receipt_variance

										else:
											# -----------------------------------------------------------
											# SCENARIO 3: Same FY, Repeated Cost Center 
											# No GL calls, No carry forward calculations. Just addition.
											# -----------------------------------------------------------
											existing_expense_row["budget_{0}".format(fy_field_name)] = (existing_expense_row.get("budget_{0}".format(fy_field_name)) or 0) + row.amount
											total_balance_budget += row.amount

											cost_center_wise_receipt = expense_receipt_amount * (row.percentage_allocation / 100)
											existing_expense_row["total_receipt_{0}".format(fy_field_name)] = (existing_expense_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + cost_center_wise_receipt
											total_available_fund += cost_center_wise_receipt
											
											# Update Balances
											existing_expense_row["balance_budget_{0}".format(fy_field_name)] = (existing_expense_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + existing_expense_row["budget_{0}".format(fy_field_name)]
											existing_expense_row["balance_receipt_{0}".format(fy_field_name)] = (existing_expense_row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + existing_expense_row["total_receipt_{0}".format(fy_field_name)]

											# Recalculate Variances
											actual_exp = existing_expense_row.get("actual_expense_{0}".format(fy_field_name)) or 0
											budget_variance = existing_expense_row["balance_budget_{0}".format(fy_field_name)] - actual_exp
											receipt_variance = existing_expense_row["balance_receipt_{0}".format(fy_field_name)] - actual_exp
											
											existing_expense_row["budget_variance_{0}".format(fy_field_name)] = budget_variance
											existing_expense_row["receipt_variance_{0}".format(fy_field_name)] = receipt_variance

											# Overwrite the stored previous year variance with this newly expanded variance
											existing_expense_row["previous_year_budget_variance"] = budget_variance
											existing_expense_row["previous_year_receipt_variance"] = receipt_variance									

										fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + total_expense


					for row in expense_data:
						if row.get("description") == "<b>Operational Expenses</b>":
							row["budget_{0}".format(fy_field_name)] = (row.get("budget_{0}".format(fy_field_name)) or 0) + total_operational_expense_budget
							row["total_receipt_{0}".format(fy_field_name)] = (row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_operational_expense_receipt
							row["actual_expense_{0}".format(fy_field_name)] = (row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_operational_expense_actual

							row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + total_carry_forward_budget
							row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + total_carry_forward_receipt

							row["balance_budget_{0}".format(fy_field_name)] = (row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_operational_expense_budget
							row["balance_receipt_{0}".format(fy_field_name)] = (row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_operational_expense_receipt

							row["budget_variance_{0}".format(fy_field_name)] = (row.get("budget_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_budget_{0}".format(fy_field_name)) - total_operational_expense_actual)
							row["receipt_variance_{0}".format(fy_field_name)] = (row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_receipt_{0}".format(fy_field_name)) - total_operational_expense_actual)

							total_consumption = total_consumption + total_operational_expense_actual
							
							# total_carry_forward_budget = row.get("budget_variance_{0}".format(fy_field_name))
							# total_carry_forward_receipt = row.get("receipt_variance_{0}".format(fy_field_name))

							if total_operational_expense_budget > 0:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (total_operational_expense_actual * 100) / total_operational_expense_budget
							else:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0
							if total_operational_expense_receipt > 0:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = (total_operational_expense_actual * 100) / total_operational_expense_receipt
							else:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = 0


							total_row["budget_{0}".format(fy_field_name)] = (total_row.get("budget_{0}".format(fy_field_name)) or 0) + total_operational_expense_budget
							total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_operational_expense_receipt
							total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_operational_expense_actual
							total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_budget_{0}".format(fy_field_name)) - total_operational_expense_actual)
							total_row["receipt_variance_{0}".format(fy_field_name)] = (total_row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_receipt_{0}".format(fy_field_name)) - total_operational_expense_actual)
							total_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + total_carry_forward_budget
							total_row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + total_carry_forward_receipt
							total_row["balance_budget_{0}".format(fy_field_name)] = (total_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_operational_expense_budget
							total_row["balance_receipt_{0}".format(fy_field_name)] = (total_row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_operational_expense_receipt

					
							# Adding Data for Overhead Calculation

							if len(data_for_overhead)>0:
								for d in data_for_overhead:
									if project not in projects_used_in_overhead:
										data_for_overhead.append({
											"project_budget": project,
											"total_expense_{0}".format(fy_field_name): total_operational_expense_actual,
											"budget_{0}".format(fy_field_name): total_carry_forward_budget + total_operational_expense_budget
										})
										projects_used_in_overhead.append(project)
										break
									else:
										if project == d.get("project_budget"):
											d["total_expense_{0}".format(fy_field_name)] = (d.get("total_expense_{0}".format(fy_field_name)) or 0) + total_operational_expense_actual
											d["budget_{0}".format(fy_field_name)] = (d.get("budget_{0}".format(fy_field_name)) or 0) + total_carry_forward_budget + total_operational_expense_budget
							else:
								data_for_overhead.append({
									"project_budget": project,
									"total_expense_{0}".format(fy_field_name): total_operational_expense_actual,
									"budget_{0}".format(fy_field_name): total_carry_forward_budget + total_operational_expense_budget
								})
								projects_used_in_overhead.append(project)
					previous_fy = current_fy
	print(total_row,"<------total_row after expense")
	print(data_for_overhead,"<--------data_for_overhead after Expense")
	# ==============================================================
	# 2. INVESTMENTS
	# ==============================================================

	investment_data.append({"description":"<b>Investments</b>"})
	previous_year_budget_variance = 0
	previous_year_receipt_variance = 0
	project_wise_carry_forward_budget_variance = 0
	investment_group_ledger_accounts = []
	pb_list = []
	# total_investment_budget = 0
	# total_investment_receipt = 0
	# total_investment_actual = 0
	company = frappe.get_doc("Company", filters.get("company"))
	if len(company.custom_default_budget_group_ledger_for_investment)>0:
		for account in company.custom_default_budget_group_ledger_for_investment:
			investment_group_ledger_accounts.append(cstr(account.account))

	if len(project_budget)>0:
		for project in project_budget:
			project_wise_carry_forward_budget_variance = 0
			if len(fiscal_year_list)>0:
				for fy in fiscal_year_list:
					total_investment_budget = 0
					total_investment_receipt = 0
					total_investment_actual = 0
					total_carry_forward_budget = 0
					total_carry_forward_receipt = 0
					total_balance_budget = 0
					total_available_fund = 0

					fy_wise_total_expenses_for_overhead = 0
					fy_field_name = (fy.name).replace("-","_")
					project_budget_allocation_details = frappe.db.sql(f"""
									SELECT
										tpba.project_budget,
										tpba.company,
										tpba.fiscal_year,
										tpba.startup_investment,
										tpba.startup_investment_percentage,
										tfy.year_start_date,
										tfy.year_end_date,
										tpb.grant_ledger_account,
										tpb.overhead_cost_center,
										tpb.project_start_date 
									FROM
										`tabFiscal Year Wise Project Budget Allocation` tpba
									INNER JOIN `tabFiscal Year` tfy ON
										tfy.name = tpba.fiscal_year
									INNER JOIN `tabProject Budget` tpb ON
										tpb.name = tpba.project_budget
									WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
								""",as_dict= True,debug=1)
					if len(project_budget_allocation_details)>0:
			
						total_investment_budget = total_investment_budget + project_budget_allocation_details[0].startup_investment

						group_by = "Group by Account"
						include_dimensions = 1
						include_default_book_entries = 1

						if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
							print("IN FROM IFF",project_budget_allocation_details[0].name)
							report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
						else :
							print("IN FROM ELSE")
							report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
						
						if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
							print("IN TO IF")
							report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
						else:
							print("IN TO ELSE")
							report_to_date = getdate(filters.get("to_date"))
						
						total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_allocation_details[0].company,report_from_date,report_to_date,project_budget_allocation_details[0].grant_ledger_account,project_budget_allocation_details[0].project_budget)
						receipt_amount_for_investment = ( total_receipt * project_budget_allocation_details[0].startup_investment_percentage ) / 100
						total_investment_receipt = total_investment_receipt + receipt_amount_for_investment

						filters_of_investment_expense_for_general_ledger = frappe._dict({
							"company": project_budget_allocation_details[0].company,
							"from_date": report_from_date,
							"to_date": report_to_date,
							"account":investment_group_ledger_accounts,
							"cost_center":[project_budget_allocation_details[0].project_budget],
							"group_by": group_by,
							"include_dimensions": include_dimensions,
							"include_default_book_entries": include_default_book_entries
						})

						gl_report_data_for_investments = gl_execute(filters_of_investment_expense_for_general_ledger)
						if len(gl_report_data_for_investments[1]) >0:
							account_list = []
							for investment_row in gl_report_data_for_investments[1]:
								if investment_row.get("account") and investment_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
									# check length of description
									description_for_report = investment_row.get("cost_center") + " _ " + investment_row.get("account")
									description_length = len(description_for_report)
									if description_length>max_description_length:
										max_description_length = description_length
									if description_for_report not in account_list:
										report_row = {}
										expense = investment_row.get("debit") - investment_row.get("credit")
										report_row["description"] = description_for_report
										report_row["indent"] = 1
										report_row["project_budget"] = project_budget_allocation_details[0].project_budget
										report_row["actual_expense_{0}".format(fy_field_name)] = expense
										report_row["budget_{0}".format(fy_field_name)] = 0
										report_row["total_receipt_{0}".format(fy_field_name)] = 0
										total_investment_actual = total_investment_actual + expense
										# Calculating Variance and Percentages 

										budget_variance = report_row["budget_{0}".format(fy_field_name)] - report_row["actual_expense_{0}".format(fy_field_name)]
										report_row["budget_variance_{0}".format(fy_field_name)] = budget_variance

										if report_row["budget_{0}".format(fy_field_name)] > 0:
											spent_as_percent_against_budget = (report_row["actual_expense_{0}".format(fy_field_name)] * 100) / report_row["budget_{0}".format(fy_field_name)]
										else:
											spent_as_percent_against_budget = 0

										report_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = spent_as_percent_against_budget

										investment_data.append(report_row)
										account_list.append(description_for_report)
										report_row["previous_year_budget_variance"] = report_row.get("budget_variance_{0}".format(fy_field_name))

										fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + expense
									else :
										# if fiscal_year_changed == False:
										for existing_investment_row in investment_data:
											if existing_investment_row.get("description") == description_for_report:
												existing_investment_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = existing_investment_row.get("previous_year_budget_variance")
												existing_investment_row["balance_budget_{0}".format(fy_field_name)] = existing_investment_row.get("budget_{0}".format(fy_field_name)) + existing_investment_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))

												expense = existing_investment_row.get("actual_expense_{0}".format(fy_field_name)) + (investment_row.get("debit") - investment_row.get("credit"))
												existing_investment_row["actual_expense_{0}".format(fy_field_name)] = expense
												existing_investment_row["budget_variance_{0}".format(fy_field_name)] = existing_investment_row["balance_budget_{0}".format(fy_field_name)] - existing_investment_row["actual_expense_{0}".format(fy_field_name)]
												if existing_investment_row["budget_{0}".format(fy_field_name)] > 0:
													existing_investment_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (existing_investment_row["actual_expense_{0}".format(fy_field_name)] * 100) / existing_investment_row["budget_{0}".format(fy_field_name)]
												else:
													existing_investment_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0

												total_investment_actual = total_investment_actual + (investment_row.get("debit") - investment_row.get("credit"))
												fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + (investment_row.get("debit") - investment_row.get("credit"))

												existing_investment_row["previous_year_budget_variance"] = existing_investment_row.get("budget_variance_{0}".format(fy_field_name))
										# elif fiscal_year_changed == True:

					# else:
					# 	data_for_overhead.append({
					# 		"project_budget": project,
					# 		"total_expense_{0}".format(fy_field_name): fy_wise_total_expenses_for_overhead
					# 	})

					for row in investment_data:
						if row.get("description") == "<b>Investments</b>":
							row["budget_{0}".format(fy_field_name)] = (row.get("budget_{0}".format(fy_field_name)) or 0) + total_investment_budget
							row["actual_expense_{0}".format(fy_field_name)] = (row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_investment_actual
							row["total_receipt_{0}".format(fy_field_name)] = (row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_investment_receipt

							row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = previous_year_budget_variance
							row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = previous_year_receipt_variance

							# below 2 variables are for overhead calculations only
							project_wise_balance_budget = project_wise_carry_forward_budget_variance + total_investment_budget
							project_wise_budget_variance = project_wise_balance_budget - total_investment_actual

							row["balance_budget_{0}".format(fy_field_name)] = (row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_investment_budget
							row["balance_receipt_{0}".format(fy_field_name)] = (row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_investment_receipt
							
							row["budget_variance_{0}".format(fy_field_name)] = (row.get("budget_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name)) - total_investment_actual
							row["receipt_variance_{0}".format(fy_field_name)] = (row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name)) - total_investment_actual

							total_consumption = total_consumption + total_investment_actual
							if row.get("balance_budget_{0}".format(fy_field_name)) > 0:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (total_investment_actual * 100) / row.get("balance_budget_{0}".format(fy_field_name))
							else:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0
							if row.get("balance_receipt_{0}".format(fy_field_name)) > 0:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = (total_investment_actual * 100) / row.get("balance_receipt_{0}".format(fy_field_name))
							else:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = 0
							previous_year_budget_variance = row.get("budget_variance_{0}".format(fy_field_name))
							previous_year_receipt_variance = row.get("receipt_variance_{0}".format(fy_field_name))

							total_row["budget_{0}".format(fy_field_name)] = (total_row.get("budget_{0}".format(fy_field_name)) or 0) + total_investment_budget
							total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_investment_receipt
							total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_investment_actual
							total_row["balance_budget_{0}".format(fy_field_name)] = (total_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_investment_budget
							total_row["balance_receipt_{0}".format(fy_field_name)] = (total_row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_investment_receipt
							total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name)) - total_investment_actual
							total_row["receipt_variance_{0}".format(fy_field_name)] = (total_row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name)) - total_investment_actual
							total_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
							total_row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name))

							if len(data_for_overhead)>0:
								for d in data_for_overhead:
									if d.get("project_budget") == project:
										d["total_expense_{0}".format(fy_field_name)] = (d.get("total_expense_{0}".format(fy_field_name)) or 0) + fy_wise_total_expenses_for_overhead
										d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + project_wise_carry_forward_budget_variance + total_investment_budget
							# for overhead calculations only
							project_wise_carry_forward_budget_variance = project_wise_budget_variance

	print(total_row,"total after investment+++++++++++++++++++++++++++++++++++++++")
	print(data_for_overhead,"---------------overhead after investmenttttttttt")

	# ==============================================================
	# 3. CAPEX
	# ==============================================================

	capex_data.append({"description":"<b>Capex</b>"})
	project_budget_list = []
	account_list = []
	previous_year_budget_variance = 0
	previous_year_receipt_variance = 0
	project_wise_carry_forward_budget_variance = 0
	company_default_capex_account = company.custom_default_budget_capex_account

	if len(project_budget)>0:
		for project in project_budget:
			project_wise_carry_forward_budget_variance = 0
			if len(fiscal_year_list)>0:
				for fy in fiscal_year_list:
					total_capex_budget = 0
					total_capex_receipt = 0
					total_capex_actual = 0
					capex_expense = 0
					fy_wise_total_expenses_for_overhead = 0
					fy_field_name = (fy.name).replace("-","_")
					project_budget_allocation_details = frappe.db.sql(f"""
									SELECT
										tpb.name,
										tpba.company,
										tpba.fiscal_year,
										tpb.project_start_date,
										tpb.grant_ledger_account,
										tfy.year_start_date,
										tfy.year_end_date,
										tpba.capex,
										tpba.capex_percentage
									FROM
										`tabFiscal Year Wise Project Budget Allocation` tpba
									INNER JOIN `tabFiscal Year` tfy ON
										tfy.name = tpba.fiscal_year
									INNER JOIN `tabProject Budget` tpb ON
										tpb.name = tpba.project_budget
									WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
								""",as_dict= True,debug=1)
					if len(project_budget_allocation_details)>0:
						total_capex_budget = total_capex_budget + project_budget_allocation_details[0].capex
						if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
							print("IN FROM IFF",project_budget_allocation_details[0].name)
							report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
						else :
							print("IN FROM ELSE",getdate(project_budget_allocation_details[0].year_start_date))
							report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
						
						if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
							print("IN TO IF")
							report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
						else:
							print("IN TO ELSE")
							report_to_date = getdate(filters.get("to_date"))

						total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_allocation_details[0].company,report_from_date,report_to_date,project_budget_allocation_details[0].grant_ledger_account,project_budget_allocation_details[0].name)
						receipt_amount_for_capex = ( total_receipt * project_budget_allocation_details[0].capex_percentage ) / 100
						total_capex_receipt = total_capex_receipt + receipt_amount_for_capex

						capex_report_row = {}
						capex_expense = 0

						gl_list = frappe.db.get_all("GL Entry",
									filters={"posting_date":["between",[report_from_date,report_to_date]],"account":["descendants of (inclusive)",company_default_capex_account],"cost_center":["descendants of (inclusive)",project_budget_allocation_details[0].name]},
									fields=["sum(debit) as total_debit", "sum(credit) as total_credit", "account", "cost_center"],group_by="account")

						if len(gl_list)>0:
							# account_list = []
							for capex_row in gl_list:
								account_type = frappe.db.get_value("Account",capex_row.get("account"),"account_type")
								if account_type and account_type == "Fixed Asset":
									# check length of description
									description_for_report = capex_row.get("cost_center") + " _ " + capex_row.get("account")
									description_length = len(description_for_report)
									if description_length>max_description_length:
										max_description_length = description_length

									if capex_row.get("account") and description_for_report not in account_list:
										capex_report_row = {}	
										capex_expense = 0
										capex_expense = capex_row.total_debit - capex_row.total_credit
										if capex_expense > 0 and project not in project_budget_list:
											project_budget_list.append(project)
										capex_report_row["description"] = description_for_report
										capex_report_row["indent"] = 1
										capex_report_row["project_budget"] = project_budget_allocation_details[0].name
										capex_report_row["budget_{0}".format(fy_field_name)] = 0
										capex_report_row["actual_expense_{0}".format(fy_field_name)] = capex_expense

										# Calculating Variance and Percentages 

										budget_variance = capex_report_row["budget_{0}".format(fy_field_name)] - capex_report_row["actual_expense_{0}".format(fy_field_name)]
										capex_report_row["budget_variance_{0}".format(fy_field_name)] = budget_variance

										if capex_report_row["budget_{0}".format(fy_field_name)] > 0:
											spent_as_percent_against_budget = (capex_report_row["actual_expense_{0}".format(fy_field_name)] * 100) / capex_report_row["budget_{0}".format(fy_field_name)]
										else:
											spent_as_percent_against_budget = 0
										capex_report_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = spent_as_percent_against_budget

										capex_data.append(capex_report_row)
										total_capex_actual = total_capex_actual + capex_expense
										account_list.append(description_for_report)
										capex_report_row["previous_year_budget_variance"] = capex_report_row.get("budget_variance_{0}".format(fy_field_name))
										fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + capex_expense
									else :
										for existing_capex_row in capex_data:
											if existing_capex_row.get("description") == description_for_report:
												existing_capex_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = existing_capex_row.get("previous_year_budget_variance")
												existing_capex_row["balance_budget_{0}".format(fy_field_name)] = existing_capex_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
												capex_expense = capex_expense + (capex_row.total_debit - capex_row.total_credit)
												if capex_expense > 0 and project not in project_budget_list:
													project_budget_list.append(project)
												existing_capex_row["actual_expense_{0}".format(fy_field_name)] = capex_expense
												existing_capex_row["project_budget"] = ", ".join(project_budget_list)
												existing_capex_row["budget_variance_{0}".format(fy_field_name)] = existing_capex_row["balance_budget_{0}".format(fy_field_name)] - existing_capex_row["actual_expense_{0}".format(fy_field_name)]
												if existing_capex_row["balance_budget_{0}".format(fy_field_name)] > 0:
													existing_capex_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (existing_capex_row["actual_expense_{0}".format(fy_field_name)] * 100) / existing_capex_row["budget_{0}".format(fy_field_name)]
												else:
													existing_capex_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0

												total_capex_actual = total_capex_actual + (capex_row.total_debit - capex_row.total_credit)
												fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + (capex_row.total_debit - capex_row.total_credit)
						else:
							capex_expense = 0

					for row in capex_data:
						if row.get("description") == "<b>Capex</b>":
							row["budget_{0}".format(fy_field_name)] = (row.get("budget_{0}".format(fy_field_name)) or 0) + total_capex_budget
							row["actual_expense_{0}".format(fy_field_name)] = (row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_capex_actual
							row["total_receipt_{0}".format(fy_field_name)] = (row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_capex_receipt
							# row["budget_variance_{0}".format(fy_field_name)] = (row.get("budget_variance_{0}".format(fy_field_name)) or 0) + total_capex_budget - total_capex_actual
							# row["receipt_variance_{0}".format(fy_field_name)] = (row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + total_capex_receipt - total_capex_actual

							row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = previous_year_budget_variance
							row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = previous_year_receipt_variance
							# for overhead calculations only
							project_wise_balance_budget = project_wise_carry_forward_budget_variance + total_capex_budget
							project_wise_budget_variance = project_wise_balance_budget - total_capex_actual

							row["balance_budget_{0}".format(fy_field_name)] = (row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_capex_budget
							row["balance_receipt_{0}".format(fy_field_name)] = (row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_capex_receipt
							
							row["budget_variance_{0}".format(fy_field_name)] = (row.get("budget_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name)) - total_capex_actual
							row["receipt_variance_{0}".format(fy_field_name)] = (row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name)) - total_capex_actual

							total_consumption = total_consumption + total_capex_actual
							if row.get("balance_budget_{0}".format(fy_field_name)) > 0:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (total_capex_actual * 100) / row.get("balance_budget_{0}".format(fy_field_name))
							else:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0
							if row.get("balance_receipt_{0}".format(fy_field_name)) > 0:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = (total_capex_actual * 100) / row.get("balance_receipt_{0}".format(fy_field_name))
							else:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = 0
							previous_year_budget_variance = row.get("budget_variance_{0}".format(fy_field_name))
							previous_year_receipt_variance = row.get("receipt_variance_{0}".format(fy_field_name))

							total_row["budget_{0}".format(fy_field_name)] = (total_row.get("budget_{0}".format(fy_field_name)) or 0) + total_capex_budget
							total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_capex_receipt
							total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + total_capex_actual
							total_row["balance_budget_{0}".format(fy_field_name)] = (total_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_capex_budget
							total_row["balance_receipt_{0}".format(fy_field_name)] = (total_row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_capex_receipt
							total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name)) - total_capex_actual
							total_row["receipt_variance_{0}".format(fy_field_name)] = (total_row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name)) - total_capex_actual
							total_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
							total_row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name))

							# Adding data for overhead calculation
							if len(data_for_overhead)>0:
								for d in data_for_overhead:
									if d.get("project_budget") == project:
										d["total_expense_{0}".format(fy_field_name)] = d.get("total_expense_{0}".format(fy_field_name)) + fy_wise_total_expenses_for_overhead
										d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + project_wise_carry_forward_budget_variance + total_capex_budget
							# for overhead calculations only
							project_wise_carry_forward_budget_variance = project_wise_budget_variance

	print(total_row,"Total after capex+++++++++++++++++++++++++++++++++++++++")
	print(data_for_overhead,"++++++++++++ overhead after capexxxxxxxxxxxx")
	# ==============================================================
	# 4. ADVANCES
	# ==============================================================

	advance_accounts = [company.custom_advance_to_employee, company.custom_advance_to_vendor]
	project_budget_list = []
	project_wise_carry_forward_budget_variance = 0
	account_list = []

	advances_data.append({"description":"<b>Advances</b>"})

	if len(project_budget)>0:
		if len(advance_accounts)>0:
			# for account in advance_accounts:
			for account in advance_accounts:
				for project in project_budget:
					project_wise_carry_forward_budget_variance = 0
					if len(fiscal_year_list)>0:
						for fy in fiscal_year_list:
							total_debit = 0
							total_credit = 0
							advance_expense = 0
							fy_wise_total_expenses_for_overhead = 0
							fy_field_name = (fy.name).replace("-","_")
							project_budget_allocation_details = frappe.db.sql(f"""
											SELECT
												tpb.name,
												tpb.company,
											  	tfy.year_start_date,
												tfy.year_end_date,
												tpb.project_start_date,
											  	tpba.fiscal_year
											FROM
												`tabFiscal Year Wise Project Budget Allocation` tpba
											INNER JOIN `tabFiscal Year` tfy ON
												tfy.name = tpba.fiscal_year
											INNER JOIN `tabProject Budget` tpb ON
												tpb.name = tpba.project_budget
											WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
								""",as_dict= True)
							if len(project_budget_allocation_details)>0:
								group_by = "Group by Voucher (Consolidated)"
								include_dimensions = 1
								include_default_book_entries = 1

								if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
									print("IN FROM IFF",project_budget_allocation_details[0].name)
									report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
								else :
									print("IN FROM ELSE",getdate(project_budget_allocation_details[0].year_start_date))
									report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
								
								if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
									print("IN TO IF")
									report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
								else:
									print("IN TO ELSE")
									report_to_date = getdate(filters.get("to_date"))

								filters_of_advances_for_general_ledger = frappe._dict({
									"company": project_budget_allocation_details[0].company,
									"from_date": report_from_date,
									"to_date": report_to_date,
									"account":[account],
									"cost_center":[project_budget_allocation_details[0].name],
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
								
								# if len(data_for_overhead)>0:
								# 	for d in data_for_overhead:
								# 		if d.get("project_budget") == project:
								# 			d["total_expense_{0}".format(fy_field_name)] = d.get("total_expense_{0}".format(fy_field_name)) + (total_debit - total_credit)
								# 			d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
									
								if account not in account_list:
									advance_report_row = {}
									advance_report_row["description"] = account
									advance_report_row["indent"] = 1
									advance_report_row["project_budget"] = ", ".join(project_budget_list)
									advance_report_row["budget_{0}".format(fy_field_name)] = 0
									advance_report_row["actual_expense_{0}".format(fy_field_name)] = advance_expense
									advance_report_row["total_receipt_{0}".format(fy_field_name)] = 0

									# Calculating Variance and Percentages 

									budget_variance = advance_report_row["budget_{0}".format(fy_field_name)] - advance_report_row["actual_expense_{0}".format(fy_field_name)]
									advance_report_row["budget_variance_{0}".format(fy_field_name)] = budget_variance

									if advance_report_row["budget_{0}".format(fy_field_name)] > 0:
										spent_as_percent_against_budget = (advance_report_row["actual_expense_{0}".format(fy_field_name)] * 100) / advance_report_row["budget_{0}".format(fy_field_name)]
									else:
										spent_as_percent_against_budget = 0
									advance_report_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = spent_as_percent_against_budget

									advances_data.append(advance_report_row)
									account_list.append(account)
									advance_report_row["previous_year_budget_variance"] = advance_report_row.get("budget_variance_{0}".format(fy_field_name))
									fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + advance_expense
									####### project_wise_balance_budget and project_wise_budget_variance are for overhead claculation purpose only
									project_wise_balance_budget = project_wise_carry_forward_budget_variance + advance_report_row.get("budget_{0}".format(fy_field_name))
									project_wise_budget_variance = project_wise_balance_budget - advance_expense

									total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + advance_report_row.get("actual_expense_{0}".format(fy_field_name))
									total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + advance_report_row.get("budget_variance_{0}".format(fy_field_name))

									if len(data_for_overhead)>0:
										for d in data_for_overhead:
											if d.get("project_budget") == project:
												d["total_expense_{0}".format(fy_field_name)] = d.get("total_expense_{0}".format(fy_field_name)) + (total_debit - total_credit)
												d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + project_wise_carry_forward_budget_variance
									# for overhead calculations only
									project_wise_carry_forward_budget_variance = project_wise_budget_variance
								else :
									for existing_advance_row in advances_data:
										if account == existing_advance_row.get("description"):
											# for overhead calculations only
											project_wise_balance_budget = project_wise_carry_forward_budget_variance
											project_wise_budget_variance = project_wise_balance_budget - advance_expense
											existing_advance_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (existing_advance_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("previous_year_budget_variance")
											existing_advance_row["balance_budget_{0}".format(fy_field_name)] = (existing_advance_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
											# advance_expense = advance_expense + (capex_row.total_debit - capex_row.total_credit)

											if advance_expense > 0 and project not in project_budget_list:
												project_budget_list.append(project)
											existing_advance_row["actual_expense_{0}".format(fy_field_name)] = (existing_advance_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + advance_expense
											existing_advance_row["project_budget"] = ", ".join(project_budget_list)
											existing_advance_row["budget_variance_{0}".format(fy_field_name)] = (existing_advance_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + existing_advance_row["balance_budget_{0}".format(fy_field_name)] - existing_advance_row["actual_expense_{0}".format(fy_field_name)]
											if existing_advance_row["balance_budget_{0}".format(fy_field_name)] > 0:
												existing_advance_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (existing_advance_row["actual_expense_{0}".format(fy_field_name)] * 100) / existing_advance_row["budget_variance_{0}".format(fy_field_name)]
											else:
												existing_advance_row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0
											fy_wise_total_expenses_for_overhead = fy_wise_total_expenses_for_overhead + advance_expense

											total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("actual_expense_{0}".format(fy_field_name))
											total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("budget_variance_{0}".format(fy_field_name))
											total_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
											total_row["balance_budget_{0}".format(fy_field_name)] = (total_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + existing_advance_row.get("balance_budget_{0}".format(fy_field_name))

											if len(data_for_overhead)>0:
												for d in data_for_overhead:
													if d.get("project_budget") == project:
														d["total_expense_{0}".format(fy_field_name)] = d.get("total_expense_{0}".format(fy_field_name)) + (total_debit - total_credit)
														d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + project_wise_carry_forward_budget_variance
											# for overhead calculations only
											project_wise_carry_forward_budget_variance = project_wise_budget_variance
							# if len(data_for_overhead)>0:
							# 	for d in data_for_overhead:
							# 		if d.get("project_budget") == project:
							# 			d["total_expense_{0}".format(fy_field_name)] = d.get("total_expense_{0}".format(fy_field_name)) + fy_wise_total_expenses_for_overhead
							# 			d["budget_{0}".format(fy_field_name)]= (d.get("budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_capex_budget


	print(total_row,"Total after advances+++++++++++++++++++++++++++++++++++++++")
	print(data_for_overhead,"+++++++++++++++++++===========================data for overhead after advances")
	# ==============================================================
	# 5. OVERHEAD
	# ==============================================================

	overhead_data.append({"description":"<b>Overhead</b>"})
	# overhead_calculation_based_on = filters.get("overhead_calculation_based_on")
	total_previous_year_budget_variance = 0
	total_previous_year_receipt_variance = 0
	project_wise_carry_forward_budget_variance = 0
	project_budget_list = []
	print("**********OVERHEAD CALCULATION STARTS HERE**********")
	print(data_for_overhead,"+++++++++++++data_for_overhead+++++++++++++")
	if len(project_budget)>0:
		overhead_report_row = {}
		for project in project_budget:
			project_wise_carry_forward_budget_variance = 0
			if len(fiscal_year_list)>0:
				for fy in fiscal_year_list:
					total_overhead_budget = 0
					total_overhead_receipt = 0
					total_overhead_actual = 0
					overhead_expense = 0
					fy_field_name = (fy.name).replace("-","_")

					project_budget_allocation_details = frappe.db.sql(f"""
									SELECT
										tpb.name,
										tpb.company,
										tpb.project_start_date,
										tpb.grant_ledger_account,
										tpb.overhead_cost_center,
										tpba.overhead_percentage,
										tpba.overhead_amount,
										tpba.fiscal_year,
										tfy.year_start_date,
										tfy.year_end_date
									FROM
										`tabFiscal Year Wise Project Budget Allocation` tpba
									INNER JOIN `tabFiscal Year` tfy ON
										tfy.name = tpba.fiscal_year
									INNER JOIN `tabProject Budget` tpb ON
										tpb.name = tpba.project_budget
									WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
						""",as_dict= True)
					if len(project_budget_allocation_details)>0:

						if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
							print("IN FROM IFF",project_budget_allocation_details[0].name)
							report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
						else :
							print("IN FROM ELSE",getdate(project_budget_allocation_details[0].year_start_date))
							report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
						
						if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
							print("IN TO IF")
							report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
						else:
							print("IN TO ELSE")
							report_to_date = getdate(filters.get("to_date"))

						total_overhead_budget = total_overhead_budget + project_budget_allocation_details[0].overhead_amount
						total_receipt = get_total_receipt_amount_from_general_ledger(project_budget_allocation_details[0].company,report_from_date,report_to_date,project_budget_allocation_details[0].grant_ledger_account,project_budget_allocation_details[0].name)
						receipt_amount_for_overhead = ( total_receipt * project_budget_allocation_details[0].overhead_percentage ) / 100
						total_overhead_receipt = total_overhead_receipt + receipt_amount_for_overhead

						# if len(data_for_overhead)>0:
						# 	for d in data_for_overhead:
						# 		if d.get("project_budget") == project:
						# 			total_budget_to_calculate_overhead_actual_percentage = d.get("budget_{0}".format(fy_field_name))
						# 			overhead_actual_percentage = (project_budget_allocation_details[0].overhead_amount / total_budget_to_calculate_overhead_actual_percentage ) * 100
						# 			print(overhead_actual_percentage,"<--calculated percentage",total_budget_to_calculate_overhead_actual_percentage,"<---budget without overhead","-----------------extra claculation")
						# 			print(( d.get("total_expense_{0}".format(fy_field_name)) * overhead_actual_percentage ) / 100,"--------------------calculation for overhead expense------------------", project_budget_allocation_details[0].overhead_amount, d.get("total_expense_{0}".format(fy_field_name)))
						# 			overhead_expense = overhead_expense + ( ( d.get("total_expense_{0}".format(fy_field_name)) * overhead_actual_percentage ) / 100 )
						# 			if project not in project_budget_list:
						# 				project_budget_list.append(project)
						
									# total_overhead_actual = total_overhead_actual + overhead_expense
					# print(overhead_expense,"***********************")
					# if len(overhead_data)==1:
					# 	### calculation for overhead expense

					# 	if len(data_for_overhead)>0:
					# 		for d in data_for_overhead:
					# 			if d.get("project_budget") == project:
					# 				total_budget_to_calculate_overhead_actual_percentage = (total_row.get("budget_{0}".format(fy_field_name)) or 0) 
					# 				overhead_actual_percentage = (project_budget_allocation_details[0].overhead_amount / total_budget_to_calculate_overhead_actual_percentage ) * 100
					# 				print(overhead_actual_percentage,total_budget_to_calculate_overhead_actual_percentage,"--------------------calculation for overhead expense------------------", project_budget_allocation_details[0].overhead_percentage, d.get("total_expense_{0}".format(fy_field_name)))
					# 				overhead_expense = overhead_expense + ( ( d.get("total_expense_{0}".format(fy_field_name)) * overhead_actual_percentage ) / 100 )
					# 				if project not in project_budget_list:
					# 					project_budget_list.append(project)
					# 	overhead_report_row = {}
					# 	overhead_report_row["description"] = ""
					# 	overhead_report_row["indent"] = 1
					# 	overhead_report_row["project_budget"] = ",".join(project_budget_list if len(project_budget_list) > 0 else "")
					# 	overhead_report_row["budget_{0}".format(fy_field_name)] = 0
					# 	overhead_report_row["actual_expense_{0}".format(fy_field_name)] = overhead_expense
					# 	overhead_report_row["budget_variance_{0}".format(fy_field_name)] = overhead_report_row.get("budget_{0}".format(fy_field_name)) - overhead_report_row.get("actual_expense_{0}".format(fy_field_name))
						
					# 	previous_year_budget_variance = overhead_report_row.get("budget_variance_{0}".format(fy_field_name))
						
					# 	overhead_data.append(overhead_report_row)
					# else:
					# 	for existing_overhead_row in overhead_data:
					# 		if existing_overhead_row.get("description") == "":
					# 			# if len(data_for_overhead)>0:
					# 			# 	for d in data_for_overhead:
					# 			# 		if d.get("project_budget") == project:
					# 			# 			total_budget_to_calculate_overhead_actual_percentage = d.get("budget_{0}".format(fy_field_name))
					# 			# 			overhead_actual_percentage = (project_budget_allocation_details[0].overhead_amount / total_budget_to_calculate_overhead_actual_percentage ) * 100
					# 			# 			print(overhead_actual_percentage,total_budget_to_calculate_overhead_actual_percentage,"--------------------calculation for overhead expense------------------", project_budget_allocation_details[0].overhead_amount, d.get("total_expense_{0}".format(fy_field_name)))
					# 			# 			overhead_expense = overhead_expense + ( ( d.get("total_expense_{0}".format(fy_field_name)) * overhead_actual_percentage ) / 100 )
					# 			# 			if project not in project_budget_list:
					# 			# 				project_budget_list.append(project)

					# 			existing_overhead_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = previous_year_budget_variance
					# 			existing_overhead_row["balance_budget_{0}".format(fy_field_name)] = existing_overhead_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
					# 			existing_overhead_row["actual_expense_{0}".format(fy_field_name)] = (existing_overhead_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + overhead_expense
					# 			existing_overhead_row["budget_variance_{0}".format(fy_field_name)] = existing_overhead_row.get("balance_budget_{0}".format(fy_field_name)) - existing_overhead_row.get("actual_expense_{0}".format(fy_field_name))
								
					# 			previous_year_budget_variance = existing_overhead_row.get("budget_variance_{0}".format(fy_field_name))
								
					# total_overhead_actual = total_overhead_actual + overhead_expense

					for row in overhead_data:
						if row.get("description") == "<b>Overhead</b>":
							row["budget_{0}".format(fy_field_name)] = (row.get("budget_{0}".format(fy_field_name)) or 0) + total_overhead_budget
							# row["actual_expense_{0}".format(fy_field_name)] = (row.get("actual_expense_{0}".format(fy_field_name)) or 0) + overhead_expense
							row["total_receipt_{0}".format(fy_field_name)] = (row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_overhead_receipt

							row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + total_previous_year_budget_variance
							row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + total_previous_year_receipt_variance

							row["balance_budget_{0}".format(fy_field_name)] = (row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) + total_overhead_budget
							row["balance_receipt_{0}".format(fy_field_name)] = (row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) + total_overhead_receipt
							
							if len(data_for_overhead)>0:
								for d in data_for_overhead:
									if d.get("project_budget") == project:

										overhead_amount_to_calculate_actual_percentage = project_wise_carry_forward_budget_variance + total_overhead_budget
										total_budget_to_calculate_overhead_actual_percentage = d.get("budget_{0}".format(fy_field_name))
										print(total_budget_to_calculate_overhead_actual_percentage,"===============total_budget_to_calculate_overhead_actual_percentage")
										if total_budget_to_calculate_overhead_actual_percentage>0:
											overhead_actual_percentage = (overhead_amount_to_calculate_actual_percentage / total_budget_to_calculate_overhead_actual_percentage ) * 100
										else :
											overhead_actual_percentage = 0
										print(overhead_amount_to_calculate_actual_percentage,"=============overhead_amount_to_calculate_actual_percentage----------------")
										print(overhead_actual_percentage,total_budget_to_calculate_overhead_actual_percentage,"--------------------calculation for overhead expense------------------", d.get("total_expense_{0}".format(fy_field_name)))
										overhead_expense = overhead_expense + (( d.get("total_expense_{0}".format(fy_field_name)) * overhead_actual_percentage ) / 100 )
										print(overhead_expense,"-------------------------------overhead expense")
										if project not in project_budget_list:
											project_budget_list.append(project)
							
							project_wise_balance_budget = project_wise_carry_forward_budget_variance + total_overhead_budget
							project_wise_budget_variance = project_wise_balance_budget - flt(overhead_expense,0)
							project_wise_carry_forward_budget_variance = project_wise_budget_variance

							row["actual_expense_{0}".format(fy_field_name)] = (row.get("actual_expense_{0}".format(fy_field_name)) or 0) + flt(overhead_expense,0)

							row["budget_variance_{0}".format(fy_field_name)] = (row.get("budget_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name)) - flt(overhead_expense,0)
							row["receipt_variance_{0}".format(fy_field_name)] = (row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name)) - flt(overhead_expense,0)

							total_previous_year_budget_variance = row.get("budget_variance_{0}".format(fy_field_name))
							total_previous_year_receipt_variance = row.get("receipt_variance_{0}".format(fy_field_name))
							if total_overhead_budget > 0:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = (flt(overhead_expense,0) * 100) / total_overhead_budget
							else:
								row["spent_as_percent_against_budget_{0}".format(fy_field_name)] = 0
							if total_overhead_receipt > 0:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = (flt(overhead_expense,0) * 100) / total_overhead_receipt
							else:
								row["spent_as_percent_against_receipt_{0}".format(fy_field_name)] = 0

							total_row["budget_{0}".format(fy_field_name)] = (total_row.get("budget_{0}".format(fy_field_name)) or 0) + total_overhead_budget
							total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + total_overhead_receipt
							total_row["actual_expense_{0}".format(fy_field_name)] = (total_row.get("actual_expense_{0}".format(fy_field_name)) or 0) + flt(overhead_expense,0)
							total_row["budget_variance_{0}".format(fy_field_name)] = (total_row.get("budget_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_budget_{0}".format(fy_field_name)) - flt(overhead_expense,0))
							total_row["receipt_variance_{0}".format(fy_field_name)] = (total_row.get("receipt_variance_{0}".format(fy_field_name)) or 0) + (row.get("balance_receipt_{0}".format(fy_field_name)) - flt(overhead_expense,0))
							total_row["carry_forward_budget_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_budget_from_last_year_{0}".format(fy_field_name))
							total_row["carry_forward_receipt_from_last_year_{0}".format(fy_field_name)] = (total_row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name)) or 0) + row.get("carry_forward_receipt_from_last_year_{0}".format(fy_field_name))
							total_row["balance_budget_{0}".format(fy_field_name)] = (total_row.get("balance_budget_{0}".format(fy_field_name)) or 0) + row.get("balance_budget_{0}".format(fy_field_name))
							total_row["balance_receipt_{0}".format(fy_field_name)] = (total_row.get("balance_receipt_{0}".format(fy_field_name)) or 0) + row.get("balance_receipt_{0}".format(fy_field_name))

	print(total_row,"Total after overhead+++++++++++++++++++++++++++++++++++++++")
	# ==============================================================
	# 6. INCOME
	# ==============================================================
	income_data.append({"description":"<b>Income</b>"})

	company_default_income_account = company.custom_default_budget_income_account
	account_list = []
	
	total_income = 0

	if len(project_budget)>0:
		for project in project_budget:
			if len(fiscal_year_list)>0:
				for fy in fiscal_year_list:
					income = 0
					fy_field_name = (fy.name).replace("-","_")
					project_budget_allocation_details = frappe.db.sql(f"""
									SELECT
										tpb.name,
										tpb.company,
										tfy.year_start_date,
										tfy.year_end_date,
										tpb.project_start_date,
										tpba.fiscal_year
									FROM
										`tabFiscal Year Wise Project Budget Allocation` tpba
									INNER JOIN `tabFiscal Year` tfy ON
										tfy.name = tpba.fiscal_year
									INNER JOIN `tabProject Budget` tpb ON
										tpb.name = tpba.project_budget
									WHERE tpba.project_budget = '{project}' and tpba.fiscal_year = '{fy.name}'
								""",as_dict= True)
					if len(project_budget_allocation_details)>0:
						group_by = "Group by Account"
						include_dimensions = 1
						include_default_book_entries = 1

						if getdate(project_budget_allocation_details[0].project_start_date) >= getdate(project_budget_allocation_details[0].year_start_date):
							print("IN FROM IFF",project_budget_allocation_details[0].name)
							report_from_date = getdate(project_budget_allocation_details[0].project_start_date)
						else :
							print("IN FROM ELSE",getdate(project_budget_allocation_details[0].year_start_date))
							report_from_date = getdate(project_budget_allocation_details[0].year_start_date)
						
						if getdate(filters.get("to_date")) >= getdate(project_budget_allocation_details[0].year_end_date):
							print("IN TO IF")
							report_to_date = getdate(project_budget_allocation_details[0].year_end_date)
						else:
							print("IN TO ELSE")
							report_to_date = getdate(filters.get("to_date"))

						filters_of_income_for_general_ledger = frappe._dict({
							"company": project_budget_allocation_details[0].company,
							"from_date": report_from_date,
							"to_date": report_to_date,
							"account":[company_default_income_account],
							"cost_center":[project_budget_allocation_details[0].name],
							"group_by": group_by,
							"include_dimensions": include_dimensions,
							"include_default_book_entries": include_default_book_entries
						})
						
						gl_report_data_for_income = gl_execute(filters_of_income_for_general_ledger)

						if len(gl_report_data_for_income)>0:
							for income_row in gl_report_data_for_income[1]:
								if income_row.get("account") and income_row.get("account") not in ["'Opening'","'Closing (Opening + Total)'","'Total'"]:
									if income_row.get("voucher_type") != "Period Closing Voucher":
										if income_row.get("account") not in account_list:
											total_income = 0
											income = income_row.get("credit") - income_row.get("debit")
											total_income = total_income + income
											income_report_row = {}
											income_report_row["description"] = income_row.get("account")
											income_report_row["indent"] = 1
											income_report_row["project_budget"] = project_budget_allocation_details[0].name
											income_report_row["budget_{0}".format(fy_field_name)] = 0
											income_report_row["total_receipt_{0}".format(fy_field_name)] = income
											
											income_data.append(income_report_row)
											account_list.append(income_row.get("account"))
											# total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + income_report_row.get("total_receipt_{0}".format(fy_field_name))
										else :
											for existing_income_row in income_data:
												if existing_income_row.get("description") == income_row.get("account"):
													income = income + (income_row.get("credit") - income_row.get("debit"))
													existing_income_row["total_receipt_{0}".format(fy_field_name)] = income
													total_income = total_income + (income_row.get("credit") - income_row.get("debit"))
													# total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + income_report_row.get("total_receipt_{0}".format(fy_field_name))

						else:
							income = 0
						total_row["total_receipt_{0}".format(fy_field_name)] = (total_row.get("total_receipt_{0}".format(fy_field_name)) or 0) + income
	print(total_row,"Total after income+++++++++++++++++++++++++++++++++++++++")

	report_data = expense_data + investment_data + capex_data + advances_data + overhead_data + income_data
	report_data.append(total_row)

	#set column's width based on max data
	print(max_description_length,"----------length")
	columns = get_columns(filters)
	if len(columns)>0:
		for col in columns:
			if col.get("fieldname") == "description":
				if col.get("width")>max_description_length*8:
					pass
				else:
					col["width"] = max_description_length*8
	return report_data, columns

def get_total_receipt_amount_from_general_ledger(company,start_date,end_date,grant_ledger_account,cost_center):
	group_by = "Group by Voucher (Consolidated)"
	include_dimensions = 1
	include_default_book_entries = 1

	filters_of_receipt_for_general_ledger = frappe._dict({
		"company": company,
		"from_date": start_date,
		"to_date": end_date,
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
	
	print(total_receipt,"-------------------------------------------------------total receipt")

	return total_receipt

@frappe.whitelist()
def fetch_project_start_date_from_project_budget(project_budget):
	import json
	project_budget = json.loads(project_budget)
	lowest_date = None
	if len(project_budget)>0:
		print(project_budget, type(project_budget),"----------->>>>>>>>>>>>>")
		for project in project_budget:
			project_start_date = frappe.db.get_value("Project Budget", project, "project_start_date")
			print(project, project_start_date)
			if lowest_date == None:
				lowest_date = project_start_date
			if lowest_date and lowest_date > project_start_date:
				lowest_date = project_start_date
	return lowest_date