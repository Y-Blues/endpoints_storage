"""
Metadata of the items readable by a subject, as serializable dicts.
"""

import copy

from ycappuccino.api.endpoints_storage import READ, CrudError, IAuthorization, IItemCatalog, NotFound
from ycappuccino.api.storage import IItemManager
from ycappuccino.endpoints_storage.access import Access


class ItemCatalog(IItemCatalog):

    def __init__(self, items: IItemManager, authorizations: list[IAuthorization]) -> None:
        self._items = items
        self._access = Access(items, authorizations)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def get_items(self, subject: dict | None = None) -> list:
        readable = []
        for item in self._items.get_items():
            try:
                await self._access.check(item["id"], READ, subject)
            except CrudError:
                continue
            readable.append(_public(item))
        return readable

    async def get_item(self, item_id: str, subject: dict | None = None) -> dict:
        return _public(await self._access.check(item_id, READ, subject))

    async def get_item_by_plural(self, plural: str, subject: dict | None = None) -> dict:
        try:
            item = self._items.get_item_by_plural(plural)
        except KeyError:
            raise NotFound(f"unknown plural {plural}") from None
        return await self.get_item(item["id"], subject)

    async def get_schema(self, item_id: str, subject: dict | None = None) -> dict:
        await self._access.check(item_id, READ, subject)
        return copy.deepcopy(self._items.get_schema(item_id))

    async def get_empty(self, item_id: str, subject: dict | None = None) -> dict | None:
        await self._access.check(item_id, READ, subject)
        return copy.deepcopy(self._items.get_empty(item_id))


def _public(item: dict) -> dict:
    return {
        "id": item["id"],
        "plural": item["plural"],
        "app": item.get("app"),
        "module": item.get("module"),
        "secure_read": bool(item.get("secureRead", False)),
        "secure_write": bool(item.get("secureWrite", False)),
        "writable": bool(item.get("isWritable", True)),
        "multipart": item.get("multipart"),
        "refs": copy.deepcopy(item.get("refs", {})),
    }
