"""Per-group shop products and atomic redemption orders."""

from dataclasses import dataclass
from uuid import uuid4

from .common import account_balance, apply_change, ensure_account, iso_time
from .database import EconomyDatabase
from .errors import EconomyError


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    description: str
    price: int
    stock: int | None
    enabled: bool


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    product_name: str
    quantity: int
    total_price: int
    balance: int

    @property
    def short_id(self) -> str:
        return self.order_id[:8]


def _product_from_row(row) -> Product:
    return Product(
        product_id=row["id"],
        name=row["name"],
        description=row["description"],
        price=row["price"],
        stock=row["stock"],
        enabled=bool(row["enabled"]),
    )


async def list_products(database: EconomyDatabase, group_id: int) -> list[Product]:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT id, name, description, price, stock, enabled FROM shop_products "
            "WHERE group_id = ? AND enabled = 1 ORDER BY id",
            (group_id,),
        )
        rows = await cursor.fetchall()
    return [_product_from_row(row) for row in rows]


async def create_product(
    database: EconomyDatabase,
    *,
    group_id: int,
    name: str,
    description: str,
    price: int,
    stock: int | None,
    created_by: int,
) -> Product:
    name = name.strip()
    description = description.strip()
    if not name or len(name) > 50:
        raise EconomyError("商品名称不能为空且不能超过50个字符。")
    if price <= 0:
        raise EconomyError("商品价格必须是正整数。")
    if stock is not None and stock < 0:
        raise EconomyError("商品库存不能是负数。")

    now = iso_time()
    try:
        async with database.transaction() as connection:
            cursor = await connection.execute(
                "INSERT INTO shop_products"
                "(group_id, name, description, price, stock, enabled, created_by, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (group_id, name, description, price, stock, created_by, now, now),
            )
            product_id = int(cursor.lastrowid)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise EconomyError("本群已经存在同名商品。") from exc
        raise
    return Product(product_id, name, description, price, stock, True)


async def update_product(
    database: EconomyDatabase,
    *,
    group_id: int,
    product_id: int,
    name: str,
    description: str,
    price: int,
    stock: int | None,
) -> Product:
    name = name.strip()
    if not name or len(name) > 50 or price <= 0 or (stock is not None and stock < 0):
        raise EconomyError("商品参数无效，请检查名称、价格和库存。")
    now = iso_time()
    try:
        async with database.transaction() as connection:
            result = await connection.execute(
                "UPDATE shop_products SET name = ?, description = ?, price = ?, stock = ?, "
                "updated_at = ? WHERE group_id = ? AND id = ?",
                (name, description.strip(), price, stock, now, group_id, product_id),
            )
            if result.rowcount != 1:
                raise EconomyError("没有找到这个商品。")
            cursor = await connection.execute(
                "SELECT id, name, description, price, stock, enabled FROM shop_products "
                "WHERE group_id = ? AND id = ?",
                (group_id, product_id),
            )
            row = await cursor.fetchone()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise EconomyError("本群已经存在同名商品。") from exc
        raise
    assert row is not None
    return _product_from_row(row)


async def set_product_enabled(
    database: EconomyDatabase,
    group_id: int,
    product_id: int,
    enabled: bool,
) -> None:
    async with database.transaction() as connection:
        result = await connection.execute(
            "UPDATE shop_products SET enabled = ?, updated_at = ? WHERE group_id = ? AND id = ?",
            (int(enabled), iso_time(), group_id, product_id),
        )
        if result.rowcount != 1:
            raise EconomyError("没有找到这个商品。")


