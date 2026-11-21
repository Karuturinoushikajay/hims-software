from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.pharmacy import services


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class InventoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "pharmacy.read")
        days = int(request.query_params.get("near_expiry_days") or 30)
        return Response(services.inventory_snapshot(facility, near_expiry_days=days))


class DrugView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "pharmacy.read")
        return Response(services.list_drugs(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_drug(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class DrugDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, drug_id):
        facility = _facility(request)
        return Response(
            services.update_drug_pharmacy(
                actor=request.user, facility=facility, drug_id=drug_id, data=request.data, request=request
            )
        )


class SupplierView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "pharmacy.read")
        return Response(services.list_suppliers(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_supplier(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class PurchaseOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "pharmacy.read")
        return Response(services.list_purchase_orders(facility))

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.create_purchase_order(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class GoodsReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.receive_goods(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class SaleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.sell(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class ReturnView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.return_sale_line(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class AdjustView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.adjust_stock(actor=request.user, facility=facility, data=request.data, request=request)
        )
