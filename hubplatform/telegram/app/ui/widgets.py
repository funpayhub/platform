from __future__ import annotations


__all__ = [
    'confirmable_button',
    'text_navigation_buttons',
    'cancel_button',
]

from hubplatform.telegram.ui import Button, MenuContext
from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.app.ui.callbacks import (
    Dummy,
    ClearState,
    ChangePageTo,
    ToggleConfirmation,
)
from hubplatform.i18n import Translator, I18nString


def confirmable_button(
    id: str,
    ctx: MenuContext,
    text: str,
    callback_data: CallbackData = Dummy(),
    style: str | None = None,
) -> list[Button]:
    key = f'open_confirmation:{id}'
    confirmation_opened = ctx.data.get(key)

    btn = Button(
        text=text if not confirmation_opened else 'Отмена',
        button_id=f'toggle_confirmation:{id}',
        callback_data=ToggleConfirmation(confirmation_id=id),
        style=style if not confirmation_opened else None,
    )

    if confirmation_opened:
        return [Button(button_id=id, text=text, callback_data=callback_data, style=style), btn]
    return [btn]


def _nav_button(button_id: str, text_id: str, text: str, enabled: bool, page: int) -> Button:
    return Button(
        button_id=button_id,
        text=text,
        callback_data=ChangePageTo(text_page={text_id: page}) if enabled else Dummy(),
        disabled=not enabled,
    )


def text_navigation_buttons(id: str, max_pages: int, current_page: int) -> list[Button]:
    if max_pages < 2:
        return []

    return [
        _nav_button('first', id, '⇤', current_page > 0, 0),
        _nav_button('prev', id, '←', current_page > 0, current_page - 1),
        Button(
            button_id='counter',
            text=f'{current_page + 1} / {max_pages}',
            callback_data=Dummy(),
            disabled=True,
        ),
        _nav_button('next', id, '→', current_page < max_pages - 1, current_page + 1),
        _nav_button('last', id, '⇥', current_page < max_pages - 1, max_pages - 1),
    ]


def cancel_button(
    open_session_id: str | None = None, translator: Translator | None = None
) -> Button:
    return Button(
        button_id='cancel',
        text=I18nString(key='telegram-ui-basic-widgets-cancel', fallback='Отмена').translate_(
            translator=translator
        ),
        callback_data=ClearState(open_session_id=open_session_id),
        style='danger',
    )
