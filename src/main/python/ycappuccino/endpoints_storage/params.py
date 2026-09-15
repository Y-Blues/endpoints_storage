"""
Helpers shared by the services: filters, ids and fields checks, conversion of errors and results.
"""

import contextlib
import copy
import json

from ycappuccino.api.endpoints_storage import InvalidRequest

DRAFT_SEPARATOR = "~"
DRAFT_FIELDS = ("_draft", "_draft_of")
NO_DRAFT = {"_draft": {"$exists": False}}
# page size when all the ids of a query are read
PAGE = 1000


@contextlib.contextmanager
def invalid_request():
    """turn a ValueError (invalid JSON, integer or expand) into InvalidRequest"""
    try:
        yield
    except ValueError as error:
        raise InvalidRequest(str(error)) from error


def parse_filter(value) -> dict:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        with invalid_request():
            value = json.loads(value)
    if not isinstance(value, dict):
        raise InvalidRequest(f"filter must be a JSON object, got {value!r}")
    return value


def with_condition(params, condition) -> dict:
    """copy of params whose filter also requires the condition"""
    params = dict(params or {})
    user_filter = copy.deepcopy(parse_filter(params.get("filter")))
    condition = copy.deepcopy(condition)
    params["filter"] = {"$and": [user_filter, condition]} if user_filter else condition
    return params


def check_id(id) -> str:
    if not isinstance(id, str) or not id or DRAFT_SEPARATOR in id:
        raise InvalidRequest(f"invalid id {id!r}")
    return id


def check_fields(fields, forbidden) -> dict:
    if not isinstance(fields, dict):
        raise InvalidRequest("fields must be a JSON object")
    for name in forbidden:
        if name in fields:
            raise InvalidRequest(f"field {name} can't be written")
    return dict(fields)


def to_dict(model, item, private_fields=False) -> dict:
    """copy of the storage model of the model, without the private properties of the item"""
    document = copy.deepcopy(model.get_storage_model())
    if not private_fields:
        for name in item.get("private_property", []):
            document.pop(name, None)
    return document


def to_fields(document) -> dict:
    """fields to write a read document again: without _id, references flattened to their id"""
    fields = {}
    for name, value in document.items():
        if name == "_id":
            continue
        if isinstance(value, dict) and set(value) == {"ref"}:
            value = value["ref"]
        fields[name] = copy.deepcopy(value)
    return fields


async def all_ids(manager, item_id, filter, subject) -> list:
    """ids of all the documents of the item matching the filter"""
    ids = []
    offset = 0
    while True:
        models = await manager.get_many(
            item_id, {"filter": filter, "sort": {"_id": 1}, "limit": PAGE, "offset": offset}, subject
        )
        ids.extend(model.get_storage_model()["_id"] for model in models)
        if len(models) < PAGE:
            return ids
        offset += PAGE
