from django.urls import path

from apps.ipd.views import (
    AdmissionDetailView,
    AdmissionView,
    BedBoardView,
    CancelAdmissionView,
    CancelDischargeView,
    CertificatePdfView,
    CertificateView,
    DailyChargeView,
    DischargePdfView,
    DischargeSummaryView,
    DoctorOrderView,
    MarView,
    NursingNoteView,
    SettlementPreviewView,
    SettleView,
    TransferBedView,
    TransferDoctorView,
)

urlpatterns = [
    path("ipd/bed-board", BedBoardView.as_view(), name="ipd-bed-board"),
    path("ipd/admissions", AdmissionView.as_view(), name="ipd-admissions"),
    path("ipd/admissions/<uuid:admission_id>", AdmissionDetailView.as_view(), name="ipd-admission"),
    path(
        "ipd/admissions/<uuid:admission_id>/transfer-doctor",
        TransferDoctorView.as_view(),
        name="ipd-transfer-doctor",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/transfer-bed",
        TransferBedView.as_view(),
        name="ipd-transfer-bed",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/nursing-notes",
        NursingNoteView.as_view(),
        name="ipd-nursing",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/doctor-orders",
        DoctorOrderView.as_view(),
        name="ipd-orders",
    ),
    path("ipd/admissions/<uuid:admission_id>/mar", MarView.as_view(), name="ipd-mar"),
    path(
        "ipd/admissions/<uuid:admission_id>/discharge-summary",
        DischargeSummaryView.as_view(),
        name="ipd-discharge-summary",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/settlement",
        SettlementPreviewView.as_view(),
        name="ipd-settlement",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/settle",
        SettleView.as_view(),
        name="ipd-settle",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/cancel-discharge",
        CancelDischargeView.as_view(),
        name="ipd-cancel-discharge",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/cancel",
        CancelAdmissionView.as_view(),
        name="ipd-cancel-admission",
    ),
    path(
        "ipd/admissions/<uuid:admission_id>/discharge.pdf",
        DischargePdfView.as_view(),
        name="ipd-discharge-pdf",
    ),
    path("ipd/daily-charges", DailyChargeView.as_view(), name="ipd-daily-charges"),
    path("ipd/certificates", CertificateView.as_view(), name="ipd-certificates"),
    path(
        "ipd/certificates/<uuid:cert_id>/pdf",
        CertificatePdfView.as_view(),
        name="ipd-certificate-pdf",
    ),
]
