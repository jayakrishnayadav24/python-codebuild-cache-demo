from fastapi import APIRouter, HTTPException
from src.models.product import ProductSchema

router = APIRouter()

_store: dict = {}


@router.get("/products")
def list_products():
    return list(_store.values())


@router.get("/products/{product_id}")
def get_product(product_id: int):
    product = _store.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/products")
def create_product(product: ProductSchema):
    product_id = len(_store) + 1
    product.id = product_id
    _store[product_id] = product.model_dump()
    return product
