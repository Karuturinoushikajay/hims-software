from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.laboratory import pdfs, services
from apps.laboratory.models import LabDepartment


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class CatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(
            {
                "tests": services.list_tests(facility),
                "packages": services.list_packages(facility),
                "reagents": services.list_reagents(facility),
                "departments": [{"value": c.value, "label": c.label} for c in LabDepartment],
                "critical": services.critical_alerts(facility),
            }
        )


class TestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(services.list_tests(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_test(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class TestFieldView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, test_id):
        facility = _facility(request)
        return Response(
            services.add_test_field(
                actor=request.user,
                facility=facility,
                test_id=test_id,
                data=request.data,
                request=request,
            ),
            status=201,
        )


class TestReagentLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, test_id):
        facility = _facility(request)
        return Response(
            services.link_reagent(
                actor=request.user,
                facility=facility,
                test_id=test_id,
                data=request.data,
                request=request,
            ),
            status=201,
        )


class PackageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(services.list_packages(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_package(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class ReagentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(services.list_reagents(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_reagent(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class ReagentAdjustView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.adjust_reagent(
                actor=request.user, facility=facility, data=request.data, request=request
            )
        )


class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(
            services.list_orders(
                facility,
                status=request.query_params.get("status") or "",
                department=request.query_params.get("department") or "",
                q=request.query_params.get("q") or "",
            )
        )

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.register_order(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(services.get_order(facility, order_id))


class WorklistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        return Response(
            services.worklist(
                facility,
                department=request.query_params.get("department") or "",
                status=request.query_params.get("status") or "",
            )
        )


class CollectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.collect_sample(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class ReceiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.receive_sample(
                actor=request.user, facility=facility, item_id=item_id, request=request
            )
        )


class ResultView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.enter_results(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class AmendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.amend_results(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class VerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.verify_item(
                actor=request.user, facility=facility, item_id=item_id, request=request
            )
        )


class AuthorizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.authorize_item(
                actor=request.user, facility=facility, item_id=item_id, request=request
            )
        )


class DispatchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.dispatch_item(
                actor=request.user, facility=facility, item_id=item_id, request=request
            )
        )


class CancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.cancel_item(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class BarcodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.barcode_label(actor=request.user, facility=facility, item_id=item_id)
        )


class ReportPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        facility = _facility(request)
        require_permission(request.user, facility, "laboratory.read")
        order = services._order(facility, order_id)
        content = pdfs.render_lab_report_pdf(order)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{order.lab_no}.pdf"'
        return response
