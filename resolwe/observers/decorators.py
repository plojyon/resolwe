import functools
import inspect

from rest_framework import response

from . import observer
from . import request as observer_request


def observable(viewset):
    """Make a ViewSet observable.

    If decorated method returns a response containing a list of items, it must
    use the provided `LimitOffsetPagination` for any pagination. In case a
    non-list response is returned, the resulting item will be wrapped into a
    list.

    When multiple decorators are used, `observable` must be the first one to be
    applied as it needs access to the method name.
    """

    if inspect.isclass(viewset):
        list_method = getattr(viewset, "list", None)
        if list_method is not None:
            viewset.list = observable(list_method)

        return viewset

    # Do not decorate an already observable method twice.
    if getattr(viewset, "is_observable", False):
        return viewset

    @functools.wraps(viewset)
    def wrapper(self, request, *args, **kwargs):
        if observer_request.OBSERVABLE_QUERY_PARAMETER in request.query_params:
            # TODO: Validate the session identifier.
            session_id = request.query_params[
                observer_request.OBSERVABLE_QUERY_PARAMETER
            ]

            # Create request and subscribe the session to given observer.
            request = observer_request.Request(
                self.__class__, viewset.__name__, request, args, kwargs
            )

            # Initialize observer and subscribe.
            instance = observer.QueryObserver(request)
            data = instance.subscribe(session_id)

            return response.Response({"observer": instance.id, "items": data})
        else:
            # Non-reactive API.
            return viewset(self, request, *args, **kwargs)

    wrapper.is_observable = True

    return wrapper
