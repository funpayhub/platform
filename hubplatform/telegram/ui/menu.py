from __future__ import annotations


__all__ = [
    'MenuSpec',
    'MenuRenderResult',
    'SessionRef',
    'MenuEnvironment',
    'MenuViewState',
    'MenuContext',
    'MenuBuildContext',
]

from typing import Any, Mapping, MutableSequence
from dataclasses import field as dataclass_field

from pydantic import Field, BaseModel, JsonValue, ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from hubplatform.telegram.ui.session import MenuFrame
from hubplatform.telegram.ui.keyboard import Keyboard, KeyboardBlockSpec
from hubplatform.telegram.ui.exceptions import ButtonRenderError, KeyboardBlockBuildingError
from hubplatform.telegram.callback_data.hash import HashService


@pydantic_dataclass(
    config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True),
)
class MenuSpec:
    header_text: str = ''
    header_body_sep: str = '<hr/>\n'
    body_text: str = ''
    body_footer_sep: str = '\n<hr/>'
    footer_text: str = ''
    header_footer_sep: str = '\n<hr/>\n'
    header_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)
    main_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)
    footer_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)

    @property
    def total_blocks(self) -> list[KeyboardBlockSpec]:
        return [
            *self.header_keyboard,
            *self.main_keyboard,
            *self.footer_keyboard,
        ]

    async def render(
        self,
        di_context: Mapping[str, Any],
        hash_service: HashService | None = None,
    ) -> MenuRenderResult:
        building_errors: list[KeyboardBlockBuildingError] = []
        keyboard: Keyboard = []

        for block in self.total_blocks:
            try:
                result = await block.build(di_context)
                keyboard.extend(result.keyboard)
            except KeyboardBlockBuildingError as e:
                building_errors.append(e)
            except Exception as e:
                new_building_e = KeyboardBlockBuildingError(block_id=block.block_id)
                new_building_e.__cause__ = e
                building_errors.append(new_building_e)

        rendered_keyboard: list[list[str]] = []
        render_errors: list[ButtonRenderError] = []
        for line in keyboard:
            result_line = []
            for button in line:
                try:
                    result_line.append(button._to_html(hash_service=hash_service))
                except ButtonRenderError as e:
                    render_errors.append(e)
                except Exception as e:
                    new_render_e = ButtonRenderError(button_id=button.button_id)
                    new_render_e.__cause__ = e
                    render_errors.append(new_render_e)
            if result_line:
                rendered_keyboard.append(result_line)

        keyboard_htmls = []
        for converted_line in rendered_keyboard:
            keyboard_htmls.append(f'<tg-button-row>{"\n".join(converted_line)}</tg-button-row>')
        keyboard_html = '\n'.join(keyboard_htmls)

        text = self.header_text
        if self.body_text:
            if text:
                text += self.header_body_sep
            text += self.body_text
        if self.footer_text:
            if self.body_text:
                text += self.body_footer_sep
            elif self.header_text:
                text += self.header_footer_sep
            text += self.footer_text

        if keyboard_html:
            text += '\n' + keyboard_html

        return MenuRenderResult(
            text=text,
            building_errors=building_errors,
            render_errors=render_errors,
        )


@pydantic_dataclass(config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class MenuRenderResult:
    text: str
    building_errors: list[KeyboardBlockBuildingError] = Field(default_factory=list)
    render_errors: list[ButtonRenderError] = Field(default_factory=list)


@pydantic_dataclass(frozen=True)
class SessionRef:
    session_id: str
    revision: int


@pydantic_dataclass(frozen=True)
class MenuEnvironment:
    chat_id: int | None = None
    thread_id: int | None = None
    message_id: int | None = None
    actor_id: int | None = None


@pydantic_dataclass(frozen=True)
class MenuViewState:
    keyboard_page: int = 0
    text_page: dict[str, int] = dataclass_field(default_factory=dict)


class MenuContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: dict[str, Any] = Field(default_factory=dict)

    def dump(self) -> dict[str, JsonValue]:
        return self.model_dump(mode='json')


class MenuBuildContext[C: MenuContext = MenuContext](BaseModel):
    menu_id: str
    context: C
    environment: MenuEnvironment | None = None
    session: SessionRef | None = None
    view_state: MenuViewState = Field(default_factory=MenuViewState)
    history: tuple[MenuFrame, ...] = ()

    def require_environment(self) -> MenuEnvironment:
        if self.environment is None:
            raise RuntimeError('There is no menu environment in current building context.')
        return self.environment

    def require_session(self) -> SessionRef:
        if self.session is None:
            raise RuntimeError('There is no session in current building context.')
        return self.session
