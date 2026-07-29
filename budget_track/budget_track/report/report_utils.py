# Copyright (c) 2026, GreyCube Technologies and contributors
# For license information, please see license.txt

import frappe


def get_cost_center_bucket_map(top_cost_centers, company):
	"""Map every cost center in the company to whichever of top_cost_centers is its ancestor
	(or itself), using the same lft/rgt tree containment ERPNext's general ledger report uses
	to expand a cost center filter to its full subtree. Used to batch gl_execute() calls across
	several cost centers at once and still attribute each returned GL entry to the right bucket."""
	if not top_cost_centers:
		return {}

	top_ranges = frappe.get_all(
		"Cost Center", filters={"name": ["in", top_cost_centers]}, fields=["name", "lft", "rgt"]
	)
	all_ccs = frappe.get_all("Cost Center", filters={"company": company}, fields=["name", "lft", "rgt"])

	bucket_map = {}
	for cc in all_ccs:
		for top in top_ranges:
			if top.lft <= cc.lft and cc.rgt <= top.rgt:
				bucket_map[cc.name] = top.name
				break
	return bucket_map
