"""
Authorization rules of the use cases: flags of @Item first, then the IAuthorization port.
"""

import logging

from ycappuccino.api.endpoints_storage import (
    DELETE,
    PRIVATE,
    READ,
    WRITE,
    Forbidden,
    NotAuthenticated,
    NotFound,
)
from ycappuccino.endpoints_storage.params import invalid_request
from ycappuccino.storage.query import PRIVATE_FIELDS, parse_expand

_logger = logging.getLogger(__name__)


class Access(object):
    """checks of a service; authorizations is the live list injected by the core"""

    def __init__(self, items, authorizations):
        self._items = items
        self._authorizations = authorizations

    def item(self, item_id) -> dict:
        try:
            item = self._items.get_item(item_id)
        except KeyError:
            raise NotFound(f"unknown item {item_id}") from None
        if item.get("abstract", False):
            raise NotFound(f"abstract item {item_id}")
        return item

    async def check(self, item_id, action, subject) -> dict:
        item = self.item(item_id)
        if action in (WRITE, DELETE) and not item.get("isWritable", True):
            raise Forbidden(f"item {item_id} is read-only")
        if not _is_secured(item, action):
            return item
        if subject is None:
            raise NotAuthenticated(f"{action} on {item_id} requires a subject")
        authorizations = list(self._authorizations)
        if not authorizations:
            _logger.warning("no IAuthorization service: %s on %s is refused", action, item_id)
            raise Forbidden(f"{action} on {item_id} is not authorized")
        if not await authorizations[0].is_authorized(subject, action, item_id):
            raise Forbidden(f"{action} on {item_id} is not authorized")
        return item

    async def check_read(self, item_id, params, subject) -> dict:
        item = await self.check(item_id, READ, subject)
        params = params or {}
        if PRIVATE_FIELDS in str(params.get("content") or ""):
            await self.check(item_id, PRIVATE, subject)
        with invalid_request():
            paths = parse_expand(params.get("expand") or "")
        for path in paths:
            for segment in path:
                await self.check(segment.name, READ, subject)
        return item


def _is_secured(item, action) -> bool:
    if action == PRIVATE:
        return True
    if action == READ:
        return bool(item.get("secureRead", False))
    return bool(item.get("secureWrite", False))
