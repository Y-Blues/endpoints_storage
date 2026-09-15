import json
import unittest

from crud_fixtures import ALICE, FakeAuthorization

from ycappuccino.api.endpoints_storage import NotAuthenticated, NotFound
from ycappuccino.endpoints_storage.catalog import ItemCatalog
from ycappuccino.storage.items import ItemManager

PUBLIC_KEYS = {"id", "plural", "app", "module", "secure_read", "secure_write", "writable", "multipart", "refs"}


class TestItemCatalog(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.authorization = FakeAuthorization()
        self.catalog = ItemCatalog(ItemManager(), [self.authorization])

    async def crud_ids(self, subject):
        return sorted(item["id"] for item in await self.catalog.get_items(subject) if item["id"].startswith("crud_"))

    async def test_items_are_filtered_by_subject(self):
        self.assertEqual(await self.crud_ids(None), ["crud_archive", "crud_book", "crud_media", "crud_novel"])
        self.assertEqual(
            await self.crud_ids(ALICE), ["crud_archive", "crud_author", "crud_book", "crud_media", "crud_novel"]
        )
        self.authorization.allowed = set()
        self.assertNotIn("crud_author", await self.crud_ids(ALICE))

    async def test_public_view_is_serializable(self):
        book = await self.catalog.get_item("crud_book")

        self.assertEqual(set(book), PUBLIC_KEYS)
        self.assertEqual(
            (book["id"], book["plural"], book["secure_read"], book["secure_write"], book["writable"], book["multipart"]),
            ("crud_book", "crud_books", False, True, True, None),
        )
        self.assertEqual(book["refs"]["crud_author"]["local_field"], "author.ref")
        self.assertFalse((await self.catalog.get_item("crud_archive"))["writable"])
        self.assertEqual((await self.catalog.get_item("crud_media"))["multipart"], "file")
        json.dumps(await self.catalog.get_items(ALICE))

    async def test_public_view_is_a_copy(self):
        book = await self.catalog.get_item("crud_book")
        book["refs"]["crud_author"]["local_field"] = "changed"

        self.assertEqual((await self.catalog.get_item("crud_book"))["refs"]["crud_author"]["local_field"], "author.ref")

    async def test_get_item_is_checked(self):
        for item_id in ("unknown", "crud_base"):
            with self.subTest(item_id=item_id):
                with self.assertRaises(NotFound):
                    await self.catalog.get_item(item_id)
        with self.assertRaises(NotAuthenticated):
            await self.catalog.get_item("crud_author")

    async def test_get_item_by_plural(self):
        self.assertEqual((await self.catalog.get_item_by_plural("crud_novels"))["id"], "crud_novel")
        with self.assertRaises(NotFound):
            await self.catalog.get_item_by_plural("unknown")
        with self.assertRaises(NotAuthenticated):
            await self.catalog.get_item_by_plural("crud_authors")

    async def test_schema(self):
        schema = await self.catalog.get_schema("crud_book")
        schema["properties"]["pages"]["type"] = "changed"

        schema = await self.catalog.get_schema("crud_book")
        self.assertEqual(schema["properties"]["pages"]["type"], "integer")
        self.assertIn("title", schema["properties"])
        with self.assertRaises(NotAuthenticated):
            await self.catalog.get_schema("crud_author")

    async def test_empty(self):
        self.assertEqual(await self.catalog.get_empty("crud_book"), {"_id": "empty", "title": ""})
        self.assertIsNone(await self.catalog.get_empty("crud_archive"))
        with self.assertRaises(NotAuthenticated):
            await self.catalog.get_empty("crud_author")


if __name__ == "__main__":
    unittest.main()
