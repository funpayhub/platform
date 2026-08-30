from __future__ import annotations


__all__ = ['FileGoodsSource']

import os
import json
from typing import cast
from os import SEEK_END
from asyncio import Lock
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import Iterable, AsyncIterator

from .base import GoodsSource
from .exceptions import NotEnoughGoodsError


_JSON_ENCODER = json.JSONEncoder()
_JSON_DECODER = json.JSONDecoder()


def _encode(val: str) -> str:
    return _JSON_ENCODER.encode(val)[1:-1]


def _decode(val: str) -> str:
    return cast(str, _JSON_DECODER.decode(f'"{val}"'))


class FileGoodsSource(GoodsSource):
    """Представляет файл с товарами."""

    def __init__(self, source: str | Path) -> None:
        if not isinstance(source, (str, Path)):
            raise ValueError('Source must be a string or Path object.')

        self._path = Path(source).expanduser().resolve()
        self._goods_amount = 0
        self._lock = Lock()
        self._source_id = self._path.as_uri()

    @asynccontextmanager
    async def _self(self) -> AsyncIterator[None]:
        async with self._lock:
            self._create_file()
            yield

    def _create_file(self) -> None:
        if not self.path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch()
            self._goods_amount = 0

    def _count_products(self) -> int:
        count = 0
        with open(self._path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    async def load(self) -> None:
        async with self._self():
            self._goods_amount = self._count_products()

    async def reload(self) -> None:
        await self.load()

    async def unload(self) -> None:
        return

    async def remove(self) -> None:
        async with self._lock:
            if self.path.exists():
                os.remove(self.path)
                self._goods_amount = 0

    async def add_goods(self, products: Iterable[str]) -> None:
        async with self._self():
            added_products = 0
            tmp = self._path.copy(self._path.with_name(self._path.name + '.tmp'))
            try:
                with open(tmp, 'a+b') as f:
                    f.seek(0, SEEK_END)
                    size = f.tell()

                    if size > 0:
                        f.seek(-1, SEEK_END)
                        ends_with_newline = f.read(1) == b'\n'
                    else:
                        ends_with_newline = True

                    f.seek(0, SEEK_END)

                    if not ends_with_newline:
                        f.write(b'\n')

                    for i in products:
                        if not i.strip():
                            continue
                        f.write(_encode(i).encode('utf-8') + b'\n')
                        added_products += 1
                tmp.replace(self._path)
                self._goods_amount += added_products
            finally:
                tmp.unlink(missing_ok=True)

    async def pop_goods(self, amount: int) -> list[str]:
        if amount < 1:
            raise ValueError('Amount must be greater than 0.')

        async with self._self():
            tmp = self._path.with_name(self._path.name + '.tmp')
            result: list[str] = []
            new_amount = 0
            current_index = 0

            try:
                with (
                    self._path.open('r', encoding='utf-8') as fin,
                    tmp.open('w', encoding='utf-8') as fout,
                ):
                    for line in fin:
                        if not line.strip():
                            continue
                        line = line.rstrip('\r\n')

                        if current_index < amount:
                            result.append(_decode(line))
                        else:
                            fout.write(line + '\n')
                            new_amount += 1
                        current_index += 1

                if len(result) < amount:
                    self._goods_amount = current_index
                    raise NotEnoughGoodsError(self)

                tmp.replace(self._path)
                self._goods_amount = new_amount
                return result
            finally:
                tmp.unlink(missing_ok=True)

    async def get_goods(self, amount: int, start: int = 0) -> list[str]:
        if start < 0:
            raise ValueError('Start must be greater than or equal to 0.')
        if amount < -1:
            raise ValueError('Amount must be greater than or equal to -1.')

        result: list[str] = []
        async with self._self():
            with open(self.path, 'r', encoding='utf-8') as f:
                current_line = 0
                while current_line < start:
                    try:
                        line = next(f).rstrip('\r\n')
                        if not line.strip():
                            continue
                        current_line += 1
                    except StopIteration:
                        self._goods_amount = current_line
                        break

                while amount == -1 or len(result) < amount:
                    try:
                        line = next(f).rstrip('\r\n')
                        if not line.strip():
                            continue
                        result.append(_decode(line))
                        current_line += 1
                    except StopIteration:
                        self._goods_amount = current_line
                        break
        return result

    async def set_goods(self, goods: list[str]) -> None:
        async with self._self():
            tmp = self._path.with_name(self._path.name + '.tmp')
            amount = 0

            try:
                with tmp.open('w', encoding='utf-8') as f:
                    for i in goods:
                        if not i.strip():
                            continue
                        f.write(_encode(i) + '\n')
                        amount += 1

                tmp.replace(self._path)
                self._goods_amount = amount
            finally:
                tmp.unlink(missing_ok=True)

    async def remove_goods(self, from_index: int, amount: int) -> None:
        if amount < 1:
            raise ValueError('Amount must be greater than 0.')

        if from_index < 0:
            raise ValueError('Index must be greater or equal to 0.')

        async with self._self():
            tmp = self._path.with_name(self._path.name + '.tmp')
            try:
                to_index = from_index + amount
                new_amount = 0
                current_product_index = 0
                with (
                    self._path.open('r', encoding='utf-8') as fin,
                    tmp.open('w', encoding='utf-8') as fout,
                ):
                    for line in fin:
                        line = line.rstrip('\r\n')
                        if not line.strip():
                            continue

                        if not (from_index <= current_product_index < to_index):
                            fout.write(line + '\n')
                            new_amount += 1
                        current_product_index += 1

                tmp.replace(self._path)
                self._goods_amount = new_amount
            finally:
                tmp.unlink(missing_ok=True)

    async def len(self) -> int:
        return self._goods_amount

    @property
    def path(self) -> Path:
        return self._path

    @property
    def source_id(self) -> str:
        return self._source_id

    def __str__(self) -> str:
        return self._path.name
