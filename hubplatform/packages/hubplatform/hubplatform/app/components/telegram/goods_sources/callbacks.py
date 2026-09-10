from __future__ import annotations


__all__ = [
    'DeleteSource',
    'ExportGoods',
    'StartFileSourceCreation',
    'StartGoodsInput',
]

from typing import Literal

from hubplatform.telegram.ui.session_callback_data import SessionCallbackData


class StartFileSourceCreation(
    SessionCallbackData,
    identifier='hubplatform.goods_sources.start_file_source_creation',
):
    pass


class StartGoodsInput(
    SessionCallbackData,
    identifier='hubplatform.goods_sources.start_goods_input',
):
    source_id: str
    action: Literal['add', 'remove', 'replace']


class ExportGoods(
    SessionCallbackData,
    identifier='hubplatform.goods_sources.export_goods',
):
    source_id: str


class DeleteSource(
    SessionCallbackData,
    identifier='hubplatform.goods_sources.delete_source',
):
    source_id: str
