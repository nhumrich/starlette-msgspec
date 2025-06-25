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
    router.register_routes(app)

    # Then add OpenAPI routes
    add_openapi_routes(app)

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

    router.register_routes(app)
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

    router.register_routes(app)
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

    router.register_routes(app)
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

    router.register_routes(app)
    add_openapi_routes(app)

    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()

    # Check that only router tags are present
    operation = schema["paths"]["/test"]["get"]
    assert "tags" in operation
    assert operation["tags"] == ["router-only"]


def test_router_prefix_in_openapi():
    """Test that router prefix is included in OpenAPI paths."""
    app = Starlette()
    router = MsgspecRouter(prefix="/api/v1")

    @router.get("/items")
    async def get_items() -> List[Item]:
        return [Item(name="Test Item", price=10.0)]

    @router.post("/items", tags=["items"])
    async def create_item(body: Item) -> Item:
        return body

    router.register_routes(app)
    add_openapi_routes(app)

    client = TestClient(app)
    
    # Test that the actual endpoints work with prefix
    response = client.get("/api/v1/items")
    assert response.status_code == 200
    
    # Test that OpenAPI schema includes the prefixed paths
    response = client.get("/openapi.json")
    schema = response.json()
    
    assert "/api/v1/items" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/items"]
    assert "post" in schema["paths"]["/api/v1/items"]
    
    # Ensure unprefixed paths are not present
    assert "/items" not in schema["paths"]


def test_multiple_routers_with_different_prefixes():
    """Test multiple routers with different prefixes in OpenAPI."""
    app = Starlette()
    
    api_router = MsgspecRouter(prefix="/api", tags=["api"])
    admin_router = MsgspecRouter(prefix="/admin", tags=["admin"])

    @api_router.get("/users")
    async def get_users() -> List[dict]:
        return [{"id": 1, "name": "User"}]

    @admin_router.get("/settings")
    async def get_settings() -> dict:
        return {"setting": "value"}

    api_router.register_routes(app)
    admin_router.register_routes(app)
    add_openapi_routes(app)

    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()

    # Check that both prefixed paths are present
    assert "/api/users" in schema["paths"]
    assert "/admin/settings" in schema["paths"]
    
    # Check that each route has correct tags
    api_operation = schema["paths"]["/api/users"]["get"]
    admin_operation = schema["paths"]["/admin/settings"]["get"]
    
    assert api_operation["tags"] == ["api"]
    assert admin_operation["tags"] == ["admin"]


def test_mounted_routers_prefix_in_openapi():
    """Test that mounted routers with prefix appear correctly in OpenAPI."""
    app = Starlette()
    
    items_router = MsgspecRouter(tags=["items"])
    users_router = MsgspecRouter(tags=["users"])

    @items_router.get("/items")
    async def get_items() -> List[Item]:
        return [Item(name="Test Item", price=10.0)]

    @users_router.get("/users")
    async def get_users() -> List[dict]:
        return [{"id": 1, "name": "User"}]

    # Mount routers under /api prefix
    MsgspecRouter.mount_routers(app, "/api", [items_router, users_router])
    add_openapi_routes(app)

    client = TestClient(app)
    
    # Test that actual endpoints work with the mount prefix
    response = client.get("/api/items")
    assert response.status_code == 200
    
    response = client.get("/api/users")
    assert response.status_code == 200
    
    # Test OpenAPI schema includes mounted paths
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Note: For mounted routers, the paths in OpenAPI should reflect the mount prefix
    # The exact behavior depends on how the mounting is implemented in the router
    assert "/api/items" in schema["paths"] or "/items" in schema["paths"]
    assert "/api/users" in schema["paths"] or "/users" in schema["paths"]


def test_prefix_with_tags_combination():
    """Test that router prefix and tags work together correctly."""
    app = Starlette()
    router = MsgspecRouter(prefix="/api/v2", tags=["v2", "api"])

    @router.get("/status", tags=["health"])
    async def get_status() -> dict:
        return {"status": "ok"}

    router.register_routes(app)
    add_openapi_routes(app)

    client = TestClient(app)
    
    # Test actual endpoint
    response = client.get("/api/v2/status")
    assert response.status_code == 200
    
    # Test OpenAPI schema
    response = client.get("/openapi.json")
    schema = response.json()
    
    assert "/api/v2/status" in schema["paths"]
    operation = schema["paths"]["/api/v2/status"]["get"]
    
    # Should have both router tags and endpoint tags
    assert operation["tags"] == ["v2", "api", "health"]


