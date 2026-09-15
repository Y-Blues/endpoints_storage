import unittest

from crud_fixtures import ALICE, FakeAuthorization

from ycappuccino.api.endpoints_storage import (
    DELETE,
    PRIVATE,
    READ,
    WRITE,
    Forbidden,
    InvalidRequest,
    NotAuthenticated,
    NotFound,
)
from ycappuccino.endpoints_storage.access import Access
from ycappuccino.storage.items import ItemManager


class TestCheck(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.authorization = FakeAuthorization(allowed=())
        self.authorizations = [self.authorization]
        self.access = Access(ItemManager(), self.authorizations)

    async def test_unknown_and_abstract_items_are_not_found(self):
        for item_id in ("unknown", "crud_base"):
            with self.subTest(item_id=item_id):
                with self.assertRaises(NotFound):
                    await self.access.check(item_id, READ, ALICE)
                with self.assertRaises(NotFound):
                    self.access.item(item_id)

    async def test_read_only_item_refuses_writes_whatever_the_subject(self):
        self.authorization.allowed = {"*"}

        for action in (WRITE, DELETE):
            with self.subTest(action=action):
                with self.assertRaises(Forbidden):
                    await self.access.check("crud_archive", action, ALICE)
        self.assertEqual((await self.access.check("crud_archive", READ, None))["id"], "crud_archive")

    async def test_unsecured_action_does_not_call_the_authorization(self):
        item = await self.access.check("crud_book", READ, None)

        self.assertEqual(item["id"], "crud_book")
        self.assertEqual(self.authorization.calls, [])

    async def test_secured_action_requires_a_subject(self):
        for item_id, action in (("crud_book", WRITE), ("crud_book", DELETE), ("crud_author", READ), ("crud_book", PRIVATE)):
            with self.subTest(item_id=item_id, action=action):
                with self.assertRaises(NotAuthenticated):
                    await self.access.check(item_id, action, None)

    async def test_secured_action_without_authorization_service_is_forbidden(self):
        self.authorizations.clear()

        with self.assertLogs("ycappuccino.endpoints_storage.access", "WARNING"):
            with self.assertRaises(Forbidden):
                await self.access.check("crud_book", WRITE, ALICE)

    async def test_secured_action_asks_the_authorization(self):
        self.authorization.allowed = {(WRITE, "crud_book")}

        self.assertEqual((await self.access.check("crud_book", WRITE, ALICE))["id"], "crud_book")
        with self.assertRaises(Forbidden):
            await self.access.check("crud_book", DELETE, ALICE)
        self.assertEqual(self.authorization.calls, [("alice", WRITE, "crud_book"), ("alice", DELETE, "crud_book")])

    async def test_authorization_registered_after_construction_is_used(self):
        self.authorizations.clear()
        self.authorizations.append(FakeAuthorization())

        self.assertEqual((await self.access.check("crud_book", WRITE, ALICE))["id"], "crud_book")


class TestCheckRead(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.authorization = FakeAuthorization(allowed=())
        self.access = Access(ItemManager(), [self.authorization])

    async def test_plain_read(self):
        self.assertEqual((await self.access.check_read("crud_book", None, None))["id"], "crud_book")

    async def test_private_fields_require_the_private_action(self):
        with self.assertRaises(NotAuthenticated):
            await self.access.check_read("crud_book", {"content": "privateField"}, None)

        self.authorization.allowed = {(PRIVATE, "crud_book")}
        await self.access.check_read("crud_book", {"content": "privateField"}, ALICE)
        self.assertEqual(self.authorization.calls[-1], ("alice", PRIVATE, "crud_book"))

    async def test_expanded_items_are_checked(self):
        with self.assertRaises(NotAuthenticated):
            await self.access.check_read("crud_book", {"expand": "crud_author"}, None)

        self.authorization.allowed = {(READ, "crud_author")}
        await self.access.check_read("crud_book", {"expand": "crud_author(limit=2).crud_book"}, ALICE)
        self.assertEqual(self.authorization.calls[-1], ("alice", READ, "crud_author"))

    async def test_unknown_expanded_item_is_not_found(self):
        with self.assertRaises(NotFound):
            await self.access.check_read("crud_book", {"expand": "unknown"}, ALICE)

    async def test_invalid_expand(self):
        with self.assertRaises(InvalidRequest):
            await self.access.check_read("crud_book", {"expand": "crud_author(limit"}, ALICE)


if __name__ == "__main__":
    unittest.main()
