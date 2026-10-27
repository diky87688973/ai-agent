**English** | [中文](applicability.zh.md)

# Standard applicability declarations

This repository currently declares **no non-applicable items**: every item in `production-standards.md` is applied as specified.
Exemptions are governed by the table rows below; anything not declared is applicable. A new exemption must include a reason and a risk bearer.

| Rule | Declaration | Reason | Risk bearer |
|---|---|---|---|

## Maintenance conventions

1. Only `MUST` / `SHOULD` items may be declared; items that are not declared remain in force.
2. The reason must be a self-contained sentence of at least 20 characters; writing only "this project does not need it" is not sufficient for a declaration.
3. The risk bearer is a specific role, or "none (the risk does not exist)"; an empty value is not accepted.
4. IDs are compared in both directions: an ID in this table that is outside the set in `scripts/standards_rules.py` is a stale declaration; an ID in the set that is not declared remains applicable. When the handbook version changes, update that set; the diff consists of ID additions and removals.
