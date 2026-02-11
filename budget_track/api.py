import frappe
from frappe import _

def set_prepared_report_zero(self, method):
    if self.report_name in ["Budget Vs Actual", "Budget Vs Actual ( Consolidated )"]:
        if self.prepared_report == 1:
            self.prepared_report = 0