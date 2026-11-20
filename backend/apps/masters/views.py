from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.masters import services


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class MasterCatalogView(APIView):
    """Read-only bundle used by the masters screen."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "masters.read")
        return Response(
            {
                "departments": services.list_departments(facility),
                "specializations": services.list_specializations(facility),
                "doctors": services.list_doctors(facility),
                "referrals": services.list_referrals(facility),
                "pros": services.list_pros(facility),
                "parties": services.list_parties(facility),
                "procedures": services.list_procedures(facility),
                "services": services.list_services(facility),
                "room_types": services.list_room_types(facility),
                "wards": services.list_wards(facility),
                "tariffs": services.list_tariffs(facility),
                "discount_rules": services.list_discount_rules(facility),
                "payment_modes": services.list_payment_modes(facility),
                "taxes": services.list_taxes(facility),
                "templates": services.list_templates(facility),
                "countries": services.list_countries(),
                "states": services.list_states(),
                "cities": services.list_cities(),
                "areas": services.list_areas(),
            }
        )


class _WriteView(APIView):
    permission_classes = [IsAuthenticated]

    def _actor(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "masters.write")
        return facility


class DepartmentView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(
            services.create_department(facility, request.user, request.data, request),
            status=201,
        )


class SpecializationView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(
            services.create_specialization(facility, request.user, request.data, request),
            status=201,
        )


class DoctorView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_doctor(facility, request.user, request.data, request), status=201)


class DoctorDetailView(_WriteView):
    def patch(self, request, doctor_id):
        facility = self._actor(request)
        return Response(services.update_doctor(facility, request.user, doctor_id, request.data, request))


class ScheduleView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.set_schedule(facility, request.user, request.data, request), status=201)


class ReferralView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_referral(facility, request.user, request.data, request), status=201)


class ProView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_pro(facility, request.user, request.data, request), status=201)


class PartyView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_party(facility, request.user, request.data, request), status=201)


class ProcedureView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_procedure(facility, request.user, request.data, request), status=201)


class ServiceView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_service(facility, request.user, request.data, request), status=201)


class RoomTypeView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_room_type(facility, request.user, request.data, request), status=201)


class WardView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_ward(facility, request.user, request.data, request), status=201)


class RoomView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_room(facility, request.user, request.data, request), status=201)


class BedView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_bed(facility, request.user, request.data, request), status=201)


class TariffAdjustView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.adjust_charges(facility, request.user, request.data, request))


class TariffCopyView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.copy_tariffs(facility, request.user, request.data, request))


class DiscountRuleView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(
            services.create_discount_rule(facility, request.user, request.data, request),
            status=201,
        )


class DiscountRuleDetailView(_WriteView):
    def patch(self, request, rule_id):
        facility = self._actor(request)
        return Response(
            services.update_discount_rule(facility, request.user, rule_id, request.data, request)
        )


class PaymentModeDetailView(_WriteView):
    def patch(self, request, mode_id):
        facility = self._actor(request)
        return Response(
            services.update_payment_mode(facility, request.user, mode_id, request.data, request)
        )


class TaxView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_tax(facility, request.user, request.data, request), status=201)


class TemplateView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_template(facility, request.user, request.data, request), status=201)


class CountryView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_country(request.user, facility, request.data, request), status=201)


class StateView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_state(request.user, facility, request.data, request), status=201)


class CityView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_city(request.user, facility, request.data, request), status=201)


class AreaView(_WriteView):
    def post(self, request):
        facility = self._actor(request)
        return Response(services.create_area(request.user, facility, request.data, request), status=201)
