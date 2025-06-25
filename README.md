# starlette-msgspec

A FastAPI-like router for Starlette with msgspec integration for automatic request validation and OpenAPI documentation.

## Installation

```bash
# Install with pip
pip install starlette-msgspec

# Or with uv
uv pip install starlette-msgspec

# For development (from cloned repository)
uv pip install -e ".[test]"
```

## Usage

```python
from starlette.applications import Starlette
from starlette_msgspec import MsgspecRouter, Body
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


@router.route("/items/", "POST", tags=["items"])
async def create_item(body: Body[Item]):
    return body.value


@router.route("/items/", "GET", tags=["items"])
async def get_items() -> List[Item]:
    # ... implementation
    return [Item(name="Example", price=10.5)]


# Include the router and the OpenAPI docs middleware
app.include_router(router)
app.add_middleware(router.openapi_middleware)
```

## Features

- FastAPI-like router with method, path, and tags
- Automatic request validation based on msgspec types
- OpenAPI documentation generation using msgspec's built-in schema capabilities
- Type annotations for request body and response

## Running the example

```bash
# Install dependencies
uv pip install -e ".[test]" uvicorn

# Run the example
python examples/basic_app.py
```

Then visit http://localhost:8000/docs to see the Swagger UI documentation.