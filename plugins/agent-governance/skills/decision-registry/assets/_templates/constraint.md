---
id: C-NNN
type: constraint
domain: internal          # internal | external
title: One sentence stating the boundary
force: binding            # binding | guidance | assumption
status: active            # active | superseded | retired
enforcement: skill        # retrieved | skill | resident | gated | code | eliminated
scope:
  regions: all            # all, or [EMEA, us-*]
  projects: all           # all, or [project-a, alpha-*]
  activities: [customer-email]   # from `activities` in schema.json
source: Where it comes from (document / meeting / who said it)
source_tier: policy-document   # see source_tier_by_domain in schema.json
acquisition: human_only   # public_source | held_copy | human_only | unrecorded
# exactly one companion field, depending on acquisition:
#   source_url / archive_ref / asked / reacquire
asked: Who was asked / when / in what setting
verified: YYYY-MM-DD
review_by: YYYY-MM-DD
consequence: What happens if it is crossed (one line, written for your future self)
evidence: []              # paths (relative to the notes root) to the long-form reasoning
hard_value: {}            # optional thresholds, e.g. {trigger_any: [{metric: max_open_incidents, op: "<=", value: 5, unit: count}]}
tags: []
---

## Boundary

(Body. Only the conclusion and when it applies; the reasoning lives in the evidence.)

## Still unclear

(Be honest. Write "nothing" if nothing.)
