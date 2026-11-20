from rest_framework import serializers


class AppointmentSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    doctor_id = serializers.UUIDField()
    source = serializers.ChoiceField(choices=["WALKIN", "ONLINE"])


class ConsultationSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    doctor_id = serializers.UUIDField()
    appointment_id = serializers.UUIDField(required=False, allow_null=True)
    patient_type = serializers.CharField(required=False, allow_blank=True)
    party_id = serializers.UUIDField(required=False, allow_null=True)
    referral_doctor_id = serializers.UUIDField(required=False, allow_null=True)
    pro_id = serializers.UUIDField(required=False, allow_null=True)
    attendant_relation = serializers.CharField(required=False, allow_blank=True)
    attendant_name = serializers.CharField(required=False, allow_blank=True)
    attendant_mobile = serializers.CharField(required=False, allow_blank=True)
    insurance_covered = serializers.BooleanField(required=False)
    remarks = serializers.CharField(required=False, allow_blank=True)
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    bp_systolic = serializers.IntegerField(required=False, allow_null=True)
    bp_diastolic = serializers.IntegerField(required=False, allow_null=True)
    temperature_f = serializers.DecimalField(max_digits=5, decimal_places=1, required=False, allow_null=True)
    discount_type = serializers.CharField(required=False, allow_blank=True)
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    payment_mode = serializers.CharField(required=False, allow_blank=True)


class ProcedureSerializer(serializers.Serializer):
    patient_id = serializers.UUIDField()
    procedure_id = serializers.UUIDField()
    doctor_id = serializers.UUIDField(required=False, allow_null=True)
    discount_type = serializers.CharField(required=False, allow_blank=True)
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    payment_mode = serializers.CharField(required=False, allow_blank=True)
