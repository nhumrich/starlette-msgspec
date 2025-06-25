import inspect
import functools
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints, get_origin, get_args
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from starlette.middleware import Middleware
import msgspec


class MsgspecRouter:
    """Router that handles routes with msgspec integration."""
    
    def __init__(self, prefix: str = "", title: str = "API", version: str = "0.1.0"):
        self.routes = []
        self.prefix = prefix
        self.title = title
        self.version = version
        self.registered_models = set()
        self.route_info = []
        
    def route(self, path: str, method: Optional[str|list[str]] = 'GET', tags: Optional[List[str]] = None, summary: Optional[str] = None,
              description: Optional[str] = None):
        """Decorator for registering a route handler."""
        def decorator(func: Callable):
            signature = inspect.signature(func)
            type_hints = get_type_hints(func, include_extras=True)
            
            # Check for body parameter
            body_param = None
            if 'body' in signature.parameters and 'body' in type_hints:
                body_type = type_hints['body']
                body_param = ('body', body_type)
                # Register the model for OpenAPI
                self.registered_models.add(body_type)
            
            # Get return type for response schema
            return_type = type_hints.get('return')
            if return_type:
                # Handle List[Type], etc.
                if get_origin(return_type):
                    args = get_args(return_type)
                    if args:
                        model_type = args[0]
                        if hasattr(model_type, '__annotations__'):
                            self.registered_models.add(model_type)
                # Direct type
                elif hasattr(return_type, '__annotations__'):
                    self.registered_models.add(return_type)
            
            @functools.wraps(func)
            async def endpoint(request: Request):
                kwargs = {}
                
                # Handle body parameter if it exists
                if body_param:
                    body_raw = await request.body()
                    try:
                        body_data = msgspec.json.decode(body_raw, type=body_param[1])
                        kwargs[body_param[0]] = body_data
                    except msgspec.ValidationError as e:
                        return JSONResponse(
                            {"detail": str(e)},
                            status_code=422
                        )
                
                # Call the handler function
                result = await func(**kwargs)
                
                # Return JSONResponse with msgspec encoding
                response = JSONResponse(
                    msgspec.to_builtins(result)
                )
                
                return response
            
            # Store route information for OpenAPI
            route_info = {
                "path": path,
                "method": method.lower(),
                "tags": tags or [],
                "summary": summary or func.__name__,
                "description": description or func.__doc__ or "",
                "body_param": body_param,
                "return_type": return_type,
                "handler": func.__name__
            }
            
            self.route_info.append(route_info)
            
            # Create Starlette Route
            route = Route(
                self.prefix + path,
                endpoint,
                methods=[method]
            )
            
            self.routes.append(route)
            return func
            
        return decorator
    
    def get(self, path: str, tags: Optional[List[str]] = None, summary: Optional[str] = None, description: Optional[str] = None):
        """Decorator for registering a GET route handler."""
        return self.route(path, "GET", tags, summary, description)
    
    def post(self, path: str, tags: Optional[List[str]] = None, summary: Optional[str] = None, description: Optional[str] = None):
        """Decorator for registering a POST route handler."""
        return self.route(path, "POST", tags, summary, description)
    
    def put(self, path: str, tags: Optional[List[str]] = None, summary: Optional[str] = None, description: Optional[str] = None):
        """Decorator for registering a PUT route handler."""
        return self.route(path, "PUT", tags, summary, description)
    
    def delete(self, path: str, tags: Optional[List[str]] = None, summary: Optional[str] = None, description: Optional[str] = None):
        """Decorator for registering a DELETE route handler."""
        return self.route(path, "DELETE", tags, summary, description)
    
    def patch(self, path: str, tags: Optional[List[str]] = None, summary: Optional[str] = None, description: Optional[str] = None):
        """Decorator for registering a PATCH route handler."""
        return self.route(path, "PATCH", tags, summary, description)
    
    def include_router(self, app):
        """Include this router's routes in a Starlette application."""
        for route in self.routes:
            app.routes.append(route)
        
        # Register this router's metadata with the app for OpenAPI generation
        if not hasattr(app, '_msgspec_routers'):
            app._msgspec_routers = []
        app._msgspec_routers.append(self)
    
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
    
    def generate_openapi_schema(self) -> Dict[str, Any]:
        """Generate the OpenAPI schema using msgspec's schema generation."""
        # Generate component schemas for all registered models
        schemas, components = msgspec.json.schema_components(
            self.registered_models,
            ref_template="#/components/schemas/{name}"
        )
        
        # Create the base OpenAPI schema
        schema = {
            "openapi": "3.0.2",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": getattr(self, 'description', 'API Documentation'),
            },
            "paths": {},
            "components": {
                "schemas": components
            }
        }
        
        # Add paths from route info
        for route_info in self.route_info:
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


def generate_openapi_schema(app, title: str = "API", version: str = "0.1.0", description: str = "API Documentation") -> Dict[str, Any]:
    """Generate OpenAPI schema from all registered routers in the app."""
    if not hasattr(app, '_msgspec_routers') or not app._msgspec_routers:
        # Fallback: create empty schema if no routers registered
        return {
            "openapi": "3.0.2",
            "info": {
                "title": title,
                "version": version,
                "description": description,
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
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
            all_models,
            ref_template="#/components/schemas/{name}"
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
        "components": {
            "schemas": components
        }
    }
    
    # Helper function to convert refs (reuse from router)
    def _convert_refs_to_components(schema_obj: Dict[str, Any], components_schemas: Dict[str, Any]) -> Dict[str, Any]:
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
                    result[key] = _convert_refs_to_components(value, components_schemas)
                elif isinstance(value, list):
                    result[key] = [
                        _convert_refs_to_components(item, components_schemas) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        elif isinstance(schema_obj, list):
            return [
                _convert_refs_to_components(item, components_schemas) if isinstance(item, dict) else item
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
            body_schema = _convert_refs_to_components(body_schema, schema["components"]["schemas"])
            
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
            response_schema = _convert_refs_to_components(response_schema, schema["components"]["schemas"])
            
            operation["responses"]["200"]["content"] = {
                "application/json": {
                    "schema": response_schema
                }
            }
        
        schema["paths"][path][method] = operation
        
    return schema


def add_openapi_routes(app, router: MsgspecRouter = None, openapi_path: str = "/openapi.json", docs_path: str = "/docs", title: str = "API", version: str = "0.1.0", description: str = "API Documentation"):
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
        schema = generate_openapi_schema(app, title, version, description)
        return JSONResponse(schema)
    
    async def docs_endpoint(request):
        html = generate_swagger_html()
        return HTMLResponse(html)
    
    # Add routes to the app
    from starlette.routing import Route
    app.routes.append(Route(openapi_path, openapi_endpoint))
    app.routes.append(Route(docs_path, docs_endpoint))

