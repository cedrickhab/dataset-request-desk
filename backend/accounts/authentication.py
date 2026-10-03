"""Session authentication that always enforces CSRF and reports 401 correctly."""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication

# Methods that cannot change state, so CSRF does not apply to them.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CSRFSessionAuthentication(SessionAuthentication):
    """SessionAuthentication with two deliberate corrections.

    1. CSRF on anonymous unsafe requests.

       DRF's APIView.as_view() wraps every view in csrf_exempt, so Django's
       CsrfViewMiddleware never fires for the API. DRF substitutes its own
       check inside SessionAuthentication.enforce_csrf -- but authenticate()
       returns early when there is no session user, so enforce_csrf is never
       reached for an anonymous caller. The result is that POST /auth/login,
       the one anonymous endpoint that accepts credentials, would have no CSRF
       protection whatsoever. This class closes that gap.

    2. 401 rather than 403 for unauthenticated callers.

       DRF downgrades NotAuthenticated to PermissionDenied when the
       authenticator exposes no authenticate_header, which would make every
       anonymous request a 403. The API contract specifies 401 for
       unauthenticated and 403 for an authenticated caller lacking the role,
       and conflating them hides which of the two actually happened.
       'Session' is used as the scheme because browsers raise a native
       credential prompt only for Basic and Digest.
    """

    def authenticate(self, request):  # noqa: ANN001, ANN201 - DRF request type
        result = super().authenticate(request)
        if result is None and request.method not in SAFE_METHODS:
            # Anonymous state-changing request: check the token anyway. Raises
            # PermissionDenied (403) when the token is missing or wrong.
            self.enforce_csrf(request)
        return result

    def authenticate_header(self, request) -> str:  # noqa: ANN001
        return "Session"
