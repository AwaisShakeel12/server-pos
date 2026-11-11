import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Store(models.Model):
    """Tenant/store boundary for hosted sync customers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='owned_stores',
    )
    phone = models.CharField(max_length=50, blank=True, default='')
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StoreMembership(models.Model):
    """User access to a store with role/permission-based controls."""

    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MANAGER = 'manager'
    ROLE_CASHIER = 'cashier'
    ROLE_VIEWER = 'viewer'

    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_CASHIER, 'Cashier'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    # Granular permission codenames (backend-enforced)
    PERM_SETTINGS_MANAGE = 'settings.manage'
    PERM_USERS_MANAGE = 'users.manage'
    PERM_DEVICES_MANAGE = 'devices.manage'
    PERM_PRODUCTS_READ = 'products.read'
    PERM_PRODUCTS_MANAGE = 'products.manage'
    PERM_SALES_READ = 'sales.read'
    PERM_SALES_CREATE = 'sales.create'
    PERM_SALES_MANAGE = 'sales.manage'
    PERM_UDHAR_READ = 'udhar.read'
    PERM_UDHAR_MANAGE = 'udhar.manage'
    PERM_ANALYTICS_READ = 'analytics.read'
    PERM_SYNC = 'sync.use'

    ROLE_DEFAULT_PERMISSIONS = {
        ROLE_OWNER: {'*'},
        ROLE_ADMIN: {'*'},
        ROLE_MANAGER: {
            PERM_SETTINGS_MANAGE, PERM_USERS_MANAGE, PERM_DEVICES_MANAGE,
            PERM_PRODUCTS_READ, PERM_PRODUCTS_MANAGE,
            PERM_SALES_READ, PERM_SALES_CREATE, PERM_SALES_MANAGE,
            PERM_UDHAR_READ, PERM_UDHAR_MANAGE,
            PERM_ANALYTICS_READ, PERM_SYNC,
        },
        ROLE_CASHIER: {
            PERM_PRODUCTS_READ,
            PERM_SALES_READ, PERM_SALES_CREATE,
            PERM_UDHAR_READ,
            PERM_ANALYTICS_READ,
            PERM_SYNC,
        },
        ROLE_VIEWER: {
            PERM_PRODUCTS_READ, PERM_SALES_READ, PERM_UDHAR_READ, PERM_ANALYTICS_READ,
        },
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='store_memberships',
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CASHIER)
    # Optional explicit overrides/additions; effective perms = role defaults + these
    permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'store')]
        ordering = ['store__name', 'user__username']

    def __str__(self):
        return f"{self.user} @ {self.store} ({self.role})"

    def effective_permissions(self):
        defaults = set(self.ROLE_DEFAULT_PERMISSIONS.get(self.role, set()))
        extra = set(self.permissions or [])
        return defaults | extra

    def has_permission(self, codename):
        perms = self.effective_permissions()
        return '*' in perms or codename in perms


class Device(models.Model):
    """Registered POS/mobile client instance for sync tracking."""

    TYPE_DESKTOP = 'desktop'
    TYPE_MOBILE = 'mobile'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_DESKTOP, 'Desktop POS'),
        (TYPE_MOBILE, 'Mobile POS'),
        (TYPE_OTHER, 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=255)
    device_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DESKTOP)
    # Client-generated stable identifier for idempotent registration/mapping
    client_identifier = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_cursor = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['store', 'client_identifier']),
        ]

    def __str__(self):
        return f"{self.name} ({self.store})"

    def mark_synced(self, cursor=''):
        self.last_sync_at = timezone.now()
        if cursor:
            self.last_sync_cursor = cursor
        self.save(update_fields=['last_sync_at', 'last_sync_cursor', 'updated_at'])


class SyncMetadataMixin(models.Model):
    """Common sync-ready fields for tenant-scoped domain records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='%(class)ss')
    # Optional mapping to local/client-side record id (e.g. POS SQLite integer id)
    client_record_id = models.CharField(max_length=100, blank=True, default='')
    source_device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='%(class)s_updates'
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.version = (self.version or 1) + 1
        self.save(update_fields=['is_deleted', 'deleted_at', 'version', 'updated_at'])


class Product(SyncMetadataMixin):
    """Inventory/product record synced across devices."""

    name = models.CharField(max_length=255)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    expiry_date = models.CharField(max_length=50, blank=True, default='')
    image_path = models.CharField(max_length=500, blank=True, default='')
    # Dynamic/custom columns and extra fields (barcode, discount_% etc.)
    custom_attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name', '-updated_at']
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
            models.Index(fields=['store', 'client_record_id']),
        ]

    def __str__(self):
        return self.name


class CustomColumn(SyncMetadataMixin):
    """Custom column definition (inventory/POS schema)."""

    TYPE_TEXT = 'text'
    TYPE_NUMBER = 'number'
    TYPE_DATE = 'date'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_NUMBER, 'Number'),
        (TYPE_DATE, 'Date'),
    ]

    name = models.CharField(max_length=100)
    column_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
        ]

    def __str__(self):
        return f"{self.name} ({self.store})"


class Sale(SyncMetadataMixin):
    """Bill/sale record. Items/discounts stored as JSON for fidelity and simple sync."""

    bill_number = models.CharField(max_length=100, blank=True, default='')
    customer_name = models.CharField(max_length=255, blank=True, default='')
    date = models.CharField(max_length=50, blank=True, default='')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    language = models.CharField(max_length=10, blank=True, default='en')
    items = models.JSONField(default=list, blank=True)
    discount_info = models.JSONField(default=dict, blank=True)
    payment_info = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
            models.Index(fields=['store', 'client_record_id']),
            models.Index(fields=['store', 'bill_number']),
        ]

    def __str__(self):
        return f"Sale {self.bill_number or self.id} ({self.store})"


class Udhar(SyncMetadataMixin):
    """Credit/loan (udhar) record."""

    customer_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default='')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True, default='')
    date = models.CharField(max_length=50, blank=True, default='')
    # Business-level last update timestamp from client (optional)
    business_updated_at = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
            models.Index(fields=['store', 'client_record_id']),
        ]

    def __str__(self):
        return f"Udhar {self.customer_name} ({self.store})"


class DiscountRule(SyncMetadataMixin):
    """Auto-discount rule configuration."""

    name = models.CharField(max_length=255, blank=True, default='')
    pct = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    start_date = models.CharField(max_length=50, blank=True, default='')
    end_date = models.CharField(max_length=50, blank=True, default='')
    active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-updated_at', 'name']
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
        ]

    def __str__(self):
        return f"{self.pct}% rule ({self.store})"


class StoreSetting(SyncMetadataMixin):
    """Flexible sync-relevant key-value store setting/config per tenant.

    Examples: custom_columns, card_fields, receipt_fields, column_mode,
    store profile/branding extras, receipt elements, auto_delete_months, etc.
    """

    key = models.CharField(max_length=120)
    value = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['key']
        unique_together = [('store', 'key')]
        indexes = [
            models.Index(fields=['store', 'updated_at']),
            models.Index(fields=['store', 'is_deleted']),
            models.Index(fields=['store', 'key']),
        ]

    def __str__(self):
        return f"{self.store}:{self.key}"
