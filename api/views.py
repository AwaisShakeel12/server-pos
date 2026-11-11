from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework import generics, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
from .permissions import StoreContextPermission, get_membership_for_request
from .serializers import (
    CustomColumnSerializer,
    DeviceRegisterSerializer,
    DeviceSerializer,
    DiscountRuleSerializer,
    LoginSerializer,
    ProductSerializer,
    SaleSerializer,
    SignupSerializer,
    StoreMembershipSerializer,
    StoreSerializer,
    StoreSettingSerializer,
    UdharSerializer,
    UserSerializer,
)

User = get_user_model()


# =========================
# Hosted UI (minimal pages)
# =========================

def hosted_signup(request):
    if request.user.is_authenticated:
        return redirect('hosted-dashboard')
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        password_confirm = request.POST.get('password_confirm') or ''
        store_name = (request.POST.get('store_name') or '').strip()
        store_slug = (request.POST.get('store_slug') or slugify(store_name)).strip().lower()
        phone = (request.POST.get('phone') or '').strip()
        address = (request.POST.get('address') or '').strip()

        ctx = {
            'form': {
                'username': username, 'email': email, 'store_name': store_name,
                'store_slug': store_slug, 'phone': phone, 'address': address,
            }
        }
        if not (username and password and store_name and store_slug):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'hosted/signup.html', ctx)
        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'hosted/signup.html', ctx)
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'hosted/signup.html', ctx)
        if Store.objects.filter(slug__iexact=store_slug).exists():
            messages.error(request, 'Store slug already exists.')
            return render(request, 'hosted/signup.html', ctx)
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                store = Store.objects.create(name=store_name, slug=store_slug, owner=user, phone=phone, address=address)
                StoreMembership.objects.create(user=user, store=store, role=StoreMembership.ROLE_OWNER, is_active=True)
            login(request, user)
            messages.success(request, 'Account and store created successfully.')
            return redirect('hosted-dashboard')
        except Exception as e:
            messages.error(request, f'Could not create account: {e}')
            return render(request, 'hosted/signup.html', ctx)

    return render(request, 'hosted/signup.html', {'form': {}})


def hosted_login(request):
    if request.user.is_authenticated:
        return redirect('hosted-dashboard')
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next') or 'hosted-dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'hosted/login.html')


def hosted_logout(request):
    logout(request)
    return redirect('hosted-login')


@login_required
def hosted_dashboard(request):
    memberships = list(StoreMembership.objects.select_related('store').filter(
        user=request.user, is_active=True, store__is_active=True
    ))
    stores = [m.store for m in memberships]
    memberships_by_store = {str(m.store_id): m for m in memberships}
    selected_store_id = request.GET.get('store') or (str(stores[0].id) if stores else None)
    selected_membership = memberships_by_store.get(str(selected_store_id)) if selected_store_id else None
    devices = []
    members = []
    synced_counts = {}
    selected_effective_permissions = []
    if selected_membership:
        store = selected_membership.store
        try:
            selected_effective_permissions = sorted(list(selected_membership.effective_permissions()))
        except Exception:
            selected_effective_permissions = []
        devices = list(Device.objects.filter(store=store).order_by('-updated_at')[:20])
        can_manage_users = (
            selected_membership.has_permission(StoreMembership.PERM_USERS_MANAGE)
            or '*' in (selected_membership.effective_permissions() if hasattr(selected_membership, 'effective_permissions') else [])
        )
        if can_manage_users:
            members = list(
                StoreMembership.objects.select_related('user').filter(store=store).order_by('user__username')[:50]
            )
        try:
            synced_counts = {
                'products': Product.objects.filter(store=store, is_deleted=False).count(),
                'sales': Sale.objects.filter(store=store, is_deleted=False).count(),
                'udhar': Udhar.objects.filter(store=store, is_deleted=False).count(),
                'settings': StoreSetting.objects.filter(store=store, is_deleted=False).count(),
                'custom_columns': CustomColumn.objects.filter(store=store, is_deleted=False).count(),
                'discount_rules': DiscountRule.objects.filter(store=store, is_deleted=False).count(),
            }
        except Exception:
            synced_counts = {}
    return render(request, 'hosted/dashboard.html', {
        'stores': stores,
        'memberships_by_store': memberships_by_store,
        'selected_store_id': str(selected_store_id) if selected_store_id else None,
        'selected_membership': selected_membership,
        'selected_effective_permissions': selected_effective_permissions,
        'devices': devices,
        'members': members,
        'synced_counts': synced_counts,
    })


