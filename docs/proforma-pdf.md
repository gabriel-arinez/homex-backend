# Approved HOMEX proforma PDF

`GET /api/v1/proformas/{id}/documento-pdf/` generates a fresh Letter PDF for the authenticated requesting user. Existing object visibility and seller permissions are unchanged. There is no signer parameter or generated-file cache.

## Data contract

- `renderizar_proforma_pdf(id, usuario=request.user)` requires an explicit authenticated actor. The requesting actor signs; `proforma.vendedor` and historical audit fields are never updated.
- Client snapshots take precedence over live client/prospect values. The company is the document recipient; the contact's stored names identify its representative. Historical companies without a contact leave that signature name blank, never substitute the company name or invent a representative. A user without first/last names is identified by their authenticated username.
- Line quantities retain stored precision. Negotiated lines display their persisted gross negotiated amount, not an invented unit price. Discounts are displayed only when nonzero. Line `total` and proforma `total` are read directly; no calculation updates commercial data.
- A persisted total inconsistent with the sum of persisted line totals is logged by record ID only. It is not repaired and the persisted header total remains the displayed amount. No production records are scanned or migrated by this change.
- The technical projection preserves original text, nonempty extensible fields, zero values, internal quantities of one, duplicate descriptive entries and stored array order. Set references determine component nesting; independent components remain visible. Internal association IDs do not appear as commercial text. Unknown descriptive fields are recursively labelled, never represented as raw JSON.
- Catalogue chairs/floors retain their available model properties and technical attributes without fabricated furniture sections. Units are taken from stored data or explicit model field names, never inferred from a bare measurement.

## Composition and privacy

`pdf_layout.ProductCard` measures and splits the specification column independently. Images occur once and remain centered in their accompanying fragment; continuation fragments reserve the same empty left column. The economic strip stays with final specification lines. Only the two signatures form an inseparable closing block; long specification/observation paragraphs remain splittable.

The existing HOMEX monogram, slogan and numbered institutional footer are retained. Bundled DejaVu Sans fonts (license in `apps/documentos/fonts/`) preserve Spanish and technical symbols, independent of host font installation. Package data includes these files.

Responses use `Cache-Control: private, no-store, max-age=0` and vary on authentication. The frontend fetches without browser-cache reuse and clears/revokes its shared preview/download/print Blob synchronously on actor changes. Pending responses from the previous actor are discarded.

## Verification

```bash
pytest apps/documentos/test_pdf_design.py --confcutdir=apps/documentos
pytest tests/api/test_pdf_request_actor.py tests/api/test_pdf_editorial.py
pytest
ruff check .
ruff format --check .
```

The pure rendering suite includes both approved complex furniture scenarios as isolated JSON fixtures, additional no-unit/zero/quantity-one/unknown-field cases, catalogue compatibility, negotiated currency, optional blocks and long pagination. Poppler `pdftotext`, when installed, also verifies text coordinates and first-page composition. Full database tests require a disposable PostgreSQL instance with permission to create the test database; never point them at production.

Render simple and multi-page test PDFs with `pdftoppm` and inspect every page before accepting visual changes. The fixtures are test data only and must never be loaded into actual quotations.

## Approved implementation validation

The implementation was independently checked in isolated copies against backend baseline `65271da` and frontend baseline `c87d23d`:

- Backend: 529 tests passed; Ruff lint and format checks passed.
- Frontend: 300 tests across 56 files passed; production build/typecheck passed.
- Browser: the real generated two-page PDF rendered through PDF.js; download bytes matched the displayed Blob; printing dispatched to the original PDF iframe without another PDF request.
- Font packaging: a built backend wheel contained both TTF files and the license.
- Visual inspection: simple one-page PDF, complete two-page executive desk/credenza, and extended three-page L-desk/rolling-cabinet document. Every page was rendered with Poppler and inspected; specification continuations stay on the right, totals use persisted amounts, and signatures remain together with 27 mm signing space.

The first isolated frontend runs lacked the documented API test origin and used an external dependency symlink; those setup failures were resolved without source changes. The final full frontend run used `VITE_API_BASE_URL=http://localhost:8000` and a dependency copy inside its isolated workspace. The browser run used a disposable loopback API origin with mocked responses. Database validation used a disposable PostgreSQL cluster; no historical quotation data was changed.
