from django.urls import include, path


urlpatterns = [
    path("", include("resolwe.api_urls")),
    path(r"saml2/", include("djangosaml2.urls")),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]
