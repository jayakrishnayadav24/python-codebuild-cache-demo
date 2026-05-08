from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.orm import DeclarativeBase
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String)
    price = Column(Numeric(19, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductSchema(BaseModel):
    id: int | None = None
    name: str
    description: str | None = None
    price: Decimal

    class Config:
        from_attributes = True
