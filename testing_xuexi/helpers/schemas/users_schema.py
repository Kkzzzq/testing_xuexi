from pydantic import BaseModel


class CreateUserResponse(BaseModel):
    id: int
    message: str
