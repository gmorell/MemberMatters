from profile.models import User, UserEventLog
from access.models import DoorLog, InterlockLog
from access import models
from .models import MemberTier, PaymentPlan
from memberbucks.models import MemberBucks
from constance import config
from services.emails import send_email_to_admin
import json
import stripe
from sentry_sdk import capture_message
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django.db.models import F, Count, Sum, Value, CharField, Count, Max
from django.db.models.functions import Concat
from datetime import timedelta
import humanize
from django.db import connection
from django.db.utils import OperationalError
from sentry_sdk import capture_exception


class StripeAPIView(APIView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not config.ENABLE_STRIPE:
            return

        try:
            stripe.api_key = config.STRIPE_SECRET_KEY
        except OperationalError as error:
            capture_exception(error)


class GetMembers(APIView):
    """
    get: This method returns a list of members.
    """

    permission_classes = (permissions.IsAdminUser | HasAPIKey,)

    def get(self, request):
        filtered = []

        members_queryset = User.objects.select_related("profile")

        screenName = request.GET.get("screenName")
        if screenName is not None:
            members_queryset = members_queryset.filter(profile__screen_name=screenName)

        members = members_queryset.all()

        for member in members:
            filtered.append(member.profile.get_basic_profile())

        return Response(filtered)


class MemberState(APIView):
    """
    get: This method gets a member's state.
    post: This method sets a member's state.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request, member_id, state=None):
        member = User.objects.get(id=member_id)

        return Response({"state": member.profile.state})

    def post(self, request, member_id, state):
        member = User.objects.get(id=member_id)
        if state == "active":
            member.profile.activate(request)
        elif state == "inactive":
            member.profile.deactivate(request)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response()


class MakeMember(APIView):
    """
    post: This activates a new member.
    """

    permission_classes = (permissions.IsAdminUser,)

    def post(self, request, member_id):
        user = User.objects.get(id=member_id)

        # if they're a new member or account only
        if user.profile.state == "noob" or user.profile.state == "accountonly":
            # give default door access
            for door in models.Doors.objects.filter(all_members=True):
                user.profile.doors.add(door)

            # give default interlock access
            for interlock in models.Interlock.objects.filter(all_members=True):
                user.profile.interlocks.add(interlock)

            # send the welcome email
            email = user.email_welcome()

            # mark them as "active"
            user.profile.state = "active"
            user.profile.save()

            subject = f"{user.profile.get_full_name()} just got turned into a member!"
            send_email_to_admin(
                subject=subject,
                template_vars={"title": subject, "message": subject},
                user=request.user,
            )

            if email:
                return Response(
                    {
                        "success": True,
                        "message": "adminTools.makeMemberSuccess",
                    }
                )

            # if there was an error sending the welcome email
            elif email is False:
                return Response(
                    {"success": False, "message": "adminTools.makeMemberErrorEmail"}
                )

            # otherwise some other error happened
            else:
                capture_message("Unknown error occurred when running makemember.")
                return Response(
                    {
                        "success": False,
                        "message": "adminTools.makeMemberError",
                    }
                )
        else:
            return Response(
                {
                    "success": False,
                    "message": "adminTools.makeMemberErrorExists",
                }
            )


class Doors(APIView):
    """
    get: returns a list of doors.
    put: updates a specific door.
    delete: deletes a specific door.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        doors = models.Doors.objects.all()

        def get_door(door):
            logs = models.DoorLog.objects.filter(door_id=door.id)

            # Query to get the statistics
            stats = (
                logs.select_related("user__profile")
                .values("door_id")
                .annotate(
                    screen_name=F("user__profile__screen_name"),
                    full_name=Concat(
                        F("user__profile__first_name"),
                        Value(" "),
                        F("user__profile__last_name"),
                        output_field=CharField(),
                    ),
                    total_swipes=Count("door_id"),
                    last_swipe=Max("date"),
                )
                .order_by("-total_swipes")
            )

            return {
                "id": door.id,
                "name": door.name,
                "description": door.description,
                "ipAddress": door.ip_address,
                "serialNumber": door.serial_number,
                "lastSeen": door.last_seen,
                "offline": door.get_unavailable(),
                "defaultAccess": door.all_members,
                "maintenanceLockout": door.locked_out,
                "playThemeOnSwipe": door.play_theme,
                "postDiscordOnSwipe": door.post_to_discord,
                "exemptFromSignin": door.exempt_signin,
                "hiddenToMembers": door.hidden,
                "totalSwipes": logs.count(),
                "userStats": stats,
            }

        return Response(map(get_door, doors))

    def put(self, request, door_id):
        door = models.Doors.objects.get(pk=door_id)

        data = request.data

        door.name = data.get("name")
        door.description = data.get("description")
        door.ip_address = data.get("ipAddress")
        door.serial_number = data.get("serialNumber")

        door.all_members = data.get("defaultAccess")
        door.locked_out = data.get("maintenanceLockout")
        door.play_theme = data.get("playThemeOnSwipe")
        door.post_to_discord = data.get("postDiscordOnSwipe")
        door.exempt_signin = data.get("exemptFromSignin")
        door.hidden = data.get("hiddenToMembers")

        door.save()

        return Response()

    def delete(self, request, door_id):
        door = models.Doors.objects.get(pk=door_id)
        door.delete()

        return Response()


class Interlocks(APIView):
    """
    get: returns a list of interlocks.
    put: update a specific interlock.
    delete: delete a specific interlock.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        interlocks = models.Interlock.objects.all()

        def get_interlock(interlock):
            # Calculate total on time
            logs = InterlockLog.objects.filter(interlock_id=interlock.id)
            total_time = logs.aggregate(total_time=Sum("total_time")).get("total_time")
            total_time_seconds = total_time.total_seconds()

            # Retrieve stats
            stats = (
                logs.select_related("user_started__profile")
                .values("interlock_id")
                .annotate(
                    screen_name=F("user_started__profile__screen_name"),
                    full_name=Concat(
                        F("user_started__profile__first_name"),
                        Value(" "),
                        F("user_started__profile__last_name"),
                        output_field=CharField(),
                    ),
                    total_swipes=Count("total_time"),
                    total_seconds=Sum("total_time"),
                )
                .order_by("-total_seconds", "-total_swipes")
            )

            return {
                "id": interlock.id,
                "authorised": interlock.authorised,
                "name": interlock.name,
                "description": interlock.description,
                "ipAddress": interlock.ip_address,
                "lastSeen": interlock.last_seen,
                "offline": interlock.get_unavailable(),
                "defaultAccess": interlock.all_members,
                "maintenanceLockout": interlock.locked_out,
                "playThemeOnSwipe": interlock.play_theme,
                "exemptFromSignin": interlock.exempt_signin,
                "hiddenToMembers": interlock.hidden,
                "totalTimeSeconds": total_time_seconds,
                "userStats": list(stats),
            }

        return Response(map(get_interlock, interlocks))

    def put(self, request, interlock_id):
        interlock = models.Interlock.objects.get(pk=interlock_id)

        data = request.data

        interlock.name = data.get("name")
        interlock.description = data.get("description")
        interlock.ip_address = data.get("ipAddress")

        interlock.all_members = data.get("defaultAccess")
        interlock.locked_out = data.get("maintenanceLockout")
        interlock.play_theme = data.get("playThemeOnSwipe")
        interlock.exempt_signin = data.get("exemptFromSignin")
        interlock.hidden = data.get("hiddenToMembers")

        interlock.save()

        return Response()

    def delete(self, request, interlock_id):
        interlock = models.Interlock.objects.get(pk=interlock_id)
        interlock.delete()

        return Response()


class MemberAccess(APIView):
    """
    get: This method gets a member's access permissions.
    """

    permission_classes = (permissions.IsAdminUser | HasAPIKey,)

    def get(self, request, member_id):
        member = User.objects.get(id=member_id)

        return Response(member.profile.get_access_permissions())


class MemberWelcomeEmail(APIView):
    """
    post: This method sends a welcome email to the specified member.
    """

    permission_classes = (permissions.IsAdminUser,)

    def post(self, request, member_id):
        member = User.objects.get(id=member_id)
        member.email_welcome()

        return Response()


class MemberProfile(APIView):
    """
    put: This method updates a member's profile.
    """

    permission_classes = (permissions.IsAdminUser,)

    def put(self, request, member_id):
        if not member_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        body = json.loads(request.body)
        member = User.objects.get(id=member_id)
        rfid_changed = False

        if member.profile.rfid != body.get("rfidCard"):
            rfid_changed = True

        member.email = body.get("email")
        member.profile.first_name = body.get("firstName")
        member.profile.last_name = body.get("lastName")
        member.profile.rfid = body.get("rfidCard")
        member.profile.phone = body.get("phone")
        member.profile.screen_name = body.get("screenName")
        member.profile.vehicle_registration_plate = body.get("vehicleRegistrationPlate")
        member.profile.exclude_from_email_export = body.get("excludeFromEmailExport")

        member.save()
        member.profile.save()

        if rfid_changed:
            for door in member.profile.doors.all():
                door.sync()

        return Response()


class MemberTiers(StripeAPIView):
    """
    get: gets a list of all membership plans.
    post: creates a new membership plan.
    put: updates a new membership plan.
    delete: a membership plan.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        tiers = MemberTier.objects.all()
        formatted_tiers = []

        for tier in tiers:
            formatted_tiers.append(
                {
                    "id": tier.id,
                    "name": tier.name,
                    "description": tier.description,
                    "visible": tier.visible,
                    "featured": tier.featured,
                }
            )

        return Response(formatted_tiers)

    def post(self, request):
        body = request.data

        try:
            product = stripe.Product.create(
                name=body["name"], description=body["description"]
            )
            tier = MemberTier.objects.create(
                name=body["name"],
                description=body["description"],
                visible=body["visible"],
                featured=body["featured"],
                stripe_id=product.id,
            )

            return Response()

        except stripe.error.AuthenticationError:
            return Response(
                {"success": False, "message": "error.stripeNotConfigured"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def delete(self, request):
        return Response()


class ManageMemberTier(StripeAPIView):
    """
    get: gets a member tier.
    put: updates a member tier.
    delete: deletes a member tier.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request, tier_id):
        body = request.data

        try:
            tier = MemberTier.objects.get(pk=tier_id)

        except MemberTier.DoesNotExist as e:
            return Response(status=status.HTTP_404_NOT_FOUND)

        formatted_tier = {
            "id": tier.id,
            "name": tier.name,
            "description": tier.description,
            "visible": tier.visible,
            "featured": tier.featured,
        }

        return Response(formatted_tier)

    def put(self, request, tier_id):
        body = request.data

        tier = MemberTier.objects.get(pk=tier_id)

        tier.name = body["name"]
        tier.description = body["description"]
        tier.visible = body["visible"]
        tier.featured = body["featured"]
        tier.save()

        return Response()

    def delete(self, request, tier_id):
        tier = MemberTier.objects.get(pk=tier_id)
        tier.delete()

        return Response()


class ManageMemberTierPlans(StripeAPIView):
    """
    post: creates a new member tier plan.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request, tier_id):
        plans = PaymentPlan.objects.filter(member_tier=tier_id)
        formatted_plans = []

        for plan in plans:
            formatted_plans.append(
                {
                    "id": plan.id,
                    "name": plan.name,
                    "stripeId": plan.stripe_id,
                    "memberTier": plan.member_tier.id,
                    "visible": plan.visible,
                    "currency": plan.currency,
                    "cost": plan.cost / 100,  # convert to dollars
                    "intervalCount": plan.interval_count,
                    "interval": plan.interval,
                }
            )

        return Response(formatted_plans)

    def post(self, request, tier_id=None):
        if tier_id is not None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        body = request.data

        member_tier = MemberTier.objects.get(pk=body["memberTier"])

        stripe_plan = stripe.Price.create(
            unit_amount=round(body["cost"]),
            currency=str(body["currency"]).lower(),
            recurring={
                "interval": body["interval"],
                "interval_count": body["intervalCount"],
            },
            product=member_tier.stripe_id,
        )

        PaymentPlan.objects.create(
            name=body["name"],
            stripe_id=stripe_plan.id,
            member_tier_id=body["memberTier"],
            visible=body["visible"],
            currency=str(body["currency"]).lower(),
            cost=round(body["cost"]),
            interval_count=body["intervalCount"],
            interval=body["interval"],
        )

        return Response()


class ManageMemberTierPlan(StripeAPIView):
    """
    get: gets a member tier plan.
    put: updates a member tier plan.
    delete: deletes a member tier plan.
    """

    permission_classes = (permissions.IsAdminUser,)

    def get(self, request, plan_id):
        body = request.data

        plan = PaymentPlan.objects.get(pk=plan_id)

        formatted_plan = {
            "id": plan.id,
            "name": plan.name,
            "member_tier": plan.member_tier,
            "visible": plan.visible,
            "cost": plan.cost,
            "interval_count": plan.interval_count,
            "interval": plan.interval,
        }

        return Response(formatted_plan)

    def put(self, request, plan_id):
        body = request.data

        plan = PaymentPlan.objects.get(pk=plan_id)

        plan.name = body["name"]
        plan.visible = body["visible"]
        plan.cost = body["cost"]
        plan.save()

        return Response()

    def delete(self, request, plan_id):
        plan = PaymentPlan.objects.get(pk=plan_id)
        plan.delete()

        return Response()


class MemberBillingInfo(StripeAPIView):
    """
    get: This method gets a member's billing info.
    """

    permission_classes = (permissions.IsAdminUser | HasAPIKey,)

    def get(self, request, member_id):
        member = User.objects.get(id=member_id)
        current_plan = member.profile.membership_plan

        billing_info = {}

        if current_plan:
            s = None

            # if we have a subscription id, fetch the details
            if member.profile.stripe_subscription_id:
                s = stripe.Subscription.retrieve(
                    member.profile.stripe_subscription_id,
                )

            # if we got subscription details
            if s:
                billing_info["subscription"] = {
                    "status": member.profile.subscription_status,
                    "billingCycleAnchor": s.billing_cycle_anchor,
                    "currentPeriodEnd": s.current_period_end,
                    "cancelAt": s.cancel_at,
                    "cancelAtPeriodEnd": s.cancel_at_period_end,
                    "startDate": s.start_date,
                }
            else:
                billing_info["subscription"] = None

        # get the most recent memberbucks transactions and order them by date
        recent_transactions = MemberBucks.objects.filter(user=member).order_by("date")[
            ::-1
        ][:100]

        def get_transaction(transaction):
            return transaction.get_transaction_display()

        billing_info["memberbucks"] = {
            "balance": member.profile.memberbucks_balance,
            "stripe_card_last_digits": member.profile.stripe_card_last_digits,
            "stripe_card_expiry": member.profile.stripe_card_expiry,
            "transactions": map(get_transaction, recent_transactions),
            "lastPurchase": member.profile.last_memberbucks_purchase,
        }

        return Response(billing_info)


class MemberLogs(APIView):
    """
    get: This method gets a member's logs.
    """

    permission_classes = (permissions.IsAdminUser | HasAPIKey,)

    def get(self, request, member_id):
        user = User.objects.get(id=member_id)

        user_event_logs = []
        door_logs = []
        interlock_logs = []

        for user_event_log in UserEventLog.objects.order_by("-date").filter(user=user)[
            :1000
        ]:
            user_event_logs.append(
                {
                    "date": user_event_log.date,
                    "description": user_event_log.description,
                    "logtype": user_event_log.get_logtype_display(),
                }
            )

        for door_log in DoorLog.objects.order_by("-date").filter(user=user)[:500]:
            door_logs.append(
                {
                    "date": door_log.date,
                    "door": door_log.door.name,
                    "success": door_log.success,
                }
            )

        for interlock_log in InterlockLog.objects.filter(user_started=user)[:1000]:
            status = None

            if not interlock_log.success:
                status = -1
            else:
                status = 1 if interlock_log.date_ended else 0

            interlock_logs.append(
                {
                    "interlockName": interlock_log.interlock.name,
                    "dateStarted": interlock_log.date_started,
                    "totalTime": interlock_log.total_time,
                    "totalCost": interlock_log.total_cost,
                    "status": status,
                    "userEnded": interlock_log.user_ended.get_full_name(),
                }
            )

        logs = {
            "userEventLogs": user_event_logs,
            "doorLogs": door_logs,
            "interlockLogs": interlock_logs,
        }

        return Response(logs)
