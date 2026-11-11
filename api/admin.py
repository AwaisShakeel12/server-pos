from django.contrib import admin

from .models import (
    CustomColumn,
    Device,
    DiscountRule,
    Product,
    Sale,
    Store,
    StoreMembership,
    StoreSetting,
    Udhar,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'owner__username', 'owner__email')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'role', 'is_active', 'updated_at')
    list_filter = ('role', 'is_active', 'store')
    search_fields = ('user__username', 'user__email', 'store__name', 'store__slug')


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'store', 'device_type', 'client_identifier', 'is_active', 'last_sync_at')
    list_filter = ('device_type', 'is_active', 'store')
    search_fields = ('name', 'client_identifier', 'store__name')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'store', 'base_price', 'quantity', 'client_record_id', 'is_deleted', 'updated_at')
    list_filter = ('store', 'is_deleted')
    search_fields = ('name', 'client_record_id')


@admin.register(CustomColumn)
class CustomColumnAdmin(admin.ModelAdmin):
    list_display = ('name', 'store', 'column_type', 'sort_order', 'is_active', 'is_deleted', 'updated_at')
    list_filter = ('store', 'column_type', 'is_active', 'is_deleted')
    search_fields = ('name',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'store', 'customer_name', 'date', 'total_amount', 'is_deleted', 'updated_at')
    list_filter = ('store', 'is_deleted')
    search_fields = ('bill_number', 'customer_name', 'client_record_id')


@admin.register(Udhar)
class UdharAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'store', 'phone', 'amount', 'paid', 'is_deleted', 'updated_at')
    list_filter = ('store', 'is_deleted')
    search_fields = ('customer_name', 'phone', 'client_record_id')


@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'store', 'pct', 'min_amount', 'active', 'is_deleted', 'updated_at')
    list_filter = ('store', 'active', 'is_deleted')
    search_fields = ('name',)


@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'store', 'is_deleted', 'updated_at')
    list_filter = ('store', 'is_deleted')
    search_fields = ('key',)
