import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
import msgspec
from typing import List

from starlette_msgspec import MsgspecRouter, add_openapi_routes

class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""

@pytest.fixture
def app():
    app = Starlette()
    router = MsgspecRouter()
    
    @router.get("/items/", tags=["items"])
    async def get_items() -> List[Item]:
        return [Item(name="Test Item", price=10.0)]
    
    @router.post("/items/", tags=["items"])
    async def create_item(body: Item) -> Item:
        return body
    
    # Add routes to the app first
    router.include_router(app)
    
    # Then add OpenAPI routes
    add_openapi_routes(app, router)
    
    return app

@pytest.fixture
def client(app):
    return TestClient(app)

def test_get_items(client):
    response = client.get("/items/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Item"
    assert data[0]["price"] == 10.0

def test_create_item(client):
    item = {"name": "New Item", "price": 15.5, "description": "A new item"}
    response = client.post("/items/", json=item)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Item"
    assert data["price"] == 15.5
    assert data["description"] == "A new item"

def test_create_item_validation(client):
    # Missing required field
    item = {"name": "Invalid Item"}
    response = client.post("/items/", json=item)
    assert response.status_code == 422
    assert "detail" in response.json()

def test_openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    
    # Check basic structure
    assert "openapi" in schema
    assert "paths" in schema
    assert "components" in schema
    assert "schemas" in schema["components"]
    
    # Check paths
    assert "/items/" in schema["paths"]
    assert "get" in schema["paths"]["/items/"]
    assert "post" in schema["paths"]["/items/"]
    
    # Check Item schema
    assert "Item" in schema["components"]["schemas"]
    item_schema = schema["components"]["schemas"]["Item"]
    assert item_schema["type"] == "object"
    assert "name" in item_schema["properties"]
    assert "price" in item_schema["properties"]