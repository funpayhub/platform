from __future__ import annotations

from typing import Any, Self

from pydantic import Field, BaseModel

from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer


class MenuContextEnvelope(BaseModel):
    menu_id: str
    keyboard_page: int
    text_page: int
    data: dict[str, Any]
    fields: dict[str, Any]


class MenuContext(BaseModel):
    menu_id: str
    keyboard_page: int = 0
    text_page: int = 0
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def _validate_menu_id(cls, menu_id: str) -> str:
        if not menu_id:
            raise ValueError('Menu ID cannot be empty.')

        return menu_id

    def _dump_context_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode='json',
            exclude=set(MenuContext.model_fields.keys()),
            fallback=pydantic_fallback_serializer,
        )

    def to_envelope(self) -> MenuContextEnvelope:
        fields = self._dump_context_fields()
        data = fields.pop('data', {})
        return MenuContextEnvelope(
            menu_id=self.menu_id,
            keyboard_page=self.keyboard_page,
            text_page=self.text_page,
            fields=fields,
            data=data,
        )

    @classmethod
    def from_envelope(cls, envelope: MenuContextEnvelope) -> Self:
        return cls.model_validate(
            envelope.fields
            | {
                'menu_id': envelope.menu_id,
                'keyboard_page': envelope.keyboard_page,
                'text_page': envelope.text_page,
                'data': envelope.data,
            }
        )
