from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette_msgspec import MsgspecRouter, Body, OpenAPIMiddleware
import msgspec
from typing import List, Optional
import uvicorn

# Define your data models with msgspec
class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""
    tax: Optional[float] = None

# Create a Starlette app
app = Starlette()

# Create a router
router = MsgspecRouter()

@router.route("/items/", "GET", tags=["items"])
async def get_items() -> List[Item]:
    """Get a list of all items."""
    return [
        Item(name="Hammer", price=9.99),
        Item(name="Screwdriver", description="Phillips head", price=5.99, tax=0.5)
    ]

@router.route("/items/", "POST", tags=["items"])
async def create_item(body: Body[Item]) -> Item:
    """Create a new item."""
    # In a real application, you would save the item
    return body.value

@router.route("/items/{item_id}", "GET", tags=["items"])
async def get_item(request) -> Item:
    """Get a single item by ID."""
    item_id = request.path_params["item_id"]
    return Item(name=f"Item {item_id}", price=10.0)

# Add routes to the app
router.include_router(app)

# Add OpenAPI documentation middleware
app.add_middleware(OpenAPIMiddleware, title="Item API", version="1.0.0")

# Add a route to redirect root to docs
async def root(request):
    return JSONResponse({
        "message": "Welcome to the Item API",
        "docs": "/docs",
        "openapi": "/openapi.json"
    })

app.add_route("/", root)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)