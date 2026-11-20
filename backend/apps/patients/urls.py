from django.urls import path

from apps.patients.views import (
    PatientDetailView,
    PatientRecentView,
    PatientSearchView,
    RegisterView,
)

urlpatterns = [
    path("patients/search", PatientSearchView.as_view(), name="patient-search"),
    path("patients/recent", PatientRecentView.as_view(), name="patient-recent"),
    path("patients/register", RegisterView.as_view(), name="patient-register"),
    path("patients/<uuid:patient_id>", PatientDetailView.as_view(), name="patient-detail"),
]
