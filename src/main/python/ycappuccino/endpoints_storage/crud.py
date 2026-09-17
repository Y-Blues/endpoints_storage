"""
CRUD use case on the documents of an item; drafts are excluded from its reads.
"""

import uuid

from ycappuccino.api.endpoints_storage import (
    DELETE,
    WRITE,
    IAuthorization,
    ICrud,
    InvalidRequest,
    NotFound,
)
from ycappuccino.api.storage import IItemManager, IManager
from ycappuccino.endpoints_storage import params as p
from ycappuccino.endpoints_storage.access import Access


class Crud(ICrud):

    def __init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization]) -> None:
        self._manager = manager
        self._access = Access(items, authorizations)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def get_one(self, item_id: str, id: str, params: dict | None = None, subject: dict | None = None) -> dict:
        item = await self._access.check_read(item_id, params, subject)
        scoped = p.with_condition(params, p.NO_DRAFT)
        with p.invalid_request():
            model = await self._manager.get_one(item_id, id, scoped, subject)
        if model is None:
            raise NotFound(f"{item_id} {id} not found")
        # the manager already removed the private properties when they were not asked
        return p.to_dict(model, item, private_fields=True)

    async def get_many(self, item_id: str, params: dict | None = None, subject: dict | None = None) -> dict:
        item = await self._access.check_read(item_id, params, subject)
        scoped = p.with_condition(params, p.NO_DRAFT)
        with p.invalid_request():
            models = await self._manager.get_many(item_id, scoped, subject)
            total = await self._manager.count(item_id, scoped, subject)
        return {"items": [p.to_dict(model, item, private_fields=True) for model in models], "total": total}

    async def create(self, item_id: str, fields: dict, subject: dict | None = None) -> dict:
        item = await self._access.check(item_id, WRITE, subject)
        fields = p.check_fields(fields, p.DRAFT_FIELDS)
        id = fields.pop("_id", None)
        id = str(uuid.uuid4()) if id is None else p.check_id(id)
        return await self._up_sert(item, id, fields, subject)

    async def update(self, item_id: str, id: str, fields: dict, subject: dict | None = None) -> dict:
        item = await self._access.check(item_id, WRITE, subject)
        p.check_id(id)
        fields = p.check_fields(fields, p.DRAFT_FIELDS)
        if fields.pop("_id", id) != id:
            raise InvalidRequest(f"the _id of the fields differs from {id}")
        return await self._up_sert(item, id, fields, subject)

    async def delete(self, item_id: str, id: str, subject: dict | None = None) -> None:
        await self._access.check(item_id, DELETE, subject)
        p.check_id(id)
        if await self._manager.get_one(item_id, id, {"filter": p.NO_DRAFT}, subject) is None:
            raise NotFound(f"{item_id} {id} not found")
        await self._manager.delete(item_id, id, subject)
        await self._manager.delete_many(item_id, {"_draft_of": id}, subject)

    async def delete_many(self, item_id: str, filter: dict, subject: dict | None = None) -> int:
        await self._access.check(item_id, DELETE, subject)
        condition = p.parse_filter(filter)
        if not condition:
            raise InvalidRequest("delete_many requires a non empty filter")
        scoped = p.with_condition({"filter": condition}, p.NO_DRAFT)["filter"]
        with p.invalid_request():
            ids = await p.all_ids(self._manager, item_id, scoped, subject)
            if ids:
                await self._manager.delete_many(item_id, {"_id": {"$in": ids}}, subject)
                await self._manager.delete_many(item_id, {"_draft_of": {"$in": ids}}, subject)
        return len(ids)

    async def _up_sert(self, item: dict, id: str, fields: dict, subject: dict | None) -> dict:
        with p.invalid_request():
            model = await self._manager.up_sert(item["id"], id, fields, subject)
        return p.to_dict(model, item)
