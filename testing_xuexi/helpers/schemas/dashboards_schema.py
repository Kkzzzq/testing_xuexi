from pydantic import BaseModel


class CreateFolderResponse(BaseModel):
    id: int
    uid: str
    title: str


class CreateDashboardStatus(BaseModel):
    status: str
    uid: str
    version: int
