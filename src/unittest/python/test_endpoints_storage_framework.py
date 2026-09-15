import asyncio
import unittest

from ycappuccino.api.endpoints_storage import Forbidden, IAuthorization
from ycappuccino.core.framework import Framework
from ycappuccino.core.testing import TemporaryApplication, wait_until

ALICE = {"sub": "alice", "tid": "acme"}

APPLICATION = {
    "conf/application.yml": """
        name: library
        bundle_prefix:
          - ycappuccino.storage
          - ycappuccino.endpoints_storage
          - PACKAGE
        layers:
          ycappuccino_storage_memory:
            active: true
        config:
          shell:
            console: false
    """,
    "PACKAGE/__init__.py": "",
    "PACKAGE/books.py": """
        from ycappuccino.api.decorators import Item, Property
        from ycappuccino.api.models import Model


        @Item(collection="books", name="PACKAGE_book", plural="PACKAGE_books", secure_write=True)
        class Book(Model):

            def __init__(self, a_dict=None):
                super().__init__(a_dict)
                self._title = None

            @Property(name="title")
            def title(self, a_value):
                self._title = a_value
    """,
}


class AllowAll(IAuthorization):

    async def is_authorized(self, subject, action, item_id):
        return True

    async def start(self):
        pass

    async def stop(self):
        pass


class TestEndpointsStorageInFramework(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = TemporaryApplication(APPLICATION).open()
        cls.addClassCleanup(cls.app.close)
        cls.framework = Framework()
        cls.framework.init(cls.app.yml_path)
        cls.addClassCleanup(cls.framework.stop)
        cls.context = cls.framework.context
        cls.book = cls.app.package + "_book"

    def service(self, specification):
        reference = wait_until(lambda: self.context.get_service_reference(specification))
        self.assertIsNotNone(reference, specification)
        return self.context.get_service(reference)

    def test_services_are_published(self):
        for specification in ("ICrud", "IDrafts", "IItemCatalog"):
            with self.subTest(specification=specification):
                self.service(specification)

    def test_catalog_lists_the_application_items(self):
        catalog = self.service("IItemCatalog")

        items = asyncio.run(catalog.get_items())

        self.assertIn(self.book, [item["id"] for item in items])

    def test_authorization_registered_later_is_used(self):
        crud = self.service("ICrud")
        drafts = self.service("IDrafts")
        with self.assertRaises(Forbidden):
            asyncio.run(crud.create(self.book, {"_id": "dune", "title": "Dune"}, ALICE))

        registration = self.context.register_service("IAuthorization", AllowAll(), {})
        self.addCleanup(registration.unregister)

        asyncio.run(crud.create(self.book, {"_id": "dune", "title": "Dune"}, ALICE))
        asyncio.run(drafts.save(self.book, "dune", "x", {"title": "Dune v2"}, ALICE))
        page = asyncio.run(crud.get_many(self.book))
        self.assertEqual((page["total"], page["items"][0]["title"]), (1, "Dune"))
        self.assertEqual(asyncio.run(drafts.get_one(self.book, "dune", "x"))["title"], "Dune v2")


if __name__ == "__main__":
    unittest.main()
