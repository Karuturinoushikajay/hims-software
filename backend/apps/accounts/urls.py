from django.urls import path

from apps.accounts.views import (
    CsrfView,
    FacilitySwitchView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    PermissionListView,
    RoleListCreateView,
    RolePermissionsView,
    RoleScreensView,
    ScreenListView,
    TotpConfirmView,
    TotpSetupView,
    UserDeactivateView,
    UserDetailView,
    UserListCreateView,
)

urlpatterns = [
    path("auth/csrf", CsrfView.as_view(), name="auth-csrf"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/password", PasswordChangeView.as_view(), name="auth-password"),
    path("auth/2fa/setup", TotpSetupView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/confirm", TotpConfirmView.as_view(), name="auth-2fa-confirm"),
    path("session/facility", FacilitySwitchView.as_view(), name="session-facility"),
    path("users", UserListCreateView.as_view(), name="users"),
    path("users/<uuid:user_id>", UserDetailView.as_view(), name="user-detail"),
    path("users/<uuid:user_id>/deactivate", UserDeactivateView.as_view(), name="user-deactivate"),
    path("roles", RoleListCreateView.as_view(), name="roles"),
    path("roles/<uuid:role_id>/permissions", RolePermissionsView.as_view(), name="role-permissions"),
    path("roles/<uuid:role_id>/screens", RoleScreensView.as_view(), name="role-screens"),
    path("permissions", PermissionListView.as_view(), name="permissions"),
    path("screens", ScreenListView.as_view(), name="screens"),
]
