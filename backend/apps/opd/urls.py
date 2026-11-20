from django.urls import path

from apps.opd.views import AppointmentView, ConsultationView, LookupView, ProcedureOrderView

urlpatterns = [
    path("opd/lookups", LookupView.as_view(), name="opd-lookups"),
    path("opd/appointments", AppointmentView.as_view(), name="opd-appointments"),
    path("opd/consultations", ConsultationView.as_view(), name="opd-consultations"),
    path("opd/procedures", ProcedureOrderView.as_view(), name="opd-procedures"),
]
