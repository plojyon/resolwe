from rest_framework import response, views

from .models import Observer, Subscriber


class QueryObserverSubscribeView(views.APIView):
    def post(self, request):
        """Handle a query observer subscription request."""
        try:
            session_id = request.query_params["subscriber"]
            table = request.query_params["table"]
            type_of_change = request.query_params["type_of_change"]
        except KeyError:
            return response.Response(status=400)

        try:
            primary_key = request.query_params["primary_key"]
        except KeyError:
            primary_key = None

        observer = Observer.objects.get_or_create(
            table=table, resource=primary_key, change_type=type_of_change
        )
        subscriber = Subscriber.objects.get(session_id=session_id)

        observer.subscribers.add(subscriber)
        return response.Response()


class QueryObserverUnsubscribeView(views.APIView):
    def post(self, request):
        """Handle a query observer unsubscription request."""
        try:
            session_id = request.query_params["subscriber"]
            table = request.query_params["table"]
            type_of_change = request.query_params["type_of_change"]
        except KeyError:
            return response.Response(status=400)

        try:
            primary_key = request.query_params["primary_key"]
        except KeyError:
            primary_key = None

        observer = Observer.objects.get_or_create(
            table=table, resource=primary_key, change_type=type_of_change
        )
        subscriber = Subscriber.objects.get(session_id=session_id)

        observer.subscribers.remove(subscriber)
        return response.Response()
