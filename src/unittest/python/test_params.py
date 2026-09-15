import shutil
import unittest
from unittest import mock

from crud_fixtures import Book, create_manager

from ycappuccino.api.endpoints_storage import InvalidRequest
from ycappuccino.endpoints_storage import params


class TestInvalidRequest(unittest.TestCase):

    def test_value_errors_become_invalid_requests(self):
        with self.assertRaisesRegex(InvalidRequest, "bad limit"):
            with params.invalid_request():
                raise ValueError("bad limit")

    def test_other_errors_are_kept(self):
        with self.assertRaises(KeyError):
            with params.invalid_request():
                raise KeyError("book")


class TestFilters(unittest.TestCase):

    def test_parse_filter(self):
        self.assertEqual(params.parse_filter(None), {})
        self.assertEqual(params.parse_filter(""), {})
        self.assertEqual(params.parse_filter({"a": 1}), {"a": 1})
        self.assertEqual(params.parse_filter('{"a": 1}'), {"a": 1})

    def test_invalid_filters(self):
        for value in ("{not json", "[1]", 3):
            with self.subTest(value=value):
                with self.assertRaises(InvalidRequest):
                    params.parse_filter(value)

    def test_with_condition_without_filter(self):
        self.assertEqual(params.with_condition(None, {"b": 2}), {"filter": {"b": 2}})

    def test_with_condition_keeps_the_other_params_and_does_not_mutate_them(self):
        original = {"filter": '{"a": 1}', "limit": 5}
        condition = {"b": {"$exists": False}}

        combined = params.with_condition(original, condition)
        combined["filter"]["$and"][1]["b"]["$exists"] = True

        self.assertEqual(original, {"filter": '{"a": 1}', "limit": 5})
        self.assertEqual(condition, {"b": {"$exists": False}})
        self.assertEqual(combined["limit"], 5)


class TestIdsAndFields(unittest.TestCase):

    def test_check_id(self):
        self.assertEqual(params.check_id("dune"), "dune")
        for id in ("", "dune~x", None, 3):
            with self.subTest(id=id):
                with self.assertRaises(InvalidRequest):
                    params.check_id(id)

    def test_check_fields(self):
        fields = {"title": "Dune"}

        checked = params.check_fields(fields, params.DRAFT_FIELDS)
        checked["title"] = "changed"

        self.assertEqual(fields, {"title": "Dune"})
        for invalid in ({"_draft": "x"}, {"_draft_of": "dune"}, ["title"]):
            with self.subTest(fields=invalid):
                with self.assertRaises(InvalidRequest):
                    params.check_fields(invalid, params.DRAFT_FIELDS)

    def test_to_fields_flattens_references_and_drops_the_id(self):
        document = {"_id": "dune", "title": "Dune", "author": {"ref": "herbert"}, "meta": {"ref": "a", "n": 1}}

        self.assertEqual(
            params.to_fields(document), {"title": "Dune", "author": "herbert", "meta": {"ref": "a", "n": 1}}
        )

    def test_to_dict_is_a_copy_without_private_properties(self):
        book = Book()
        book.id("dune")
        book.isbn("978")
        book.author("herbert")
        item = {"private_property": ["isbn"]}

        result = params.to_dict(book, item)
        result["author"]["ref"] = "changed"

        self.assertEqual(result, {"_id": "dune", "author": {"ref": "changed"}})
        self.assertEqual(book.get_storage_model()["author"], {"ref": "herbert"})
        self.assertEqual(params.to_dict(book, item, private_fields=True)["isbn"], "978")


class TestAllIds(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager, directory = create_manager()
        self.addCleanup(shutil.rmtree, directory, True)
        for id, pages in (("c", 300), ("a", 100), ("e", 500), ("b", 200), ("d", 400)):
            await self.manager.up_sert("crud_book", id, {"pages": pages})

    async def test_all_ids_reads_every_page(self):
        with mock.patch.object(params, "PAGE", 2):
            ids = await params.all_ids(self.manager, "crud_book", {"pages": {"$gte": 200}}, None)

        self.assertEqual(ids, ["b", "c", "d", "e"])


if __name__ == "__main__":
    unittest.main()
