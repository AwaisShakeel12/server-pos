from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

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

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class StoreSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'slug', 'phone', 'address', 'is_active', 'metadata',
            'owner', 'role', 'effective_permissions', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'is_active', 'created_at', 'updated_at']

    def _membership(self, obj):
        return self.context.get('memberships_by_store', {}).get(str(obj.id))

    def get_role(self, obj):
        m = self._membership(obj)
        return m.role if m else None

    def get_effective_permissions(self, obj):
        m = self._membership(obj)
        return sorted(list(m.effective_permissions())) if m else []


class StoreMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    store = serializers.PrimaryKeyRelatedField(read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = StoreMembership
        fields = [
            'id', 'user', 'store', 'store_name', 'role', 'permissions',
            'effective_permissions', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'effective_permissions']

    def get_effective_permissions(self, obj):
        return sorted(list(obj.effective_permissions()))


class DeviceSerializer(serializers.ModelSerializer):
    store = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Device
        fields = [
            'id', 'store', 'name', 'device_type', 'client_identifier',
            'is_active', 'last_sync_at', 'last_sync_cursor', 'metadata',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'store', 'last_sync_at', 'last_sync_cursor', 'created_at', 'updated_at']


class DeviceRegisterSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    device_type = serializers.ChoiceField(choices=Device.TYPE_CHOICES, default=Device.TYPE_DESKTOP)
    client_identifier = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    metadata = serializers.JSONField(required=False, default=dict)


class SyncModelSerializerMixin(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    store = serializers.PrimaryKeyRelatedField(read_only=True)
    source_device = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all(), required=False, allow_null=True)

    sync_read_only_fields = [
        'store', 'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
    ]


class ProductSerializer(SyncModelSerializerMixin):
    class Meta:
        model = Product
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'name', 'base_price', 'quantity', 'expiry_date', 'image_path', 'custom_attributes',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class CustomColumnSerializer(SyncModelSerializerMixin):
    class Meta:
        model = CustomColumn
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'name', 'column_type', 'sort_order', 'is_active', 'config',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class SaleSerializer(SyncModelSerializerMixin):
    class Meta:
        model = Sale
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'bill_number', 'customer_name', 'date', 'total_amount', 'language',
            'items', 'discount_info', 'payment_info', 'notes',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class UdharSerializer(SyncModelSerializerMixin):
    class Meta:
        model = Udhar
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'customer_name', 'phone', 'amount', 'paid', 'note', 'date', 'business_updated_at',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class DiscountRuleSerializer(SyncModelSerializerMixin):
    class Meta:
        model = DiscountRule
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'name', 'pct', 'min_amount', 'start_date', 'end_date', 'active', 'config',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class StoreSettingSerializer(SyncModelSerializerMixin):
    class Meta:
        model = StoreSetting
        fields = [
            'id', 'store', 'client_record_id', 'source_device',
            'key', 'value', 'description',
            'is_deleted', 'deleted_at', 'version', 'created_at', 'updated_at',
        ]
        read_only_fields = SyncModelSerializerMixin.sync_read_only_fields


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    store_name = serializers.CharField(max_length=255)
    store_slug = serializers.SlugField(max_length=80)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    address = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Username already exists.')
        return value

    def validate_store_slug(self, value):
        if Store.objects.filter(slug__iexact=value).exists():
            raise serializers.ValidationError('Store slug already exists.')
        return value.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )
        store = Store.objects.create(
            name=validated_data['store_name'],
            slug=validated_data['store_slug'],
            owner=user,
            phone=validated_data.get('phone', ''),
            address=validated_data.get('address', ''),
        )
        membership = StoreMembership.objects.create(
            user=user,
            store=store,
            role=StoreMembership.ROLE_OWNER,
            is_active=True,
        )
        return {'user': user, 'store': store, 'membership': membership}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
