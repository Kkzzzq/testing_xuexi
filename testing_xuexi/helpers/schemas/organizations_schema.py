from pydantic import BaseModel


class CreateOrganizationResponse(BaseModel):
    orgId: int
    message: str
