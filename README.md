# starlette-msgspec

A FastAPI-like router for Starlette with msgspec integration for automatic request validation and OpenAPI documentation.

## Installation

```bash
# Install with pip
pip install starlette-msgspec

# Or with uv
uv pip install starlette-msgspec

# For development on this library
uv sync --dev
```

## Usage

```python
from starlette.applications import Starlette
from starlette_msgspec import MsgspecRouter, add_openapi_routes
import msgspec
from typing import List


# Define your data model with msgspec
class Item(msgspec.Struct):
    name: str
    description: str = ""
    price: float
    tax: float = 0.0


app = Starlette()
router = MsgspecRouter()


@router.post("/items", tags=["items"])
async def create_item(body: Item):
    return body


@router.get("/items", tags=["items"])
async def get_items() -> List[Item]:
    # ... implementation
    return [Item(name="Example", price=10.5)]


# Include the router and add OpenAPI documentation routes
router.include_router(app)
add_openapi_routes(app, router)
```

> **💡 For a more comprehensive example** showing multiple routers, different data models, and advanced features, check out [`examples/basic_app.py`](examples/basic_app.py).

## Features

- FastAPI-like router with method, path, and tags
- Automatic request validation based on msgspec types
- OpenAPI documentation generation using msgspec's built-in schema capabilities
- Type annotations for request body and response

## Running the example

```bash
# Install dependencies
uv sync --dev

# Run the example
uv run examples/basic_app.py
```

Then visit http://localhost:8000/docs to see the Swagger UI documentation.