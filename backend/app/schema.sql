-- =====================================================================
--  Likeness: visual-search store  |  PostgreSQL 16 + pgvector
--  Runs automatically the first time the Docker container starts.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- USERS ----------------------------------------------------
CREATE TABLE users (
    id             SERIAL PRIMARY KEY,
    supabase_user_id UUID UNIQUE,
    email          TEXT        NOT NULL,
    password_hash  TEXT        NOT NULL,
    full_name      TEXT        NOT NULL,
    role           TEXT        NOT NULL DEFAULT 'customer'
                               CHECK (role IN ('customer', 'admin')),
    auth_provider  TEXT        NOT NULL DEFAULT 'password'
                               CHECK (auth_provider IN ('password', 'google')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- case-insensitive uniqueness on e-mail
CREATE UNIQUE INDEX ux_users_email ON users (lower(email));

-- ---------- CATALOG --------------------------------------------------
CREATE TABLE categories (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    slug  TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    id           SERIAL PRIMARY KEY,
    category_id  INT         NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    name         TEXT        NOT NULL,
    description  TEXT        NOT NULL DEFAULT '',
    price_cents  INT         NOT NULL CHECK (price_cents >= 0),
    stock        INT         NOT NULL DEFAULT 0 CHECK (stock >= 0),   -- can never go negative
    image_path   TEXT        NOT NULL,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,                   -- soft delete keeps order history valid
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_products_category ON products (category_id);
CREATE INDEX ix_products_name_lower ON products (lower(name));

-- ---------- VECTOR STORE (1 row per product image) -------------------
-- CLIP ViT-B/32 produces 512-dimensional vectors.
CREATE TABLE product_embeddings (
    product_id  INT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    embedding   vector(512) NOT NULL,
    model_name  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Approximate nearest-neighbour index (HNSW) using cosine distance.
CREATE INDEX ix_embeddings_hnsw
    ON product_embeddings USING hnsw (embedding vector_cosine_ops);

-- ---------- CART -----------------------------------------------------
CREATE TABLE carts (
    id          SERIAL PRIMARY KEY,
    user_id     INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cart_items (
    cart_id     INT NOT NULL REFERENCES carts(id)    ON DELETE CASCADE,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity    INT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)                -- composite key: one line per product
);

-- ---------- ORDERS ---------------------------------------------------
CREATE TABLE orders (
    id                 SERIAL PRIMARY KEY,
    user_id            INT         NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status             TEXT        NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    total_cents        INT         NOT NULL DEFAULT 0 CHECK (total_cents >= 0),  -- maintained by trigger
    stripe_session_id  TEXT UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at            TIMESTAMPTZ
);
CREATE INDEX ix_orders_user ON orders (user_id, created_at DESC);

CREATE TABLE order_items (
    order_id         INT NOT NULL REFERENCES orders(id)   ON DELETE CASCADE,
    product_id       INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity         INT NOT NULL CHECK (quantity > 0),
    unit_price_cents INT NOT NULL CHECK (unit_price_cents >= 0),  -- price snapshot at purchase time
    PRIMARY KEY (order_id, product_id)
);

-- ---------- ANALYTICS ------------------------------------------------
CREATE TABLE search_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id)    ON DELETE SET NULL,
    top_product_id  INT REFERENCES products(id) ON DELETE SET NULL,
    top_similarity  REAL,
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
--  TRIGGERS
-- =====================================================================

-- 1) keep products.updated_at fresh
CREATE OR REPLACE FUNCTION fn_touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_products_touch
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- 2) orders.total_cents is derived data: recompute whenever order_items change
CREATE OR REPLACE FUNCTION fn_recalc_order_total() RETURNS trigger AS $$
DECLARE
    oid INT := COALESCE(NEW.order_id, OLD.order_id);
BEGIN
    UPDATE orders
       SET total_cents = (SELECT COALESCE(SUM(quantity * unit_price_cents), 0)
                            FROM order_items WHERE order_id = oid)
     WHERE id = oid;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_order_items_total
    AFTER INSERT OR UPDATE OR DELETE ON order_items
    FOR EACH ROW EXECUTE FUNCTION fn_recalc_order_total();

-- =====================================================================
--  VIEWS
-- =====================================================================
CREATE VIEW v_product_sales AS
SELECT p.id,
       p.name,
       p.stock,
       COALESCE(SUM(oi.quantity) FILTER (WHERE o.status IN ('paid','shipped')), 0)                       AS units_sold,
       COALESCE(SUM(oi.quantity * oi.unit_price_cents) FILTER (WHERE o.status IN ('paid','shipped')), 0) AS revenue_cents
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.id
LEFT JOIN orders      o  ON o.id = oi.order_id
GROUP BY p.id, p.name, p.stock;
