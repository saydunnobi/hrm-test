from collections import defaultdict

from odoo import _
from odoo.exceptions import UserError


def create_stock_picking(
    env,
    *,
    picking_type,
    source_location,
    destination_location,
    lines,
    origin,
    company,
    partner=None,
    auto_validate=True,
    result_package=None,
):
    """Create and optionally validate an Odoo 19 stock picking.

    Normalized line keys:
      product: required ``product.product`` record
      quantity: required quantity in ``uom``
      uom: optional ``uom.uom`` record (defaults to product UoM)
      lot: optional ``stock.lot`` record
      description: optional move description

    Internal-source availability is checked before any movement is created.
    Tracked products require a lot/serial, and a serial line must represent one
    product unit. These restrictions keep IMEI movements auditable.
    """
    if not lines:
        raise UserError(_("There are no stock movement lines to process."))
    if not picking_type:
        raise UserError(_("No operation type is configured."))
    if not source_location or not destination_location:
        raise UserError(_("Source and destination locations are required."))

    normalized = []
    required_by_product_lot = defaultdict(float)
    for item in lines:
        product = item["product"]
        quantity = float(item["quantity"])
        uom = item.get("uom") or product.uom_id
        lot = item.get("lot")
        if quantity <= 0:
            continue
        if product.tracking != "none" and not lot:
            raise UserError(_(
                "Lot/Serial Number is required for tracked product %s.",
                product.display_name,
            ))
        quantity_product_uom = uom._compute_quantity(
            quantity,
            product.uom_id,
            round=False,
        )
        if product.tracking == "serial" and product.uom_id.compare(quantity_product_uom, 1.0) != 0:
            raise UserError(_(
                "Serial-tracked product %s must be moved one unit per serial line.",
                product.display_name,
            ))
        normalized.append({
            **item,
            "product": product,
            "quantity": quantity,
            "uom": uom,
            "lot": lot,
        })
        if source_location.usage == "internal":
            required_by_product_lot[(product, lot)] += quantity_product_uom

    if not normalized:
        raise UserError(_("Every stock movement line has zero quantity."))

    if source_location.usage == "internal":
        Quant = env["stock.quant"]
        for (product, lot), required in required_by_product_lot.items():
            available = Quant._get_available_quantity(
                product,
                source_location,
                lot_id=lot,
                strict=False,
            )
            if product.uom_id.compare(available, required) < 0:
                raise UserError(_(
                    "Insufficient stock for %(product)s in %(location)s. Required: %(required)s; available: %(available)s.",
                    product=product.display_name,
                    location=source_location.display_name,
                    required=required,
                    available=available,
                ))

    picking = env["stock.picking"].create({
        "picking_type_id": picking_type.id,
        "location_id": source_location.id,
        "location_dest_id": destination_location.id,
        "origin": origin,
        "partner_id": partner.id if partner else False,
        "company_id": company.id,
    })

    move_specs = []
    for item in normalized:
        product = item["product"]
        move = env["stock.move"].create({
            "name": item.get("description") or product.display_name,
            "product_id": product.id,
            "product_uom_qty": item["quantity"],
            "product_uom": item["uom"].id,
            "location_id": source_location.id,
            "location_dest_id": destination_location.id,
            "picking_id": picking.id,
            "company_id": company.id,
            "origin": origin,
        })
        move_specs.append((move, item))

    picking.action_confirm()
    picking.action_assign()

    for move, item in move_specs:
        quantity = item["quantity"]
        lot = item["lot"]
        if lot:
            # Reservation may have created generic lines. Rebuild them with the
            # exact serial/lot requested by the business record.
            move.move_line_ids.filtered(lambda ml: ml.state != "done").unlink()
            env["stock.move.line"].create({
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": move.product_id.id,
                "product_uom_id": move.product_uom.id,
                "quantity": quantity,
                "lot_id": lot.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "company_id": company.id,
                "picked": True,
                "result_package_id": result_package.id if result_package else False,
            })
            move.picked = True
        else:
            # In Odoo 19, move.quantity is the picked quantity. Its inverse
            # creates/updates move lines for non-tracked products.
            move.quantity = quantity
            move.picked = True
            if result_package and move.move_line_ids:
                move.move_line_ids.result_package_id = result_package.id

    if auto_validate:
        # Avoid an interactive backorder wizard; all requested quantities were
        # populated above and availability was checked before creation.
        picking.with_context(skip_backorder=True).button_validate()
        if picking.state != "done":
            raise UserError(_(
                "The transfer %s could not be validated automatically. Open it and review the operation.",
                picking.display_name,
            ))
    return picking


def group_untracked_lines(lines):
    """Group untracked stock specs by product/UoM and retain tracked lines."""
    grouped = defaultdict(float)
    result = []
    for item in lines:
        product = item["product"]
        if product.tracking == "none" and not item.get("lot"):
            uom = item.get("uom") or product.uom_id
            grouped[(product, uom)] += float(item["quantity"])
        else:
            result.append(item)
    for (product, uom), quantity in grouped.items():
        result.append({"product": product, "uom": uom, "quantity": quantity})
    return result
