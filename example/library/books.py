"""
Example: CRUD, total and drafts of books with ycappuccino-endpoints-storage.
"""

import logging

from ycappuccino.api.core import IActivityLogger
from ycappuccino.api.core_base import YCappuccinoComponent, YCappuccinoType
from ycappuccino.api.decorators import Item, Property
from ycappuccino.api.endpoints_storage import IAuthorization, ICrud, IDrafts, NotAuthenticated
from ycappuccino.api.models import Model

_logger = logging.getLogger(__name__)

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

    @Property(name="pages", type="integer", minimum=0)
    def pages(self, a_value):
        self._pages = a_value


class DemoAuthorization(IAuthorization):
    """demonstration only: alice may do everything"""

    async def is_authorized(self, subject, action, item_id):
        return subject.get("sub") == "alice"

    async def start(self):
        pass

    async def stop(self):
        pass


class Library(YCappuccinoComponent):
    """writes books, a draft and its publication at startup, and logs each step"""

    def __init__(
        self,
        crud: ICrud,
        drafts: IDrafts,
        authorization: IAuthorization,
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),
    ):
        # authorization is only required to start once an IAuthorization is published
        self._crud = crud
        self._drafts = drafts
        self._logger = logger

    def _log(self, message):
        _logger.info(message)
        self._logger.info(message)

    async def start(self):
        await self._crud.create("book", {"_id": "dune", "title": "Dune", "pages": 412}, ALICE)
        await self._crud.create("book", {"_id": "solaris", "title": "Solaris", "pages": 204}, ALICE)
        page = await self._crud.get_many("book", {"sort": {"pages": -1}, "limit": 1})
        self._log(f"{page['total']} books, longest: {page['items'][0]['title']}")

        await self._drafts.save("book", "dune", "review", {"title": "Dune (revised)"}, ALICE)
        draft = await self._drafts.get_one("book", "dune", "review")
        self._log(f"draft: {draft['title']}")
        published = await self._drafts.publish("book", "dune", "review", ALICE)
        self._log(f"published: {published['title']}")

        try:
            await self._crud.create("book", {"title": "Anonymous"})
        except NotAuthenticated as error:
            self._log(f"anonymous write refused: {error}")

    async def stop(self):
        pass
