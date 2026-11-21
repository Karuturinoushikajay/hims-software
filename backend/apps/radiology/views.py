from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.radiology import pdfs, services
from apps.radiology.models import RadiologyDepartment


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class CatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(
            {
                "tests": services.list_tests(facility),
                "templates": services.list_templates(facility),
                "consumables": services.list_consumables(facility),
                "departments": [{"value": c.value, "label": c.label} for c in RadiologyDepartment],
            }
        )


class TestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(services.list_tests(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_test(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class TestConsumableLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, test_id):
        facility = _facility(request)
        return Response(
            services.link_consumable(
                actor=request.user,
                facility=facility,
                test_id=test_id,
                data=request.data,
                request=request,
            ),
            status=201,
        )


class TemplateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(services.list_templates(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_template(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class ConsumableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(services.list_consumables(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_consumable(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class ConsumableAdjustView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.adjust_consumable(
                actor=request.user, facility=facility, data=request.data, request=request
            )
        )


class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
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
        require_permission(request.user, facility, "radiology.read")
        return Response(services.get_order(facility, order_id))


class WorklistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(
            services.worklist(
                facility,
                department=request.query_params.get("department") or "",
                status=request.query_params.get("status") or "",
            )
        )


class ScheduleBoardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        return Response(
            services.schedule_board(facility, on_date=request.query_params.get("date") or "")
        )


class ScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.schedule_item(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class StartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.start_study(
                actor=request.user, facility=facility, item_id=item_id, request=request
            )
        )


class CompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.complete_study(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
            )
        )


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        facility = _facility(request)
        return Response(
            services.save_report(
                actor=request.user,
                facility=facility,
                item_id=item_id,
                data=request.data,
                request=request,
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


class ReportPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        facility = _facility(request)
        require_permission(request.user, facility, "radiology.read")
        order = services._order(facility, order_id)
        content = pdfs.render_radiology_report_pdf(order)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{order.rad_no}.pdf"'
        return response
