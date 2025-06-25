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

def test_router_level_tags():
    """Test that router-level tags are applied to all routes."""
    app = Starlette()
    router = MsgspecRouter(tags=["api", "v1"])
    
    @router.get("/test")
    async def test_route() -> dict:
        return {"message": "test"}
    
    router.include_router(app)
    add_openapi_routes(app)
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Check that the route has router-level tags
    assert "/test" in schema["paths"]
    assert "get" in schema["paths"]["/test"]
    operation = schema["paths"]["/test"]["get"]
    assert "tags" in operation
    assert operation["tags"] == ["api", "v1"]

def test_combined_router_and_endpoint_tags():
    """Test that router-level and endpoint-level tags are combined."""
    app = Starlette()
    router = MsgspecRouter(tags=["api", "v1"])
    
    @router.get("/test", tags=["special"])
    async def test_route() -> dict:
        return {"message": "test"}
    
    router.include_router(app)
    add_openapi_routes(app)
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Check that the route has both router-level and endpoint-level tags
    operation = schema["paths"]["/test"]["get"]
    assert "tags" in operation
    assert operation["tags"] == ["api", "v1", "special"]

def test_router_without_tags():
    """Test that router without tags works as before."""
    app = Starlette()
    router = MsgspecRouter()  # No tags specified
    
    @router.get("/test", tags=["endpoint-only"])
    async def test_route() -> dict:
        return {"message": "test"}
    
    router.include_router(app)
    add_openapi_routes(app)
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Check that only endpoint tags are present
    operation = schema["paths"]["/test"]["get"]
    assert "tags" in operation
    assert operation["tags"] == ["endpoint-only"]

def test_router_tags_only():
    """Test router with tags but endpoint without tags."""
    app = Starlette()
    router = MsgspecRouter(tags=["router-only"])
    
    @router.get("/test")
    async def test_route() -> dict:
        return {"message": "test"}
    
    router.include_router(app)
    add_openapi_routes(app)
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Check that only router tags are present
    operation = schema["paths"]["/test"]["get"]
    assert "tags" in operation
    assert operation["tags"] == ["router-only"]