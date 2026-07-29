# Copyright (c) 2026, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr, today, flt, get_link_to_form
from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_execute
from budget_track.api import get_cost_center_bucket_map
from frappe.utils.nestedset import get_descendants_of
import json
from urllib.parse import urlencode

def execute(filters=None):
	if not filters:
		filters = {}
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data

def get_columns(filters):
	columns = [
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 300}
	]
	
	fiscal_year_list = frappe.db.get_all("Fiscal Year",
		or_filters={
			"year_start_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
			"year_end_date": ["between", [filters.get("from_date"), filters.get("to_date")]]
		},
		fields=["name"],
		order_by="year_start_date asc"
	)
	
	for i, fy in enumerate(fiscal_year_list):
		fy_field_name = fy.name.replace("-", "_")
		
		# Columns for subsequent years carrying over past balances
		if i > 0:
			columns.append({
				"fieldname": f"carry_forward_budget_from_last_year_{fy_field_name}",
				"label": _(f"Carry Forward Budget ({fy.name})"),
				"fieldtype": "Currency", "width": 150
			})
		
		columns.append({
			"fieldname": f"budget_{fy_field_name}",
			"label": _(f"Budget Allocated ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		
		if i > 0:
			columns.append({
				"fieldname": f"balance_budget_{fy_field_name}",
				"label": _(f"Total Balance Budget ({fy.name})"),
				"fieldtype": "Currency", "width": 150
			})
			columns.append({
				"fieldname": f"carry_forward_receipt_from_last_year_{fy_field_name}",
				"label": _(f"Carry Forward Receipt ({fy.name})"),
				"fieldtype": "Currency", "width": 150
			})
			
		columns.append({
			"fieldname": f"total_receipt_{fy_field_name}",
			"label": _(f"Total Receipt ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		
		if i > 0:
			columns.append({
				"fieldname": f"balance_receipt_{fy_field_name}",
				"label": _(f"Total Available Fund ({fy.name})"),
				"fieldtype": "Currency", "width": 150
			})
			
		columns.append({
			"fieldname": f"capital_expense_{fy_field_name}",
			"label": _(f"Capital Expenses ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		columns.append({
			"fieldname": f"revenue_expense_{fy_field_name}",
			"label": _(f"Revenue Expense ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		columns.append({
			"fieldname": f"total_expense_{fy_field_name}",
			"label": _(f"Total Expense ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		columns.append({
			"fieldname": f"budget_variance_{fy_field_name}",
			"label": _(f"Budget Variance ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		columns.append({
			"fieldname": f"receipt_variance_{fy_field_name}",
			"label": _(f"Receipt Variance ({fy.name})"),
			"fieldtype": "Currency", "width": 140
		})
		columns.append({
			"fieldname": f"spent_as_percent_against_budget_{fy_field_name}",
			"label": _(f"Spent % vs Budget ({fy.name})"),
			"fieldtype": "Percent", "precision": 2, "width": 150
		})
		columns.append({
			"fieldname": f"spent_as_percent_against_receipt_{fy_field_name}",
			"label": _(f"Spent % vs Receipt ({fy.name})"),
			"fieldtype": "Percent", "precision": 2, "width": 150
		})
		columns.append({
			"fieldname": f"general_ledger_report_link_{fy_field_name}",
			"label": _(f"GL Link ({fy.name})"),
			"fieldtype": "Small Text", "width": 100, "hidden": 1
		})
		columns.append({
			"fieldname": f"capital_expense_report_link_{fy_field_name}",
			"label": _(f"Capital Expense GL Link ({fy.name})"),
			"fieldtype": "Small Text", "width": 100, "hidden": 1
		})

	return columns

def calculate_report_dates(p_start_date, y_start_date, y_end_date, filter_to_date):
	"""
	Calculates report_from_date and report_to_date using customized date boundaries logic:
	
	- report_from_date: Max of project_start_date and year_start_date
	- report_to_date: Min of year_end_date and filter to_date
	"""
	if not p_start_date:
		report_from_date = getdate(y_start_date)
	elif getdate(p_start_date) >= getdate(y_start_date):
		report_from_date = getdate(p_start_date)
	else:
		report_from_date = getdate(y_start_date)

	if filter_to_date and getdate(filter_to_date) >= getdate(y_end_date):
		report_to_date = getdate(y_end_date)
	elif filter_to_date:
		report_to_date = getdate(filter_to_date)
	else:
		report_to_date = getdate(y_end_date)

	return report_from_date, report_to_date

def get_data(filters):
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

	fixed_asset_accounts=[]
	if company_default_capex_account:
		fixed_asset_accounts = set(frappe.get_all("Account", filters={"account_type": "Fixed Asset", "company": company, "parent_account":company_default_capex_account}, pluck="name"))
		company_default_capex_account_type = frappe.db.get_value("Account",company_default_capex_account,"account_type")
		if company_default_capex_account_type == "Fixed Asset":
			fixed_asset_accounts.append(company_default_capex_account)
	else :
		frappe.throw(_("Please set Company Default Budget Capex Account in {0}".format(get_link_to_form("Company",company))))

	# Combined list of accounts used across the Investment, Capex and Advance amount calculation logic below,
	# reused to build the Capital Expense GL Entry hyperlink further below.
	capital_expense_accounts = investment_accounts + list(fixed_asset_accounts) + advance_accounts

	fiscal_year_list = frappe.db.get_all("Fiscal Year",
		or_filters={
			"year_start_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
			"year_end_date": ["between", [filters.get("from_date"), filters.get("to_date")]]
		},
		fields=["name", "year_start_date", "year_end_date"],
		order_by="year_start_date asc"
	)
	if not fiscal_year_list:
		return []

	fy_names = tuple([fy.name for fy in fiscal_year_list])
	pb_tuple = tuple(project_budget)

	# Fetch operational structural allocations mapping child table particulars
	op_sql = """
		SELECT
			tpba.project_budget, tpba.name as allocation_name, tpba.company, tpba.fiscal_year,
			tpba.total_expenses, tpba.expense_percentage, tpfe.description,
			tpfe.amount as budget_amount, tpfe.percentage_allocation, tpfe.cost_center as cost_center_for_expense,
			tfy.year_start_date, tfy.year_end_date, tpb.project_start_date,
			tpba.total_receipt AS receipt_from_project_budget, tpb.overhead_cost_center,
			tpba.overhead_amount, tpba.overhead_percentage, tpba.total_budget as project_total_budget
		FROM `tabFiscal Year Wise Project Budget Allocation` tpba
		INNER JOIN `tabParticulars for Expenses` tpfe ON tpba.name = tpfe.parent
		INNER JOIN `tabFiscal Year` tfy ON tfy.name = tpba.fiscal_year
		INNER JOIN `tabProject Budget` tpb ON tpb.name = tpba.project_budget
		WHERE tpba.project_budget IN %s AND tpba.fiscal_year IN %s
	"""
	pb_rows = frappe.db.sql(op_sql, (pb_tuple, fy_names), as_dict=True)

	# Fetch fallback/unlisted child cost centers to handle fallback mapping
	all_child_cc = frappe.get_all("Cost Center", 
		filters={"parent_cost_center": ["in", project_budget], "company": company}, 
		fields=["name", "parent_cost_center"]
	)
	cc_by_parent = {}
	cc_parent_map = {}
	for cc in all_child_cc:
		cc_by_parent.setdefault(cc.parent_cost_center, []).append(cc.name)
		cc_parent_map[cc.name] = cc.parent_cost_center

	# Extract a unified flat set of all unique cost centers involved across years
	all_cost_centers = set()
	overhead_cost_centers = set()
	explicit_ccs = set()
	
	for row in pb_rows:
		if row.cost_center_for_expense:
			all_cost_centers.add(row.cost_center_for_expense)
			explicit_ccs.add(row.cost_center_for_expense)
			if row.cost_center_for_expense not in cc_parent_map:
				cc_parent_map[row.cost_center_for_expense] = row.project_budget
		if row.overhead_cost_center:
			overhead_cost_centers.add(row.overhead_cost_center)
			
	for pb in project_budget:
		for child_cc in cc_by_parent.get(pb, []).copy():
			if child_cc not in overhead_cost_centers:
				all_cost_centers.add(child_cc)

	# Group by Parent Cost Center, push fallbacks to the bottom, then sort alphabetically
	sorted_cc_list = sorted(
		list(all_cost_centers),
		key=lambda cc: (cc_parent_map.get(cc, ""), cc not in explicit_ccs, cc)
	)

	# Resolves any GL entry's actual cost center back to its owning bucket in sorted_cc_list, so GL
	# lookups can be batched across several cost centers per call instead of once per cost center.
	cc_bucket_map = get_cost_center_bucket_map(sorted_cc_list, company)

	# Initialize master flat row dict context to remove hierarchical tree properties
	report_rows_dict = {cc: {"description": cc} for cc in sorted_cc_list}
	overhead_row = {"description": "Overhead"}
	project_income_row = {"description": "Project Income"}
	total_row = {"description": "<b>Total</b>"}

	# Track running multi-year balances for consecutive carry forward integration
	cc_carry_forward = {cc: (0.0, 0.0) for cc in sorted_cc_list}
	overhead_carry_forward = (0.0, 0.0)
	income_carry_forward_receipt = 0.0
	project_overhead_balance_carry_forward = {pb: 0.0 for pb in project_budget}

	# Standard GL total string constants for accurate comparison filtering
	gl_labels_to_ignore = ["Opening", "Closing (Opening + Total)", "Total"]

	# Process data chronologically per fiscal cycle to apply carry-forward logic safely
	for idx, fy in enumerate(fiscal_year_list):
		fy_field_name = fy.name.replace("-", "_")
		fy_pb_rows = [r for r in pb_rows if r.fiscal_year == fy.name]
		
		project_fy_meta = {}
		cc_budget_map = {}
		processed_allocations = set()
		
		total_fy_overhead_budget = 0.0
		total_fy_overhead_receipt = 0.0

		# Project specific analytical trackers to resolve multiple selection inflation
		project_actual_revenue = {pb: 0.0 for pb in project_budget}
		project_actual_capital = {pb: 0.0 for pb in project_budget}
		project_balance_budget = {pb: 0.0 for pb in project_budget}

		fy_start_date = fy.year_start_date
		fy_end_date = fy.year_end_date
		if filters.get("to_date") and getdate(filters.get("to_date")) < getdate(fy_end_date):
			fy_end_date = filters.get("to_date")

		for row in fy_pb_rows:
			proj = row.project_budget
			if proj not in project_fy_meta:
				project_fy_meta[proj] = {
					"receipt_from_project_budget": flt(row.receipt_from_project_budget),
					"expense_percentage": flt(row.expense_percentage),
					"overhead_amount": flt(row.overhead_amount),
					"overhead_percentage": flt(row.overhead_percentage),
					"total_budget": flt(row.project_total_budget),
					"project_start_date": row.project_start_date,
					"company": row.company
				}
			
			cc = row.cost_center_for_expense
			if cc:
				base_receipt = flt(row.receipt_from_project_budget)
				cc_expense_receipt = base_receipt * (flt(row.expense_percentage) / 100.0)
				cc_receipt_child = cc_expense_receipt * (flt(row.percentage_allocation) / 100.0)
				
				key = (proj, cc)
				if key not in cc_budget_map:
					cc_budget_map[key] = {"budget": 0.0, "receipt": 0.0}
				cc_budget_map[key]["budget"] += flt(row.budget_amount)
				cc_budget_map[key]["receipt"] += flt(cc_receipt_child)
				
			if row.allocation_name not in processed_allocations:
				total_fy_overhead_budget += flt(row.overhead_amount)
				total_fy_overhead_receipt += (flt(row.receipt_from_project_budget) * flt(row.overhead_percentage or 0)) / 100.0
				processed_allocations.add(row.allocation_name)

		# 1. PROCESS CORE COST CENTERS
		# Phase A: resolve carry-forward/budget figures and each cost center's report date window.
		# report_from_date/report_to_date depend only on the cc's parent project + this FY, so cost
		# centers sharing a project end up sharing a window and can be queried together in Phase B.
		cc_calc = {}
		for cc in sorted_cc_list:
			row_data = report_rows_dict[cc]

			cf_budget, cf_receipt = cc_carry_forward[cc]
			if idx > 0:
				row_data[f"carry_forward_budget_from_last_year_{fy_field_name}"] = cf_budget
				row_data[f"carry_forward_receipt_from_last_year_{fy_field_name}"] = cf_receipt

			cc_fy_budget = 0.0
			cc_fy_receipt = 0.0

			cc_parent_project = cc_parent_map.get(cc)
			p_start_date = None
			if cc_parent_project in project_fy_meta:
				p_start_date = project_fy_meta[cc_parent_project].get("project_start_date")

			report_from_date, report_to_date = calculate_report_dates(
				p_start_date=p_start_date,
				y_start_date=fy.year_start_date,
				y_end_date=fy.year_end_date,
				filter_to_date=filters.get("to_date")
			)

			for proj in project_budget:
				if (proj, cc) in cc_budget_map:
					cc_fy_budget += cc_budget_map[(proj, cc)]["budget"]
					cc_fy_receipt += cc_budget_map[(proj, cc)]["receipt"]

			row_data[f"budget_{fy_field_name}"] = cc_fy_budget
			row_data[f"total_receipt_{fy_field_name}"] = cc_fy_receipt

			balance_budget = cc_fy_budget + cf_budget
			balance_receipt = cc_fy_receipt + cf_receipt

			if idx > 0:
				row_data[f"balance_budget_{fy_field_name}"] = balance_budget
				row_data[f"balance_receipt_{fy_field_name}"] = balance_receipt
			else:
				balance_budget = cc_fy_budget
				balance_receipt = cc_fy_receipt

			if cc_parent_project in project_balance_budget:
				project_balance_budget[cc_parent_project] += balance_budget

			cc_calc[cc] = {
				"report_from_date": getdate(report_from_date),
				"report_to_date": getdate(report_to_date),
				"balance_budget": balance_budget,
				"balance_receipt": balance_receipt,
				"cc_parent_project": cc_parent_project,
			}

		# Phase B: batch GL lookups per unique (from_date, to_date) window instead of once per cc.
		# gl_execute()'s cost_center filter expands to the whole subtree when passed several cost
		# centers, so cc_bucket_map resolves each returned entry's own cost_center back to the right row.
		ccs_by_window = {}
		for cc, calc in cc_calc.items():
			ccs_by_window.setdefault((calc["report_from_date"], calc["report_to_date"]), []).append(cc)

		rev_expense_by_cc = {cc: 0.0 for cc in sorted_cc_list}
		cap_expense_by_cc = {cc: 0.0 for cc in sorted_cc_list}

		for (window_from, window_to), ccs_in_window in ccs_by_window.items():
			# A. Revenue Expenses (Default Expense Account Context)
			filters_rev = frappe._dict({
				"company": company, "from_date": window_from, "to_date": window_to,
				"account": [company_default_expense_account], "cost_center": ccs_in_window,
				"include_dimensions": 1, "include_default_book_entries": 1
			})
			gl_rev = gl_execute(filters_rev)
			if len(gl_rev) > 1 and gl_rev[1]:
				for gl_row in gl_rev[1]:
					bucket = cc_bucket_map.get(gl_row.get("cost_center"))
					if bucket not in rev_expense_by_cc:
						continue
					if gl_row.get("voucher_type") == "Period Closing Voucher":
						continue
					if gl_row.get("voucher_type") == "Journal Entry" and gl_row.get("voucher_no") in ignored_jes:
						continue
					rev_expense_by_cc[bucket] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

			# B. Capital Expenses (Investments + Capex accounts + Advances)
			if investment_accounts:
				filters_inv = frappe._dict({
					"company": company, "from_date": window_from, "to_date": window_to,
					"account": investment_accounts, "cost_center": ccs_in_window,
					"include_dimensions": 1, "include_default_book_entries": 1
				})
				gl_inv = gl_execute(filters_inv)
				if len(gl_inv) > 1 and gl_inv[1]:
					for gl_row in gl_inv[1]:
						bucket = cc_bucket_map.get(gl_row.get("cost_center"))
						if bucket in cap_expense_by_cc:
							cap_expense_by_cc[bucket] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

			# Capex Accounts
			if fixed_asset_accounts:
				filters_capex = frappe._dict({
					"company": company, "from_date": window_from, "to_date": window_to,
					"account": list(fixed_asset_accounts), "cost_center": ccs_in_window,
					"include_dimensions": 1, "include_default_book_entries": 1
				})
				gl_capex = gl_execute(filters_capex)
				if len(gl_capex) > 1 and gl_capex[1]:
					for gl_row in gl_capex[1]:
						bucket = cc_bucket_map.get(gl_row.get("cost_center"))
						if bucket in cap_expense_by_cc:
							cap_expense_by_cc[bucket] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

			if advance_accounts:
				filters_adv = frappe._dict({
					"company": company, "from_date": window_from, "to_date": window_to,
					"account": advance_accounts, "cost_center": ccs_in_window,
					"include_dimensions": 1, "include_default_book_entries": 1
				})
				gl_adv = gl_execute(filters_adv)
				if len(gl_adv) > 1 and gl_adv[1]:
					for gl_row in gl_adv[1]:
						bucket = cc_bucket_map.get(gl_row.get("cost_center"))
						if bucket in cap_expense_by_cc:
							cap_expense_by_cc[bucket] += flt(gl_row.get("debit", 0)) - flt(gl_row.get("credit", 0))

		# Phase C: finalize each cost center's row using the batched GL results
		for cc in sorted_cc_list:
			row_data = report_rows_dict[cc]
			calc = cc_calc[cc]
			cc_parent_project = calc["cc_parent_project"]
			balance_budget = calc["balance_budget"]
			balance_receipt = calc["balance_receipt"]
			report_from_date = calc["report_from_date"]
			report_to_date = calc["report_to_date"]

			rev_expense = rev_expense_by_cc[cc]
			cap_expense = cap_expense_by_cc[cc]
			total_exp = rev_expense + cap_expense

			if cc_parent_project in project_budget:
				project_actual_revenue[cc_parent_project] += rev_expense
				project_actual_capital[cc_parent_project] += cap_expense

			row_data[f"capital_expense_{fy_field_name}"] = cap_expense
			row_data[f"revenue_expense_{fy_field_name}"] = rev_expense
			row_data[f"total_expense_{fy_field_name}"] = total_exp

			b_var = balance_budget - total_exp
			r_var = balance_receipt - total_exp

			row_data[f"budget_variance_{fy_field_name}"] = b_var
			row_data[f"receipt_variance_{fy_field_name}"] = r_var

			row_data[f"spent_as_percent_against_budget_{fy_field_name}"] = flt((total_exp * 100.0) / balance_budget, 2) if balance_budget > 0 else 0.0
			row_data[f"spent_as_percent_against_receipt_{fy_field_name}"] = flt((total_exp * 100.0) / balance_receipt, 2) if balance_receipt > 0 else 0.0

			report_filters_for_hyperlink = {
				"company": company, "account": json.dumps([company_default_expense_account]), "cost_center": json.dumps([cc]),
				"group_by": "Categorize by Voucher (Consolidated)", "include_dimensions": 1, "include_default_book_entries": 1,
				"from_date": str(report_from_date), "to_date": str(report_to_date)
			}
			row_data[f"general_ledger_report_link_{fy_field_name}"] = f"/app/query-report/General%20Ledger?{urlencode(report_filters_for_hyperlink)}"

			report_filters_for_capex_hyperlink = {
				"company": company, "account": json.dumps(capital_expense_accounts), "cost_center": json.dumps([cc]),
				"group_by": "Categorize by Voucher (Consolidated)", "include_dimensions": 1, "include_default_book_entries": 1,
				"from_date": str(report_from_date), "to_date": str(report_to_date)
			}
			row_data[f"capital_expense_report_link_{fy_field_name}"] = f"/app/query-report/General%20Ledger?{urlencode(report_filters_for_capex_hyperlink)}"

			cc_carry_forward[cc] = (b_var, r_var)

		# 2. PROCESS OVERHEAD LOGIC FOR CURRENT FY (SUM OF INDIVIDUAL SELECTED PROJECTS)
		cf_oh_budget, cf_oh_receipt = overhead_carry_forward
		if idx > 0:
			overhead_row[f"carry_forward_budget_from_last_year_{fy_field_name}"] = cf_oh_budget
			overhead_row[f"carry_forward_receipt_from_last_year_{fy_field_name}"] = cf_oh_receipt
			
		overhead_row[f"budget_{fy_field_name}"] = total_fy_overhead_budget
		overhead_row[f"total_receipt_{fy_field_name}"] = total_fy_overhead_receipt
		
		bal_oh_budget = total_fy_overhead_budget + cf_oh_budget
		bal_oh_receipt = total_fy_overhead_receipt + cf_oh_receipt
		
		if idx > 0:
			overhead_row[f"balance_budget_{fy_field_name}"] = bal_oh_budget
			overhead_row[f"balance_receipt_{fy_field_name}"] = bal_oh_receipt
		else:
			bal_oh_budget = total_fy_overhead_budget
			bal_oh_receipt = total_fy_overhead_receipt
			
		overhead_revenue = 0.0
		overhead_capital = 0.0
		
		for proj, meta in project_fy_meta.items():
			p_start_date = meta.get("project_start_date")
			is_cc_start_fy = bool(p_start_date) and getdate(fy.year_start_date) <= getdate(p_start_date) <= getdate(fy.year_end_date)

			if is_cc_start_fy:
				# CC Start FY: rate is based on this FY's own allocated budget/overhead
				budget_ex_overhead = meta["total_budget"] - meta["overhead_amount"]
				oh_amount_for_rate = meta["overhead_amount"]
			else:
				# Other FYs: rate is based on the cumulative Total Balance Budget (carry-forward aware),
				# and the overhead numerator is the Balance Overhead Budget
				# (carry forward overhead budget from last year + current year's overhead allocation)
				budget_ex_overhead = project_balance_budget.get(proj, 0.0)
				oh_amount_for_rate = meta["overhead_amount"] + project_overhead_balance_carry_forward.get(proj, 0.0)

			overhead_rate = (oh_amount_for_rate / budget_ex_overhead) * 100.0 if budget_ex_overhead > 0 else 0.0

			proj_overhead_revenue = (project_actual_revenue.get(proj, 0.0) * overhead_rate) / 100.0
			proj_overhead_capital = (project_actual_capital.get(proj, 0.0) * overhead_rate) / 100.0

			overhead_revenue += proj_overhead_revenue
			overhead_capital += proj_overhead_capital

			# Carry forward the unspent Balance Overhead Budget into the next fiscal year
			project_overhead_balance_carry_forward[proj] = oh_amount_for_rate - (proj_overhead_revenue + proj_overhead_capital)

		overhead_row[f"capital_expense_{fy_field_name}"] = overhead_capital
		overhead_row[f"revenue_expense_{fy_field_name}"] = overhead_revenue
		overhead_row[f"total_expense_{fy_field_name}"] = overhead_revenue + overhead_capital
		
		overhead_actual_total = overhead_revenue + overhead_capital
		oh_b_var = bal_oh_budget - overhead_actual_total
		oh_r_var = bal_oh_receipt - overhead_actual_total
		
		overhead_row[f"budget_variance_{fy_field_name}"] = oh_b_var
		overhead_row[f"receipt_variance_{fy_field_name}"] = oh_r_var
		overhead_row[f"spent_as_percent_against_budget_{fy_field_name}"] = flt((overhead_actual_total * 100.0) / bal_oh_budget, 2) if bal_oh_budget > 0 else 0.0
		overhead_row[f"spent_as_percent_against_receipt_{fy_field_name}"] = flt((overhead_actual_total * 100.0) / bal_oh_receipt, 2) if bal_oh_receipt > 0 else 0.0
		
		overhead_carry_forward = (oh_b_var, oh_r_var)

		# 3. PROCESS PROJECT INCOME LOGIC FOR CURRENT FY
		if idx > 0:
			project_income_row[f"carry_forward_budget_from_last_year_{fy_field_name}"] = 0.0
			project_income_row[f"carry_forward_receipt_from_last_year_{fy_field_name}"] = income_carry_forward_receipt
			
		project_income_row[f"budget_{fy_field_name}"] = 0.0
		total_income_actual_receipt = 0.0

		inc_from_date = fy.year_start_date
		inc_to_date = fy.year_end_date
		
		for proj, meta in project_fy_meta.items():
			p_from, p_to = calculate_report_dates(
				p_start_date=meta.get("project_start_date"),
				y_start_date=fy.year_start_date,
				y_end_date=fy.year_end_date,
				filter_to_date=filters.get("to_date")
			)
			if getdate(p_from) > getdate(inc_from_date):
				inc_from_date = p_from
			if getdate(p_to) < getdate(inc_to_date):
				inc_to_date = p_to
				
		filters_inc = frappe._dict({
			"company": company, "from_date": getdate(inc_from_date), "to_date": getdate(inc_to_date),
			"account": [company_default_income_account], "cost_center": project_budget,
			"group_by": "Categorize by Account", "include_dimensions": 1, "include_default_book_entries": 1
		})
		gl_inc = gl_execute(filters_inc)
		if len(gl_inc) > 1 and gl_inc[1]:
			for gl_row in gl_inc[1]:
				if gl_row.get("account") and cstr(gl_row.get("account")).strip("'") not in gl_labels_to_ignore:
					if gl_row.get("voucher_type") != "Period Closing Voucher":
						if gl_row.get("voucher_type") == "Journal Entry" and gl_row.get("voucher_no") in ignored_jes:
							continue
						total_income_actual_receipt += flt(gl_row.get("credit", 0)) - flt(gl_row.get("debit", 0))
						
		project_income_row[f"total_receipt_{fy_field_name}"] = total_income_actual_receipt
		bal_inc_receipt = total_income_actual_receipt + income_carry_forward_receipt
		
		if idx > 0:
			project_income_row[f"balance_budget_{fy_field_name}"] = 0.0
			project_income_row[f"balance_receipt_{fy_field_name}"] = bal_inc_receipt
			
		project_income_row[f"capital_expense_{fy_field_name}"] = 0.0
		project_income_row[f"revenue_expense_{fy_field_name}"] = 0.0
		project_income_row[f"total_expense_{fy_field_name}"] = 0.0
		project_income_row[f"budget_variance_{fy_field_name}"] = 0.0
		project_income_row[f"receipt_variance_{fy_field_name}"] = bal_inc_receipt
		project_income_row[f"spent_as_percent_against_budget_{fy_field_name}"] = 0.0
		project_income_row[f"spent_as_percent_against_receipt_{fy_field_name}"] = 0.0
		
		income_carry_forward_receipt = bal_inc_receipt

		# 4. SUMMARIZE THE MASTER GRAND TOTAL ROW FOR THE ACTIVE FY PERIOD
		tot_cb = tot_cr = tot_b = tot_bb = tot_tr = tot_br = tot_cap = tot_rev = tot_exp = tot_bv = tot_rv = 0.0
		all_rows_to_sum = list(report_rows_dict.values()) + [overhead_row, project_income_row]
		
		for r in all_rows_to_sum:
			tot_cb += r.get(f"carry_forward_budget_from_last_year_{fy_field_name}", 0.0)
			tot_cr += r.get(f"carry_forward_receipt_from_last_year_{fy_field_name}", 0.0)
			tot_b += r.get(f"budget_{fy_field_name}", 0.0)
			tot_bb += r.get(f"balance_budget_{fy_field_name}", 0.0)
			tot_tr += r.get(f"total_receipt_{fy_field_name}", 0.0)
			tot_br += r.get(f"balance_receipt_{fy_field_name}", 0.0)
			tot_cap += r.get(f"capital_expense_{fy_field_name}", 0.0)
			tot_rev += r.get(f"revenue_expense_{fy_field_name}", 0.0)
			tot_exp += r.get(f"total_expense_{fy_field_name}", 0.0)
			tot_bv += r.get(f"budget_variance_{fy_field_name}", 0.0)
			tot_rv += r.get(f"receipt_variance_{fy_field_name}", 0.0)
			
		if idx > 0:
			total_row[f"carry_forward_budget_from_last_year_{fy_field_name}"] = tot_cb
			total_row[f"carry_forward_receipt_from_last_year_{fy_field_name}"] = tot_cr
			total_row[f"balance_budget_{fy_field_name}"] = tot_bb
			total_row[f"balance_receipt_{fy_field_name}"] = tot_br
			
		total_row[f"budget_{fy_field_name}"] = tot_b
		total_row[f"total_receipt_{fy_field_name}"] = tot_tr
		total_row[f"capital_expense_{fy_field_name}"] = tot_cap
		total_row[f"revenue_expense_{fy_field_name}"] = tot_rev
		total_row[f"total_expense_{fy_field_name}"] = tot_exp
		total_row[f"budget_variance_{fy_field_name}"] = tot_bv
		total_row[f"receipt_variance_{fy_field_name}"] = tot_rv
		
		calc_bb = tot_bb if idx > 0 else tot_b
		calc_br = tot_br if idx > 0 else tot_tr
		
		total_row[f"spent_as_percent_against_budget_{fy_field_name}"] = flt((tot_exp * 100.0) / calc_bb, 2) if calc_bb > 0 else 0.0
		total_row[f"spent_as_percent_against_receipt_{fy_field_name}"] = flt((tot_exp * 100.0) / calc_br, 2) if calc_br > 0 else 0.0

	# Assemble the clean dataset rows strictly sequentially without indentations
	final_data = []
	for cc in sorted_cc_list:
		final_data.append(report_rows_dict[cc])
	final_data.append(overhead_row)
	final_data.append(project_income_row)
	final_data.append(total_row)
	
	return final_data

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