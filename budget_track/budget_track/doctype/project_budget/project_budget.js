// Copyright (c) 2025, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project Budget", {
	setup(frm) {

        frm.set_query("parent_cost_center_for_project", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":1
                },
            }
        })

        frm.set_query("grant_ledger_account", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":0
                },
            }
        })

        frm.set_query("overhead_cost_center", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":0
                },
            }
        })

        frm.set_query("cost_center" , "particulars_for_expenses", function(doc){
            return {
                filters: {
                    "company": doc.company,
                    "is_group":0
                },
            }
        })

        
	},

    refresh(frm) {
        frappe.db.get_list("Fiscal Year Wise Project Budget Allocation", {
            fields: ['project_budget'],
            filters: {
            project_budget: frm.doc.name
            }
        })
        .then(exists => {
            if (exists) { 
                frm.add_custom_button(__("Check Allocation"), function() {
                    frappe.set_route("query-report", "Check Budget Allocation", { "project_budget": frm.doc.name });
                    frm.reload_doc()
                });
            }
        })
    },

    onload_post_render(frm){
        frappe.db.get_value("Company",frm.doc.company,"custom_default_budget_expense_account")
        .then(r => {
            console.log(r.message.custom_default_budget_expense_account,"===",frm.doc.company)
            if (r.message.custom_default_budget_expense_account == null || r.message.custom_default_budget_expense_account == ""){
                frappe.throw(__("Please set Company Default Expense Account in Company Doctype"))
            } else {
                console.log("IN ELSE")
                frm.set_query("description", "particulars_for_expenses", function(doc){
                return {
                    filters: {
                        "company": frm.doc.company,
                        "parent_account":r.message.custom_default_budget_expense_account,
                        "is_group":0
                    },
                }
            })
            }
        })
    },

    fetch_cost_centers(frm) {
        frm.set_value("particulars_for_expenses", "");
        frm.call("fetch_cost_centers").then((r) => {
            console.log(r.message)
            let cost_center_list = r.message
            cost_center_list.forEach((e) => {
                var d = frm.add_child("particulars_for_expenses");
                frappe.model.set_value(d.doctype, d.name, "cost_center", e.name)
            });
            refresh_field("particulars_for_expenses");
        });
    },

    startup_investment(frm) {
        calculate_total_budget(frm)
    },

    capex(frm) {
        calculate_total_budget(frm)
    },

    total_expenses(frm) {
        calculate_total_budget(frm)
    },

    validate(frm) {
        calculate_percentage_allocation_for_expenses(frm)
    }


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

let calculate_total_budget = function (frm) {
    let total_budget = (frm.doc.startup_investment || 0) + (frm.doc.capex || 0) + (frm.doc.total_expenses || 0)
    frm.set_value("total_budget", total_budget) 
}

let calculate_percentage_allocation_for_expenses = function (frm) {
    let total_expense = frm.doc.total_expenses || 0
    frm.doc.particulars_for_expenses.forEach(function(row) {
        percentage_of_expense = ( row.amount * 100 ) / total_expense
        frappe.model.set_value(row.doctype, row.name, "percentage_allocation", percentage_of_expense)
    })
}