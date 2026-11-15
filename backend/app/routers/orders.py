import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import CURRENCY, FRONTEND_URL, STRIPE_SECRET_KEY
from ..db import get_conn
from ..security import current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])


def restock_and_cancel(conn, order_id: int) -> None:
    """Compensating transaction: give the reserved stock back and mark the order cancelled."""
    conn.execute(
        """UPDATE products p SET stock = p.stock + oi.quantity
           FROM order_items oi WHERE oi.order_id = %s AND oi.product_id = p.id""", (order_id,)
    )
    conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s", (order_id,))


@router.post("/checkout")
def checkout(user=Depends(current_user), conn=Depends(get_conn)):
    # ---- ACID transaction: lock rows, check stock, create order, decrement stock, empty cart ----
    lines = conn.execute(
        """SELECT p.id, p.name, p.price_cents, p.stock, ci.quantity
           FROM carts c
           JOIN cart_items ci ON ci.cart_id = c.id
           JOIN products p    ON p.id = ci.product_id
           WHERE c.user_id = %s AND p.is_active
           ORDER BY p.id                       -- consistent lock order prevents deadlocks
           FOR UPDATE OF p""", (user["id"],)   # row-level lock: two shoppers can't buy the last item
    ).fetchall()
    if not lines:
        raise HTTPException(400, "Your cart is empty.")
    for ln in lines:
        if ln["quantity"] > ln["stock"]:
            raise HTTPException(409, f"Only {ln['stock']} left of “{ln['name']}”. Update your cart and try again.")

    order = conn.execute("INSERT INTO orders (user_id) VALUES (%s) RETURNING id", (user["id"],)).fetchone()
    oid = order["id"]
    for ln in lines:
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (%s, %s, %s, %s)",
            (oid, ln["id"], ln["quantity"], ln["price_cents"]),
        )
        conn.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (ln["quantity"], ln["id"]))
    conn.execute("DELETE FROM cart_items WHERE cart_id = (SELECT id FROM carts WHERE user_id = %s)", (user["id"],))
    conn.commit()

    # ---- Payment ----
    if not STRIPE_SECRET_KEY:  # demo mode: no Stripe key configured
        conn.execute("UPDATE orders SET status = 'paid', paid_at = now() WHERE id = %s", (oid,))
        conn.commit()
        return {"order_id": oid, "checkout_url": f"{FRONTEND_URL}/orders/success?order_id={oid}&demo=1"}

    try:
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "quantity": ln["quantity"],
                "price_data": {"currency": CURRENCY, "unit_amount": ln["price_cents"],
                               "product_data": {"name": ln["name"]}},
            } for ln in lines],
            customer_email=user["email"],
            success_url=f"{FRONTEND_URL}/orders/success?order_id={oid}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/orders",
            metadata={"order_id": str(oid)},
        )
    except Exception as exc:  # Stripe is down / key is wrong -> undo the reservation
        restock_and_cancel(conn, oid)
        conn.commit()
        raise HTTPException(502, f"Payment provider error: {getattr(exc, 'user_message', None) or exc}")

    conn.execute("UPDATE orders SET stripe_session_id = %s WHERE id = %s", (session.id, oid))
    conn.commit()
    return {"order_id": oid, "checkout_url": session.url}


class ConfirmIn(BaseModel):
    session_id: str


@router.post("/confirm")
def confirm(body: ConfirmIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Called by the success page: asks Stripe whether the session was actually paid."""
    order = conn.execute(
        "SELECT id, status FROM orders WHERE stripe_session_id = %s AND user_id = %s",
        (body.session_id, user["id"]),
    ).fetchone()
    if not order:
        raise HTTPException(404, "Order not found.")
    if order["status"] == "pending":
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(body.session_id)
        if session.payment_status == "paid":
            conn.execute("UPDATE orders SET status = 'paid', paid_at = now() WHERE id = %s", (order["id"],))
            conn.commit()
            return {"order_id": order["id"], "status": "paid"}
    return {"order_id": order["id"], "status": order["status"]}


@router.post("/{order_id}/cancel")
def cancel(order_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    order = conn.execute(
        "SELECT status FROM orders WHERE id = %s AND user_id = %s FOR UPDATE", (order_id, user["id"])
    ).fetchone()
    if not order:
        raise HTTPException(404, "Order not found.")
    if order["status"] != "pending":
        raise HTTPException(409, "Only unpaid orders can be cancelled.")
    restock_and_cancel(conn, order_id)
    conn.commit()
    return {"order_id": order_id, "status": "cancelled"}


@router.get("")
def my_orders(user=Depends(current_user), conn=Depends(get_conn)):
    orders = conn.execute(
        "SELECT id, status, total_cents, created_at FROM orders WHERE user_id = %s ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    if not orders:
        return []
    items = conn.execute(
        """SELECT oi.order_id, oi.quantity, oi.unit_price_cents, p.id AS product_id, p.name, p.image_path
           FROM order_items oi JOIN products p ON p.id = oi.product_id
           WHERE oi.order_id = ANY(%s)""", ([o["id"] for o in orders],)
    ).fetchall()
    by_order: dict[int, list] = {}
    for it in items:
        it["image_url"] = f"/media/{it.pop('image_path')}"
        by_order.setdefault(it["order_id"], []).append(it)
    for o in orders:
        o["items"] = by_order.get(o["id"], [])
    return orders
