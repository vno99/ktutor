"""Admin user management API domain (s13b).

Exposes the admin-only ``POST /api/users`` and
``PUT /api/users/{pseudo}/role`` endpoints for creating non-eleve
accounts and changing a user's role. The endpoints are mounted
under the ``/api/users`` prefix by :mod:`app.api.users.router`.
"""
