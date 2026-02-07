from pydantic import BaseModel


class I18nText(BaseModel):
    id: int
    text: str | None
