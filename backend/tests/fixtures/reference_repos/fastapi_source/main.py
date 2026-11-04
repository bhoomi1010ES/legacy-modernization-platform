"""Minimal FastAPI service."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

app = FastAPI(title="Synthetic Inventory API", version="1.0.0")

class InventoryItem(BaseModel):
    id: int
    sku: str = Field(..., max_length=64)
    quantity: int = Field(default=0, ge=0)
    unit_price: float = Field(default=0.0, ge=0.0)

ITEMS: dict[int, InventoryItem] = {}

@app.get("/items", response_model=List[InventoryItem])
def list_items():
    return list(ITEMS.values())

@app.get("/items/{item_id}", response_model=InventoryItem)
def get_item(item_id: int):
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail="Item not found")
    return ITEMS[item_id]

@app.post("/items", response_model=InventoryItem, status_code=201)
def create_item(item: InventoryItem):
    ITEMS[item.id] = item
    return item
