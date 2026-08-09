from __future__ import annotations


class HubPlatformException(Exception):  # noqa: N818
    ...


class TranslatableException(HubPlatformException): ...


class BadHashError(TranslatableException): ...
