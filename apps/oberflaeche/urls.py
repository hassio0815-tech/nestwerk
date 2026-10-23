from django.urls import path

from apps.oberflaeche import views

app_name = "oberflaeche"

urlpatterns = [
    path("styleguide/", views.styleguide, name="styleguide"),
]