def test_mount_prefix_with_multiple_routers_in_openapi():
    """Test that mount-level prefix is correctly reflected in OpenAPI when mounting multiple routers."""
    app = Starlette()
    
    # Create routers without individual prefixes
    items_router = MsgspecRouter(tags=["items"])
    users_router = MsgspecRouter(tags=["users"])
    admin_router = MsgspecRouter(tags=["admin"])

    @items_router.get("/items")
    async def get_items() -> List[Item]:
        return [Item(name="Test Item", price=10.0)]

    @items_router.post("/items")
    async def create_item(body: Item) -> Item:
        return body

    @users_router.get("/users")
    async def get_users() -> List[dict]:
        return [{"id": 1, "name": "User"}]

    @users_router.post("/users", tags=["create"])
    async def create_user(body: dict) -> dict:
        return body

    @admin_router.get("/settings")
    async def get_settings() -> dict:
        return {"theme": "dark", "notifications": True}

    # Mount all routers under /api prefix
    MsgspecRouter.mount_routers(app, "/api", [items_router, users_router, admin_router])
    add_openapi_routes(app)

    client = TestClient(app)
    
    # Test that actual endpoints work with the mount prefix
    response = client.get("/api/items")
    assert response.status_code == 200
    
    response = client.get("/api/users")
    assert response.status_code == 200
    
    response = client.get("/api/settings")
    assert response.status_code == 200
    
    # Test that OpenAPI schema includes the mount prefix in paths
    response = client.get("/openapi.json")
    schema = response.json()
    
    # For mounted routers, the mount prefix SHOULD be included in OpenAPI paths
    # so that the API documentation reflects the actual accessible endpoints
    assert "/api/items" in schema["paths"]
    assert "/api/users" in schema["paths"] 
    assert "/api/settings" in schema["paths"]
    
    # Verify that unprefixed paths are NOT in the OpenAPI schema
    assert "/items" not in schema["paths"]
    assert "/users" not in schema["paths"]
    assert "/settings" not in schema["paths"]
    
    # Check that tags are correctly applied
    items_operation = schema["paths"]["/api/items"]["get"]
    users_operation = schema["paths"]["/api/users"]["post"]
    settings_operation = schema["paths"]["/api/settings"]["get"]
    
    assert items_operation["tags"] == ["items"]
    assert users_operation["tags"] == ["users", "create"]  # Router tag + endpoint tag
    assert settings_operation["tags"] == ["admin"]


def test_mount_prefix_with_individual_router_prefixes():
    """Test mounting routers that have their own prefixes plus a mount prefix."""
    app = Starlette()
    
    # Create routers WITH individual prefixes
    v1_router = MsgspecRouter(prefix="/v1", tags=["v1"])
    v2_router = MsgspecRouter(prefix="/v2", tags=["v2"])

    @v1_router.get("/status")
    async def get_v1_status() -> dict:
        return {"version": "1.0", "status": "ok"}

    @v2_router.get("/status")
    async def get_v2_status() -> dict:
        return {"version": "2.0", "status": "ok"}

    # Mount both routers under /api prefix
    MsgspecRouter.mount_routers(app, "/api", [v1_router, v2_router])
    add_openapi_routes(app)

    client = TestClient(app)
    
    # Test that actual endpoints work with both mount prefix AND individual router prefix
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.0"
    
    response = client.get("/api/v2/status")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2.0"
    
    # Test OpenAPI schema
    response = client.get("/openapi.json")
    schema = response.json()
    
    # The OpenAPI should show the mount prefix + individual router prefixes
    assert "/api/v1/status" in schema["paths"]
    assert "/api/v2/status" in schema["paths"]
    
    # Verify that paths without mount prefix are not present
    assert "/v1/status" not in schema["paths"]
    assert "/v2/status" not in schema["paths"]
    
    # Verify tags
    v1_operation = schema["paths"]["/api/v1/status"]["get"]
    v2_operation = schema["paths"]["/api/v2/status"]["get"]
    
    assert v1_operation["tags"] == ["v1"]
    assert v2_operation["tags"] == ["v2"]
