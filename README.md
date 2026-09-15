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
