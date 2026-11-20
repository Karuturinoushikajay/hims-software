from django.urls import path

from apps.numbering.views import NumberSequenceListView

urlpatterns = [
    path("number-sequences", NumberSequenceListView.as_view(), name="number-sequences"),
]
