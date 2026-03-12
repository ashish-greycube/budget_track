# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FiscalYearWiseProjectBudgetAllocation(Document):

	def validate(self):
	
		# total_budget = (self.startup_investment or 0) + (self.capex or 0) + (self.total_expenses or 0)
		# overhead_amount = (total_budget * self.overhead_percentage ) / 100
		# percentage_without_overhead = 100 - self.overhead_percentage
		total_budget = (self.startup_investment or 0) + (self.total_expenses or 0) + (self.capex or 0) + (self.overhead_amount or 0)

		expense_percentage = ( (self.total_expenses or 0) * 100 ) / (total_budget or 0)
		capex_percentage = ( (self.capex or 0) * 100 ) / (total_budget or 0)
		investment_percentage = ( (self.startup_investment or 0) * 100 ) / (total_budget or 0)
		overhead_percentage = ( (self.overhead_amount or 0) * 100 ) / (total_budget or 0)

		# self.overhead_amount = overhead_amount
		self.startup_investment_percentage = investment_percentage
		self.capex_percentage = capex_percentage
		self.expense_percentage = expense_percentage
		self.overhead_percentage = overhead_percentage

		if len(self.particulars_for_expenses)>0:
			for row in self.particulars_for_expenses:
				expense_percentage_cc_wise = ( row.amount * 100 ) / self.total_expenses
				row.percentage_allocation = expense_percentage_cc_wise
	
	@frappe.whitelist()
	def get_expense_details_from_project_budget(self):
		project_budget_doc = frappe.get_doc("Project Budget", self.project_budget)
		expense_details_list = []
		print(type(project_budget_doc.particulars_for_expenses))
		print(project_budget_doc.particulars_for_expenses,"===")
		if len(project_budget_doc.particulars_for_expenses) > 0:
			for row in project_budget_doc.particulars_for_expenses:
				expense_row = {}
				expense_row["description"] = row.description
				expense_row["propsoed_utilization"] = row.propsoed_utilization
				expense_row["cost_center"] = row.cost_center
				expense_details_list.append(expense_row)
		return expense_details_list