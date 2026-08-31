"""Per-group point shop and owner/global-admin product management."""

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import Rule

from src.config import get_app_settings
from src.services.economy import EconomyError, get_economy_database
from src.services.economy.commands import (
    command_text,
    is_group_owner,
    message_request_id,
)
from src.services.economy.shop import (
    create_product,
    fulfill_order,
    list_products,
    redeem_product,
    refund_order,
    set_product_enabled,
    update_product,
)


def _rule(command: str):
    def matches(event: GroupMessageEvent) -> bool:
        return command_text(event, command) is not None

    return Rule(matches)


shop = on_message(rule=_rule("商店"), priority=10, block=True)
redeem = on_message(rule=_rule("兑换"), priority=10, block=True)
add_product = on_message(rule=_rule("添加商品"), priority=10, block=True)
edit_product = on_message(rule=_rule("修改商品"), priority=10, block=True)
enable_product = on_message(rule=_rule("上架商品"), priority=10, block=True)
disable_product = on_message(rule=_rule("下架商品"), priority=10, block=True)
fulfill = on_message(rule=_rule("核销订单"), priority=10, block=True)
refund = on_message(rule=_rule("退款订单"), priority=10, block=True)


def _require_manager(event: GroupMessageEvent) -> None:
    is_global_admin = event.user_id in get_app_settings().admin_ids
    if not is_group_owner(event) and not is_global_admin:
        raise EconomyError("只有群主或机器人管理员可以管理商品和订单。")


def _parse_stock(value: str) -> int | None:
    value = value.strip()
    if value in {"无限", "不限", "-"}:
        return None
    stock = int(value)
    if stock < 0:
        raise ValueError
    return stock


@shop.handle()
async def handle_shop(event: GroupMessageEvent) -> None:
    try:
        products = await list_products(get_economy_database(), event.group_id)
    except Exception:
        logger.exception("Shop listing failed")
        await shop.finish("商店查询失败，请稍后再试。")
    if not products:
        await shop.finish("本群商店暂时没有上架商品。")
    lines = ["本群积分商店："]
    for product in products:
        stock = "无限" if product.stock is None else str(product.stock)
        description = f"｜{product.description}" if product.description else ""
        lines.append(
            f"#{product.product_id} {product.name}｜{product.price}积分｜库存 {stock}{description}"
        )
    lines.append("发送：兑换 商品编号 [数量]")
    await shop.finish("\n".join(lines))


@redeem.handle()
async def handle_redeem(event: GroupMessageEvent) -> None:
    parts = (command_text(event, "兑换") or "").split()
    if not 1 <= len(parts) <= 2 or not all(part.isdigit() for part in parts):
        await redeem.finish("用法：兑换 商品编号 [数量]\n例如：兑换 1 2")
    try:
        result = await redeem_product(
            get_economy_database(),
            group_id=event.group_id,
            user_id=event.user_id,
            product_id=int(parts[0]),
            quantity=int(parts[1]) if len(parts) == 2 else 1,
            request_id=message_request_id(event, "shop-redeem"),
        )
    except EconomyError as exc:
        await redeem.finish(MessageSegment.at(event.user_id) + f" {exc}")
    except Exception:
        logger.exception("Product redemption failed")
        await redeem.finish("兑换失败，请稍后再试。")
    await redeem.finish(
        MessageSegment.at(event.user_id) + f" 兑换成功：{result.product_name} × {result.quantity}\n"
        f"消耗 {result.total_price} 积分，余额 {result.balance}\n订单号：{result.short_id}"
    )


@add_product.handle()
async def handle_add_product(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        parts = [part.strip() for part in (command_text(event, "添加商品") or "").split("|")]
        if len(parts) not in {3, 4}:
            raise EconomyError("用法：添加商品 名称|价格|库存|说明\n库存填“无限”表示不限。")
        product = await create_product(
            get_economy_database(),
            group_id=event.group_id,
            name=parts[0],
            price=int(parts[1]),
            stock=_parse_stock(parts[2]),
            description=parts[3] if len(parts) == 4 else "",
            created_by=event.user_id,
        )
    except (ValueError, EconomyError) as exc:
        await add_product.finish(str(exc) or "商品参数格式不正确。")
    except Exception:
        logger.exception("Product creation failed")
        await add_product.finish("添加商品失败，请稍后再试。")
    await add_product.finish(f"商品已添加：#{product.product_id} {product.name}")


@edit_product.handle()
async def handle_edit_product(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        parts = [part.strip() for part in (command_text(event, "修改商品") or "").split("|")]
        if len(parts) < 5:
            raise EconomyError("用法：修改商品 编号|名称|价格|库存|说明")
        product = await update_product(
            get_economy_database(),
            group_id=event.group_id,
            product_id=int(parts[0]),
            name=parts[1],
            price=int(parts[2]),
            stock=_parse_stock(parts[3]),
            description="|".join(parts[4:]),
        )
    except (ValueError, EconomyError) as exc:
        await edit_product.finish(str(exc) or "商品参数格式不正确。")
    except Exception:
        logger.exception("Product update failed")
        await edit_product.finish("修改商品失败，请稍后再试。")
    await edit_product.finish(f"商品已更新：#{product.product_id} {product.name}")


async def _handle_product_switch(
    event: GroupMessageEvent,
    command: str,
    enabled: bool,
    matcher,
) -> None:
    try:
        _require_manager(event)
        argument = (command_text(event, command) or "").strip()
        if not argument.isdigit():
            raise EconomyError(f"用法：{command} 商品编号")
        await set_product_enabled(get_economy_database(), event.group_id, int(argument), enabled)
    except EconomyError as exc:
        await matcher.finish(str(exc))
    except Exception:
        logger.exception("Product status update failed")
        await matcher.finish("商品状态修改失败，请稍后再试。")
    await matcher.finish("商品已上架。" if enabled else "商品已下架。")


@enable_product.handle()
async def handle_enable_product(event: GroupMessageEvent) -> None:
    await _handle_product_switch(event, "上架商品", True, enable_product)


@disable_product.handle()
async def handle_disable_product(event: GroupMessageEvent) -> None:
    await _handle_product_switch(event, "下架商品", False, disable_product)


@fulfill.handle()
async def handle_fulfill(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        token = (command_text(event, "核销订单") or "").strip()
        if len(token) < 4:
            raise EconomyError("用法：核销订单 订单号")
        order_id = await fulfill_order(
            get_economy_database(),
            group_id=event.group_id,
            order_token=token,
            fulfilled_by=event.user_id,
        )
    except EconomyError as exc:
        await fulfill.finish(str(exc))
    except Exception:
        logger.exception("Order fulfillment failed")
        await fulfill.finish("核销失败，请稍后再试。")
    await fulfill.finish(f"订单 {order_id[:8]} 已核销。")


@refund.handle()
async def handle_refund(event: GroupMessageEvent) -> None:
    try:
        _require_manager(event)
        token = (command_text(event, "退款订单") or "").strip()
        if len(token) < 4:
            raise EconomyError("用法：退款订单 订单号")
        result = await refund_order(
            get_economy_database(), group_id=event.group_id, order_token=token
        )
    except EconomyError as exc:
        await refund.finish(str(exc))
    except Exception:
        logger.exception("Order refund failed")
        await refund.finish("退款失败，请稍后再试。")
    await refund.finish(
        f"订单 {result.short_id} 已退款 {result.total_price} 积分，用户余额 {result.balance}。"
    )
