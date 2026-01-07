# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProjectBudget(Document):

	def validate(self):
		if self.startup_investment and self.capex and self.total_expenses and self.overhead_percentage:
			overhead_amount = (self.total_budget * self.overhead_percentage ) / 100
			percentage_without_overhead = 100 - self.overhead_percentage

			expenase_percentage = ( self.total_expenses * percentage_without_overhead ) / self.total_budget
			capex_percentage = ( self.capex * percentage_without_overhead ) / self.total_budget
			investment_percentage = ( self.startup_investment * percentage_without_overhead ) / self.total_budget

			self.overhead_amount = overhead_amount
			self.startup_investment_percentage = investment_percentage
			self.capex_percentage = capex_percentage
			self.expense_percentage = expenase_percentage
	
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