# =========================
# API views
# =========================

class ApiRootView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'name': 'ProjectPOS Sync API',
            'version': 'v1',
            'status': 'ok',
            'endpoints': {
                'auth_signup': request.build_absolute_uri('auth/signup/'),
                'auth_login': request.build_absolute_uri('auth/login/'),
                'auth_me': request.build_absolute_uri('auth/me/'),
                'stores': request.build_absolute_uri('stores/'),
                'devices': request.build_absolute_uri('devices/'),
                'devices_register': request.build_absolute_uri('devices/register/'),
                'products': request.build_absolute_uri('products/'),
                'custom_columns': request.build_absolute_uri('custom-columns/'),
                'sales': request.build_absolute_uri('sales/'),
                'udhar': request.build_absolute_uri('udhar/'),
                'discount_rules': request.build_absolute_uri('discount-rules/'),
                'settings': request.build_absolute_uri('settings/'),
                'sync': request.build_absolute_uri('sync/'),
                'sync_pull': request.build_absolute_uri('sync/pull/'),
                'sync_push': request.build_absolute_uri('sync/push/'),
            }
        })


class SignupAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        token, _ = Token.objects.get_or_create(user=result['user'])
        return Response({
            'token': token.key,
            'user': UserSerializer(result['user']).data,
            'store': StoreSerializer(result['store'], context={'memberships_by_store': {str(result['store'].id): result['membership']}}).data,
            'membership': StoreMembershipSerializer(result['membership']).data,
        }, status=status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, username=serializer.validated_data['username'], password=serializer.validated_data['password'])
        if not user:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        memberships = list(StoreMembership.objects.select_related('store').filter(user=user, is_active=True, store__is_active=True))
        memberships_by_store = {str(m.store_id): m for m in memberships}
        stores = [m.store for m in memberships]
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data,
            'stores': StoreSerializer(stores, many=True, context={'memberships_by_store': memberships_by_store}).data,
        })


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = list(StoreMembership.objects.select_related('store').filter(user=request.user, is_active=True, store__is_active=True))
        memberships_by_store = {str(m.store_id): m for m in memberships}
        stores = [m.store for m in memberships]
        return Response({
            'user': UserSerializer(request.user).data,
            'stores': StoreSerializer(stores, many=True, context={'memberships_by_store': memberships_by_store}).data,
            'memberships': StoreMembershipSerializer(memberships, many=True).data,
        })


class StoreViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Store.objects.filter(memberships__user=self.request.user, memberships__is_active=True, is_active=True).distinct().order_by('name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        memberships = StoreMembership.objects.filter(user=self.request.user, is_active=True)
        ctx['memberships_by_store'] = {str(m.store_id): m for m in memberships}
        return ctx


class StoreMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = StoreMembership.objects.select_related('store', 'user').filter(is_active=True, store__is_active=True)
        # Users can see memberships for stores they belong to; user management detail filtered later by perms in Phase 2/3
        my_store_ids = StoreMembership.objects.filter(user=self.request.user, is_active=True).values_list('store_id', flat=True)
        qs = qs.filter(store_id__in=my_store_ids)
        store_id = self.request.query_params.get('store_id')
        if store_id:
            qs = qs.filter(store_id=store_id)
        # Non-admins only see own membership unless they have users.manage (enforced lightly here)
        my_memberships = StoreMembership.objects.filter(user=self.request.user, is_active=True, store_id__in=my_store_ids)
        can_manage_any = any(m.has_permission(StoreMembership.PERM_USERS_MANAGE) or '*' in m.effective_permissions() for m in my_memberships)
        if not can_manage_any:
            qs = qs.filter(user=self.request.user)
        return qs.order_by('store__name', 'user__username')


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def _get_membership(self):
        store_id = self.request.query_params.get('store_id') or self.request.data.get('store_id') or getattr(self.request, 'store_id_hint', None)
        m = get_membership_for_request(self.request, store_id=store_id)
        if m:
            self.request.store_membership = m
            self.request.store = m.store
        return m

    def get_queryset(self):
        m = self._get_membership()
        if not m:
            return Device.objects.none()
        # devices.manage required to list all; otherwise allow read own context if has sync/use? keep simple: require devices.manage or sync.use for visibility
        if not (m.has_permission(StoreMembership.PERM_DEVICES_MANAGE) or m.has_permission(StoreMembership.PERM_SYNC) or '*' in m.effective_permissions()):
            return Device.objects.none()
        return Device.objects.filter(store=m.store).order_by('-updated_at')

    def perform_create(self, serializer):
        m = self._get_membership()
        if not m or not m.has_permission(StoreMembership.PERM_DEVICES_MANAGE):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('devices.manage permission required.')
        serializer.save(store=m.store)

    def perform_update(self, serializer):
        m = self._get_membership()
        if not m or not m.has_permission(StoreMembership.PERM_DEVICES_MANAGE):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('devices.manage permission required.')
        serializer.save()

    def perform_destroy(self, instance):
        m = self._get_membership()
        if not m or not m.has_permission(StoreMembership.PERM_DEVICES_MANAGE):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('devices.manage permission required.')
        instance.delete()


class DeviceRegisterAPIView(APIView):
    """Idempotent device registration for POS/mobile clients during sync setup."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = get_membership_for_request(request, store_id=data['store_id'])
        if not membership:
            return Response({'detail': 'No active membership for this store.'}, status=status.HTTP_403_FORBIDDEN)
        if not (membership.has_permission(StoreMembership.PERM_DEVICES_MANAGE) or membership.has_permission(StoreMembership.PERM_SYNC)):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        client_identifier = data.get('client_identifier') or ''
        device = None
        if client_identifier:
            device = Device.objects.filter(store=membership.store, client_identifier=client_identifier).first()
        if device:
            device.name = data['name']
            device.device_type = data.get('device_type') or device.device_type
            device.is_active = True
            device.metadata = data.get('metadata') or device.metadata or {}
            device.save()
            created = False
        else:
            device = Device.objects.create(
                store=membership.store,
                name=data['name'],
                device_type=data.get('device_type', Device.TYPE_DESKTOP),
                client_identifier=client_identifier,
                metadata=data.get('metadata') or {},
            )
            created = True
        return Response({'created': created, 'device': DeviceSerializer(device).data}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class StoreScopedSyncViewSet(viewsets.ModelViewSet):
    """Base viewset for tenant-scoped sync-ready resources."""

    permission_classes = [IsAuthenticated]
    # Override in subclasses:
    # required_permission_by_action = { 'list': 'x.read', 'create': 'x.create', ... }
    required_permission_by_action = {}

    def get_membership(self):
        if hasattr(self.request, 'store_membership'):
            return self.request.store_membership
        store_id = (
            self.request.query_params.get('store_id')
            or self.request.data.get('store_id')
            or self.kwargs.get('store_id')
        )
        m = get_membership_for_request(self.request, store_id=store_id)
        if m:
            self.request.store_membership = m
            self.request.store = m.store
        return m

    def _required_for_request(self):
        action = getattr(self, 'action', None)
        by_action = getattr(self, 'required_permission_by_action', {}) or {}
        if action in by_action:
            return by_action[action]
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return by_action.get('list') or by_action.get('retrieve') or by_action.get('read')
        return None

    def has_action_permission(self, membership):
        required = self._required_for_request()
        if not required:
            return True
        if isinstance(required, (list, tuple, set)):
            return any(membership.has_permission(c) for c in required)
        return membership.has_permission(str(required))

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        m = self.get_membership()
        if not m:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Store context/membership required. Provide store_id or use a single-store account.')
        if not self.has_action_permission(m):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Insufficient permissions for this action.')

    def get_queryset(self):
        m = self.get_membership()
        if not m:
            return self.queryset.none()
        qs = self.queryset.filter(store=m.store)
        # By default hide soft-deleted records unless explicitly requested
        include_deleted = self.request.query_params.get('include_deleted') in ('1', 'true', 'True', 'yes')
        if not include_deleted and hasattr(self.queryset.model, 'is_deleted'):
            qs = qs.filter(is_deleted=False)
        # Simple incremental-sync helper filter
        updated_since = self.request.query_params.get('updated_since')
        if updated_since:
            qs = qs.filter(updated_at__gt=updated_since)
        client_record_id = self.request.query_params.get('client_record_id')
        if client_record_id:
            qs = qs.filter(client_record_id=client_record_id)
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        m = self.get_membership()
        extra = {'store': m.store}
        source_device = serializer.validated_data.get('source_device')
        if source_device and source_device.store_id != m.store_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'source_device': 'Device does not belong to this store.'})
        serializer.save(**extra)

    def perform_update(self, serializer):
        m = self.get_membership()
        source_device = serializer.validated_data.get('source_device')
        if source_device and source_device.store_id != m.store_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'source_device': 'Device does not belong to this store.'})
        instance = serializer.instance
        serializer.save(version=(getattr(instance, 'version', 1) or 1) + 1)

    def perform_destroy(self, instance):
        # Soft delete for syncable records
        if hasattr(instance, 'soft_delete'):
            instance.soft_delete()
        else:
            instance.delete()


class ProductViewSet(StoreScopedSyncViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_PRODUCTS_READ,
        'retrieve': StoreMembership.PERM_PRODUCTS_READ,
        'create': StoreMembership.PERM_PRODUCTS_MANAGE,
        'update': StoreMembership.PERM_PRODUCTS_MANAGE,
        'partial_update': StoreMembership.PERM_PRODUCTS_MANAGE,
        'destroy': StoreMembership.PERM_PRODUCTS_MANAGE,
    }


class CustomColumnViewSet(StoreScopedSyncViewSet):
    queryset = CustomColumn.objects.all()
    serializer_class = CustomColumnSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_SETTINGS_MANAGE,
        'retrieve': StoreMembership.PERM_SETTINGS_MANAGE,
        'create': StoreMembership.PERM_SETTINGS_MANAGE,
        'update': StoreMembership.PERM_SETTINGS_MANAGE,
        'partial_update': StoreMembership.PERM_SETTINGS_MANAGE,
        'destroy': StoreMembership.PERM_SETTINGS_MANAGE,
    }


class SaleViewSet(StoreScopedSyncViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_SALES_READ,
        'retrieve': StoreMembership.PERM_SALES_READ,
        'create': StoreMembership.PERM_SALES_CREATE,
        'update': StoreMembership.PERM_SALES_MANAGE,
        'partial_update': StoreMembership.PERM_SALES_MANAGE,
        'destroy': StoreMembership.PERM_SALES_MANAGE,
    }


class UdharViewSet(StoreScopedSyncViewSet):
    queryset = Udhar.objects.all()
    serializer_class = UdharSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_UDHAR_READ,
        'retrieve': StoreMembership.PERM_UDHAR_READ,
        'create': StoreMembership.PERM_UDHAR_MANAGE,
        'update': StoreMembership.PERM_UDHAR_MANAGE,
        'partial_update': StoreMembership.PERM_UDHAR_MANAGE,
        'destroy': StoreMembership.PERM_UDHAR_MANAGE,
    }


class DiscountRuleViewSet(StoreScopedSyncViewSet):
    queryset = DiscountRule.objects.all()
    serializer_class = DiscountRuleSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_SETTINGS_MANAGE,
        'retrieve': StoreMembership.PERM_SETTINGS_MANAGE,
        'create': StoreMembership.PERM_SETTINGS_MANAGE,
        'update': StoreMembership.PERM_SETTINGS_MANAGE,
        'partial_update': StoreMembership.PERM_SETTINGS_MANAGE,
        'destroy': StoreMembership.PERM_SETTINGS_MANAGE,
    }


class StoreSettingViewSet(StoreScopedSyncViewSet):
    queryset = StoreSetting.objects.all()
    serializer_class = StoreSettingSerializer
    required_permission_by_action = {
        'list': StoreMembership.PERM_SETTINGS_MANAGE,
        'retrieve': StoreMembership.PERM_SETTINGS_MANAGE,
        'create': StoreMembership.PERM_SETTINGS_MANAGE,
        'update': StoreMembership.PERM_SETTINGS_MANAGE,
        'partial_update': StoreMembership.PERM_SETTINGS_MANAGE,
        'destroy': StoreMembership.PERM_SETTINGS_MANAGE,
    }


# =========================
# Sync protocol (Phase 3)
# =========================

SYNC_ENTITY_REGISTRY = {
    'products': {
        'model': Product,
        'serializer': ProductSerializer,
        'read_perm': StoreMembership.PERM_PRODUCTS_READ,
        'write_perm': StoreMembership.PERM_PRODUCTS_MANAGE,
    },
    'custom_columns': {
        'model': CustomColumn,
        'serializer': CustomColumnSerializer,
        'read_perm': StoreMembership.PERM_SETTINGS_MANAGE,
        'write_perm': StoreMembership.PERM_SETTINGS_MANAGE,
    },
    'sales': {
        'model': Sale,
        'serializer': SaleSerializer,
        'read_perm': StoreMembership.PERM_SALES_READ,
        'write_perm': StoreMembership.PERM_SALES_CREATE,  # cashiers can create bills; manage checked for updates
        'manage_perm': StoreMembership.PERM_SALES_MANAGE,
    },
    'udhar': {
        'model': Udhar,
        'serializer': UdharSerializer,
        'read_perm': StoreMembership.PERM_UDHAR_READ,
        'write_perm': StoreMembership.PERM_UDHAR_MANAGE,
    },
    'discount_rules': {
        'model': DiscountRule,
        'serializer': DiscountRuleSerializer,
        'read_perm': StoreMembership.PERM_SETTINGS_MANAGE,
        'write_perm': StoreMembership.PERM_SETTINGS_MANAGE,
    },
    'settings': {
        'model': StoreSetting,
        'serializer': StoreSettingSerializer,
        'read_perm': StoreMembership.PERM_SETTINGS_MANAGE,
        'write_perm': StoreMembership.PERM_SETTINGS_MANAGE,
    },
}


def _parse_sync_dt(value):
    if not value:
        return None
    if hasattr(value, 'tzinfo'):
        return value
    dt = parse_datetime(str(value))
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _get_sync_context(request, data):
    store_id = data.get('store_id') or request.query_params.get('store_id')
    membership = get_membership_for_request(request, store_id=store_id)
    if not membership:
        return None, None, Response({'detail': 'Store context/membership required. Provide valid store_id.'}, status=status.HTTP_403_FORBIDDEN)
    if not membership.has_permission(StoreMembership.PERM_SYNC):
        return None, None, Response({'detail': 'sync.use permission required.'}, status=status.HTTP_403_FORBIDDEN)

    device = None
    device_id = data.get('device_id')
    client_identifier = data.get('client_identifier') or data.get('device_client_identifier')
    if device_id:
        device = Device.objects.filter(id=device_id, store=membership.store, is_active=True).first()
        if not device:
            return None, None, Response({'detail': 'Invalid device_id for this store.'}, status=status.HTTP_400_BAD_REQUEST)
    elif client_identifier:
        device = Device.objects.filter(store=membership.store, client_identifier=str(client_identifier), is_active=True).first()
    # device optional for simple usage, but recommended
    return membership, device, None


def _entity_perm_ok(membership, entity, mode, is_update=False):
    cfg = SYNC_ENTITY_REGISTRY.get(entity)
    if not cfg:
        return False
    if mode == 'read':
        return membership.has_permission(cfg['read_perm']) or membership.has_permission('*')
    # write/push
    if entity == 'sales' and is_update and cfg.get('manage_perm'):
        return membership.has_permission(cfg['manage_perm']) or membership.has_permission(cfg['write_perm']) or membership.has_permission('*')
    return membership.has_permission(cfg['write_perm']) or membership.has_permission('*')


def _serialize_sync_record(serializer_cls, instance):
    return serializer_cls(instance).data


@transaction.atomic
def _apply_entity_changes(membership, device, entity, records):
    cfg = SYNC_ENTITY_REGISTRY[entity]
    model = cfg['model']
    serializer_cls = cfg['serializer']
    results = []
    for rec in (records or []):
        rec = rec or {}
        rec_id = rec.get('id')
        if not rec_id:
            results.append({'id': None, 'status': 'error', 'reason': 'missing id', 'record': None})
            continue
        try:
            existing = model.objects.filter(store=membership.store, id=rec_id).first()
            is_update = existing is not None
            if not _entity_perm_ok(membership, entity, 'write', is_update=is_update):
                results.append({'id': str(rec_id), 'status': 'error', 'reason': 'permission denied', 'record': None})
                continue

            incoming_updated = _parse_sync_dt(rec.get('updated_at'))
            if existing and incoming_updated and existing.updated_at and incoming_updated < existing.updated_at:
                # Simple deterministic conflict baseline: server is newer (LWW by timestamp)
                results.append({
                    'id': str(existing.id),
                    'status': 'conflict',
                    'reason': 'server newer (last-write-wins kept server)',
                    'record': _serialize_sync_record(serializer_cls, existing),
                })
                continue

            payload = dict(rec)
            payload.pop('store', None)
            payload.pop('created_at', None)
            payload.pop('deleted_at', None)
            # keep incoming id/version/updated_at hints out of direct serializer write except allowed fields
            # handle soft-delete intent
            wants_delete = bool(payload.get('is_deleted'))

            if existing:
                serializer = serializer_cls(existing, data=payload, partial=True)
                if not serializer.is_valid():
                    results.append({'id': str(rec_id), 'status': 'error', 'reason': serializer.errors, 'record': _serialize_sync_record(serializer_cls, existing)})
                    continue
                src_dev = serializer.validated_data.get('source_device')
                if src_dev and src_dev.store_id != membership.store_id:
                    results.append({'id': str(rec_id), 'status': 'error', 'reason': 'source_device does not belong to store', 'record': _serialize_sync_record(serializer_cls, existing)})
                    continue
                obj = serializer.save(version=(existing.version or 1) + 1)
                if wants_delete and not obj.is_deleted:
                    obj.soft_delete()
                elif wants_delete and obj.is_deleted and not obj.deleted_at:
                    obj.deleted_at = timezone.now()
                    obj.save(update_fields=['deleted_at', 'updated_at'])
                if device and not obj.source_device_id:
                    obj.source_device = device
                    obj.save(update_fields=['source_device', 'updated_at'])
                results.append({'id': str(obj.id), 'status': 'applied', 'reason': 'updated', 'record': _serialize_sync_record(serializer_cls, obj)})
            else:
                serializer = serializer_cls(data=payload)
                if not serializer.is_valid():
                    results.append({'id': str(rec_id), 'status': 'error', 'reason': serializer.errors, 'record': None})
                    continue
                src_dev = serializer.validated_data.get('source_device')
                if src_dev and src_dev.store_id != membership.store_id:
                    results.append({'id': str(rec_id), 'status': 'error', 'reason': 'source_device does not belong to store', 'record': None})
                    continue
                save_kwargs = {'store': membership.store}
                # Preserve client-provided UUID for idempotent sync mapping
                try:
                    import uuid as _uuid
                    save_kwargs['id'] = _uuid.UUID(str(rec_id))
                except Exception:
                    pass
                obj = serializer.save(**save_kwargs)
                if wants_delete and not obj.is_deleted:
                    obj.soft_delete()
                if device and not obj.source_device_id:
                    obj.source_device = device
                    obj.save(update_fields=['source_device', 'updated_at'])
                results.append({'id': str(obj.id), 'status': 'applied', 'reason': 'created', 'record': _serialize_sync_record(serializer_cls, obj)})
        except Exception as e:
            results.append({'id': str(rec_id), 'status': 'error', 'reason': str(e), 'record': None})
    return results


def _pull_entity_changes(membership, entity, cursor_dt, limit):
    cfg = SYNC_ENTITY_REGISTRY[entity]
    model = cfg['model']
    serializer_cls = cfg['serializer']
    qs = model.objects.filter(store=membership.store)
    if cursor_dt:
        qs = qs.filter(updated_at__gt=cursor_dt)
    qs = qs.order_by('updated_at')[:limit]
    records = list(qs)
    data = serializer_cls(records, many=True).data
    max_dt = cursor_dt
    for obj in records:
        if obj.updated_at and (max_dt is None or obj.updated_at > max_dt):
            max_dt = obj.updated_at
    return data, max_dt


def _normalize_entities(requested):
    if not requested:
        return list(SYNC_ENTITY_REGISTRY.keys())
    out = []
    for e in requested:
        if e in SYNC_ENTITY_REGISTRY and e not in out:
            out.append(e)
    return out


class SyncPullAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}
        membership, device, err = _get_sync_context(request, data)
        if err:
            return err
        cursor_dt = _parse_sync_dt(data.get('cursor') or (device.last_sync_cursor if device else None))
        entities = _normalize_entities(data.get('entities'))
        limit = int(data.get('limit') or 200)
        limit = max(1, min(limit, 1000))

        changes = {}
        next_cursor_dt = cursor_dt
        for entity in entities:
            if not _entity_perm_ok(membership, entity, 'read'):
                changes[entity] = {'error': 'permission denied', 'records': []}
                continue
            records, max_dt = _pull_entity_changes(membership, entity, cursor_dt, limit)
            changes[entity] = records
            if max_dt and (next_cursor_dt is None or max_dt > next_cursor_dt):
                next_cursor_dt = max_dt

        server_time = timezone.now()
        next_cursor = next_cursor_dt.isoformat() if next_cursor_dt else (cursor_dt.isoformat() if cursor_dt else server_time.isoformat())
        if device:
            device.mark_synced(cursor=next_cursor)

        return Response({
            'ok': True,
            'store_id': str(membership.store_id),
            'device_id': str(device.id) if device else None,
            'cursor': data.get('cursor'),
            'next_cursor': next_cursor,
            'server_time': server_time.isoformat(),
            'changes': changes,
        })


class SyncPushAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}
        membership, device, err = _get_sync_context(request, data)
        if err:
            return err
        changes = data.get('changes') or {}
        if not isinstance(changes, dict):
            return Response({'detail': 'changes must be an object keyed by entity name.'}, status=status.HTTP_400_BAD_REQUEST)

        entities = _normalize_entities(list(changes.keys()))
        results = {}
        for entity in entities:
            records = changes.get(entity) or []
            if entity not in SYNC_ENTITY_REGISTRY:
                results[entity] = [{'id': None, 'status': 'error', 'reason': 'unknown entity', 'record': None}]
                continue
            # write permission pre-check (per-record checked again, including sales update/manage nuance)
            if not _entity_perm_ok(membership, entity, 'write'):
                results[entity] = [{'id': r.get('id'), 'status': 'error', 'reason': 'permission denied', 'record': None} for r in records]
                continue
            results[entity] = _apply_entity_changes(membership, device, entity, records)

        server_time = timezone.now()
        if device:
            # Don't advance cursor blindly on push; keep last_sync_at updated
            device.last_sync_at = server_time
            device.save(update_fields=['last_sync_at', 'updated_at'])

        return Response({
            'ok': True,
            'store_id': str(membership.store_id),
            'device_id': str(device.id) if device else None,
            'server_time': server_time.isoformat(),
            'results': results,
        })


class SyncAPIView(APIView):
    """Convenience endpoint: apply push (if provided), then return pull changes."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data or {}
        membership, device, err = _get_sync_context(request, data)
        if err:
            return err

        push_results = None
        push_changes = data.get('changes') or data.get('push') or None
        if push_changes:
            if not isinstance(push_changes, dict):
                return Response({'detail': 'changes/push must be an object keyed by entity name.'}, status=status.HTTP_400_BAD_REQUEST)
            entities = _normalize_entities(list(push_changes.keys()))
            push_results = {}
            for entity in entities:
                records = push_changes.get(entity) or []
                if entity not in SYNC_ENTITY_REGISTRY:
                    push_results[entity] = [{'id': None, 'status': 'error', 'reason': 'unknown entity', 'record': None}]
                    continue
                if not _entity_perm_ok(membership, entity, 'write'):
                    push_results[entity] = [{'id': r.get('id'), 'status': 'error', 'reason': 'permission denied', 'record': None} for r in records]
                    continue
                push_results[entity] = _apply_entity_changes(membership, device, entity, records)

        # Pull phase
        cursor_dt = _parse_sync_dt(data.get('cursor') or (device.last_sync_cursor if device else None))
        pull_entities = _normalize_entities(data.get('entities') or (list(push_changes.keys()) if isinstance(push_changes, dict) else None))
        limit = int(data.get('limit') or 200)
        limit = max(1, min(limit, 1000))
        changes = {}
        next_cursor_dt = cursor_dt
        for entity in pull_entities:
            if not _entity_perm_ok(membership, entity, 'read'):
                changes[entity] = {'error': 'permission denied', 'records': []}
                continue
            records, max_dt = _pull_entity_changes(membership, entity, cursor_dt, limit)
            changes[entity] = records
            if max_dt and (next_cursor_dt is None or max_dt > next_cursor_dt):
                next_cursor_dt = max_dt

        server_time = timezone.now()
        next_cursor = next_cursor_dt.isoformat() if next_cursor_dt else (cursor_dt.isoformat() if cursor_dt else server_time.isoformat())
        if device:
            device.mark_synced(cursor=next_cursor)

        return Response({
            'ok': True,
            'store_id': str(membership.store_id),
            'device_id': str(device.id) if device else None,
            'cursor': data.get('cursor'),
            'next_cursor': next_cursor,
            'server_time': server_time.isoformat(),
            'push_results': push_results,
            'changes': changes,
        })
