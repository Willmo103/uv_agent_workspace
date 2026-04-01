from .imports import BaseModel, Optional


class DescriptionEntry(BaseModel):
    file_path: str
    reason: str
    description: Optional[str] = None
