from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from uuid import uuid4

class POIUpsert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))  # ✅ always present
    name: str
    lat: float
    lon: float
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, str]] = None

class POIResult(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, str]] = None

class NearbyQuery(BaseModel):
    lat: float
    lon: float
    radius_km: float = 5.0
    limit: int = 20
    category: Optional[str] = None
    tag: Optional[str] = None