async def redeem_product(
    database: EconomyDatabase,
    *,
    group_id: int,
    user_id: int,
    product_id: int,
    quantity: int,
    request_id: str,
) -> OrderResult:
    if quantity <= 0:
        raise EconomyError("兑换数量必须是正整数。")
    now = iso_time()
    async with database.transaction() as connection:
        duplicate = await connection.execute(
            "SELECT id FROM shop_orders WHERE request_id = ?",
            (request_id,),
        )
        if await duplicate.fetchone() is not None:
            raise EconomyError("这次兑换已经处理过了。")

        cursor = await connection.execute(
            "SELECT * FROM shop_products WHERE group_id = ? AND id = ?",
            (group_id, product_id),
        )
        product = await cursor.fetchone()
        if product is None or not product["enabled"]:
            raise EconomyError("商品不存在或已经下架。")
        if product["stock"] is not None and product["stock"] < quantity:
            raise EconomyError("商品库存不足。")

        total_price = int(product["price"]) * quantity
        await ensure_account(connection, group_id, user_id, now)
        if await account_balance(connection, group_id, user_id) < total_price:
            raise EconomyError("积分不足，无法兑换。")

        if product["stock"] is not None:
            await connection.execute(
                "UPDATE shop_products SET stock = stock - ?, updated_at = ? WHERE id = ?",
                (quantity, now, product_id),
            )
        order_id = uuid4().hex
        await connection.execute(
            "INSERT INTO shop_orders"
            "(id, group_id, user_id, product_id, product_name, unit_price, quantity, "
            "total_price, status, request_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                order_id,
                group_id,
                user_id,
                product_id,
                product["name"],
                product["price"],
                quantity,
                total_price,
                request_id,
                now,
            ),
        )
        balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=user_id,
            amount=-total_price,
            event_type="shop_redeem",
            reference_id=order_id,
            note=f"兑换商品：{product['name']} × {quantity}",
            now=now,
        )
    return OrderResult(order_id, product["name"], quantity, total_price, balance)


async def fulfill_order(
    database: EconomyDatabase,
    *,
    group_id: int,
    order_token: str,
    fulfilled_by: int,
) -> str:
    now = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT id, status FROM shop_orders WHERE group_id = ? AND id LIKE ? "
            "ORDER BY created_at DESC LIMIT 1",
            (group_id, f"{order_token.lower()}%"),
        )
        order = await cursor.fetchone()
        if order is None:
            raise EconomyError("没有找到这个订单。")
        if order["status"] != "pending":
            raise EconomyError("该订单已经处理过了。")
        await connection.execute(
            "UPDATE shop_orders SET status = 'fulfilled', fulfilled_at = ?, fulfilled_by = ? "
            "WHERE id = ?",
            (now, fulfilled_by, order["id"]),
        )
    return str(order["id"])


async def refund_order(
    database: EconomyDatabase,
    *,
    group_id: int,
    order_token: str,
) -> OrderResult:
    now = iso_time()
    async with database.transaction() as connection:
        cursor = await connection.execute(
            "SELECT * FROM shop_orders WHERE group_id = ? AND id LIKE ? "
            "ORDER BY created_at DESC LIMIT 1",
            (group_id, f"{order_token.lower()}%"),
        )
        order = await cursor.fetchone()
        if order is None:
            raise EconomyError("没有找到这个订单。")
        if order["status"] != "pending":
            raise EconomyError("只有待核销订单可以退款。")

        await connection.execute(
            "UPDATE shop_orders SET status = 'refunded', refunded_at = ? WHERE id = ?",
            (now, order["id"]),
        )
        stock_cursor = await connection.execute(
            "SELECT stock FROM shop_products WHERE id = ?",
            (order["product_id"],),
        )
        product = await stock_cursor.fetchone()
        if product is not None and product["stock"] is not None:
            await connection.execute(
                "UPDATE shop_products SET stock = stock + ?, updated_at = ? WHERE id = ?",
                (order["quantity"], now, order["product_id"]),
            )
        balance = await apply_change(
            connection,
            group_id=group_id,
            user_id=order["user_id"],
            amount=order["total_price"],
            event_type="shop_refund",
            reference_id=order["id"],
            note=f"商品订单退款：{order['product_name']}",
            now=now,
        )
    return OrderResult(
        order["id"],
        order["product_name"],
        order["quantity"],
        order["total_price"],
        balance,
    )
