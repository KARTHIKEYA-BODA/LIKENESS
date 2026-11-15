from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from ..security import current_user
from ..services import product_json

router = APIRouter(prefix="/api/cart", tags=["cart"])


class AddIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=20)


class QtyIn(BaseModel):
    quantity: int = Field(ge=1, le=20)


def cart_id_for(conn, user_id: int) -> int:
    return conn.execute(
        """INSERT INTO carts (user_id) VALUES (%s)
           ON CONFLICT (user_id) DO UPDATE SET updated_at = now() RETURNING id""", (user_id,)
    ).fetchone()["id"]


def read_cart(conn, user_id: int) -> dict:
    rows = conn.execute(
        """SELECT p.id, p.name, p.price_cents, p.stock, p.image_path, ci.quantity
           FROM carts c
           JOIN cart_items ci ON ci.cart_id = c.id
           JOIN products p    ON p.id = ci.product_id
           WHERE c.user_id = %s AND p.is_active
           ORDER BY p.name""", (user_id,)
    ).fetchall()
    items = [product_json(r) for r in rows]
    return {
        "items": items,
        "count": sum(i["quantity"] for i in items),
        "total_cents": sum(i["quantity"] * i["price_cents"] for i in items),
    }


@router.get("")
def get_cart(user=Depends(current_user), conn=Depends(get_conn)):
    cart = read_cart(conn, user["id"])
    conn.commit()
    return cart


@router.post("/items")
def add_item(body: AddIn, user=Depends(current_user), conn=Depends(get_conn)):
    product = conn.execute("SELECT stock FROM products WHERE id = %s AND is_active", (body.product_id,)).fetchone()
    if not product:
        raise HTTPException(404, "Product not found.")
    if product["stock"] < 1:
        raise HTTPException(409, "This item is out of stock.")
    cid = cart_id_for(conn, user["id"])
    # UPSERT: add to the existing line, but never beyond the stock on hand
    conn.execute(
        """INSERT INTO cart_items (cart_id, product_id, quantity)
           VALUES (%(c)s, %(p)s, LEAST(%(q)s, %(stock)s))
           ON CONFLICT (cart_id, product_id)
           DO UPDATE SET quantity = LEAST(cart_items.quantity + %(q)s, %(stock)s)""",
        {"c": cid, "p": body.product_id, "q": body.quantity, "stock": product["stock"]},
    )
    cart = read_cart(conn, user["id"])
    conn.commit()
    return cart


@router.patch("/items/{product_id}")
def set_quantity(product_id: int, body: QtyIn, user=Depends(current_user), conn=Depends(get_conn)):
    stock = conn.execute("SELECT stock FROM products WHERE id = %s", (product_id,)).fetchone()
    if not stock:
        raise HTTPException(404, "Product not found.")
    conn.execute(
        """UPDATE cart_items SET quantity = LEAST(%s, %s)
           WHERE product_id = %s AND cart_id = (SELECT id FROM carts WHERE user_id = %s)""",
        (body.quantity, max(stock["stock"], 1), product_id, user["id"]),
    )
    cart = read_cart(conn, user["id"])
    conn.commit()
    return cart


@router.delete("/items/{product_id}")
def remove_item(product_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute(
        """DELETE FROM cart_items
           WHERE product_id = %s AND cart_id = (SELECT id FROM carts WHERE user_id = %s)""",
        (product_id, user["id"]),
    )
    cart = read_cart(conn, user["id"])
    conn.commit()
    return cart
