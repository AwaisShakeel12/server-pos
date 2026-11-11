from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAuthenticatedAndActive(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)


class StoreContextPermission(BasePermission):
    """
    Base permission that checks store membership and a required permission codename.
    Views may define:
      - required_permission = 'codename' or [codenames] (any-of)
      - required_permission_by_action = {'list': 'x.read', 'create': 'x.create', ...}
    Store context is resolved from request.store (set by view/mixin) or membership lookup.
    """

    message = 'You do not have permission to perform this action for this store.'

    def _get_required(self, view, request):
        action = getattr(view, 'action', None)
        by_action = getattr(view, 'required_permission_by_action', None) or {}
        if action and action in by_action:
            return by_action[action]
        if request.method in SAFE_METHODS and action in (None, 'list', 'retrieve') and 'read' in by_action:
            return by_action['read']
        req = getattr(view, 'required_permission', None)
        return req

    def _check_codename(self, membership, required):
        if not required:
            return True
        if isinstance(required, (list, tuple, set)):
            return any(membership.has_permission(c) for c in required)
        return membership.has_permission(str(required))

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        membership = getattr(request, 'store_membership', None)
        if membership is None:
            return False
        if not (membership.is_active and membership.store.is_active):
            return False
        required = self._get_required(view, request)
        return self._check_codename(membership, required)


def get_membership_for_request(request, store_id=None):
    """Resolve active membership for user in given/current store context."""
    from .models import StoreMembership
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    qs = StoreMembership.objects.select_related('store', 'user').filter(
        user=user, is_active=True, store__is_active=True,
    )
    if store_id:
        qs = qs.filter(store_id=store_id)
    # Prefer explicit header/query hints
    if not store_id:
        hinted = request.headers.get('X-Store-ID') or request.query_params.get('store_id') or request.data.get('store_id') if hasattr(request, 'data') else None
        if hinted:
            qs = qs.filter(store_id=hinted)
    memberships = list(qs[:2])
    if len(memberships) == 1:
        return memberships[0]
    if store_id and memberships:
        return memberships[0]
    # If user has exactly one membership total, use it
    if not store_id:
        all_ms = list(StoreMembership.objects.select_related('store', 'user').filter(user=user, is_active=True, store__is_active=True)[:2])
        if len(all_ms) == 1:
            return all_ms[0]
    return None
