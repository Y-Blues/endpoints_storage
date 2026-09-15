"""
The examples of README.md, kept runnable.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from ycappuccino.api.core_base import YCappuccinoComponent
from ycappuccino.api.decorators import Item, Property
from ycappuccino.api.endpoints_storage import Forbidden, IAuthorization, ICrud, NotFound
from ycappuccino.api.models import Model
from ycappuccino.endpoints_storage.crud import Crud
from ycappuccino.endpoints_storage.drafts import Drafts
from ycappuccino.storage.files import LocalFileStore
from ycappuccino.storage.items import ItemManager
from ycappuccino.storage.manager import Manager
from ycappuccino.storage.memory import MemoryStorage

ALICE = {"sub": "alice", "tid": "acme"}


@Item(collection="books", name="book", plural="books", secure_write=True)
class Book(Model):
    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._title = None
        self._pages = None

    @Property(name="title")
    def title(self, a_value):
        self._title = a_value

    @Property(name="pages", type="integer")
    def pages(self, a_value):
        self._pages = a_value


# section "Lire et écrire : ICrud"
class Shelf(YCappuccinoComponent):
    def __init__(self, crud: ICrud):
        self._crud = crud

    async def start(self):
        await self._crud.create("book", {"_id": "dune", "title": "Dune", "pages": 412}, ALICE)
        await self._crud.update("book", "dune", {"pages": 413}, ALICE)

        page = await self._crud.get_many("book", {"sort": {"pages": -1}, "limit": 10})
        print(page["total"], [book["title"] for book in page["items"]])

        await self._crud.delete("book", "dune", ALICE)

    async def stop(self):
        pass


# section "Autorisation"
class AliceOnly(IAuthorization):
    async def is_authorized(self, subject, action, item_id):
        return subject["sub"] == "alice" or action == "read"

    async def start(self):
        pass

    async def stop(self):
        pass


class TestReadmeExamples(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.directory)
        self.manager = Manager(MemoryStorage(), ItemManager(), [], [], LocalFileStore("data/files"))
        self.crud = Crud(ItemManager(), self.manager, [AliceOnly()])
        self.drafts = Drafts(ItemManager(), self.manager, [AliceOnly()])

    async def test_crud_section(self):
        with mock.patch("builtins.print") as printed:
            await Shelf(self.crud).start()

        printed.assert_called_once_with(1, ["Dune"])
        with self.assertRaises(NotFound):
            await self.crud.get_one("book", "dune")

    async def test_authorization_section(self):
        await self.crud.create("book", {"_id": "dune", "title": "Dune"}, ALICE)

        with self.assertRaises(Forbidden):
            await self.crud.update("book", "dune", {"title": "Bob"}, {"sub": "bob", "tid": "acme"})
        self.assertEqual((await self.crud.get_one("book", "dune"))["title"], "Dune")

    async def test_drafts_section(self):
        drafts = self.drafts
        await self.crud.create("book", {"_id": "dune", "title": "Dune", "pages": 412}, ALICE)
        await self.crud.create("book", {"_id": "solaris", "title": "Solaris"}, ALICE)
        await drafts.save("book", "solaris", "review", {"title": "Solaris (revised)"}, ALICE)

        await drafts.save("book", "dune", "review", {"title": "Dune (revised)"}, ALICE)
        draft = await drafts.get_one("book", "dune", "review")
        page = await drafts.get_many("book", "review", {"sort": {"title": 1}})
        await drafts.publish("book", "dune", "review", ALICE)
        await drafts.discard("book", "solaris", "review", ALICE)

        self.assertEqual(
            (draft["_id"], draft["_draft"], draft["title"], draft["pages"]),
            ("dune", "review", "Dune (revised)", 412),
        )
        self.assertEqual([book["title"] for book in page["items"]], ["Dune (revised)", "Solaris (revised)"])
        self.assertEqual((await self.crud.get_one("book", "dune"))["title"], "Dune (revised)")
        self.assertEqual((await self.crud.get_one("book", "solaris"))["title"], "Solaris")
        self.assertEqual((await drafts.get_many("book", "review"))["total"], 2)

    async def test_testing_section(self):
        manager = Manager(MemoryStorage(), ItemManager(), [], [], LocalFileStore("data/files"))
        crud = Crud(ItemManager(), manager, [AliceOnly()])

        await crud.create("book", {"_id": "dune", "title": "Dune"}, {"sub": "alice", "tid": "acme"})
        page = await crud.get_many("book")

        self.assertEqual(page["total"], 1)


if __name__ == "__main__":
    unittest.main()
