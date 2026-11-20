from django.contrib import admin

from apps.numbering.models import NumberSequence


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = (
        "document_type",
        "prefix",
        "next_value",
        "financial_year",
        "organization",
        "facility",
    )
    list_filter = ("document_type",)
