"""
Models and doubles shared by the endpoints_storage tests.
"""

import os
import tempfile

from ycappuccino.api.decorators import Empty, Item, ItemReference, Property, Reference
from ycappuccino.api.endpoints_storage import IAuthorization
from ycappuccino.api.models import Model
from ycappuccino.api.storage import ITrigger
from ycappuccino.storage.files import LocalFileStore
from ycappuccino.storage.items import ItemManager
from ycappuccino.storage.manager import Manager
from ycappuccino.storage.memory import MemoryStorage

ALICE = {"sub": "alice", "tid": "acme"}


@Item(collection="crud_authors", name="crud_author", plural="crud_authors", secure_read=True, secure_write=True)
class Author(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._name = None

    @Property(name="name")
    def name(self, a_value):
        self._name = a_value


@Item(collection="crud_books", name="crud_book", plural="crud_books", secure_write=True)
@ItemReference(from_name="crud_book", field="author", item="crud_author")
class Book(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._title = None
        self._pages = None
        self._isbn = None
        self._author = None

    @Property(name="title")
    def title(self, a_value):
        self._title = a_value

    @Property(name="pages", type="integer")
    def pages(self, a_value):
        self._pages = a_value

    @Property(name="isbn", private=True)
    def isbn(self, a_value):
        self._isbn = a_value

    @Reference(name="author")
    def author(self, a_value):
        self._author = a_value


@Item(collection="crud_books", name="crud_novel", plural="crud_novels", secure_write=True)
class Novel(Book):
    pass


@Item(collection="crud_archives", name="crud_archive", plural="crud_archives", is_writable=False)
class Archive(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._title = None

    @Property(name="title")
    def title(self, a_value):
        self._title = a_value


@Item(collection="crud_medias", name="crud_media", plural="crud_medias", multipart="file")
class Media(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._name = None
        self._file = None

    @Property(name="name")
    def name(self, a_value):
        self._name = a_value

    @Property(name="file")
    def file(self, a_value):
        self._file = a_value


@Item(collection="crud_bases", name="crud_base", plural="crud_bases", abstract=True)
class Base(Model):
    pass


@Empty()
def empty_book():
    book = Book()
    book.id("empty")
    book.title("")
    return book


empty_book()


class FakeAuthorization(IAuthorization):
    """authorizes the (action, item_id) pairs of allowed; "*" authorizes everything"""

    def __init__(self, allowed=("*",)):
        self.allowed = set(allowed)
        self.calls = []

    async def is_authorized(self, subject, action, item_id):
        self.calls.append((subject["sub"], action, item_id))
        return "*" in self.allowed or (action, item_id) in self.allowed

    async def start(self):
        pass

    async def stop(self):
        pass


class RecordingTrigger(ITrigger):

    def __init__(self, item_id, actions, post=True):
        self.item_id = item_id
        self.actions = actions
        self.post = post
        self.calls = []

    async def execute(self, action, item_id, model):
        self.calls.append((action, item_id, model.get_storage_model().get("_id")))

    async def start(self):
        pass

    async def stop(self):
        pass


def create_manager(triggers=None):
    """manager on a memory storage; the caller removes the returned directory"""
    directory = tempfile.mkdtemp()
    manager = Manager(
        MemoryStorage(),
        ItemManager(),
        triggers if triggers is not None else [],
        [],
        LocalFileStore(os.path.join(directory, "files")),
    )
    return manager, directory
