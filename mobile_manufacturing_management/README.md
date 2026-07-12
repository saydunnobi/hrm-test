# Mobile Manufacturing & IMEI Quality Management — Odoo 19

A custom Odoo 19 module that combines the requested mobile manufacturing flow in one application menu while reusing Odoo's standard Inventory and Manufacturing records.

## Included workflow

1. Raw material receipt into **Incoming Raw Material QC**.
2. Incoming IE/QC with accepted and rejected quantities.
3. Accepted stock moves to **Raw Material Store**; failed stock moves to **Raw Material Rejected**.
4. Production Material Requisition based on a Bill of Materials.
5. Approval creates an internal material issue from Raw Material Store to Production Input.
6. After storekeeper validates the issue, the module creates a standard Odoo Manufacturing Order.
7. Pre-IMEI Production QC is performed while the MO remains open.
8. Failed production QC creates a batch rework order and returns to re-test.
9. Passed production QC enables automatic generation, pasted list, or CSV import of IMEI numbers.
10. IMEI 1 is the Odoo serial number/barcode; optional IMEI 2 is stored on the same device.
11. The standard MO is completed with all IMEI serials assigned.
12. QC Stage 1 is performed by scanning the IMEI barcode.
13. QC 1 Pass moves the device to QC Stage 2; Fail moves it to Rework.
14. Rework can record and consume replacement components from Raw Material Store, then moves the same IMEI back to its failed QC stage.
15. QC Stage 2 Pass moves the device to Packaging; Fail returns it to Rework.
16. Packaging scans IMEIs into a box. Capacity is dynamic; default is 20.
17. **Close Box & Print IMEI List** creates an Odoo package, transfers all devices to Finished Goods, and opens a PDF listing the scanned IMEIs.

## Important implementation decision

Odoo requires serial numbers to be assigned before a serial-tracked Manufacturing Order can be closed. Therefore, the module treats "production complete" as physical production complete while the MO is still open. The pre-IMEI QC is completed, IMEIs are assigned, and only then is the MO marked Done. This preserves standard Odoo stock valuation and serial traceability.

## Dependencies

- `mail`
- `mrp`
- `stock`
- `barcodes`

The module implements its own QC and rework objects, so it does not require the Enterprise Quality app. A USB/Bluetooth scanner that sends the barcode as keyboard input works with Odoo's `barcode_handler` widget.

## Installation

1. Copy the `mobile_manufacturing_management` folder into an Odoo 19 custom addons directory.
2. Restart Odoo.
3. Enable Developer Mode.
4. Apps → Update Apps List.
5. Search for **Mobile Manufacturing & IMEI Quality Management** and install it.
6. Assign users one of these access levels:
   - Mobile Manufacturing / User
   - Mobile Manufacturing / Quality Inspector
   - Mobile Manufacturing / Manager

## Initial configuration

1. Open **Mobile Manufacturing → Configuration → Manufacturing Setup**.
2. Create a record and select the warehouse.
3. Set the official 8-digit TAC prefix used for IMEI generation.
4. Set Box Capacity, e.g. 20.
5. Click **Create/Link Locations**.
6. Confirm that the module created/linked:
   - Incoming Raw Material QC
   - Raw Material Store
   - Raw Material Rejected
   - Production Input
   - Device QC Stage 1
   - Device QC Stage 2
   - Rework
   - Packaging
   - Finished Goods
   - Device Rejected Hold

## Product and BoM preparation

- Finished mobile product:
  - Product type: Goods / Storable
  - Tracking: By Unique Serial Number
  - Route: Manufacture
- Raw materials and packaging materials must be storable products.
- Create the normal Odoo Bill of Materials and manufacturing operations.
- Configure Buy/reordering routes on purchased components. The module does not replace Odoo procurement rules. Material requisition approval is blocked until the Raw Material Store has the required available quantity.

## IMEI CSV format

Single SIM:

```csv
imei1
356789120000011
356789120000029
```

Dual SIM:

```csv
imei1,imei2
356789120000011,356789120000037
356789120000029,356789120000045
```

The sample file `sample_imei_import.csv` is included.

## IMEI validation

- Exactly 15 numeric digits.
- Optional Luhn check digit validation.
- IMEI 1 and IMEI 2 cannot be identical.
- Duplicate values are blocked across IMEI 1, IMEI 2, Odoo serial numbers, and device registry records.
- Automatic IMEI generation uses: `TAC (8) + sequence (6) + Luhn digit (1)`.

**Do not use the default demonstration TAC for commercial devices. Replace it with an officially allocated TAC.**

## Packaging and printing

The final scan makes a box Ready when the scanned quantity reaches Box Capacity. Because a server-side onchange cannot safely force the browser to download/print a PDF, the operator clicks **Close Box & Print IMEI List**. That single action:

- validates the Finished Goods transfer,
- assigns an Odoo package,
- marks devices Packed,
- and returns the printable IMEI PDF.

Direct silent printing requires Odoo IoT/PrintNode or a site-specific browser/IoT integration and is intentionally not hard-coded into this module.

## Upgrade/testing warning

This package has been statically validated for Python syntax and XML structure, but it has not been executed against your exact Odoo database, custom modules, routes, access rules, barcode hardware, or Odoo.sh branch. Install it first on a development/UAT database and test the complete flow before production use.

Recommended UAT cases:

- full raw QC pass;
- partial raw QC rejection;
- tracked raw material with lots/serials;
- insufficient stock during material issue;
- production QC fail and re-test;
- auto IMEI generation;
- valid and invalid CSV import;
- duplicate IMEI;
- QC 1 fail → rework → QC 1;
- QC 2 fail → rework → QC 2;
- wrong-stage barcode scan;
- full box and partial box;
- Finished Goods package and PDF output;
- multi-company access.
