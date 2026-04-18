from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from delivery.models import Delivery
from user.models import User


def _short_place_name(address):
    if not address:
        return "Unknown"
    first_segment = address.split(",")[0].strip()
    if not first_segment:
        return "Unknown"
    if len(first_segment) <= 22:
        return first_segment
    return f"{first_segment[:19]}..."


def _format_hour_label(hour_value):
    if hour_value is None:
        return "Unknown"
    start_hour = int(hour_value) % 24
    end_hour = (start_hour + 1) % 24
    return f"{start_hour:02d}:00-{end_hour:02d}:00"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_dashboard(request):
    """Business intelligence dashboard data"""
    if request.user.user_type != "ADMIN":
        return Response({"error": "Admin access required"}, status=403)

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Overall stats
    total_deliveries = Delivery.objects.count()
    completed = Delivery.objects.filter(status="DELIVERED").count()
    in_progress = Delivery.objects.filter(
        status__in=["PENDING", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY"]
    ).count()
    failed = Delivery.objects.filter(status="FAILED").count()

    # Revenue analytics
    total_revenue = (
        Delivery.objects.filter(status="DELIVERED").aggregate(total=Sum("delivery_fee"))["total"] or 0
    )
    week_revenue = (
        Delivery.objects.filter(status="DELIVERED", updated_at__date__gte=week_ago).aggregate(
            total=Sum("delivery_fee")
        )["total"]
        or 0
    )
    month_revenue = (
        Delivery.objects.filter(status="DELIVERED", updated_at__date__gte=month_ago).aggregate(
            total=Sum("delivery_fee")
        )["total"]
        or 0
    )

    # Performance metrics from real delivery durations
    delivered_windows = Delivery.objects.filter(status="DELIVERED").values_list("created_at", "updated_at")
    valid_durations = []
    for created_at, updated_at in delivered_windows:
        if created_at and updated_at and updated_at > created_at:
            valid_durations.append((updated_at - created_at).total_seconds() / 3600)
    avg_delivery_time = round(sum(valid_durations) / len(valid_durations), 2) if valid_durations else 0
    success_rate = (completed / total_deliveries * 100) if total_deliveries > 0 else 0

    # Rider analytics
    active_riders = User.objects.filter(user_type="RIDER", is_available=True).count()
    total_riders = User.objects.filter(user_type="RIDER").count()

    # Customer analytics
    total_customers = User.objects.filter(user_type="CUSTOMER").count()
    active_customers = (
        Delivery.objects.filter(created_at__date__gte=month_ago).values("customer").distinct().count()
    )

    # User totals
    total_users = User.objects.count()
    total_admins = User.objects.filter(user_type="ADMIN").count()
    total_cashiers = User.objects.filter(user_type="CASHIER").count()

    # Trend data (last 7 days)
    daily_stats = []
    for i in range(7):
        date = today - timedelta(days=6 - i)
        count = Delivery.objects.filter(created_at__date=date).count()
        revenue = (
            Delivery.objects.filter(status="DELIVERED", updated_at__date=date).aggregate(
                total=Sum("delivery_fee")
            )["total"]
            or 0
        )
        daily_stats.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "deliveries": count,
                "revenue": float(revenue),
            }
        )

    return Response(
        {
            "overview": {
                "total_deliveries": total_deliveries,
                "completed": completed,
                "in_progress": in_progress,
                "failed": failed,
                "success_rate": round(success_rate, 1),
            },
            "revenue": {
                "total": float(total_revenue),
                "week": float(week_revenue),
                "month": float(month_revenue),
            },
            "performance": {
                "avg_delivery_time": avg_delivery_time,
                "active_riders": active_riders,
                "total_riders": total_riders,
            },
            "customers": {
                "total": total_customers,
                "active": active_customers,
            },
            "users": {
                "total": total_users,
                "admins": total_admins,
                "customers": total_customers,
                "riders": total_riders,
                "cashiers": total_cashiers,
            },
            "trends": daily_stats,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def predictive_analytics(request):
    """Predictive analytics and forecasting"""
    if request.user.user_type != "ADMIN":
        return Response({"error": "Admin access required"}, status=403)

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Calculate growth rates
    last_week = Delivery.objects.filter(created_at__date__gte=week_ago, created_at__date__lt=today).count()
    prev_week = Delivery.objects.filter(
        created_at__date__gte=week_ago - timedelta(days=7),
        created_at__date__lt=week_ago,
    ).count()
    growth_rate = ((last_week - prev_week) / prev_week * 100) if prev_week > 0 else 0

    # Predict next week deliveries
    predicted_deliveries = max(0, int(round(last_week * (1 + growth_rate / 100))))

    # Revenue forecast
    avg_fee = Delivery.objects.filter(status="DELIVERED").aggregate(avg=Avg("delivery_fee"))["avg"] or 0
    predicted_revenue = predicted_deliveries * float(avg_fee)

    # Peak hours analysis from recent real deliveries
    hourly_counts = list(
        Delivery.objects.filter(created_at__date__gte=month_ago)
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    total_hourly_count = sum(item["count"] for item in hourly_counts) or 1
    peak_hours = [
        {
            "hour": _format_hour_label(item["hour"]),
            "percentage": round((item["count"] / total_hourly_count) * 100, 1),
        }
        for item in hourly_counts[:3]
    ]

    # Popular routes from real delivery addresses
    route_rows = list(
        Delivery.objects.exclude(pickup_address__isnull=True)
        .exclude(delivery_address__isnull=True)
        .exclude(pickup_address="")
        .exclude(delivery_address="")
        .values("pickup_address", "delivery_address")
        .annotate(count=Count("id"))
        .order_by("-count")[:3]
    )
    popular_routes = [
        {
            "route": f"{_short_place_name(route['pickup_address'])} -> {_short_place_name(route['delivery_address'])}",
            "count": route["count"],
        }
        for route in route_rows
    ]

    # Data-driven recommendations
    recommendations = []
    if peak_hours:
        busiest = peak_hours[0]
        recommendations.append(
            f"Assign more riders during {busiest['hour']} where demand is {busiest['percentage']}% of recent bookings."
        )

    rounded_growth = round(growth_rate, 1)
    if growth_rate > 10:
        recommendations.append(
            f"Demand is rising (+{rounded_growth}% week-over-week). Prepare staffing for about {predicted_deliveries} deliveries next week."
        )
    elif growth_rate < -10:
        recommendations.append(
            f"Demand is down ({rounded_growth}% week-over-week). Re-engage frequent customers with targeted promos."
        )

    total_recent = Delivery.objects.filter(created_at__date__gte=month_ago).count()
    recent_failed = Delivery.objects.filter(created_at__date__gte=month_ago, status="FAILED").count()
    failure_rate = (recent_failed / total_recent * 100) if total_recent > 0 else 0
    if failure_rate >= 5:
        recommendations.append(
            f"Recent failed deliveries are {round(failure_rate, 1)}%. Review routing and address verification for failed orders."
        )

    if not recommendations:
        recommendations.append(
            f"Delivery volume is stable. Keep current operations and monitor weekly trend around {last_week} orders."
        )

    return Response(
        {
            "forecast": {
                "next_week_deliveries": predicted_deliveries,
                "predicted_revenue": round(predicted_revenue, 2),
                "growth_rate": rounded_growth,
            },
            "insights": {
                "peak_hours": peak_hours,
                "popular_routes": popular_routes,
            },
            "recommendations": recommendations,
        }
    )
