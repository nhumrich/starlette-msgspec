from typing import Dict, Any

import msgspec
from starlette.responses import JSONResponse, HTMLResponse


def generate_openapi_schema(
    app,
    title: str = "API",
    version: str = "0.1.0",
    description: str = "API Documentation",
) -> Dict[str, Any]:
    """Generate OpenAPI schema from all registered routers in the app."""
    if not hasattr(app, "_msgspec_routers") or not app._msgspec_routers:
        # Fallback: create empty schema if no routers registered
        return {
            "openapi": "3.0.2",
            "info": {
                "title": title,
                "version": version,
                "description": description,
            },
            "paths": {},
            "components": {"schemas": {}},
        }

    # Collect all models and route info from all routers
    all_models = set()
    all_route_info = []

    for router in app._msgspec_routers:
        all_models.update(router.registered_models)
        all_route_info.extend(router.route_info)

    # Generate component schemas for all registered models
    if all_models:
        schemas, components = msgspec.json.schema_components(
            all_models, ref_template="#/components/schemas/{name}"
        )
    else:
        components = {}

    # Create the base OpenAPI schema
    schema = {
        "openapi": "3.0.2",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "paths": {},
        "components": {"schemas": components},
    }

    # Helper function to convert refs (reuse from router)
    def _convert_refs_to_components(
        schema_obj: Dict[str, Any], components_schemas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert $defs references to proper #/components/schemas references."""
        if isinstance(schema_obj, dict):
            # Handle $defs at the root level
            if "$defs" in schema_obj:
                for def_name, def_schema in schema_obj["$defs"].items():
                    if def_name not in components_schemas:
                        components_schemas[def_name] = def_schema

                # Remove $defs and replace with $ref
                del schema_obj["$defs"]

                # If the schema has a $ref pointing to $defs, update it
                if "$ref" in schema_obj and schema_obj["$ref"].startswith("#/$defs/"):
                    ref_name = schema_obj["$ref"].replace("#/$defs/", "")
                    schema_obj["$ref"] = f"#/components/schemas/{ref_name}"

            # Recursively process nested objects
            result = {}
            for key, value in schema_obj.items():
                if (
                    key == "$ref"
                    and isinstance(value, str)
                    and value.startswith("#/$defs/")
                ):
                    # Convert $defs reference to components/schemas reference
                    ref_name = value.replace("#/$defs/", "")
                    result[key] = f"#/components/schemas/{ref_name}"
                elif isinstance(value, dict):
                    result[key] = _convert_refs_to_components(value, components_schemas)
                elif isinstance(value, list):
                    result[key] = [
                        _convert_refs_to_components(item, components_schemas)
                        if isinstance(item, dict)
                        else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        elif isinstance(schema_obj, list):
            return [
                _convert_refs_to_components(item, components_schemas)
                if isinstance(item, dict)
                else item
                for item in schema_obj
            ]
        else:
            return schema_obj

    # Add paths from all route info
    for route_info in all_route_info:
        path = route_info["path"]
        method = route_info["method"]

        if path not in schema["paths"]:
            schema["paths"][path] = {}

        operation = {
            "summary": route_info["summary"],
            "description": route_info["description"],
            "operationId": route_info["handler"],
            "tags": route_info["tags"],
            "responses": {
                "200": {
                    "description": "Successful Response",
                },
                "422": {
                    "description": "Validation Error",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"detail": {"type": "string"}},
                            }
                        }
                    },
                },
            },
        }

        # Add request body if applicable
        if route_info["body_param"]:
            _, body_type = route_info["body_param"]

            # Generate the schema for this specific type
            body_schema = msgspec.json.schema(body_type)

            # Convert any $defs to refs to components/schemas
            body_schema = _convert_refs_to_components(
                body_schema, schema["components"]["schemas"]
            )

            operation["requestBody"] = {
                "content": {"application/json": {"schema": body_schema}},
                "required": True,
            }

        # Add response schema if applicable
        if route_info["return_type"]:
            return_type = route_info["return_type"]

            # Generate the schema for this specific return type
            response_schema = msgspec.json.schema(return_type)

            # Convert any $defs to refs to components/schemas
            response_schema = _convert_refs_to_components(
                response_schema, schema["components"]["schemas"]
            )

            operation["responses"]["200"]["content"] = {
                "application/json": {"schema": response_schema}
            }

        schema["paths"][path][method] = operation

    return schema


def add_openapi_routes(
    app,
    openapi_path: str = "/openapi.json",
    docs_path: str = "/docs",
    title: str = "API",
    version: str = "0.1.0",
    description: str = "API Documentation",
):
    """Add OpenAPI documentation routes to a Starlette application."""

    def generate_swagger_html() -> str:
        """Generate Swagger UI HTML."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title} - Swagger UI</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        const ui = SwaggerUIBundle({{
            url: '{openapi_path}',
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            deepLinking: true
        }});
    </script>
</body>
</html>"""

    # Create route handlers
    async def openapi_endpoint(request):
        if openapi_endpoint._cache is None:
            openapi_endpoint._cache = generate_openapi_schema(app, title, version, description)

        return JSONResponse(openapi_endpoint._cache)
    openapi_endpoint._cache = None

    async def docs_endpoint(request):
        if docs_endpoint._cache is None:
            openapi_endpoint._cache = generate_swagger_html()

        return HTMLResponse(openapi_endpoint._cache)
    docs_endpoint._cache = None

    # Add routes to the app
    from starlette.routing import Route

    app.routes.append(Route(openapi_path, openapi_endpoint))
    app.routes.append(Route(docs_path, docs_endpoint))
