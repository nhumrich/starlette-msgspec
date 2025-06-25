from typing import Any, Dict, List, Set, Type, Optional, get_origin, get_args, get_type_hints
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse, HTMLResponse
from starlette.requests import Request
from starlette.routing import Route, BaseRoute
from starlette.applications import Starlette
import msgspec
import inspect

# Global registry for routes when introspection doesn't work
_route_registry: Dict[str, List[Dict]] = {}
_model_registry: Dict[str, Set[Type]] = {}

def register_routes_for_app(app: ASGIApp, routes_info: List[Dict], models: Set[Type]):
    """Register routes and models for an app in the global registry."""
    app_id = str(id(app))
    _route_registry[app_id] = routes_info
    _model_registry[app_id] = models

class OpenAPIMiddleware:
    """Middleware to add OpenAPI documentation using msgspec's schema generation."""
    
    def __init__(
        self,
        app: ASGIApp,
        title: str = "API",
        version: str = "0.1.0",
        description: str = "API Documentation"
    ):
        self.app = app
        self.title = title
        self.version = version
        self.description = description
        
        # Paths for OpenAPI documentation
        self.openapi_path = "/openapi.json"
        self.docs_path = "/docs"
        
        # Use provided routes/models or introspect lazily
        self.routes_info = []
        self.models = set()
        self._introspected = False
        self._app_id = id(app)  # Store app ID for registry lookup

    def _introspect_app(self):
        """Introspect the Starlette app to extract route information and models."""
        if self._introspected:
            return
        
        # First try to get from global registry
        app_id_str = str(self._app_id)
        if app_id_str in _route_registry:
            self.routes_info = _route_registry[app_id_str]
            self.models = _model_registry.get(app_id_str, set())
            self._introspected = True
            return
            
        # Try to find routes from the app
        target_app = self._find_app_with_routes()
        
        if not target_app or not hasattr(target_app, 'routes'):
            return
            
        for route in target_app.routes:
            if isinstance(route, Route) and hasattr(route, 'endpoint'):
                self._extract_route_info(route)
        
        self._introspected = True
    
    def _find_app_with_routes(self):
        """Find the app instance that has routes, handling middleware wrapping."""
        # Start with the current app
        target_app = self.app
        
        # If this app has routes, use it
        if hasattr(target_app, 'routes') and target_app.routes:
            return target_app
            
        # Try to find the inner app through middleware chain
        current = target_app
        visited = set()
        
        while hasattr(current, 'app') and current not in visited:
            visited.add(current)
            current = current.app
            if hasattr(current, 'routes') and current.routes:
                return current
                
        return target_app
    
    def _extract_route_info(self, route: Route):
        """Extract route information from a Starlette Route."""
        endpoint = route.endpoint
        if not callable(endpoint):
            return
            
        # Get function signature and type hints
        try:
            signature = inspect.signature(endpoint)
            type_hints = get_type_hints(endpoint, include_extras=True)
        except (ValueError, TypeError):
            return
            
        # Check for Body parameter
        body_param = None
        for param_name, param in signature.parameters.items():
            if param_name in type_hints:
                param_type = type_hints[param_name]
                origin = get_origin(param_type)
                # Check if it's a Body type - handle both direct import and module reference
                if origin and (
                    getattr(origin, '__name__', None) == 'Body' or
                    str(origin).endswith('.Body') or
                    (hasattr(origin, '__module__') and 
                     origin.__module__ == 'starlette_msgspec.router' and 
                     origin.__name__ == 'Body')
                ):
                    args = get_args(param_type)
                    if args:
                        body_param = (param_name, args[0])
                        self.models.add(args[0])
        
        # Get return type for response schema
        return_type = type_hints.get('return')
        if return_type:
            # Handle List[Type], etc.
            if get_origin(return_type):
                args = get_args(return_type)
                if args:
                    model_type = args[0]
                    if hasattr(model_type, '__annotations__'):
                        self.models.add(model_type)
            # Direct type
            elif hasattr(return_type, '__annotations__'):
                self.models.add(return_type)
        
        # Extract route info
        for method in route.methods or ['GET']:
            route_info = {
                "path": route.path,
                "method": method.lower(),
                "tags": getattr(endpoint, '_tags', []),
                "summary": getattr(endpoint, '_summary', None) or endpoint.__name__,
                "description": getattr(endpoint, '_description', None) or endpoint.__doc__ or "",
                "body_param": body_param,
                "return_type": return_type,
                "handler": endpoint.__name__
            }
            self.routes_info.append(route_info)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            assert self.app is not None, "ASGI app must be provided"
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        
        if path == self.openapi_path:
            # Return the OpenAPI schema
            schema = self.generate_openapi_schema()
            response = JSONResponse(schema)
            await response(scope, receive, send)
            return

        if path == self.docs_path:
            # Return Swagger UI HTML
            html = self.generate_swagger_html()
            response = HTMLResponse(html)
            await response(scope, receive, send)
            return
            
        # Not an OpenAPI route, proceed with the app
        assert self.app is not None, "ASGI app must be provided"
        await self.app(scope, receive, send)
    
    def generate_openapi_schema(self) -> Dict[str, Any]:
        """Generate the OpenAPI schema using msgspec's schema generation."""
        # Perform lazy introspection
        self._introspect_app()
        # Generate component schemas for all registered models
        schemas, components = msgspec.json.schema_components(
            self.models,
            ref_template="#/components/schemas/{name}"
        )
        
        # Create the base OpenAPI schema
        schema = {
            "openapi": "3.0.2",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": {},
            "components": {
                "schemas": components
            }
        }
        
        # Add paths from route info
        for route_info in self.routes_info:
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
                                    "properties": {
                                        "detail": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            # Add request body if applicable
            if route_info["body_param"]:
                _, body_type = route_info["body_param"]
                
                # Generate the schema for this specific type
                body_schema = msgspec.json.schema(body_type)
                
                # Convert any $defs to refs to components/schemas
                body_schema = self._convert_refs_to_components(body_schema, schema["components"]["schemas"])
                
                operation["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": body_schema
                        }
                    },
                    "required": True
                }
            
            # Add response schema if applicable
            if route_info["return_type"]:
                return_type = route_info["return_type"]
                
                # Generate the schema for this specific return type
                response_schema = msgspec.json.schema(return_type)
                
                # Convert any $defs to refs to components/schemas  
                response_schema = self._convert_refs_to_components(response_schema, schema["components"]["schemas"])
                
                operation["responses"]["200"]["content"] = {
                    "application/json": {
                        "schema": response_schema
                    }
                }
            
            schema["paths"][path][method] = operation
            
        return schema
    
    def _convert_refs_to_components(self, schema_obj: Dict[str, Any], components_schemas: Dict[str, Any]) -> Dict[str, Any]:
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
                if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                    # Convert $defs reference to components/schemas reference
                    ref_name = value.replace("#/$defs/", "")
                    result[key] = f"#/components/schemas/{ref_name}"
                elif isinstance(value, dict):
                    result[key] = self._convert_refs_to_components(value, components_schemas)
                elif isinstance(value, list):
                    result[key] = [
                        self._convert_refs_to_components(item, components_schemas) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        elif isinstance(schema_obj, list):
            return [
                self._convert_refs_to_components(item, components_schemas) if isinstance(item, dict) else item
                for item in schema_obj
            ]
        else:
            return schema_obj
    
    def generate_swagger_html(self) -> str:
        """Generate Swagger UI HTML."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{self.title} - Swagger UI</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        </head>
        <body>
            <div id="swagger-ui"></div>
            <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
            <script>
                const ui = SwaggerUIBundle({{
                    url: '{self.openapi_path}',
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
        </html>
        """