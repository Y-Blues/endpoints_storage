# endpoints_storage natif : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Réécrire `endpoints_storage` en trois services natifs async indépendants du transport (`ICrud`, `IDrafts`, `IItemCatalog`) au-dessus de `IManager`, avec autorisation par le port `IAuthorization`, brouillons et total paginé.

**Architecture:** Le contrat (interfaces, erreurs, actions) est un nouveau module `ycappuccino.api.endpoints_storage`. `storage` gagne `count`. `endpoints_storage` est un projet uv en modules focalisés : `params` (paramètres, ids, erreurs), `access` (règles d'autorisation), `crud`, `drafts`, `catalog`, testés sans Pelix sur un vrai `Manager` en mémoire, plus un test d'intégration dans le framework.

**Tech Stack:** Python ≥ 3.10, uv (`uv_build`), Pelix/iPOPO 3, unittest (`IsolatedAsyncioTestCase`), `ycappuccino-api`, `ycappuccino-core`, `ycappuccino-storage`.

**Spec:** `endpoints_storage/docs/superpowers/specs/2026-09-15-endpoints-storage-design.md`

## Global Constraints

- Chemins relatifs à la racine du workspace `/home/apisu/Documents/perso/repositories` ; `api`, `storage`, `endpoints_storage` sont des dépôts git séparés.
- **Aucun commit** : l'utilisateur commite lui-même. Chaque tâche se termine par la vérification des tests. Les suppressions de fichiers suivis se font avec `git rm` (ce n'est pas un commit).
- Commande de test, lancée depuis le dépôt concerné : `uv run python -m unittest discover -s src/unittest/python`. `uv` doit être dans le `PATH` ; s'il est absent, s'arrêter et le signaler.
- `requires-python = ">=3.10"`.
- Aucun décorateur iPOPO dans `endpoints_storage` : uniquement des composants natifs (`YCappuccinoComponent`) aux méthodes `async`, sans `@Layer`.
- Actions d'autorisation : `"read"`, `"write"`, `"delete"`, `"private"`.
- Id d'un brouillon : `f"{id}~{draft}"` ; champs `_draft` et `_draft_of`. Un id ou un nom de brouillon contenant `~` lève `InvalidRequest`.
- Les services reçoivent `authorizations: list[IAuthorization]` (liste vivante) et utilisent son premier élément ; jamais `IAuthorization | None`.
- Résultats : dicts (copie de `model.get_storage_model()`), jamais de `Model`.
- Pagination interne des ids : pages de `1000`, tri `{"_id": 1}`.
- Les ids d'items des modèles de test sont préfixés `crud_` (registre global partagé par tous les modules de test d'un même processus).

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `api/src/main/python/ycappuccino/api/endpoints_storage.py` (créé) | erreurs, constantes d'actions, `ICrud`, `IDrafts`, `IItemCatalog`, `IAuthorization` |
| `api/src/main/python/ycappuccino/api/storage.py` (modifié) | `IStorage.count`, `IManager.count` |
| `storage/src/main/python/ycappuccino/storage/memory.py`, `mongo.py`, `manager.py` (modifiés) | implémentations de `count` |
| `endpoints_storage/pyproject.toml` (réécrit) | projet uv `ycappuccino-endpoints-storage` |
| `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/params.py` | combinaison de filtres, validation d'ids et de champs, conversion des `ValueError`, pagination des ids, dict d'un modèle, références à plat |
| `.../endpoints_storage/access.py` | `Access` : `item`, `check`, `check_read` |
| `.../endpoints_storage/crud.py` | `Crud(ICrud)` |
| `.../endpoints_storage/drafts.py` | `Drafts(IDrafts)` |
| `.../endpoints_storage/catalog.py` | `ItemCatalog(IItemCatalog)` |
| `endpoints_storage/src/unittest/python/crud_fixtures.py` | modèles `crud_*`, `FakeAuthorization`, `create_services` |
| `endpoints_storage/example/`, `README.md` | exemple exécutable et documentation |

---

### Task 1: api, contrat `endpoints_storage`

