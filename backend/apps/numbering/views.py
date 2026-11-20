from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.numbering.models import NumberSequence


class NumberSequenceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = getattr(request, "facility", None)
        if not facility:
            raise AppError("No active facility.", code="no_facility")
        require_permission(request.user, facility, "numbering.read")

        facility_seqs = NumberSequence.objects.filter(facility=facility).order_by(
            "document_type", "financial_year"
        )
        org_seqs = NumberSequence.objects.filter(
            organization=facility.organization
        ).order_by("document_type")

        def serialize(seq):
            return {
                "id": str(seq.id),
                "document_type": seq.document_type,
                "financial_year": seq.financial_year,
                "prefix": seq.prefix,
                "next_value": seq.next_value,
                "padding": seq.padding,
                "owner": "organization" if seq.organization_id else "facility",
            }

        return Response(
            {
                "organization": [serialize(s) for s in org_seqs],
                "facility": [serialize(s) for s in facility_seqs],
            }
        )
