import inspect
import functools
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    get_type_hints,
    get_origin,
    get_args,
)
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.applications import Starlette
import msgspec


class MsgspecRouter:
    """Router that handles routes with msgspec integration."""

    @classmethod
    def mount_routers(
        cls, app: Starlette, prefix: str, routers: list["MsgspecRouter"]
    ):
        all_routes = []
        for router in routers:
            all_routes.extend(router.routes)
            # Update route_info paths to include mount prefix for OpenAPI
            for route_info in router.route_info:
                route_info["path"] = prefix + route_info["path"]
            router._register_with_openapi(app)

        app.routes.append(Mount(prefix, routes=all_routes))

    def __init__(
        self,
        prefix: str = "",
        tags: Optional[List[str]] = None,
    ):
        self.routes = []
        self.prefix = prefix
        self.tags = tags or []
        self.registered_models = set()
        self.route_info = []

    def route(
        self,
        path: str,
        method: Optional[str | list[str]] = "GET",
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a route handler."""

        def decorator(func: Callable):
            signature = inspect.signature(func)
            type_hints = get_type_hints(func, include_extras=True)

            # Check for body parameter
            body_param = None
            if "body" in signature.parameters and "body" in type_hints:
                body_type = type_hints["body"]
                body_param = ("body", body_type)
                # Register the model for OpenAPI
                self.registered_models.add(body_type)

            # Get return type for response schema
            return_type = type_hints.get("return")
            if return_type:
                # Handle List[Type], etc.
                if get_origin(return_type):
                    args = get_args(return_type)
                    if args:
                        model_type = args[0]
                        if hasattr(model_type, "__annotations__"):
                            self.registered_models.add(model_type)
                # Direct type
                elif hasattr(return_type, "__annotations__"):
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
                        return JSONResponse({"detail": str(e)}, status_code=422)

                # Call the handler function
                result = await func(**kwargs)

                # Return JSONResponse with msgspec encoding
                response = JSONResponse(msgspec.to_builtins(result))

                return response

            # Store route information for OpenAPI
            # Combine router-level tags with endpoint-level tags
            combined_tags = list(self.tags)  # Start with router tags
            if tags:
                combined_tags.extend(tags)  # Add endpoint tags

            route_info = {
                "path": self.prefix + path,
                "method": method.lower(),
                "tags": combined_tags,
                "summary": summary or func.__name__,
                "description": description or func.__doc__ or "",
                "body_param": body_param,
                "return_type": return_type,
                "handler": func.__name__,
            }

            self.route_info.append(route_info)

            # Create Starlette Route
            route = Route(self.prefix + path, endpoint, methods=[method])

            self.routes.append(route)
            return func

        return decorator

    def get(
        self,
        path: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a GET route handler."""
        return self.route(path, "GET", tags, summary, description)

    def post(
        self,
        path: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a POST route handler."""
        return self.route(path, "POST", tags, summary, description)

    def put(
        self,
        path: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a PUT route handler."""
        return self.route(path, "PUT", tags, summary, description)

    def delete(
        self,
        path: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a DELETE route handler."""
        return self.route(path, "DELETE", tags, summary, description)

    def patch(
        self,
        path: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Decorator for registering a PATCH route handler."""
        return self.route(path, "PATCH", tags, summary, description)

    def register_routes(self, app: Starlette):
        """Include this router's routes in a Starlette application."""
        app.routes.extend(self.routes)

        self._register_with_openapi(app)

    def _register_with_openapi(self, app: Starlette):
        # Register this router's metadata with the app for OpenAPI generation
        if not hasattr(app, "_msgspec_routers"):
            app._msgspec_routers = []
        app._msgspec_routers.append(self)

    def _convert_refs_to_components(
        self, schema_obj: Dict[str, Any], components_schemas: Dict[str, Any]
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
                    result[key] = self._convert_refs_to_components(
                        value, components_schemas
                    )
                elif isinstance(value, list):
                    result[key] = [
                        self._convert_refs_to_components(item, components_schemas)
                        if isinstance(item, dict)
                        else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        elif isinstance(schema_obj, list):
            return [
                self._convert_refs_to_components(item, components_schemas)
                if isinstance(item, dict)
                else item
                for item in schema_obj
            ]
        else:
            return schema_obj
