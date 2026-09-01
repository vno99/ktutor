"""HTTP API package for ktutor (s09).

Each subpackage is a domain (``auth``, ``users``, ``documents``, ``chat``,
``exercises``, ``evaluations``, ``dashboard``, ``notifications``) and
contains a ``router.py`` and ``schemas.py``. s09 ships the first domain
(``chat``); subsequent stories fill the rest.

The API is mounted under ``/api`` (see ``app/main.py``).
"""
