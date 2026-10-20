from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from comments.models import ADMIN_ASK_LIMIT, AskQuota, Comment, Delivery, Driver


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_code", "active", "created_at")
    search_fields = ("name", "employee_code")


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("reference", "driver", "created_at")
    search_fields = ("reference", "driver__name", "driver__employee_code")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("driver", "delivery", "analysis_status", "stars", "sentiment", "score", "customer_name", "created_at")
    list_filter = ("analysis_status", "sentiment", "stars")
    search_fields = ("body", "customer_name", "order_reference", "delivery__reference", "driver__name")
    readonly_fields = (
        "driver",
        "analysis_status",
        "sentiment",
        "score",
        "stars",
        "summary",
        "aspects",
        "highlights",
        "model_name",
        "created_at",
    )


admin.site.unregister(User)


@admin.register(User)
class KutumaUserAdmin(UserAdmin):
    """Superusers create staff admins. Those admins get 15 Ask AI questions."""

    list_display = ("username", "email", "is_staff", "is_superuser", "ask_requests")

    def ask_requests(self, obj):
        if obj.is_superuser:
            return "Unlimited"
        used = AskQuota.objects.filter(user=obj).values_list("used", flat=True).first() or 0
        return f"{used} / {ADMIN_ASK_LIMIT}"

    ask_requests.short_description = "Chat requests"

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.append("ask_requests")
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        return (*fieldsets, ("Ask AI", {"fields": ("ask_requests",)}))

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_staff = True
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
