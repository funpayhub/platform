from __future__ import annotations

from math import ceil
from functools import partial

from hubplatform.i18n import Translator
from hubplatform.telegram.ui import (
    Button,
    MenuSpec,
    MenuBuildContext,
    KeyboardBlockSpec,
    MenuBuildingState,
)
from hubplatform.telegram.ui.keyboard import Keyboard

from .callbacks import Dummy, GoBack, ChangePageTo


class StripAndNavigationFinalizer:
    def __init__(
        self,
        back_button: bool = True,
        max_blocks_in_keyboard: int = 10,
    ) -> None:
        self.back_button = back_button
        self.max_blocks_in_keyboard = max_blocks_in_keyboard

    async def __call__(
        self,
        ctx: MenuBuildContext,
        state: MenuBuildingState,
        translator: Translator,
    ) -> MenuSpec:
        keyboard = state.menu.main_keyboard

        pages = ceil(len(keyboard) / self.max_blocks_in_keyboard)
        state.menu.footer_keyboard.append(
            KeyboardBlockSpec(
                block_id='hubplatform.navigation',
                builder=partial(_nav, ctx=ctx, tr=translator, pages=pages, back=self.back_button),
            )
        )

        start = ctx.view_state.keyboard_page * self.max_blocks_in_keyboard
        state.menu.main_keyboard = keyboard[start : start + self.max_blocks_in_keyboard]

        return state.menu


def _nav_button(button_id: str, text: str, enabled: bool, page: int) -> Button:
    return Button(
        button_id=button_id,
        text=text if enabled else ' ',
        callback_data=ChangePageTo(keyboard_page=page) if enabled else Dummy(),
    )


async def _nav(ctx: MenuBuildContext, tr: Translator, pages: int, back: bool) -> Keyboard:
    kb: Keyboard = []

    if ctx.history and back:
        kb.append([Button(button_id='back', text=tr.translate('◀️ Назад'), callback_data=GoBack())])

    if pages < 2:
        return kb

    page = ctx.view_state.keyboard_page
    kb.insert(
        0,
        [
            _nav_button('first', '⏪', page > 0, 0),
            _nav_button('prev', '◀️', page > 0, page - 1),
            Button(button_id='counter', text=f'{page + 1} / {pages}', callback_data=Dummy()),
            _nav_button('next', '▶️', page < pages - 1, page + 1),
            _nav_button('last', '⏩', page < pages - 1, pages - 1),
        ],
    )

    return kb


# async def build_view_navigation_btns(ctx: MenuContext, total_pages: int = -1) -> KeyboardBuilder:
#     kb: KeyboardBuilder = KeyboardBuilder()
#     unknown_max_pages = total_pages == -1
#
#     if not unknown_max_pages and total_pages < 2:
#         return kb
#
#     page_amount_btn = Button.callback_button(
#         button_id='menu_page_counter',
#         text=f'{ctx.view_page + (1 if unknown_max_pages or total_pages else 0)}'
#         + (f' / {total_pages}' if not unknown_max_pages else ''),
#         callback_data=cbs.ActivateChangingPageState(
#             mode='text',
#             total_pages=total_pages,
#             ui_history=ctx.as_ui_history(),
#         ).pack()
#         if unknown_max_pages or total_pages > 1
#         else cbs.Dummy().pack(),
#     )
#
#     nav_kb = [
#         _btn('first_view_page', '⏪', ctx.view_page > 0, ctx, None, 0),
#         _btn('previous_view_page', '◀️', ctx.view_page > 0, ctx, None, ctx.view_page - 1),
#         page_amount_btn,
#         _btn('next_view_page', '▶️', unknown_max_pages or ctx.view_page < total_pages - 1, ctx,
#              None, ctx.view_page + 1),
#         _btn('last_view_page', '⏩', not unknown_max_pages and ctx.view_page < total_pages - 1, ctx,
#              None, total_pages - 1),
#     ]
#
#     kb.insert(0, nav_kb)
#     return kb
#
