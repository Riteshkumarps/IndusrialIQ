from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str = ""
    snippet: str = ""
    confidence: float = 0.0


class AttributeValue(BaseModel):
    value: Any = None
    uom: Optional[str] = None
    confidence: float = 0.0
    evidence: Optional[Evidence] = None


class Product(BaseModel):
    id: str
    mpn: str = ""
    raw_description: str = ""
    manufacturer_raw: Optional[str] = None
    brand_raw: Optional[str] = None

    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    department: Optional[str] = None
    product_type: Optional[str] = None

    attributes: Dict[str, AttributeValue] = Field(default_factory=dict)

    title: str = ""
    invoice_description: str = ""
    mobile_description: str = ""
    short_description: str = ""
    long_description: str = ""

    evidence: List[Evidence] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)

    quality_score: float = 0.0
    needs_human_review: bool = True
