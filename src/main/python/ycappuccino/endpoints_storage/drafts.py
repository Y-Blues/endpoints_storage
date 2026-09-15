"""
Named drafts of the documents of an item: the draft x of the document id is the document id~x of the same
item, marked with _draft and _draft_of.
"""

from ycappuccino.api.endpoints_storage import (
    WRITE,
    IAuthorization,
    IDrafts,
    InvalidRequest,
    NotFound,
)
from ycappuccino.api.storage import IItemManager, IManager
from ycappuccino.endpoints_storage import params as p
from ycappuccino.endpoints_storage.access import Access
from ycappuccino.storage.query import PRIVATE_FIELDS

# read of the complete document, to copy it
ALL_FIELDS = {"content": PRIVATE_FIELDS}


class Drafts(IDrafts):

    def __init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization]):
        self._manager = manager
        self._access = Access(items, authorizations)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_one(self, item_id, id, draft, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        _check(item, id, draft)
        with p.invalid_request():
            model = await self._manager.get_one(item_id, _draft_id(id, draft), params, subject)
            if model is None:
                model = await self._manager.get_one(item_id, id, p.with_condition(params, p.NO_DRAFT), subject)
        if model is None:
            raise NotFound(f"{item_id} {id} not found")
        return _result(model, item, private_fields=True)

    async def get_many(self, item_id, draft, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        _check_draftable(item)
        _check_name(draft)
        suffix = p.DRAFT_SEPARATOR + draft
        with p.invalid_request():
            draft_ids = await p.all_ids(self._manager, item_id, {"_draft": draft}, subject)
            originals = [draft_id[: -len(suffix)] for draft_id in draft_ids]
            versions = {
                "$or": [{"_draft": {"$exists": False}, "_id": {"$nin": originals}}, {"_draft": draft}]
            }
            scoped = p.with_condition(params, versions)
            models = await self._manager.get_many(item_id, scoped, subject)
            total = await self._manager.count(item_id, scoped, subject)
        return {"items": [_result(model, item, private_fields=True) for model in models], "total": total}

    async def save(self, item_id, id, draft, fields, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        fields = p.check_fields(fields, ("_id",) + p.DRAFT_FIELDS)
        draft_id = _draft_id(id, draft)
        with p.invalid_request():
            if await self._manager.get_one(item_id, draft_id, None, subject) is None:
                original = await self._manager.get_one(
                    item_id, id, {"filter": p.NO_DRAFT, **ALL_FIELDS}, subject
                )
                if original is not None:
                    fields = {**p.to_fields(original.get_storage_model()), **fields}
            fields.update({"_draft": draft, "_draft_of": id})
            model = await self._manager.up_sert(item_id, draft_id, fields, subject)
        return _result(model, item, private_fields=False)

    async def publish(self, item_id, id, draft, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        draft_id = _draft_id(id, draft)
        with p.invalid_request():
            version = await self._manager.get_one(item_id, draft_id, ALL_FIELDS, subject)
            if version is None:
                raise NotFound(f"{item_id} {id} has no draft {draft}")
            model = await self._manager.up_sert(item_id, id, p.to_fields(version.get_storage_model()), subject)
            await self._manager.delete(item_id, draft_id, subject)
        return _result(model, item, private_fields=False)

    async def discard(self, item_id, id, draft, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        draft_id = _draft_id(id, draft)
        if await self._manager.get_one(item_id, draft_id, None, subject) is None:
            raise NotFound(f"{item_id} {id} has no draft {draft}")
        await self._manager.delete(item_id, draft_id, subject)


def _draft_id(id, draft) -> str:
    return f"{id}{p.DRAFT_SEPARATOR}{draft}"


def _check(item, id, draft) -> None:
    _check_draftable(item)
    p.check_id(id)
    _check_name(draft)


def _check_draftable(item) -> None:
    if item.get("multipart"):
        raise InvalidRequest(f"item {item['id']} is multipart: it has no drafts")


def _check_name(draft) -> None:
    if not isinstance(draft, str) or not draft or p.DRAFT_SEPARATOR in draft:
        raise InvalidRequest(f"invalid draft name {draft!r}")


def _result(model, item, private_fields) -> dict:
    """document of the model; a draft version gets the id of its original and its draft name"""
    document = p.to_dict(model, item, private_fields)
    id, separator, draft = document["_id"].rpartition(p.DRAFT_SEPARATOR)
    if separator:
        document["_id"] = id
        document["_draft"] = draft
    return document
