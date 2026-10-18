# Synthetic test set

144 made-up fixed-asset schedules, each with an answer key. We use them to score our agent before the
organisers do. Everything is invented: companies, assets and figures.

## Why we made it

The organisers gave us 72 sample documents in 10 layouts. Their final test uses **layouts nobody has seen**.
If we only test on their 72, we can't tell whether the agent really understands schedules or has just learned
those 10 layouts. So we generate new layouts ourselves and test on those.

## What's in here

| Folder or file | What it is |
|---|---|
| `dev/` | 72 documents we may look at, debug on and tune against |
| `holdout/` | 72 documents we **only score on and never look at** while building. They stand in for the hidden test. |
| `*.pdf` / `*.xlsx` | the document the agent reads |
| `*.key.json` | the answer key: every amount in cents, where it is printed (page and box, or cell), and any planted problem |
| `documents.csv` | one line per document: kind, format, size, problems, and a one-line summary of what makes it different |
| `flags.csv` | one line per difference, e.g. `dev_014, orientation, portrait` or `dev_014, number_style, (1.234,56) for negatives` |

Both halves have the same mix:

| | per half |
|---|---|
| Anlagenspiegel (gross, per asset) | 22 |
| Anlagengitter (per class) | 20 |
| Anlagenverzeichnis (asset register) | 20 |
| Anlagenspiegel, net (book values only) | 10 |
| Text PDF / scan / Excel / outline PDF | 22 / 22 / 16 / 12 |
| Scans: light / medium / heavy | 7 / 8 / 7 |

## What changes from document to document

**1. The layout (every document).** The same kind of information, laid out differently each time:
- which columns there are and in what order (for example book values first, or depreciation before cost)
- what the column headers say ("Zugänge", "Zugang 2025", "+ Zugänge" …), on one or two lines, with or without
  a group header above them
- how numbers look: `1.234,56`, `1234,56`, `1.234,56-`, `(1.234,56)` or `1,234.56`; zero as `0,00`, blank or `-`;
  whether disposals and depreciation are printed with a minus
- how rows are grouped and summed: class headings, subtotals per class, account or balance-sheet position,
  a grand total or none, and what those sum lines are called
- font, font size, portrait or landscape, lines or no lines, page header and footer
- one year or two years in one file; euro or thousand euro

**2. The format.** The finished table is saved as one of:
- a **text PDF**, where the text can be copied
- an **Excel** file, sometimes with the numbers stored as text or the table shifted away from cell A1
- an **outline PDF**, which looks sharp but has no text to copy (every letter is drawn as a shape)
- a **scan**, an image of the printout, at one of three severities:
  - *light*: a clean office scan
  - *medium*: lower quality, tick marks beside rows, a highlighted row, sometimes a page upside down
  - *heavy*: low resolution or fax, strong tilt, stamps on the table, ticks on the figures, uneven lighting,
    a dark edge, sometimes a page turned sideways

**3. Planted problems (some documents).** The tricky things real hand-overs contain:
- a subtotal that doesn't add up (the agent should report it as printed and flag it)
- two numbers printed with no gap between them
- an asset name running onto a second line
- the column header only on the first page
- "Übertrag" carry-over lines at page breaks
- a cover letter, blank page or unrelated page mixed in
- on scans, values covered by a stamp or tick (flagged `obscured` in the key, because the agent may
  legitimately be unable to read them)

## How we know the answers are right

Every document passes the organisers' own checks (`datagen/check.py`):
- each row adds up: cost at start + additions − disposals ± transfers = cost at end, and the same for
  depreciation and book value
- every subtotal equals the sum of its rows, except the ones we broke on purpose
- every amount in a clean PDF is printed on the page the key says
- every Excel cell holds the value the key says
- scans and outline PDFs have no copyable text

## Rebuilding it

```bash
.venv/bin/python datagen/build_testset.py synthetic_testset
.venv/bin/python datagen/check.py synthetic_testset
```

Same command, same files, byte for byte. Outline PDFs need Ghostscript (`brew install ghostscript`). The code is in
`datagen/`, built on the organisers' generator, which we did not change.

## Numbers

| | dev | holdout | organisers' sample |
|---|---|---|---|
| Documents | 72 | 72 | 72 |
| Amount values | about 33,000 | about 31,000 | about 36,000 |
