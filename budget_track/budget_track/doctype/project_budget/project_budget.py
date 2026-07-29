# Copyright (c) 2025, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProjectBudget(Document):

	def validate(self):
		self.total_budget = (self.total_expenses or 0) + (self.overhead_amount or 0)

		if self.total_budget>0:
			expenase_percentage = ( (self.total_expenses or 0) * 100 ) / (self.total_budget or 0)
			overhead_percentage = ( (self.overhead_amount or 0) * 100 ) / (self.total_budget or 0)

			self.expense_percentage = expenase_percentage
			self.overhead_percentage = overhead_percentage

		if len(self.particulars_for_expenses)>0:
			for row in self.particulars_for_expenses:
				expense_percentage_cc_wise = ( row.amount * 100 ) / self.total_expenses
				if row.cost_center == self.overhead_cost_center:
					frappe.throw("Row #{0} : You cannot select cost center <b>{1}</b> for Expenses".format(row.idx, self.overhead_cost_center))
				row.percentage_allocation = expense_percentage_cc_wise
				for child_row in self.particulars_for_expenses:
					if child_row.description == row.description and row.idx!=child_row.idx:
						print(child_row.idx)
						if child_row.cost_center == row.cost_center:
							frappe.throw("Row {0}: You cannot select expense account <b>{1}</b> for cost center <b>{2}</b> again.".format(child_row.idx, child_row.description, child_row.cost_center))
	
	@frappe.whitelist()
	def fetch_cost_centers(self):
		if self.parent_cost_center_for_project:
			child_cost_centers = frappe.get_all("Cost Center",
				filters={
					"parent_cost_center": self.parent_cost_center_for_project,
					"company": self.company,
					"name": ["!=", self.overhead_cost_center]
				},
				fields=["name"])
			return child_cost_centers
