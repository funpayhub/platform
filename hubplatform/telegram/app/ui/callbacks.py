__all__ = [
    'OpenMenu',
    'ChangePageTo',
    'GoBack',
    'Dummy',
]


from hubplatform.telegram.ui import UICallbackData, CallbackData, MenuContextSnapshot


class OpenMenu(UICallbackData, identifier='hubplatform.open_menu'):
    context: MenuContextSnapshot
    new_message: bool = False


class ChangePageTo(UICallbackData, identifier='hubplatform.change_page_to'):
    keyboard_page: int | None = None
    text_page: int | None = None


class GoBack(UICallbackData, identifier='hubplatform.go_back'): pass


class Dummy(UICallbackData, identifier='hubplatform.dummy'): pass