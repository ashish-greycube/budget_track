// Copyright (c) 2025, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fiscal Year Wise Project Budget Allocation", {

    setup(frm) {
        frm.set_query("cost_center" , "particulars_for_expenses", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":0
                },
            }
        })

        frm.set_query("description", "particulars_for_expenses", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":0
                },
            }
        })
    },
	project_budget(frm) {
        frm.set_value("particulars_for_expenses", "");
        
        if(frm.doc.project_budget) {
            frm.call("get_expense_details_from_project_budget").then(
            r => {
                let expense_details = r.message

                expense_details.forEach(element => {
                    var d = frm.add_child("particulars_for_expenses")
                    frappe.model.set_value(d.doctype, d.name, "description", element.description)
                    frappe.model.set_value(d.doctype, d.name, "propsoed_utilization", element.propsoed_utilization)
                    frappe.model.set_value(d.doctype, d.name, "cost_center", element.cost_center)
                });

                frm.refresh_fields("particulars_for_expenses")
            })
        }
	},
});

frappe.ui.form.on("Particulars for Expenses", {
    amount(frm, cdt, cdn) {
        calculate_total_expenses(frm, cdt, cdn)
    },
    particulars_for_expenses_remove(frm, cdt, cdn) {
        calculate_total_expenses(frm, cdt, cdn)
    }

})

let calculate_total_expenses = function (frm, cdt, cdn) {
    let total_expense = 0
    frm.doc.particulars_for_expenses.forEach(function(row) {
        total_expense = total_expense + (row.amount || 0)
    })

    frm.set_value("total_expenses", total_expense)
}