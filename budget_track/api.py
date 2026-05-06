import frappe
from frappe import _
from frappe.utils import get_link_to_form

def set_prepared_report_zero(self, method):
    if self.report_name in ["Budget Vs Actual", "Budget Vs Actual ( Consolidated )"]:
        if self.prepared_report == 1:
            self.prepared_report = 0

def get_child_cash_account_of_company(company):
    cash_group_ledger = frappe.db.get_value("Company",company,"custom_receipt_against_account")
    if not cash_group_ledger:
        frappe.throw(_("Please set Receipt Against Account in company {0}".format(get_link_to_form("Company",company))))
    
    cash_non_group_accounts = frappe.db.get_all("Account",
                                                filters={"company":company,"is_group":0,"parent_account":cash_group_ledger},
                                                pluck="name")
    print(cash_non_group_accounts,"============")
    return cash_non_group_accounts
    