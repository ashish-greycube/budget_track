# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr, today, flt, get_link_to_form
from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_execute
from budget_track.api import get_cost_center_bucket_map
import json
from urllib.parse import urlencode

def execute(filters=None):
	if not filters:
		filters = {}
	data, columns = get_data(filters)
	return columns, data

def get_columns(filters):
	return [
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 260, "sticky": 1},
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_receipt", "label": _("Total Receipt"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "capital_expense", "label": _("Capital Expenses"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "revenue_expense", "label": _("Revenue Expense"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "total_expense", "label": _("Total Expense"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "budget_variance", "label": _("Budget Variance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "receipt_variance", "label": _("Receipt Variance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "spent_as_percent_against_budget", "label": _("Spent % against Budget"), "fieldtype": "Percent", "precision": 2, "width": 200},
		{"fieldname": "spent_as_percent_against_receipt", "label": _("Spent % against Receipt"), "fieldtype": "Percent", "precision": 2, "width": 200}
	]

def get_data(filters):
	max_description_length = 0
	project_budget = filters.get("project_budget") or []
	company = filters.get("company")
	if not company or not project_budget:
		return []

	# Pre-fetch Company configurations
	company_doc = frappe.get_cached_doc("Company", company)
	company_default_expense_account = company_doc.custom_default_budget_expense_account
	company_default_capex_account = company_doc.custom_default_budget_capex_account
	company_default_income_account = company_doc.custom_default_budget_income_account
	
	investment_accounts = [cstr(account.account) for account in company_doc.get("custom_default_budget_group_ledger_for_investment", [])]
	advance_accounts = [acc for acc in [company_doc.custom_advance_to_employee, company_doc.custom_advance_to_vendor] if acc]
	ignored_jes = set(frappe.get_all("Journal Entry", filters={"custom_to_ignore_in_budget_vs_actual": 1, "docstatus": 1}, pluck="name"))
	# fixed_asset_accounts = set(frappe.get_all("Account", filters={"account_type": "Fixed Asset", "company": company,"parent_account":company_default_capex_account}, pluck="name"))

	# Combined list of accounts used across the Investment, Capex and Advance amount calculation logic above,
	# reused to build the Capital Expense GL Entry hyperlink further below.
	fixed_asset_accounts=[]
	if company_default_capex_account:
		company_default_capex_account_type = frappe.db.get_value("Account",company_default_capex_account,"account_type")
		if company_default_capex_account_type == "Fixed Asset":
			fixed_asset_accounts.append(company_default_capex_account)
	else :
		frappe.throw(_("Please set Company Default Budget Capex Account in {0}".format(get_link_to_form("Company",company))))
	capital_expense_accounts = investment_accounts + fixed_asset_accounts + advance_accounts

	# Bulk query project details matching the new child table parameters
	pb_query = frappe.db.sql("""
		SELECT
			tpb.name, tpb.company, tpb.project_start_date, tpb.overhead_amount, tpb.total_budget,tpb.expense_percentage,
			tpb.overhead_percentage, tpb.total_receipt AS receipt_from_project_budget, tpb.overhead_cost_center,
			tpfe.cost_center AS cost_center_for_expense, tpfe.amount AS budget_amount, tpfe.percentage_allocation
		FROM `tabProject Budget` tpb
		LEFT JOIN `tabParticulars for Expenses` tpfe ON tpb.name = tpfe.parent
		WHERE tpb.name IN %s
	""", (tuple(project_budget),), as_dict=True)

	if not pb_query:
		return []

	# Fetch structural child cost centers
	all_child_cc = frappe.get_all("Cost Center", 
		filters={"parent_cost_center": ["in", project_budget], "company": company}, 
		fields=["name", "parent_cost_center"]
	)
	
	cc_by_parent = {}
	for cc in all_child_cc:
		cc_by_parent.setdefault(cc.parent_cost_center, []).append(cc.name)

	budget_heads = {}
	total_overhead_budget = 0
	total_overhead_receipt = 0
	processed_pbs = set()

	# 1. Process explicit budget data and calculate structural receipt allocations
	for row in pb_query:
		base_receipt = row.receipt_from_project_budget or 0
		cc_expense_receipt = base_receipt * ((row.expense_percentage or 0) / 100)

		cc = row.cost_center_for_expense
		if not cc:
			continue

		cc_receipt_child = cc_expense_receipt * ((row.percentage_allocation or 0) / 100)

		if cc not in budget_heads:
			budget_heads[cc] = {
				"budget": flt(row.budget_amount),
				"total_receipt": flt(cc_receipt_child),
				"capital_expense": 0.0,
				"revenue_expense": 0.0,
				"project_start_date": row.project_start_date,
				"company": row.company,
				"parent_cc": row.name  # Stored to support grouped sorting and isolated overheads
			}
		else:
			budget_heads[cc]["budget"] += flt(row.budget_amount)
			budget_heads[cc]["total_receipt"] += flt(cc_receipt_child)

	# 2. Backfill fallback unlisted child cost centers
	for row in pb_query:
		if row.name not in processed_pbs:
			total_overhead_budget += flt(row.overhead_amount)
			total_overhead_receipt += (flt(row.receipt_from_project_budget) * flt(row.overhead_percentage or 0)) / 100
			
			children = cc_by_parent.get(row.name, [])
			for child_cc in children:
				if child_cc != row.overhead_cost_center and child_cc not in budget_heads:
					budget_heads[child_cc] = {
						"budget": 0.0,
						"total_receipt": 0.0,
						"capital_expense": 0.0,
						"revenue_expense": 0.0,
						"project_start_date": row.project_start_date,
						"company": row.company,
						"parent_cc": row.name  # Stored to support grouped sorting and isolated overheads
					}
			processed_pbs.add(row.name)

	# --- Calculate Ledger Entries Based on Custom Account Logic ---
	# Batched by project start date instead of once per cost center: gl_execute() re-runs full
	# permission/dimension/opening-balance resolution on every call, so calling it per cost center
	# (up to 4x each) does not scale with the number of cost centers. cc_bucket_map maps each GL
	# entry's own cost center back to the top-level cost center it belongs to, since gl_execute's
	# cost_center filter expands to the whole subtree when several cost centers are queried together.
	cc_bucket_map = get_cost_center_bucket_map(list(budget_heads.keys()), company)

	ccs_by_start_date = {}
	for cc, data in budget_heads.items():
		ccs_by_start_date.setdefault(data["project_start_date"], []).append(cc)

	to_date = getdate(today())

	for start_date, ccs_in_group in ccs_by_start_date.items():
		# A. Revenue Expenses: Calculated based on company_default_expense_account
		filters_rev = frappe._dict({
			"company": company, "from_date": start_date, "to_date": to_date,
			"account": [company_default_expense_account], "cost_center": ccs_in_group,
			"include_dimensions": 1, "include_default_book_entries": 1
		})
		gl_rev = gl_execute(filters_rev)
		if len(gl_rev) > 1 and gl_rev[1]:
			for gl_row in gl_rev[1]:
				bucket = cc_bucket_map.get(gl_row.get("cost_center"))
				if not bucket:
					continue
				if gl_row.get("voucher_type") == "Period Closing Voucher":
					continue
				if gl_row.get("voucher_type") == "Journal Entry" and gl_row.get("voucher_no") in ignored_jes:
					continue
				budget_heads[bucket]["revenue_expense"] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

		# B. Capital Expenses: Investments + Capex Accounts + Advances filtered by Target Cost Centers
		# Investments
		if investment_accounts:
			filters_inv = frappe._dict({
				"company": company, "from_date": start_date, "to_date": to_date,
				"account": investment_accounts, "cost_center": ccs_in_group,
				"include_dimensions": 1, "include_default_book_entries": 1
			})
			gl_inv = gl_execute(filters_inv)
			if len(gl_inv) > 1 and gl_inv[1]:
				for gl_row in gl_inv[1]:
					bucket = cc_bucket_map.get(gl_row.get("cost_center"))
					if bucket:
						budget_heads[bucket]["capital_expense"] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

		# Capex Accounts
		# if fixed_asset_accounts:
		account_type = frappe.db.get_value("Account",company_default_capex_account,"account_type")
		if account_type == "Fixed Asset":
			filters_capex = frappe._dict({
				"company": company, "from_date": start_date, "to_date": to_date,
				"account": list(fixed_asset_accounts), "cost_center": ccs_in_group,
				"include_dimensions": 1, "include_default_book_entries": 1
			})
			gl_capex = gl_execute(filters_capex)
			if len(gl_capex) > 1 and gl_capex[1]:
				for gl_row in gl_capex[1]:
					bucket = cc_bucket_map.get(gl_row.get("cost_center"))
					if bucket:
						budget_heads[bucket]["capital_expense"] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

		# Advances (Employee & Vendor Accounts)
		if advance_accounts:
			filters_adv = frappe._dict({
				"company": company, "from_date": start_date, "to_date": to_date,
				"account": advance_accounts, "cost_center": ccs_in_group,
				"include_dimensions": 1, "include_default_book_entries": 1
			})
			gl_adv = gl_execute(filters_adv)
			if len(gl_adv) > 1 and gl_adv[1]:
				for gl_row in gl_adv[1]:
					bucket = cc_bucket_map.get(gl_row.get("cost_center"))
					if bucket:
						budget_heads[bucket]["capital_expense"] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

	# --- Aggregate Actual Expenses Grouped strictly by Project Budget ---
	project_expenses = {}
	for cc, data in budget_heads.items():
		pid = data.get("parent_cc")
		if pid:
			if pid not in project_expenses:
				project_expenses[pid] = {"revenue": 0.0, "capital": 0.0}
			project_expenses[pid]["revenue"] += data["revenue_expense"]
			project_expenses[pid]["capital"] += data["capital_expense"]

	# --- Construct Final Dataset View ---
	report_data = []
	sum_budget = sum_receipt = sum_cap = sum_rev = sum_total_exp = 0.0

	# Custom Sort Priority: 
	# 1st: Parent Cost Center group string
	# 2nd: 0 if line has budget, 1 if line is 0-budget fallback (pushes 0-budget to bottom)
	# 3rd: Cost Center string name alphabetically within their sub-priority
	sorted_budget_heads = sorted(
		budget_heads.items(),
		key=lambda x: (x[1].get("parent_cc", ""), 1 if x[1]["budget"] == 0 else 0, x[0])
	)

	for cc, data in sorted_budget_heads:
		total_exp = data["capital_expense"] + data["revenue_expense"]
		b_var = data["budget"] - total_exp
		r_var = data["total_receipt"] - total_exp
		
		report_filters_for_revenue_expense_hyperlink = {
			"company": company,
			"account": json.dumps([company_default_expense_account]),
			"cost_center": json.dumps([cc]),
			"group_by": "Categorize by Voucher (Consolidated)",
			"include_dimensions": 1,
			"include_default_book_entries": 1,
			"from_date": str(data["project_start_date"]),
			"to_date": str(today())
		}
		query_string_reve_exp = urlencode(report_filters_for_revenue_expense_hyperlink)
		reve_exp_report_link = f"/app/query-report/General%20Ledger?{query_string_reve_exp}"

		report_filters_for_capital_expense_hyperlink = {
			"company": company,
			"account": json.dumps(capital_expense_accounts),
			"cost_center": json.dumps([cc]),
			"group_by": "Categorize by Voucher (Consolidated)",
			"include_dimensions": 1,
			"include_default_book_entries": 1,
			"from_date": str(data["project_start_date"]),
			"to_date": str(today())
		}
		query_string_cap_exp = urlencode(report_filters_for_capital_expense_hyperlink)
		cap_exp_report_link = f"/app/query-report/General%20Ledger?{query_string_cap_exp}"

		row = {
			"description": cc,
			"budget": data["budget"],
			"total_receipt": data["total_receipt"],
			"capital_expense": data["capital_expense"],
			"revenue_expense": data["revenue_expense"],
			"_revenue_expense_link": reve_exp_report_link,       # Stores route context for the frontend JS formatter
			"_capital_expense_link": cap_exp_report_link,  # Stores route context for the frontend JS formatter
			"total_expense": total_exp,
			"budget_variance": b_var,
			"receipt_variance": r_var,
			"spent_as_percent_against_budget": flt((total_exp * 100) / data["budget"], 2) if data["budget"] > 0 else 0.0,
			"spent_as_percent_against_receipt": flt((total_exp * 100) / data["total_receipt"], 2) if data["total_receipt"] > 0 else 0.0
		}
		if len(cc)>max_description_length:
			max_description_length = len(cc)
		
		sum_budget += row["budget"]
		sum_receipt += row["total_receipt"]
		sum_cap += row["capital_expense"]
		sum_rev += data["revenue_expense"]
		sum_total_exp += total_exp
		report_data.append(row)

	########### --- Isolated Overhead Row Calculation --- ############
	overhead_revenue = 0.0
	overhead_capital = 0.0
	processed_pbs.clear()

	for row in pb_query:
		if row.name not in processed_pbs:
			budget_ex_overhead = flt(row.total_budget) - flt(row.overhead_amount)
			overhead_rate = (flt(row.overhead_amount) / budget_ex_overhead) * 100 if budget_ex_overhead > 0 else 0.0
			
			# Fetch the specific isolated accumulated expenses for this Project Budget only
			isolated_p_exp = project_expenses.get(row.name, {"revenue": 0.0, "capital": 0.0})
			
			# Calculate separate overhead splits using isolated project expenses (No data mixed across projects!)
			overhead_revenue += (isolated_p_exp["revenue"] * overhead_rate) / 100
			overhead_capital += (isolated_p_exp["capital"] * overhead_rate) / 100
			processed_pbs.add(row.name)

	overhead_total_expense = overhead_capital + overhead_revenue

	overhead_row = {
		"description": "Overhead",
		"budget": total_overhead_budget,
		"total_receipt": total_overhead_receipt,
		"capital_expense": overhead_capital,
		"revenue_expense": overhead_revenue,
		"total_expense": overhead_total_expense,
		"budget_variance": total_overhead_budget - overhead_total_expense,
		"receipt_variance": total_overhead_receipt - overhead_total_expense,
		"spent_as_percent_against_budget": flt((overhead_total_expense * 100) / total_overhead_budget, 2) if total_overhead_budget > 0 else 0.0,
		"spent_as_percent_against_receipt": flt((overhead_total_expense * 100) / total_overhead_receipt, 2) if total_overhead_receipt > 0 else 0.0
	}
	report_data.append(overhead_row)

	############ --- Project Income Row Calculation --- ############
	total_income_actual_receipt = 0.0
	income_report_link = None
	first_pb = pb_query[0] if pb_query else None
	if first_pb:
		report_filters_for_income_hyperlink = {
			"company": company,
			"account": json.dumps([company_default_income_account]),
			"cost_center": json.dumps(project_budget),
			"group_by": "Categorize by Voucher (Consolidated)",
			"include_dimensions": 1,
			"include_default_book_entries": 1,
			"from_date": str(first_pb.project_start_date),
			"to_date": str(today())
		}
		query_string_income = urlencode(report_filters_for_income_hyperlink)
		income_report_link = f"/app/query-report/General%20Ledger?{query_string_income}"

		filters_inc = frappe._dict({
			"company": company, "from_date": first_pb.project_start_date, "to_date": getdate(today()),
			"account": [company_default_income_account], "cost_center": project_budget,
			"group_by": "Categorize by Account", "include_dimensions": 1, "include_default_book_entries": 1
		})
		gl_inc = gl_execute(filters_inc)
		if len(gl_inc) > 1 and gl_inc[1]:
			for row in gl_inc[1]:
				if row.get("account") and row.get("account") not in ["'Opening'", "'Closing (Opening + Total)'", "'Total'"]:
					if row.get("voucher_type") != "Period Closing Voucher":
						if row.get("voucher_type") == "Journal Entry" and row.get("voucher_no") in ignored_jes:
							continue
						total_income_actual_receipt += flt(row.get("credit", 0)) - flt(row.get("debit", 0))

	income_row = {
		"description": "Project Income",
		"budget": 0.0,
		"total_receipt": total_income_actual_receipt,
		"_total_receipt_link": income_report_link,       # Stores route context for the frontend JS formatter
		"capital_expense": 0.0,
		"revenue_expense": 0.0,
		"total_expense": 0.0,
		"budget_variance": 0.0,
		"receipt_variance": total_income_actual_receipt,
		"spent_as_percent_against_budget": 0.0,
		"spent_as_percent_against_receipt": 0.0
	}
	report_data.append(income_row)

	# --- Master Grand Total Calculation ---
	final_budget = sum_budget + total_overhead_budget
	final_receipt = sum_receipt + total_overhead_receipt + total_income_actual_receipt
	final_capital_expense = sum_cap + overhead_capital
	final_revenue_expense = sum_rev + overhead_revenue
	final_total_exp = final_capital_expense + final_revenue_expense

	report_data.append({
		"description": "<b>Total</b>",
		"budget": final_budget,
		"total_receipt": final_receipt,
		"capital_expense": final_capital_expense,
		"revenue_expense": final_revenue_expense,
		"total_expense": final_total_exp,
		"budget_variance": final_budget - final_total_exp,
		"receipt_variance": final_receipt - final_total_exp,
		"spent_as_percent_against_budget": flt((final_total_exp * 100) / final_budget, 2) if final_budget > 0 else 0.0,
		"spent_as_percent_against_receipt": flt((final_total_exp * 100) / final_receipt, 2) if final_receipt > 0 else 0.0
	})

	columns = get_columns(filters)
	if len(columns)>0:
		for col in columns:
			if col.get("fieldname") == "description":
				if col.get("width")>max_description_length*8:
					pass
				else:
					col["width"] = max_description_length*8

	return report_data, columns