from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette_msgspec import MsgspecRouter, add_openapi_routes, generate_openapi_schema
import msgspec
from typing import List, Optional
import uvicorn

# Define your data models with msgspec
class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""
    tax: Optional[float] = None

class User(msgspec.Struct):
    id: int
    name: str
    email: str

# Create a Starlette app
app = Starlette()

# Create multiple routers - one for items, one for users
items_router = MsgspecRouter()
users_router = MsgspecRouter()

# Items routes
@items_router.get("/items", tags=["items"])
async def get_items() -> List[Item]:
    """Get a list of all items."""
    return [
        Item(name="Hammer", price=9.99),
        Item(name="Screwdriver", description="Phillips head", price=5.99, tax=0.5)
    ]

@items_router.post("/items", tags=["items"])
async def create_item(body: Item) -> Item:
    """Create a new item."""
    # In a real application, you would save the item
    return body

@items_router.get("/items/{item_id}", tags=["items"])
async def get_item(request) -> Item:
    """Get a single item by ID."""
    item_id = request.path_params["item_id"]
    return Item(name=f"Item {item_id}", price=10.0)

# Users routes
@users_router.get("/users", tags=["users"])
async def get_users() -> List[User]:
    """Get a list of all users."""
    return [
        User(id=1, name="Alice", email="alice@example.com"),
        User(id=2, name="Bob", email="bob@example.com")
    ]

@users_router.post("/users", tags=["users"])
async def create_user(body: User) -> User:
    """Create a new user."""
    # In a real application, you would save the user
    return body

# Add routes to the app
items_router.include_router(app)
users_router.include_router(app)

# Add OpenAPI documentation routes
add_openapi_routes(app, title="Item & User API", version="1.0.0", description="API for managing items and users")

# Add a basic root document for demo purposes
async def root(request):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Item API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; }
            a { color: #007bff; text-decoration: none; margin: 10px 0; display: block; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>Welcome to the Item API</h1>
        <p>Choose one of the following options:</p>
        <a href="/docs">📖 API Documentation</a>
        <a href="/openapi.json">🔧 OpenAPI Specification</a>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

app.add_route("/", root)

# Example: Generate OpenAPI schema programmatically
# This is useful for different deployment solutions where you want to
# generate the schema without hosting it as a route,
# or if you want to use the json for an existing openapi documentation library
def save_openapi_schema():
    """Generate and save OpenAPI schema to a file."""
    # This now works with ALL registered routers on the app
    schema = generate_openapi_schema(app, title="Item & User API", version="1.0.0", description="API for managing items and users")
    import json
    with open("openapi.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("OpenAPI schema saved to openapi.json")

if __name__ == "__main__":
    # Uncomment the line below to generate OpenAPI schema file
    # save_openapi_schema()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)