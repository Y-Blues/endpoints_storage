import shutil
import unittest

from crud_fixtures import ALICE, FakeAuthorization, RecordingTrigger, create_manager

from ycappuccino.api.endpoints_storage import InvalidRequest, NotAuthenticated, NotFound
from ycappuccino.endpoints_storage.drafts import Drafts
from ycappuccino.storage.items import ItemManager

PRIVATE = {"content": "privateField"}


class TestDrafts(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.trigger = RecordingTrigger("crud_book", ("upsert",))
        self.manager, directory = create_manager([self.trigger])
        self.addCleanup(shutil.rmtree, directory, True)
        self.drafts = Drafts(ItemManager(), self.manager, [FakeAuthorization()])
        await self.manager.up_sert("crud_book", "dune", {"title": "Dune", "pages": 412, "isbn": "978", "author": "herbert"})
        await self.manager.up_sert("crud_book", "solaris", {"title": "Solaris", "pages": 204})
        await self.manager.up_sert("crud_novel", "hyperion", {"title": "Hyperion", "pages": 482})
        for id, draft, title in (("dune", "x", "Dune v2"), ("new", "x", "New"), ("dune", "y", "Dune y")):
            await self.manager.up_sert(
                "crud_book", f"{id}~{draft}", {"title": title, "_draft": draft, "_draft_of": id}
            )
        self.trigger.calls.clear()

    async def stored(self, id):
        model = await self.manager.get_one("crud_book", id, PRIVATE)
        return None if model is None else model.get_storage_model()

    @staticmethod
    def versions(page):
        return [(document["_id"], document.get("_draft")) for document in page["items"]]

    async def test_get_one_returns_the_draft_version_under_the_original_id(self):
        dune = await self.drafts.get_one("crud_book", "dune", "x")

        self.assertEqual((dune["_id"], dune["_draft"], dune["title"]), ("dune", "x", "Dune v2"))

    async def test_get_one_falls_back_to_the_original(self):
        solaris = await self.drafts.get_one("crud_book", "solaris", "x")

        self.assertEqual(solaris["title"], "Solaris")
        self.assertNotIn("_draft", solaris)
        with self.assertRaises(NotFound):
            await self.drafts.get_one("crud_book", "unknown", "x")

    async def test_get_many_replaces_the_originals_by_their_draft(self):
        page = await self.drafts.get_many("crud_book", "x", {"sort": {"_id": 1}})

        self.assertEqual(
            self.versions(page), [("dune", "x"), ("hyperion", None), ("new", "x"), ("solaris", None)]
        )
        self.assertEqual(page["items"][0]["title"], "Dune v2")
        self.assertEqual(page["total"], 4)

    async def test_get_many_pagination_and_filter(self):
        page = await self.drafts.get_many("crud_book", "x", {"sort": {"_id": 1}, "limit": 2, "offset": 1})
        filtered = await self.drafts.get_many(
            "crud_book", "x", {"filter": {"title": {"$in": ["Dune v2", "Solaris"]}}, "sort": {"_id": 1}}
        )

        self.assertEqual(self.versions(page), [("hyperion", None), ("new", "x")])
        self.assertEqual(page["total"], 4)
        self.assertEqual(self.versions(filtered), [("dune", "x"), ("solaris", None)])
        self.assertEqual(filtered["total"], 2)

    async def test_first_save_starts_from_the_original(self):
        saved = await self.drafts.save("crud_book", "dune", "z", {"pages": 500}, ALICE)

        self.assertEqual((saved["_id"], saved["_draft"], saved["title"], saved["pages"]), ("dune", "z", "Dune", 500))
        self.assertNotIn("isbn", saved)
        stored = await self.stored("dune~z")
        self.assertEqual((stored["isbn"], stored["author"]), ("978", {"ref": "herbert"}))
        self.assertEqual(
            await self.manager.count("crud_book", {"filter": {"_draft": "z", "_draft_of": "dune"}}), 1
        )

    async def test_next_saves_update_the_draft(self):
        saved = await self.drafts.save("crud_book", "dune", "x", {"pages": 1}, ALICE)

        self.assertEqual((saved["title"], saved["pages"]), ("Dune v2", 1))

    async def test_save_without_original(self):
        saved = await self.drafts.save("crud_book", "fresh", "x", {"title": "Fresh"}, ALICE)

        self.assertEqual((saved["_id"], saved["_draft"], saved["title"]), ("fresh", "x", "Fresh"))
        self.assertIsNone(await self.stored("fresh"))

    async def test_publish_writes_the_draft_on_the_original(self):
        published = await self.drafts.publish("crud_book", "dune", "x", ALICE)

        self.assertEqual((published["_id"], published["title"], published["pages"]), ("dune", "Dune v2", 412))
        self.assertNotIn("_draft", published)
        stored = await self.stored("dune")
        self.assertEqual((stored["isbn"], stored["author"]), ("978", {"ref": "herbert"}))
        self.assertIsNone(await self.stored("dune~x"))
        self.assertIsNotNone(await self.stored("dune~y"))
        self.assertEqual(self.trigger.calls, [("upsert", "crud_book", "dune")])

    async def test_publish_without_draft(self):
        with self.assertRaises(NotFound):
            await self.drafts.publish("crud_book", "solaris", "x", ALICE)

    async def test_discard(self):
        await self.drafts.discard("crud_book", "dune", "x", ALICE)

        self.assertIsNone(await self.stored("dune~x"))
        self.assertEqual((await self.stored("dune"))["title"], "Dune")
        with self.assertRaises(NotFound):
            await self.drafts.discard("crud_book", "dune", "x", ALICE)

    async def test_invalid_requests(self):
        cases = (
            lambda: self.drafts.get_one("crud_book", "dune", ""),
            lambda: self.drafts.get_many("crud_book", "a~b"),
            lambda: self.drafts.save("crud_book", "a~b", "x", {}, ALICE),
            lambda: self.drafts.save("crud_book", "dune", "x", {"_id": "dune"}, ALICE),
            lambda: self.drafts.save("crud_book", "dune", "x", {"_draft": "y"}, ALICE),
            lambda: self.drafts.save("crud_media", "logo", "x", {"name": "logo"}, ALICE),
            lambda: self.drafts.get_one("crud_media", "logo", "x"),
        )
        for index, case in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(InvalidRequest):
                    await case()

    async def test_writes_are_checked(self):
        with self.assertRaises(NotAuthenticated):
            await self.drafts.save("crud_book", "dune", "x", {"pages": 1})


if __name__ == "__main__":
    unittest.main()
