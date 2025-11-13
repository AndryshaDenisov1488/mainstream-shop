"""
Вспомогательные структуры для работы со статусами заказов.
Единый источник правды для отображения, css-бейджей и фильтров.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class OrderStatusMeta:
    code: str
    label: str
    badge: str
    category: str = "default"


# Порядок важен — именно так статусы будут показаны в выпадающих списках.
STATUS_ORDER: Sequence[str] = (
    "draft",
    "checkout_initiated",
    "awaiting_payment",
    "paid",
    "processing",
    "awaiting_info",
    "ready",
    "links_sent",
    "completed",
    "completed_partial_refund",
    "refund_required",
    "refunded_partial",
    "refunded_full",
    "cancelled_unpaid",
    "cancelled_manual",
)


STATUS_DEFINITIONS: Dict[str, OrderStatusMeta] = {
    "draft": OrderStatusMeta("draft", "Черновик", "secondary"),
    "checkout_initiated": OrderStatusMeta(
        "checkout_initiated", "Оформление инициировано", "secondary"
    ),
    "awaiting_payment": OrderStatusMeta(
        "awaiting_payment", "Ожидание оплаты", "warning"
    ),
    "paid": OrderStatusMeta("paid", "Оплачен (ожидает оператора)", "info"),
    "processing": OrderStatusMeta("processing", "В обработке оператором", "primary"),
    "awaiting_info": OrderStatusMeta(
        "awaiting_info", "Нужно уточнить детали", "warning"
    ),
    "ready": OrderStatusMeta("ready", "Готов к отправке", "info"),
    "links_sent": OrderStatusMeta("links_sent", "Ссылки отправлены", "primary"),
    "completed": OrderStatusMeta("completed", "Выполнен", "success"),
    "completed_partial_refund": OrderStatusMeta(
        "completed_partial_refund", "Выполнен (частичный возврат)", "success"
    ),
    "refund_required": OrderStatusMeta(
        "refund_required", "Требуется возврат", "warning"
    ),
    "refunded_partial": OrderStatusMeta(
        "refunded_partial", "Частичный возврат", "warning"
    ),
    "refunded_full": OrderStatusMeta("refunded_full", "Полный возврат", "danger"),
    "cancelled_unpaid": OrderStatusMeta(
        "cancelled_unpaid", "Отменен (не оплачен)", "secondary", category="cancelled"
    ),
    "cancelled_manual": OrderStatusMeta(
        "cancelled_manual", "Отменен вручную", "dark", category="cancelled"
    ),
}

# Легаси-алиасы, чтобы старые фильтры/ссылки продолжали работать.
LEGACY_STATUS_ALIASES: Dict[str, List[str]] = {
    "pending": ["paid"],
    "pending_payment": ["awaiting_payment"],
    "cancelled": ["cancelled_unpaid", "cancelled_manual"],
}


def get_status_label(code: str) -> str:
    """Человекочитаемое имя статуса."""
    return STATUS_DEFINITIONS.get(code, OrderStatusMeta(code, code, "secondary")).label


def get_status_badge(code: str) -> str:
    """CSS‑класс бейджа для статуса."""
    return STATUS_DEFINITIONS.get(code, OrderStatusMeta(code, code, "secondary")).badge


def expand_status_filter(value: str) -> List[str]:
    """
    Возвращает список реальных статусов для фильтра.
    Нужен чтобы поддерживать алиасы вроде 'cancelled'.
    """
    if not value:
        return []
    if value in STATUS_DEFINITIONS:
        return [value]
    return LEGACY_STATUS_ALIASES.get(value, [])


def get_status_filter_choices(include_cancelled_group: bool = True) -> List[OrderStatusMeta]:
    """
    Возвращает список метаданных для построения выпадающего списка фильтров.
    Можно добавить агрегированный пункт 'cancelled'.
    """
    choices: List[OrderStatusMeta] = [STATUS_DEFINITIONS[code] for code in STATUS_ORDER if code in STATUS_DEFINITIONS]
    if include_cancelled_group:
        choices.append(OrderStatusMeta("cancelled", "Отменен (все)", "dark", category="cancelled"))
    return choices