**Files:**
- Create: `api/src/main/python/ycappuccino/api/endpoints_storage.py`
- Test: `api/src/unittest/python/test_interfaces.py` (ajout d'une classe)

**Interfaces:**
- Produces: `ycappuccino.api.endpoints_storage` avec `READ = "read"`, `WRITE = "write"`, `DELETE = "delete"`, `PRIVATE = "private"` ; exceptions `CrudError(Exception)`, `NotAuthenticated`, `Forbidden`, `NotFound`, `InvalidRequest` (sous-classes de `CrudError`) ; ABC `ICrud`, `IDrafts`, `IItemCatalog`, `IAuthorization` avec les signatures ci-dessous.

- [ ] **Step 1: Write the failing test**

Ajouter à `api/src/unittest/python/test_interfaces.py`, avant `if __name__ == "__main__":` :

```python
class TestEndpointsStorageInterfaces(unittest.TestCase):

    def test_interfaces_are_abstract_components(self):
        from ycappuccino.api.endpoints_storage import IAuthorization, ICrud, IDrafts, IItemCatalog

        for klass in (ICrud, IDrafts, IItemCatalog, IAuthorization):
            with self.subTest(interface=klass.__name__):
                self.assertTrue(issubclass(klass, YCappuccinoComponent))
                self.assertTrue(inspect.isabstract(klass))

    def test_operations_are_coroutines(self):
        from ycappuccino.api.endpoints_storage import IAuthorization, ICrud, IDrafts, IItemCatalog

        operations = (
            (ICrud, ("get_one", "get_many", "create", "update", "delete", "delete_many")),
            (IDrafts, ("get_one", "get_many", "save", "publish", "discard")),
            (IItemCatalog, ("get_items", "get_item", "get_item_by_plural", "get_schema", "get_empty")),
            (IAuthorization, ("is_authorized",)),
        )
        for klass, methods in operations:
            for method in methods:
                with self.subTest(method=f"{klass.__name__}.{method}"):
                    self.assertTrue(inspect.iscoroutinefunction(getattr(klass, method)))

    def test_errors_share_a_base_class(self):
        from ycappuccino.api.endpoints_storage import (
            CrudError,
            Forbidden,
            InvalidRequest,
            NotAuthenticated,
            NotFound,
        )

        for klass in (NotAuthenticated, Forbidden, NotFound, InvalidRequest):
            with self.subTest(error=klass.__name__):
                self.assertTrue(issubclass(klass, CrudError))
        self.assertTrue(issubclass(CrudError, Exception))
        self.assertFalse(issubclass(InvalidRequest, ValueError))

    def test_actions(self):
        from ycappuccino.api import endpoints_storage

        self.assertEqual(
            (endpoints_storage.READ, endpoints_storage.WRITE, endpoints_storage.DELETE, endpoints_storage.PRIVATE),
            ("read", "write", "delete", "private"),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python -p test_interfaces.py`
Expected: 4 erreurs `ModuleNotFoundError: No module named 'ycappuccino.api.endpoints_storage'`.

- [ ] **Step 3: Implement**

Créer `api/src/main/python/ycappuccino/api/endpoints_storage.py` :

```python
"""
endpoints_storage api: use cases on the models declared with @Item, independent of any transport.

A subject is the dict decoded from the JWT: {"sub": <account id>, "tid": <tenant id>}, or None when anonymous.
Results are serializable dicts; failures are CrudError subclasses that the adapters translate.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ycappuccino.api.core_base import YCappuccinoComponent

# actions checked by IAuthorization
READ = "read"
WRITE = "write"
DELETE = "delete"
PRIVATE = "private"


class CrudError(Exception):
    """failure of a use case, translated by the adapters"""


class NotAuthenticated(CrudError):
    """secured action without subject (HTTP 401)"""


class Forbidden(CrudError):
    """read-only item, or subject not authorized (HTTP 403)"""


class NotFound(CrudError):
    """unknown or abstract item, missing document or draft (HTTP 404)"""


class InvalidRequest(CrudError):
    """invalid parameters, id or fields (HTTP 400)"""


class ICrud(YCappuccinoComponent, ABC):
    """reads and writes of the documents of an item; drafts are excluded"""

    @abstractmethod
    async def get_one(
        self, item_id: str, id: str, params: Optional[dict] = None, subject: Optional[dict] = None
    ) -> dict:
        """document id; NotFound when missing"""

    @abstractmethod
    async def get_many(self, item_id: str, params: Optional[dict] = None, subject: Optional[dict] = None) -> dict:
        """{"items": documents matching params, "total": number of matching documents}"""

    @abstractmethod
    async def create(self, item_id: str, fields: dict, subject: Optional[dict] = None) -> dict:
        """upsert the document fields["_id"], or a new uuid, and return it"""

    @abstractmethod
    async def update(self, item_id: str, id: str, fields: dict, subject: Optional[dict] = None) -> dict:
        """upsert the fields of the document id and return it"""

    @abstractmethod
    async def delete(self, item_id: str, id: str, subject: Optional[dict] = None) -> None:
        """delete the document id and its drafts; NotFound when missing"""

    @abstractmethod
    async def delete_many(self, item_id: str, filter: dict, subject: Optional[dict] = None) -> int:
        """delete the documents matching the non empty filter, and their drafts; return their number"""


class IDrafts(YCappuccinoComponent, ABC):
    """named drafts of the documents of an item"""

    @abstractmethod
    async def get_one(
        self, item_id: str, id: str, draft: str, params: Optional[dict] = None, subject: Optional[dict] = None
    ) -> dict:
        """draft version of the document id, else the document; NotFound when both are missing"""

    @abstractmethod
    async def get_many(
        self, item_id: str, draft: str, params: Optional[dict] = None, subject: Optional[dict] = None
    ) -> dict:
        """{"items", "total"} where the documents having the draft are replaced by their draft version"""

    @abstractmethod
    async def save(self, item_id: str, id: str, draft: str, fields: dict, subject: Optional[dict] = None) -> dict:
        """upsert the draft of the document id and return its draft version"""

    @abstractmethod
    async def publish(self, item_id: str, id: str, draft: str, subject: Optional[dict] = None) -> dict:
        """write the draft on the document id, delete the draft and return the document"""

    @abstractmethod
    async def discard(self, item_id: str, id: str, draft: str, subject: Optional[dict] = None) -> None:
        """delete the draft of the document id; NotFound when missing"""


class IItemCatalog(YCappuccinoComponent, ABC):
    """metadata of the items readable by a subject"""

    @abstractmethod
    async def get_items(self, subject: Optional[dict] = None) -> list:
        """public metadata of the non abstract items readable by the subject"""

    @abstractmethod
    async def get_item(self, item_id: str, subject: Optional[dict] = None) -> dict:
        """public metadata of the item"""

    @abstractmethod
    async def get_item_by_plural(self, plural: str, subject: Optional[dict] = None) -> dict:
        """public metadata of the item with this plural name"""

    @abstractmethod
    async def get_schema(self, item_id: str, subject: Optional[dict] = None) -> dict:
        """json schema of the item"""

    @abstractmethod
    async def get_empty(self, item_id: str, subject: Optional[dict] = None) -> Optional[dict]:
        """storage model of the empty instance of the item, or None"""


class IAuthorization(YCappuccinoComponent, ABC):
    """decides whether a subject may perform an action on an item"""

    @abstractmethod
    async def is_authorized(self, subject: dict, action: str, item_id: str) -> bool:
        """action among READ, WRITE, DELETE and PRIVATE"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`, 48 tests.

### Task 2: storage, `count`

**Files:**
- Modify: `api/src/main/python/ycappuccino/api/storage.py` (classes `IStorage` et `IManager`)
- Modify: `api/src/unittest/python/test_interfaces.py` (`test_storage_operations_are_coroutines`)
- Modify: `storage/src/main/python/ycappuccino/storage/memory.py`, `mongo.py`, `manager.py`
- Modify: `storage/src/unittest/python/storage_contract.py`, `test_manager_read.py`
- Modify: `storage/README.md` (tableau des méthodes du manager)

**Interfaces:**
- Produces: `IStorage.count(collection: str, query: dict) -> int` (async) ; `IManager.count(item_id: str, params: dict | None = None, subject: dict | None = None) -> int` (async), même périmètre que `get_many` sans `offset` ni `limit`.

- [ ] **Step 1: Write the failing tests**

Dans `api/src/unittest/python/test_interfaces.py`, remplacer dans `test_storage_operations_are_coroutines` :

```python
            (IStorage, ("get_one", "get_many", "up_sert", "delete")),
            (IManager, ("get_one", "get_many", "up_sert", "up_sert_model", "delete", "delete_many")),
```

par :

```python
            (IStorage, ("get_one", "get_many", "up_sert", "delete", "count")),
            (IManager, ("get_one", "get_many", "up_sert", "up_sert_model", "delete", "delete_many", "count")),
```

Dans `storage/src/unittest/python/storage_contract.py`, ajouter après `test_delete_returns_the_number_of_deleted_documents` :

```python
    async def test_count(self):
        await self.insert_books()

        self.assertEqual(await self.storage.count(self.collection, {}), 3)
        self.assertEqual(await self.storage.count(self.collection, {"pages": {"$gt": 300}}), 2)
        self.assertEqual(await self.storage.count("missing_" + self.collection, {}), 0)
```

Dans `storage/src/unittest/python/test_manager_read.py`, ajouter à la fin de la classe `TestManagerRead` (avant `if __name__ == "__main__":`) :

```python
    async def test_count_uses_the_scope_of_get_many(self):
        self.filters.append(TenantFilter())

        self.assertEqual(await self.manager.count("manager_book"), 3)
        self.assertEqual(await self.manager.count("manager_novel"), 1)
        self.assertEqual(
            await self.manager.count("manager_book", {"filter": '{"pages": {"$gt": 300}}', "limit": 1, "offset": 5}),
            2,
        )
        self.assertEqual(await self.manager.count("manager_book", subject={"sub": "alice", "tid": "acme"}), 2)
```

(Données du `asyncSetUp` : `dune` 412 pages tenant `acme`, `solaris` 204 pages tenant `other`, `hyperion` novel 482 pages tenant `acme`. Sans sujet, aucun `IFilter` ne s'applique.)

- [ ] **Step 2: Run tests to verify they fail**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python -p test_interfaces.py`
Expected: FAIL sur `IStorage.count` et `IManager.count` (`AttributeError`).

Run (depuis `storage`) : `uv run python -m unittest discover -s src/unittest/python -p "test_m*.py"`
Expected: `AttributeError: 'MemoryStorage' object has no attribute 'count'` et `'Manager' object has no attribute 'count'` (les tests Mongo sont ignorés si Docker est absent).

- [ ] **Step 3: Implement**

Dans `api/src/main/python/ycappuccino/api/storage.py`, ajouter à la fin de `IStorage` :

```python
    @abstractmethod
    async def count(self, collection: str, query: dict) -> int:
        """number of documents matching the query"""
```

et à la fin de `IManager` :

```python
    @abstractmethod
    async def count(self, item_id: str, params: Optional[dict] = None, subject: Optional[dict] = None) -> int:
        """number of models get_many would return without offset and limit"""
```

Dans `storage/src/main/python/ycappuccino/storage/memory.py`, ajouter après `delete` :

```python
    async def count(self, collection, query):
        return sum(1 for document in self._documents(collection) if matches(document, query))
```

Dans `storage/src/main/python/ycappuccino/storage/mongo.py`, ajouter après `delete` :

```python
    async def count(self, collection, query):
        return await self._db[collection].count_documents(query)
```

Dans `storage/src/main/python/ycappuccino/storage/manager.py`, ajouter après `get_many` :

```python
    async def count(self, item_id, params=None, subject=None):
        item = self._items.get_item(item_id)
        read = parse_read_params(params)
        query = await self._scope(item_id, subject, read.filter)
        return await self._storage.count(item["collection"], query)
```

Dans `storage/README.md`, ajouter au tableau « Méthode | Rôle » de la section « Utiliser le manager », après la ligne `delete_many` :

```markdown
| `count(item_id, params=None, subject=None)` | nombre de documents que `get_many` renverrait sans `offset` ni `limit` |
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

Run (depuis `storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK` (tests Mongo ignorés sans Docker, sinon passés).

### Task 3: endpoints_storage, projet uv, fixtures et `params`

**Files:**
- Modify: `endpoints_storage/pyproject.toml` (tout le fichier), `endpoints_storage/.gitignore` (tout le fichier)
- Modify: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/__init__.py` (tout le fichier)
- Delete (`git rm`) : `build.py`, `setup.py`, `data/log/Log-Activity-main.log`, `example/__init__.py`, `example/models/`, `example/data/log/Log-Activity-main.log`, `src/main/python/ycappuccino/endpoints_storage/bundles/`, `src/main/python/ycappuccino/endpoints_storage/conf/`, `src/unittest/`
- Create: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/params.py`
- Create: `endpoints_storage/src/unittest/python/crud_fixtures.py`
- Test: `endpoints_storage/src/unittest/python/test_params.py`

**Interfaces:**
- Consumes (Task 1) : `InvalidRequest` ; (Task 2) : `IManager.count`.
- Produces, dans `ycappuccino.endpoints_storage.params` :
  - constantes `DRAFT_SEPARATOR = "~"`, `DRAFT_FIELDS = ("_draft", "_draft_of")`, `NO_DRAFT = {"_draft": {"$exists": False}}`, `PAGE = 1000` ;
  - `invalid_request()` : context manager qui transforme un `ValueError` en `InvalidRequest` ;
  - `parse_filter(value) -> dict` : dict, JSON ou vide (`{}`) ; sinon `InvalidRequest` ;
  - `with_condition(params: dict | None, condition: dict) -> dict` : copie de `params` dont `filter` vaut `{"$and": [filtre, condition]}` (ou `condition` si le filtre est vide) ;
  - `check_id(id) -> str` : `InvalidRequest` si ce n'est pas un texte non vide sans `~` ;
  - `check_fields(fields, forbidden: tuple) -> dict` : copie ; `InvalidRequest` si ce n'est pas un dict ou s'il contient un nom interdit ;
  - `to_dict(model, item: dict, private_fields: bool = False) -> dict` : copie profonde du storage model, sans les propriétés privées de l'item sauf `private_fields` ;
  - `to_fields(document: dict) -> dict` : champs à réécrire à partir d'un document lu : sans `_id`, références `{"ref": x}` remplacées par `x` ;
  - `async all_ids(manager, item_id, filter, subject) -> list[str]` : ids de tous les documents du filtre, par pages de `PAGE` triées par `_id`.
- Produces, dans `crud_fixtures.py` : modèles `Author` (`crud_author`, `secure_read`, `secure_write`), `Book` (`crud_book`, `secure_write`, propriétés `title`, `pages` entier, `isbn` privée, référence `author` vers `crud_author`, empty `{"_id": "empty", "title": ""}`), `Novel(Book)` (`crud_novel`, même collection, `secure_write`), `Archive` (`crud_archive`, `is_writable=False`, `title`), `Media` (`crud_media`, `multipart="file"`, `name`, `file`), `Base` (`crud_base`, abstrait) ; `ALICE = {"sub": "alice", "tid": "acme"}` ; `FakeAuthorization(allowed=("*",))` avec `.allowed` (set de `(action, item_id)` ou `"*"`) et `.calls` (liste de `(sub, action, item_id)`) ; `RecordingTrigger(item_id, actions, post=True)` avec `.calls` ; `create_manager(triggers=None) -> (Manager, directory)`.

- [ ] **Step 1: Replace the PyBuilder project**

```bash
cd endpoints_storage
git rm -q -r build.py setup.py data/log/Log-Activity-main.log example/__init__.py example/models \
  example/data/log/Log-Activity-main.log \
  src/main/python/ycappuccino/endpoints_storage/bundles src/main/python/ycappuccino/endpoints_storage/conf \
  src/unittest
rm -rf example/models src/unittest
mkdir -p src/unittest/python
```

`endpoints_storage/pyproject.toml` :

```toml
[project]
name = "ycappuccino-endpoints-storage"
version = "0.1.0"
description = "YCappuccino endpoints_storage: CRUD, drafts and item catalog use cases on the @Item models, independent of any transport"
requires-python = ">=3.10"
dependencies = [
    "ycappuccino-api",
    "ycappuccino-core",
    "ycappuccino-storage",
]

[build-system]
requires = ["uv_build>=0.12.13,<0.13"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "ycappuccino.endpoints_storage"
module-root = "src/main/python"

[tool.uv.sources]
ycappuccino-api = { path = "../api", editable = true }
ycappuccino-core = { path = "../core", editable = true }
ycappuccino-storage = { path = "../storage", editable = true }
```

`endpoints_storage/.gitignore` :

```
data
.venv
__pycache__
dist
```

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/__init__.py` :

```python
"""use cases on the models declared with @Item: CRUD, drafts and item catalog"""
```

Run (depuis `endpoints_storage`) : `uv sync`
Expected: environnement créé, `ycappuccino-api`, `ycappuccino-core`, `ycappuccino-storage` installés en éditable.

- [ ] **Step 2: Write the fixtures**

`endpoints_storage/src/unittest/python/crud_fixtures.py` :

```python
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
```

- [ ] **Step 3: Write the failing test**

`endpoints_storage/src/unittest/python/test_params.py` :

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `ImportError: cannot import name 'params' from 'ycappuccino.endpoints_storage'`.

- [ ] **Step 5: Implement**

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/params.py` :

```python
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
```

Note : `all_ids` lit `PAGE` à chaque appel (variable de module), ce qui permet au test de la remplacer.

- [ ] **Step 6: Run tests to verify they pass**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 4: endpoints_storage, règles d'autorisation (`access`)

**Files:**
- Create: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/access.py`
- Test: `endpoints_storage/src/unittest/python/test_access.py`

**Interfaces:**
- Consumes (Task 1) : `READ`, `WRITE`, `DELETE`, `PRIVATE`, `NotAuthenticated`, `Forbidden`, `NotFound` ; (Task 3) : `params.invalid_request`, fixtures ; `ycappuccino.storage.query.parse_expand` et `PRIVATE_FIELDS` (`"privateField"`).
- Produces: `Access(items: IItemManager, authorizations: list)` avec :
  - `item(item_id) -> dict` : métadonnées ; `NotFound` si l'item est inconnu ou abstrait ;
  - `async check(item_id, action, subject) -> dict` : les 6 étapes de la spec (section 2.3), renvoie l'item ;
  - `async check_read(item_id, params, subject) -> dict` : `check` en `read`, puis `private` si `content` contient `privateField`, puis `read` sur l'item de chaque segment d'`expand` ; un `expand` invalide lève `InvalidRequest`.

- [ ] **Step 1: Write the failing test**

`endpoints_storage/src/unittest/python/test_access.py` :

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_access.py`
Expected: `ModuleNotFoundError: No module named 'ycappuccino.endpoints_storage.access'`.

- [ ] **Step 3: Implement**

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/access.py` :

```python
"""
Authorization rules of the use cases: flags of @Item first, then the IAuthorization port.
"""

import logging

from ycappuccino.api.endpoints_storage import (
    DELETE,
    PRIVATE,
    READ,
    WRITE,
    Forbidden,
    NotAuthenticated,
    NotFound,
)
from ycappuccino.endpoints_storage.params import invalid_request
from ycappuccino.storage.query import PRIVATE_FIELDS, parse_expand

_logger = logging.getLogger(__name__)


class Access(object):
    """checks of a service; authorizations is the live list injected by the core"""

    def __init__(self, items, authorizations):
        self._items = items
        self._authorizations = authorizations

    def item(self, item_id) -> dict:
        try:
            item = self._items.get_item(item_id)
        except KeyError:
            raise NotFound(f"unknown item {item_id}") from None
        if item.get("abstract", False):
            raise NotFound(f"abstract item {item_id}")
        return item

    async def check(self, item_id, action, subject) -> dict:
        item = self.item(item_id)
        if action in (WRITE, DELETE) and not item.get("isWritable", True):
            raise Forbidden(f"item {item_id} is read-only")
        if not _is_secured(item, action):
            return item
        if subject is None:
            raise NotAuthenticated(f"{action} on {item_id} requires a subject")
        authorizations = list(self._authorizations)
        if not authorizations:
            _logger.warning("no IAuthorization service: %s on %s is refused", action, item_id)
            raise Forbidden(f"{action} on {item_id} is not authorized")
        if not await authorizations[0].is_authorized(subject, action, item_id):
            raise Forbidden(f"{action} on {item_id} is not authorized")
        return item

    async def check_read(self, item_id, params, subject) -> dict:
        item = await self.check(item_id, READ, subject)
        params = params or {}
        if PRIVATE_FIELDS in str(params.get("content") or ""):
            await self.check(item_id, PRIVATE, subject)
        with invalid_request():
            paths = parse_expand(params.get("expand") or "")
        for path in paths:
            for segment in path:
                await self.check(segment.name, READ, subject)
        return item


def _is_secured(item, action) -> bool:
    if action == PRIVATE:
        return True
    if action == READ:
        return bool(item.get("secureRead", False))
    return bool(item.get("secureWrite", False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 5: endpoints_storage, `Crud`

**Files:**
- Create: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/crud.py`
- Test: `endpoints_storage/src/unittest/python/test_crud.py`

**Interfaces:**
- Consumes (Task 1) : `ICrud`, `IAuthorization`, `WRITE`, `DELETE`, `InvalidRequest`, `NotFound` ; (Task 2) : `IManager.count` ; (Task 3) : `params` ; (Task 4) : `Access`.
- Produces: `Crud(items: IItemManager, manager: IManager, authorizations: list[IAuthorization])` implémentant `ICrud`.

Les lectures renvoient `to_dict(model, item, private_fields=True)` car le `Manager` a déjà retiré les propriétés privées quand `content` ne contient pas `privateField` ; les écritures renvoient `to_dict(model, item)`, sans propriétés privées. Le contrôle d'accès passe avant la validation des ids et des champs.

- [ ] **Step 1: Write the failing test**

`endpoints_storage/src/unittest/python/test_crud.py` :

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_crud.py`
Expected: `ModuleNotFoundError: No module named 'ycappuccino.endpoints_storage.crud'`.

- [ ] **Step 3: Implement**

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/crud.py` :

```python
"""
CRUD use case on the documents of an item; drafts are excluded from its reads.
"""

import uuid

from ycappuccino.api.endpoints_storage import (
    DELETE,
    WRITE,
    IAuthorization,
    ICrud,
    InvalidRequest,
    NotFound,
)
from ycappuccino.api.storage import IItemManager, IManager
from ycappuccino.endpoints_storage import params as p
from ycappuccino.endpoints_storage.access import Access


class Crud(ICrud):

    def __init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization]):
        self._manager = manager
        self._access = Access(items, authorizations)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_one(self, item_id, id, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        scoped = p.with_condition(params, p.NO_DRAFT)
        with p.invalid_request():
            model = await self._manager.get_one(item_id, id, scoped, subject)
        if model is None:
            raise NotFound(f"{item_id} {id} not found")
        # the manager already removed the private properties when they were not asked
        return p.to_dict(model, item, private_fields=True)

    async def get_many(self, item_id, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        scoped = p.with_condition(params, p.NO_DRAFT)
        with p.invalid_request():
            models = await self._manager.get_many(item_id, scoped, subject)
            total = await self._manager.count(item_id, scoped, subject)
        return {"items": [p.to_dict(model, item, private_fields=True) for model in models], "total": total}

    async def create(self, item_id, fields, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        fields = p.check_fields(fields, p.DRAFT_FIELDS)
        id = fields.pop("_id", None)
        id = str(uuid.uuid4()) if id is None else p.check_id(id)
        return await self._up_sert(item, id, fields, subject)

    async def update(self, item_id, id, fields, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        p.check_id(id)
        fields = p.check_fields(fields, p.DRAFT_FIELDS)
        if fields.pop("_id", id) != id:
            raise InvalidRequest(f"the _id of the fields differs from {id}")
        return await self._up_sert(item, id, fields, subject)

    async def delete(self, item_id, id, subject=None):
        await self._access.check(item_id, DELETE, subject)
        p.check_id(id)
        if await self._manager.get_one(item_id, id, {"filter": p.NO_DRAFT}, subject) is None:
            raise NotFound(f"{item_id} {id} not found")
        await self._manager.delete(item_id, id, subject)
        await self._manager.delete_many(item_id, {"_draft_of": id}, subject)

    async def delete_many(self, item_id, filter, subject=None):
        await self._access.check(item_id, DELETE, subject)
        condition = p.parse_filter(filter)
        if not condition:
            raise InvalidRequest("delete_many requires a non empty filter")
        scoped = p.with_condition({"filter": condition}, p.NO_DRAFT)["filter"]
        with p.invalid_request():
            ids = await p.all_ids(self._manager, item_id, scoped, subject)
            if ids:
                await self._manager.delete_many(item_id, {"_id": {"$in": ids}}, subject)
                await self._manager.delete_many(item_id, {"_draft_of": {"$in": ids}}, subject)
        return len(ids)

    async def _up_sert(self, item, id, fields, subject):
        with p.invalid_request():
            model = await self._manager.up_sert(item["id"], id, fields, subject)
        return p.to_dict(model, item)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 6: endpoints_storage, `Drafts`

**Files:**
- Create: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/drafts.py`
- Test: `endpoints_storage/src/unittest/python/test_drafts.py`

**Interfaces:**
- Consumes (Task 1) : `IDrafts`, `IAuthorization`, `WRITE`, `InvalidRequest`, `NotFound` ; (Task 3) : `params` (`DRAFT_SEPARATOR`, `DRAFT_FIELDS`, `NO_DRAFT`, `with_condition`, `check_id`, `check_fields`, `to_dict`, `to_fields`, `all_ids`, `invalid_request`), fixtures (`RecordingTrigger`, `create_manager(triggers)`) ; (Task 4) : `Access`.
- Produces: `Drafts(items: IItemManager, manager: IManager, authorizations: list[IAuthorization])` implémentant `IDrafts`.

Un résultat dont le `_id` stocké contient `~` est une version brouillon : son `_id` redevient l'id de l'original et `_draft` reçoit le nom du brouillon.

- [ ] **Step 1: Write the failing test**

`endpoints_storage/src/unittest/python/test_drafts.py` :

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_drafts.py`
Expected: `ModuleNotFoundError: No module named 'ycappuccino.endpoints_storage.drafts'`.

- [ ] **Step 3: Implement**

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/drafts.py` :

```python
"""
Named drafts of the documents of an item: the draft x of the document id is the document id~x of the same
item, marked with _draft and _draft_of.
"""

from ycappuccino.api.endpoints_storage import (
    WRITE,
    IAuthorization,
    IDrafts,
    InvalidRequest,
    NotFound,
)
from ycappuccino.api.storage import IItemManager, IManager
from ycappuccino.endpoints_storage import params as p
from ycappuccino.endpoints_storage.access import Access
from ycappuccino.storage.query import PRIVATE_FIELDS

# read of the complete document, to copy it
ALL_FIELDS = {"content": PRIVATE_FIELDS}


class Drafts(IDrafts):

    def __init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization]):
        self._manager = manager
        self._access = Access(items, authorizations)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_one(self, item_id, id, draft, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        _check(item, id, draft)
        with p.invalid_request():
            model = await self._manager.get_one(item_id, _draft_id(id, draft), params, subject)
            if model is None:
                model = await self._manager.get_one(item_id, id, p.with_condition(params, p.NO_DRAFT), subject)
        if model is None:
            raise NotFound(f"{item_id} {id} not found")
        return _result(model, item, private_fields=True)

    async def get_many(self, item_id, draft, params=None, subject=None):
        item = await self._access.check_read(item_id, params, subject)
        _check_draftable(item)
        _check_name(draft)
        suffix = p.DRAFT_SEPARATOR + draft
        with p.invalid_request():
            draft_ids = await p.all_ids(self._manager, item_id, {"_draft": draft}, subject)
            originals = [draft_id[: -len(suffix)] for draft_id in draft_ids]
            versions = {
                "$or": [{"_draft": {"$exists": False}, "_id": {"$nin": originals}}, {"_draft": draft}]
            }
            scoped = p.with_condition(params, versions)
            models = await self._manager.get_many(item_id, scoped, subject)
            total = await self._manager.count(item_id, scoped, subject)
        return {"items": [_result(model, item, private_fields=True) for model in models], "total": total}

    async def save(self, item_id, id, draft, fields, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        fields = p.check_fields(fields, ("_id",) + p.DRAFT_FIELDS)
        draft_id = _draft_id(id, draft)
        with p.invalid_request():
            if await self._manager.get_one(item_id, draft_id, None, subject) is None:
                original = await self._manager.get_one(
                    item_id, id, {"filter": p.NO_DRAFT, **ALL_FIELDS}, subject
                )
                if original is not None:
                    fields = {**p.to_fields(original.get_storage_model()), **fields}
            fields.update({"_draft": draft, "_draft_of": id})
            model = await self._manager.up_sert(item_id, draft_id, fields, subject)
        return _result(model, item, private_fields=False)

    async def publish(self, item_id, id, draft, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        draft_id = _draft_id(id, draft)
        with p.invalid_request():
            version = await self._manager.get_one(item_id, draft_id, ALL_FIELDS, subject)
            if version is None:
                raise NotFound(f"{item_id} {id} has no draft {draft}")
            model = await self._manager.up_sert(item_id, id, p.to_fields(version.get_storage_model()), subject)
            await self._manager.delete(item_id, draft_id, subject)
        return _result(model, item, private_fields=False)

    async def discard(self, item_id, id, draft, subject=None):
        item = await self._access.check(item_id, WRITE, subject)
        _check(item, id, draft)
        draft_id = _draft_id(id, draft)
        if await self._manager.get_one(item_id, draft_id, None, subject) is None:
            raise NotFound(f"{item_id} {id} has no draft {draft}")
        await self._manager.delete(item_id, draft_id, subject)


def _draft_id(id, draft) -> str:
    return f"{id}{p.DRAFT_SEPARATOR}{draft}"


def _check(item, id, draft) -> None:
    _check_draftable(item)
    p.check_id(id)
    _check_name(draft)


def _check_draftable(item) -> None:
    if item.get("multipart"):
        raise InvalidRequest(f"item {item['id']} is multipart: it has no drafts")


def _check_name(draft) -> None:
    if not isinstance(draft, str) or not draft or p.DRAFT_SEPARATOR in draft:
        raise InvalidRequest(f"invalid draft name {draft!r}")


def _result(model, item, private_fields) -> dict:
    """document of the model; a draft version gets the id of its original and its draft name"""
    document = p.to_dict(model, item, private_fields)
    id, separator, draft = document["_id"].rpartition(p.DRAFT_SEPARATOR)
    if separator:
        document["_id"] = id
        document["_draft"] = draft
    return document
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 7: endpoints_storage, `ItemCatalog`

**Files:**
- Create: `endpoints_storage/src/main/python/ycappuccino/endpoints_storage/catalog.py`
- Test: `endpoints_storage/src/unittest/python/test_catalog.py`

**Interfaces:**
- Consumes (Task 1) : `IItemCatalog`, `IAuthorization`, `READ`, `CrudError`, `NotFound` ; (Task 3) : fixtures ; (Task 4) : `Access`.
- Produces: `ItemCatalog(items: IItemManager, authorizations: list[IAuthorization])` implémentant `IItemCatalog`. Vue publique d'un item : dict aux clés exactes `id`, `plural`, `app`, `module`, `secure_read`, `secure_write`, `writable`, `multipart`, `refs`.

Le registre des items est global au processus : les autres modules de test y ajoutent leurs items. Les tests ne regardent donc que les ids préfixés `crud_`. `app` peut valoir `None` (quand `@ItemReference` est appliqué avant `@Item`, le registre ne reçoit pas cette clé).

- [ ] **Step 1: Write the failing test**

`endpoints_storage/src/unittest/python/test_catalog.py` :

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_catalog.py`
Expected: `ModuleNotFoundError: No module named 'ycappuccino.endpoints_storage.catalog'`.

- [ ] **Step 3: Implement**

`endpoints_storage/src/main/python/ycappuccino/endpoints_storage/catalog.py` :

```python
"""
Metadata of the items readable by a subject, as serializable dicts.
"""

import copy

from ycappuccino.api.endpoints_storage import READ, CrudError, IAuthorization, IItemCatalog, NotFound
from ycappuccino.api.storage import IItemManager
from ycappuccino.endpoints_storage.access import Access


class ItemCatalog(IItemCatalog):

    def __init__(self, items: IItemManager, authorizations: list[IAuthorization]):
        self._items = items
        self._access = Access(items, authorizations)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_items(self, subject=None):
        readable = []
        for item in self._items.get_items():
            try:
                await self._access.check(item["id"], READ, subject)
            except CrudError:
                continue
            readable.append(_public(item))
        return readable

    async def get_item(self, item_id, subject=None):
        return _public(await self._access.check(item_id, READ, subject))

    async def get_item_by_plural(self, plural, subject=None):
        try:
            item = self._items.get_item_by_plural(plural)
        except KeyError:
            raise NotFound(f"unknown plural {plural}") from None
        return await self.get_item(item["id"], subject)

    async def get_schema(self, item_id, subject=None):
        await self._access.check(item_id, READ, subject)
        return copy.deepcopy(self._items.get_schema(item_id))

    async def get_empty(self, item_id, subject=None):
        await self._access.check(item_id, READ, subject)
        return copy.deepcopy(self._items.get_empty(item_id))


def _public(item) -> dict:
    return {
        "id": item["id"],
        "plural": item["plural"],
        "app": item.get("app"),
        "module": item.get("module"),
        "secure_read": bool(item.get("secureRead", False)),
        "secure_write": bool(item.get("secureWrite", False)),
        "writable": bool(item.get("isWritable", True)),
        "multipart": item.get("multipart"),
        "refs": copy.deepcopy(item.get("refs", {})),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 8: endpoints_storage, intégration au framework et exemple

**Files:**
- Test: `endpoints_storage/src/unittest/python/test_endpoints_storage_framework.py`
- Modify: `endpoints_storage/example/conf/application.yml` (tout le fichier)
- Create: `endpoints_storage/example/library/__init__.py` (vide), `endpoints_storage/example/library/books.py`

**Interfaces:**
- Consumes (Tasks 1, 5, 6, 7) : `ICrud`, `IDrafts`, `IItemCatalog`, `IAuthorization`, `Forbidden`, `NotAuthenticated`, `Crud`, `Drafts`, `ItemCatalog` ; `ycappuccino.core.framework.Framework` ; `ycappuccino.core.testing.TemporaryApplication`, `wait_until`.

Les services récupérés par `context.get_service` sont les proxies générés : leurs méthodes renvoient des coroutines, exécutées dans le test avec `asyncio.run` (le backend mémoire n'est lié à aucune boucle).

Ordre de chargement du framework : les packages de `bundle_prefix` dans l'ordre, les classes d'un module par ordre alphabétique, chacune instanciée aussitôt. Dans l'exemple, `Library` exige en plus une `IAuthorization` : elle ne démarre qu'après `DemoAuthorization`, que les services ont déjà reçue dans leur liste.

- [ ] **Step 1: Write the integration test**

`endpoints_storage/src/unittest/python/test_endpoints_storage_framework.py` :

```python
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
```

- [ ] **Step 2: Run the integration test**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_endpoints_storage_framework.py`
Expected: `OK`, 3 tests. En cas d'échec de `test_authorization_registered_later_is_used` sur le second `create`, vérifier que les trois services déclarent bien `authorizations: list[IAuthorization]` (et non `IAuthorization | None`).

- [ ] **Step 3: Rebuild the example**

`endpoints_storage/example/conf/application.yml` :

```yaml
---
name: library
bundle_prefix:
  - ycappuccino.storage
  - ycappuccino.endpoints_storage
  - library
layers:
  ycappuccino_storage_memory:
    active: true
config:
  http_server:
    active: false
```

`endpoints_storage/example/library/__init__.py` : fichier vide.

`endpoints_storage/example/library/books.py` :

```python
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
```

- [ ] **Step 4: Run the example**

Run (dans `endpoints_storage/example`) :

```bash
rm -rf data
timeout -s INT 8 uv run --project .. ycappuccino < /dev/null
grep -E "2 books, longest: Dune|draft: Dune \(revised\)|published: Dune \(revised\)|anonymous write refused" data/log/Log-Activity-main.log
```

Expected: `timeout` sort avec le code 124, la sortie contient `Interrupted by user, shutting down`, et `grep` affiche les quatre lignes.

- [ ] **Step 5: Run all endpoints_storage tests**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

### Task 9: README vérifié, CLAUDE.md et vérification finale

**Files:**
- Create: `endpoints_storage/README.md`
- Test: `endpoints_storage/src/unittest/python/test_readme.py`
- Modify: `CLAUDE.md` (racine du workspace, trois passages)

**Interfaces:**
- Consumes: tout ce qui précède. Les exemples du README et `test_readme.py` doivent rester identiques (mêmes classes, mêmes appels).

- [ ] **Step 1: Write the README**

`endpoints_storage/README.md` :

````markdown
# ycappuccino-endpoints-storage

Cas d'usage CRUD sur les modèles `@Item`, indépendants de tout transport : lecture et écriture, total pour la pagination, brouillons nommés et métadonnées des items, avec les règles d'autorisation. Les adaptateurs (HTTP, remote, client pyscript) traduisent leur protocole vers ces services, et leurs erreurs vers leurs codes.

Conception : [docs/superpowers/specs/2026-09-15-endpoints-storage-design.md](docs/superpowers/specs/2026-09-15-endpoints-storage-design.md).

Prérequis : lire les README de [core](../core/README.md) et de [storage](../storage/README.md).

## Mise en place

```bash
uv add --editable ../endpoints_storage
```

`conf/application.yml` :

```yaml
name: library
bundle_prefix:
  - ycappuccino.storage
  - ycappuccino.endpoints_storage
  - library
layers:
  ycappuccino_storage_memory:
    active: true
```

Trois services sont publiés : `ICrud`, `IDrafts` et `IItemCatalog`, déclarés dans `ycappuccino.api.endpoints_storage`.

## Conventions

- **Items** : désignés par leur `item_id` (le `name` de `@Item`). `IItemCatalog.get_item_by_plural` traduit le pluriel d'une URL.
- **Sujet** : `subject` est le dict décodé du jeton, `{"sub": <compte>, "tid": <tenant>}`, ou `None` pour un appel anonyme. Il est transmis au manager : les `IFilter` de storage s'appliquent.
- **Résultats** : des dicts sérialisables, avec `_id` et les propriétés déclarées du modèle.
- **Paramètres de lecture** : `params` accepte les clés du manager (`filter`, `sort`, `limit`, `offset`, `expand`, `content`).

## Lire et écrire : `ICrud`

```python
from ycappuccino.api.core_base import YCappuccinoComponent
from ycappuccino.api.endpoints_storage import ICrud

ALICE = {"sub": "alice", "tid": "acme"}


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
```

| Méthode | Action | Rôle |
|---|---|---|
| `get_one(item_id, id, params=None, subject=None)` | `read` | le document ; `NotFound` s'il est absent |
| `get_many(item_id, params=None, subject=None)` | `read` | `{"items": [...], "total": n}` ; `total` ignore `offset` et `limit` |
| `create(item_id, fields, subject=None)` | `write` | upsert de `fields["_id"]`, ou d'un nouvel uuid |
| `update(item_id, id, fields, subject=None)` | `write` | upsert partiel : seuls les champs fournis changent |
| `delete(item_id, id, subject=None)` | `delete` | supprime le document et ses brouillons ; `NotFound` s'il est absent |
| `delete_many(item_id, filter, subject=None)` | `delete` | supprime selon un filtre **non vide** ; renvoie le nombre supprimé |

- Les lectures excluent les brouillons.
- Un id ne peut pas contenir `~`, et `_draft`/`_draft_of` ne s'écrivent pas par `ICrud`.
- Une écriture ne renvoie jamais les propriétés privées.

## Autorisation

Chaque opération est contrôlée dans cet ordre :

1. un item inconnu ou abstrait lève `NotFound` ;
2. `write` ou `delete` sur un item `is_writable=False` lève `Forbidden` ;
3. une action non sécurisée est autorisée : `read` si l'item n'a pas `secure_read`, `write` et `delete` s'il n'a pas `secure_write` ;
4. une action sécurisée sans sujet lève `NotAuthenticated` ;
5. sans aucun service `IAuthorization`, une action sécurisée lève `Forbidden` (fermé par défaut) ;
6. sinon `IAuthorization.is_authorized(subject, action, item_id)` décide, et `False` lève `Forbidden`.

L'action `private` est toujours sécurisée ; elle est contrôlée quand `params["content"]` contient `privateField`. Chaque item cité dans `expand` est contrôlé en `read`.

`IAuthorization` est fournie par l'application, et plus tard par `permissions_app` :

```python
from ycappuccino.api.endpoints_storage import IAuthorization


class AliceOnly(IAuthorization):
    async def is_authorized(self, subject, action, item_id):
        return subject["sub"] == "alice" or action == "read"

    async def start(self):
        pass

    async def stop(self):
        pass
```

Elle peut démarrer après les services : ils la reçoivent dès qu'elle est publiée.

## Brouillons : `IDrafts`

Un brouillon nommé est une copie de travail d'un document, invisible des lectures d'`ICrud`.

```python
await drafts.save("book", "dune", "review", {"title": "Dune (revised)"}, ALICE)

await drafts.get_one("book", "dune", "review")
# {"_id": "dune", "_draft": "review", "title": "Dune (revised)", "pages": 412}

await drafts.get_many("book", "review", {"sort": {"title": 1}})
# les documents qui ont un brouillon review sont remplacés par leur brouillon

await drafts.publish("book", "dune", "review", ALICE)     # écrit le brouillon sur dune, puis le supprime
await drafts.discard("book", "solaris", "review", ALICE)  # abandonne le brouillon de solaris
```

- **Premier `save`** : il part des propriétés du document, s'il existe. Les suivants mettent à jour le brouillon.
- **Lectures** : `get_one` renvoie le brouillon, sinon le document. `get_many` inclut aussi les brouillons sans document.
- **`publish`** : il passe par le manager, donc les triggers `upsert` du document s'exécutent.
- **Actions** : `save`, `publish` et `discard` demandent `write` ; les lectures demandent `read`.
- **Stockage** : le brouillon `review` de `dune` est le document `dune~review`, marqué `_draft` et `_draft_of`.

Limites :
- pas de brouillon pour un item `multipart` ;
- un filtre sur `_id` ne trouve pas la version brouillon ;
- le tri sur `_cat` et `_mat` utilise les dates du brouillon.

## Métadonnées : `IItemCatalog`

| Méthode | Rôle |
|---|---|
| `get_items(subject=None)` | items non abstraits lisibles par le sujet |
| `get_item(item_id, subject=None)` | vue publique de l'item |
| `get_item_by_plural(plural, subject=None)` | vue publique de l'item de ce pluriel |
| `get_schema(item_id, subject=None)` | JSON schema de l'item |
| `get_empty(item_id, subject=None)` | modèle vide déclaré par `@Empty`, ou `None` |

La vue publique contient `id`, `plural`, `app`, `module`, `secure_read`, `secure_write`, `writable`, `multipart` et `refs`.

## Erreurs

Toutes héritent de `CrudError` (`ycappuccino.api.endpoints_storage`) :

| Erreur | Cas | Code HTTP indicatif |
|---|---|---|
| `NotAuthenticated` | action sécurisée sans sujet | 401 |
| `Forbidden` | item en lecture seule, sujet refusé, aucune `IAuthorization` | 403 |
| `NotFound` | item inconnu ou abstrait, document ou brouillon absent | 404 |
| `InvalidRequest` | filtre ou paramètre invalide, `~` dans un id ou un nom de brouillon, champ interdit | 400 |

## Tester avec endpoints_storage

Les services s'instancient directement sur le backend mémoire :

```python
import unittest

from ycappuccino.endpoints_storage.crud import Crud
from ycappuccino.storage.files import LocalFileStore
from ycappuccino.storage.items import ItemManager
from ycappuccino.storage.manager import Manager
from ycappuccino.storage.memory import MemoryStorage


class TestShelf(unittest.IsolatedAsyncioTestCase):
    async def test_alice_writes_a_book(self):
        manager = Manager(MemoryStorage(), ItemManager(), [], [], LocalFileStore("data/files"))
        crud = Crud(ItemManager(), manager, [AliceOnly()])

        await crud.create("book", {"_id": "dune", "title": "Dune"}, {"sub": "alice", "tid": "acme"})
        page = await crud.get_many("book")

        self.assertEqual(page["total"], 1)
```

## Développer endpoints_storage

```bash
uv sync
uv run python -m unittest discover -s src/unittest/python
```

L'exemple `example/` se lance avec `cd example && uv run --project .. ycappuccino`.
````

- [ ] **Step 2: Write the README test**

`endpoints_storage/src/unittest/python/test_readme.py` :

```python
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
```

- [ ] **Step 3: Run the README test**

Run (depuis `endpoints_storage`) : `uv run python -m unittest discover -s src/unittest/python -p test_readme.py`
Expected: `OK`, 4 tests. Si un test échoue, corriger le README **et** le test pour qu'ils restent identiques, pas seulement le test.

- [ ] **Step 4: Update CLAUDE.md**

Dans `CLAUDE.md` (racine du workspace), remplacer :

```markdown
- `storage` → `ycappuccino.storage`: native persistence of `@Item` models (generic async `Manager`, memory/Mongo backends selected by layer, triggers, subject filters, expand, uploads). See `storage/README.md`.
- The others are feature layers not yet migrated to the new framework: `endpoints_service`, `endpoints_storage`, `hosts`, `permissions_app`, `remote`, `scheduler`, `scripts`, `swagger`, `component-creator`.
```

par :

```markdown
- `storage` → `ycappuccino.storage`: native persistence of `@Item` models (generic async `Manager`, memory/Mongo backends selected by layer, triggers, subject filters, expand, uploads). See `storage/README.md`.
- `endpoints_storage` → `ycappuccino.endpoints_storage`: transport-independent use cases `ICrud`, `IDrafts`, `IItemCatalog` over `IManager` (contract in `api/endpoints_storage.py`), authorized through the `IAuthorization` port. See `endpoints_storage/README.md`.
- The others are feature layers not yet migrated to the new framework: `endpoints_service`, `hosts`, `http_server`, `permissions_app`, `remote`, `scheduler`, `scripts`, `swagger`, `component-creator`.
```

Remplacer :

```markdown
Folder, project and package names don't always match: `endpoints_storage` is project `endpoint_crud`, `permissions_app` is `permissions`, `storage` is `repositories`, and `endpoints_service` is package `ycappuccino.endpoints_services`.
```

par :

```markdown
Folder, project and package names don't always match: `http_server` is project `http` with package `ycappuccino.endpoints`, `permissions_app` is `permissions`, and `endpoints_service` is package `ycappuccino.endpoints_services`.
```

Remplacer :

```markdown
`api`, `core` and `storage` are built with **uv** (`pyproject.toml`, `uv_build` backend with `module-root = "src/main/python"` and a dotted `module-name`). `core` depends on `../api`, and `storage` on `../api` and `../core`, as editable path sources. The other repos still have PyBuilder `build.py`/`setup.py`.
```

par :

```markdown
`api`, `core`, `storage` and `endpoints_storage` are built with **uv** (`pyproject.toml`, `uv_build` backend with `module-root = "src/main/python"` and a dotted `module-name`). `core` depends on `../api`, `storage` on `../api` and `../core`, and `endpoints_storage` on `../api`, `../core` and `../storage`, as editable path sources. The other repos still have PyBuilder `build.py`/`setup.py`.
```

- [ ] **Step 5: Final verification**

Run, depuis chaque dépôt, dans cet ordre :

```bash
cd api && uv run python -m unittest discover -s src/unittest/python
cd ../core && uv run python -m unittest discover -s src/unittest/python
cd ../storage && uv run python -m unittest discover -s src/unittest/python
cd ../endpoints_storage && uv run python -m unittest discover -s src/unittest/python
```

Expected: `OK` pour les quatre dépôts (tests Mongo de `storage` ignorés sans Docker).

Run (depuis `endpoints_storage`) : `git status --short`
Expected: aucune trace de `build.py`, `setup.py`, `bundles/`, `conf/` ni des anciens tests ; nouveaux fichiers listés comme non suivis.
