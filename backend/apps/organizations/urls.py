from django.urls import path

from apps.organizations.views import (
    FacilityListCreateView,
    FacilitySettingsView,
    OrganizationListCreateView,
)

urlpatterns = [
    path("organizations", OrganizationListCreateView.as_view(), name="organizations"),
    path("facilities", FacilityListCreateView.as_view(), name="facilities"),
    path(
        "facilities/<uuid:facility_id>/settings",
        FacilitySettingsView.as_view(),
        name="facility-settings",
    ),
]
