---
marp: true
theme: gaia
paginate: true
size: 16:9
title: CarthAgents architecture
style: |
  section { font-family: Arial, sans-serif; background: #0d2333; color: #edf6fb; padding: 52px 60px; justify-content: flex-start; }
  h1 { font-size: 42px; font-weight: 700; letter-spacing: -1px; color: #edf6fb; margin: 0 0 16px; }
  p { font-size: 25px; line-height: 1.35; }
  strong { color: #6fe0c5; }
  img { display: block; margin: 25px auto 12px; max-width: 100%; }
  section::after { color: #8cafbe; font-size: 18px; }
---

# From unfamiliar reports to traceable values

**The model interprets layout. Code reads the amounts.**

![w:1120 h:350 Architecture](pitch-diagrams/flow.svg)

Source evidence stays attached through JSON, workbook and review.

---

# Capture evidence before assigning meaning

One Excel cell, three linked facts.

![w:1120 h:330 Evidence example](pitch-diagrams/evidence.svg)

**Stable handle · untouched source value · exact location**

Example fields from the native Excel evidence format.

---

# Map the meaning. Retrieve the amount.

A section rule maps column B across matching asset rows.

![w:1120 h:350 Mapping and execution](pitch-diagrams/mapping.svg)

**Preserve printed discrepancies. Abstain when evidence is missing.**

One example output; the section rule applies across the table.
