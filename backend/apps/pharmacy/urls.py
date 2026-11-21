from django.urls import path

from apps.pharmacy.views import (
    AdjustView,
    DrugDetailView,
    DrugView,
    GoodsReceiptView,
    InventoryView,
    PurchaseOrderView,
    ReturnView,
    SaleView,
    SupplierView,
)

urlpatterns = [
    path("pharmacy/inventory", InventoryView.as_view(), name="pharmacy-inventory"),
    path("pharmacy/drugs", DrugView.as_view(), name="pharmacy-drugs"),
    path("pharmacy/drugs/<uuid:drug_id>", DrugDetailView.as_view(), name="pharmacy-drug"),
    path("pharmacy/suppliers", SupplierView.as_view(), name="pharmacy-suppliers"),
    path("pharmacy/purchase-orders", PurchaseOrderView.as_view(), name="pharmacy-pos"),
    path("pharmacy/grn", GoodsReceiptView.as_view(), name="pharmacy-grn"),
    path("pharmacy/sales", SaleView.as_view(), name="pharmacy-sales"),
    path("pharmacy/returns", ReturnView.as_view(), name="pharmacy-returns"),
    path("pharmacy/adjust", AdjustView.as_view(), name="pharmacy-adjust"),
]
