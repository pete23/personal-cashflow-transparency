# Vendored front-end libraries

Served by `cashflow serve` so the pivot UI works offline and loads nothing from third parties.
All are MIT licensed and stay under their own licences, not the project's GPLv3. Each licence file is kept
alongside and must ship with the libraries; the minified PivotTable.js and subtotal.js carry no header of their own.

| File | Package | Licence | Source |
|---|---|---|---|
| `pivot.min.js`, `pivot.min.css` | pivottable 2.23.0 | MIT, `LICENSE-pivottable.md` | https://cdn.jsdelivr.net/npm/pivottable@2.23.0/dist/ |
| `subtotal.min.js`, `subtotal.min.css` | subtotal 1.11.0-alpha.0 (npm `latest`) | MIT, `LICENSE-subtotal.txt` | https://cdn.jsdelivr.net/npm/subtotal@1.11.0-alpha.0/dist/ |
| `jquery.min.js` | jquery 3.7.1 | MIT, `LICENSE-jquery.txt` | https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/ |
| `jquery-ui.min.js` | jquery-ui 1.13.2 (drag and drop for pivottable) | MIT, `LICENSE-jquery-ui.txt` | https://cdn.jsdelivr.net/npm/jquery-ui@1.13.2/dist/ |

To upgrade, replace the files from the new version's `dist/` and update this table.
