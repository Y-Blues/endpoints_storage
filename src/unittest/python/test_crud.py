import shutil
import unittest
import uuid

from crud_fixtures import ALICE, FakeAuthorization, create_manager

from ycappuccino.api.endpoints_storage import Forbidden, InvalidRequest, NotAuthenticated, NotFound
from ycappuccino.endpoints_storage.crud import Crud
from ycappuccino.storage.items import ItemManager

PRIVATE = {"content": "privateField"}


class TestCrud(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager, directory = create_manager()
        self.addCleanup(shutil.rmtree, directory, True)
        self.authorization = FakeAuthorization()
        self.crud = Crud(ItemManager(), self.manager, [self.authorization])
        await self.manager.up_sert("crud_author", "herbert", {"name": "Frank Herbert"})
        await self.manager.up_sert("crud_book", "dune", {"title": "Dune", "pages": 412, "isbn": "978", "author": "herbert"})
        await self.manager.up_sert("crud_book", "solaris", {"title": "Solaris", "pages": 204})
        await self.manager.up_sert("crud_novel", "hyperion", {"title": "Hyperion", "pages": 482})
        await self.manager.up_sert("crud_book", "dune~x", {"title": "Dune draft", "_draft": "x", "_draft_of": "dune"})

    async def stored(self, id):
        model = await self.manager.get_one("crud_book", id, PRIVATE)
        return None if model is None else model.get_storage_model()

    async def test_get_one_returns_a_dict_without_private_properties(self):
        dune = await self.crud.get_one("crud_book", "dune")

        self.assertIsInstance(dune, dict)
        self.assertEqual(dune["title"], "Dune")
        self.assertEqual(dune["author"], {"ref": "herbert"})
        self.assertNotIn("isbn", dune)

    async def test_get_one_with_private_fields(self):
        self.assertEqual((await self.crud.get_one("crud_book", "dune", PRIVATE, ALICE))["isbn"], "978")

    async def test_get_one_of_a_missing_document_or_of_a_draft(self):
        for id in ("unknown", "dune~x"):
            with self.subTest(id=id):
                with self.assertRaises(NotFound):
                    await self.crud.get_one("crud_book", id)

    async def test_get_many_returns_items_and_total_without_drafts(self):
        page = await self.crud.get_many("crud_book", {"sort": {"pages": 1}, "limit": 2})

        self.assertEqual([book["_id"] for book in page["items"]], ["solaris", "dune"])
        self.assertEqual(page["total"], 3)

    async def test_get_many_combines_the_filter(self):
        page = await self.crud.get_many("crud_book", {"filter": '{"pages": {"$gt": 300}}', "sort": {"_id": 1}})

        self.assertEqual([book["_id"] for book in page["items"]], ["dune", "hyperion"])
        self.assertEqual(page["total"], 2)

    async def test_invalid_read_params(self):
        for params in ({"limit": "many"}, {"filter": "{"}, {"sort": "[1]"}):
            with self.subTest(params=params):
                with self.assertRaises(InvalidRequest):
                    await self.crud.get_many("crud_book", params)

    async def test_secured_read_requires_a_subject(self):
        with self.assertRaises(NotAuthenticated):
            await self.crud.get_one("crud_author", "herbert")
        self.assertEqual((await self.crud.get_one("crud_author", "herbert", subject=ALICE))["name"], "Frank Herbert")

    async def test_create_with_and_without_id(self):
        foundation = await self.crud.create("crud_book", {"_id": "foundation", "title": "Foundation"}, ALICE)
        generated = await self.crud.create("crud_book", {"title": "Untitled"}, ALICE)

        self.assertEqual(foundation["_id"], "foundation")
        self.assertEqual((await self.stored("foundation"))["title"], "Foundation")
        uuid.UUID(generated["_id"])
        self.assertEqual((await self.stored(generated["_id"]))["title"], "Untitled")

    async def test_write_result_has_no_private_property(self):
        created = await self.crud.create("crud_book", {"_id": "emma", "title": "Emma", "isbn": "111"}, ALICE)

        self.assertNotIn("isbn", created)
        self.assertEqual((await self.stored("emma"))["isbn"], "111")

    async def test_update_is_a_partial_upsert(self):
        updated = await self.crud.update("crud_book", "dune", {"pages": 413}, ALICE)

        self.assertEqual((updated["title"], updated["pages"]), ("Dune", 413))
        await self.crud.update("crud_book", "new", {"_id": "new", "title": "New"}, ALICE)
        self.assertEqual((await self.stored("new"))["title"], "New")

    async def test_writes_are_checked(self):
        with self.assertRaises(NotAuthenticated):
            await self.crud.create("crud_book", {"title": "Anonymous"})
        with self.assertRaises(Forbidden):
            await self.crud.update("crud_archive", "a", {"title": "Archive"}, ALICE)

    async def test_invalid_writes(self):
        cases = (
            lambda: self.crud.create("crud_book", {"_id": "a~b"}, ALICE),
            lambda: self.crud.create("crud_book", {"title": "t", "_draft": "x"}, ALICE),
            lambda: self.crud.update("crud_book", "a~b", {}, ALICE),
            lambda: self.crud.update("crud_book", "dune", {"_draft_of": "solaris"}, ALICE),
            lambda: self.crud.update("crud_book", "dune", {"_id": "solaris"}, ALICE),
            lambda: self.crud.update("crud_book", "dune", ["pages"], ALICE),
        )
        for index, case in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(InvalidRequest):
                    await case()

    async def test_delete_removes_the_drafts(self):
        await self.crud.delete("crud_book", "dune", ALICE)

        self.assertIsNone(await self.stored("dune"))
        self.assertIsNone(await self.stored("dune~x"))

    async def test_delete_of_a_missing_document(self):
        with self.assertRaises(NotFound):
            await self.crud.delete("crud_book", "unknown", ALICE)

    async def test_delete_many_requires_a_filter(self):
        for filter in (None, {}, ""):
            with self.subTest(filter=filter):
                with self.assertRaises(InvalidRequest):
                    await self.crud.delete_many("crud_book", filter, ALICE)

    async def test_delete_many_removes_the_matching_documents_and_their_drafts(self):
        deleted = await self.crud.delete_many("crud_book", {"pages": {"$gt": 300}}, ALICE)

        self.assertEqual(deleted, 2)
        for id in ("dune", "hyperion", "dune~x"):
            self.assertIsNone(await self.stored(id))
        self.assertIsNotNone(await self.stored("solaris"))

    async def test_delete_is_checked(self):
        self.authorization.allowed = set()

        with self.assertRaises(Forbidden):
            await self.crud.delete("crud_book", "dune", ALICE)


if __name__ == "__main__":
    unittest.main()
