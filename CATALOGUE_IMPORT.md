# Try a synthetic catalogue update

Open **Manage products** → **Update products from CSV** in the local VEE app. In the original workspace, select **Try product updates** to create an isolated database. If you are already in a demo workspace, the import applies to that workspace. Use only fictional data.

1. Select **Review sample CSV**. The supplied file adds `BRG-6209-2RS`, updates `BRG-6206-ZZ` from 18 to 24 units and NZD 15.75 to 16.20 per unit, and retires `BRG-6202-ZZ`.
2. Expand a product to compare every field. A retired SKU is unavailable for new quotations. Products omitted from the CSV keep their current values.
3. Check **I have reviewed these changes** and select **Apply product changes**. The result shows the revision number. Returning to file selection before activation leaves the active catalogue intact.
4. Choose **Go to enquiries**, open **New enquiry** and enter `2 x BRG-6209-2RS` for Kauri Engineering. Verify the part and create a draft. At the sample list price of NZD 28.40, the two bearings total NZD 65.32 including NZD 8.52 GST. Availability is synthetic and delivery remains unconfirmed.
5. Select **Return to original workspace** when finished. Start another catalogue demo to repeat the sample from the bundled catalogue.

To try the upload control, choose **Download sample CSV**, expand **Upload a sample CSV**, choose the downloaded file, tick the fictional-data confirmation and select **Review uploaded CSV**. The released [synthetic catalogue sample](vee/fixtures/synthetic_catalogue.csv) is also available in the repository.

## File format

Use a comma-delimited UTF-8 CSV with one header and up to 100 product rows. File size is limited to 65,536 bytes (64 KiB). The browser accepts one `.csv` per upload. Quote fields containing commas using standard CSV quotes.

| Header, in order | Accepted value |
| --- | --- |
| `sku` | Unique uppercase reference with hyphen-separated letters or digits, up to 48 characters. Use the prefix for its family. |
| `family` | `Bearing` (BRG), `Pneumatic cylinder` (CYL), `Fastener` (BLT), or `Hydraulic adapter` (ADP). |
| `name` | Fictional display name. |
| `specs` | All required fields for the family, as `key=value` pairs separated by semicolons. Include units as shown below. |
| `status` | `active` or `discontinued`. Retire an existing SKU explicitly. |
| `stock` | Whole units from 0 through 999999. Blank means unknown. |
| `price_nzd` | NZD net unit list price with up to two decimal places, from 0 through 99999999.99. Blank means unknown. |

| Family | Example `specs` |
| --- | --- |
| Bearing | `bore=25 mm;outside diameter=52 mm;width=15 mm;closure=rubber seals` |
| Pneumatic cylinder | `bore=32 mm;stroke=100 mm;action=double acting;standard=ISO 15552;port=G1/8;mount=foot mount` |
| Fastener | `thread=M12;length=80 mm;pitch=1.75 mm;grade=8.8` |
| Hydraulic adapter | `thread=BSPP;size=1/4 in;pressure=250 bar;connection=male to male` |

Each supplied row describes the full product, including stock and price. A blank commercial field replaces an earlier known value with unknown. Existing customer pricing agreements continue to apply. A contract-only customer needs an explicit agreement for the SKU. The app assigns synthetic catalogue and commercial sources to changed products and ties them to the activated revision.

## Validation and recovery

A failed validation identifies the problem on the upload page. Correct the file and select it again. Review does not publish data. Opening the same pending file against the same revision returns its existing review. A previously activated file cannot publish a second copy.

If a second tab activates another revision first, select **Review a fresh file** and submit the CSV again. Its comparison will use the current records. The server checks the revision and applies all product changes in one SQLite transaction. A failed activation preserves the previously active catalogue. To correct a published value, import a compensating change as another revision.

Previously approved quote snapshots retain their recorded prices and quantities. For a pending enquiry with changed evidence, refresh the catalogue evidence and repeat the employee checks. Returning to an isolated demo after restarting the local app uses its saved revision while the workspace cookie selects it.
