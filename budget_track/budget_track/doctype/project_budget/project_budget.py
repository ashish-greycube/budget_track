# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProjectBudget(Document):

	def validate(self):
		# if self.startup_investment and self.capex and self.total_expenses and self.overhead_percentage:
		# overhead_amount = ((self.total_budget or 0) * (self.overhead_percentage or 0) ) / 100
		# percentage_without_overhead = 100 - (self.overhead_percentage or 0)
		self.total_budget = (self.startup_investment or 0) + (self.total_expenses or 0) + (self.capex or 0) + (self.overhead_amount or 0)

		expenase_percentage = ( (self.total_expenses or 0) * 100 ) / (self.total_budget or 0)
		capex_percentage = ( (self.capex or 0) * 100 ) / (self.total_budget or 0)
		investment_percentage = ( (self.startup_investment or 0) * 100 ) / (self.total_budget or 0)
		overhead_percentage = ( (self.overhead_amount or 0) * 100 ) / (self.total_budget or 0)

		self.startup_investment_percentage = investment_percentage
		self.capex_percentage = capex_percentage
		self.expense_percentage = expenase_percentage
		self.overhead_percentage = overhead_percentage

		if len(self.particulars_for_expenses)>0:
			for row in self.particulars_for_expenses:
				expense_percentage_cc_wise = ( row.amount * 100 ) / self.total_expenses
				row.percentage_allocation = expense_percentage_cc_wise
	
	@frappe.whitelist()
	def fetch_cost_centers(self):
		if self.parent_cost_center_for_project:
			child_cost_centers = frappe.get_all("Cost Center",
				filters={
					"parent_cost_center": self.parent_cost_center_for_project,
					"company": self.company
				},
				fields=["name"])
			return child_cost_centers
