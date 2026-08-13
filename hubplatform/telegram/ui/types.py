from typing import Any
from pydantic import BaseModel


class MenuContext(BaseModel):
    menu_id: str
    menu_page: int = 0
    view_page: int = 0



class MenuState(BaseModel):
    menu_id: str
    keyboard_page: int
    text_page: int
    context: MenuContext
    data: dict[str, Any]