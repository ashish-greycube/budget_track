import frappe
from frappe import _

def set_prepared_report_zero(self, method):
    if self.report_name == "Budget Vs Actual":
        if self.prepared_report == 1:
            self.prepared_report = 0