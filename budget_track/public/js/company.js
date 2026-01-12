frappe.ui.form.on("Company", {
    setup(frm) {
        frm.set_query("custom_default_budget_expense_account", function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        })
        frm.set_query("custom_default_budget_income_account", function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        })
        frm.set_query("custom_default_budget_capex_account", function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        })
        frm.set_query("custom_advance_to_employee", function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        })
        frm.set_query("custom_advance_to_vendor", function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        })

        cur_frm.fields_dict.custom_default_budget_group_ledger_for_investment.get_query = function (doc) {
            return {
                filters: {
                    "company": doc.name
                },
            }
        }
    }
})