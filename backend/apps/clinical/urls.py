from django.urls import path

from apps.clinical.views import (
    AllergyView,
    AttachmentView,
    CatalogView,
    FollowUpView,
    OrderView,
    PrescriptionPdfView,
    PrescriptionView,
    SummaryPdfView,
    TimelineView,
    VisitNoteView,
)

urlpatterns = [
    path("clinical/catalog", CatalogView.as_view(), name="clinical-catalog"),
    path("clinical/patients/<uuid:patient_id>/timeline", TimelineView.as_view(), name="clinical-timeline"),
    path("clinical/visits/<uuid:visit_id>/note", VisitNoteView.as_view(), name="clinical-visit-note"),
    path("clinical/visits/<uuid:visit_id>/summary.pdf", SummaryPdfView.as_view(), name="clinical-summary-pdf"),
    path("clinical/allergies", AllergyView.as_view(), name="clinical-allergies"),
    path("clinical/prescriptions", PrescriptionView.as_view(), name="clinical-prescriptions"),
    path(
        "clinical/prescriptions/<uuid:prescription_id>.pdf",
        PrescriptionPdfView.as_view(),
        name="clinical-prescription-pdf",
    ),
    path("clinical/orders", OrderView.as_view(), name="clinical-orders"),
    path("clinical/follow-ups", FollowUpView.as_view(), name="clinical-follow-ups"),
    path("clinical/attachments", AttachmentView.as_view(), name="clinical-attachments"),
]
