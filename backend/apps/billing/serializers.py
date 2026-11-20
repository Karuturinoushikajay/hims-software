from rest_framework import serializers

from apps.billing.models import PaymentMode


class ChargeSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    description = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    hospital_share = serializers.DecimalField(max_digits=14, decimal_places=2)
    doctor_share = serializers.DecimalField(max_digits=14, decimal_places=2)
    tax_category_id = serializers.UUIDField(required=False, allow_null=True)
    discount_type = serializers.CharField(required=False, allow_blank=True)
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    mode = serializers.ChoiceField(
        choices=[m for m in PaymentMode.values if m != PaymentMode.ADVANCE],
        required=False,
        default=PaymentMode.CASH,
    )


class CollectDueSerializer(serializers.Serializer):
    bill_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    mode = serializers.ChoiceField(choices=[m for m in PaymentMode.values if m != PaymentMode.ADVANCE])


class AdvanceSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    mode = serializers.ChoiceField(choices=[m for m in PaymentMode.values if m != PaymentMode.ADVANCE])


class ApplyAdvanceSerializer(serializers.Serializer):
    bill_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class AmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class RefundSerializer(serializers.Serializer):
    bill_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    mode = serializers.ChoiceField(choices=[m for m in PaymentMode.values if m != PaymentMode.ADVANCE])
    reason = serializers.CharField(max_length=255)


class AuthorizeSerializer(serializers.Serializer):
    approve = serializers.BooleanField()


class CreditNoteSerializer(serializers.Serializer):
    bill_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=255)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    mode = serializers.ChoiceField(
        choices=[m for m in PaymentMode.values if m != PaymentMode.ADVANCE],
        required=False,
        default=PaymentMode.CASH,
    )


class OpeningCashSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(max_digits=14, decimal_places=2)


class CountedCashSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(max_digits=14, decimal_places=2)


class DiscountRequestSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    doctor_id = serializers.UUIDField()
    discount_type = serializers.CharField(required=False, allow_blank=True)
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    payment_mode = serializers.CharField(required=False, allow_blank=True)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    bp_systolic = serializers.IntegerField(required=False)
    temperature_f = serializers.DecimalField(max_digits=5, decimal_places=1, required=False)
