import inspect
import functools
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, get_type_hints, get_origin, get_args
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
import msgspec

T = TypeVar("T")

class Body(Generic[T]):
    """Wrapper for request body data."""
    def __init__(self, value: T):
        self.value = value


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
            
            # Check for Body parameter
            body_param = None
            for param_name, param in signature.parameters.items():
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    origin = get_origin(param_type)
                    if origin is Body:
                        body_param = (param_name, get_args(param_type)[0])
                        # Register the model for OpenAPI
                        self.registered_models.add(body_param[1])
            
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
                        kwargs[body_param[0]] = Body(body_data)
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
    
    def include_router(self, app):
        """Include this router's routes in a Starlette application."""
        for route in self.routes:
            app.routes.append(route)

