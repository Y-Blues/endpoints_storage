# endpoints_storage natif : design

Date : 2026-09-15. Sous-projet 2 de la reprise des dépôts YCappuccino, après `core`, `api` et `storage`.

## Objectif

`endpoints_storage` fournit les cas d'usage CRUD sur les modèles `@Item`, indépendamment de tout transport : lecture, écriture, suppression, total pour la pagination, brouillons et métadonnées des items, avec les règles d'autorisation. Les adaptateurs (`http_server`, `remote`, client pyscript) ne font que traduire leur protocole vers ces services et les erreurs vers leurs codes.

Il est réécrit en composants natifs (`YCappuccinoComponent`, injection par le constructeur, API async) au-dessus de `IManager` et `IItemManager` de `storage`.

## Décisions

| Sujet | Décision |
|---|---|
| Transport | Aucun : les services ne connaissent ni URL, ni en-tête, ni jeton |
| Découpage | Trois services : `ICrud` (données), `IDrafts` (brouillons), `IItemCatalog` (métadonnées), plus le port `IAuthorization` |
| Identification | Par `item_id`, comme `IManager` ; l'adaptateur traduit le pluriel via `IItemCatalog.get_item_by_plural` |
| Sujet | Dict déjà décodé (`{"sub", "tid", ...}`) ou `None` pour un appel anonyme |
| Résultats | Dicts sérialisables (storage model), jamais de `Model` |
| Erreurs | Exceptions typées dans `api`, traduites par chaque adaptateur |
| Autorisation | Dans le cas d'usage : drapeaux de `@Item` puis port `IAuthorization` avec des actions `read`/`write`/`delete`/`private` ; fermée par défaut |
| Brouillons | Documents dédiés (`_draft`, `_draft_of`), exclus des lectures normales, avec `publish` et `discard` |
| Total | `count` ajouté à `IStorage` et `IManager` dans `storage` |
| Chargement | Composants sans `@Layer`, chargés dès que le package est scanné |

## 1. Contrat dans `api` (`ycappuccino.api.endpoints_storage`)

Nouveau module. L'ancien `ycappuccino.api.endpoints` (`UrlPath`, `IHandlerEndpoint`, `IRightManager`...) reste inchangé jusqu'au sous-projet `http_server`.

### 1.1 Erreurs

```python
class CrudError(Exception): ...
class NotAuthenticated(CrudError): ...   # 401 : item sécurisé et sujet absent
class Forbidden(CrudError): ...          # 403 : item en lecture seule, ou sujet non autorisé
class NotFound(CrudError): ...           # 404 : item inconnu ou abstrait, document ou brouillon absent
class InvalidRequest(CrudError): ...     # 400 : paramètres invalides, id ou champs interdits
```

Les codes en commentaire sont indicatifs : ils guident les adaptateurs HTTP, les services ne les connaissent pas.

### 1.2 Services

```python
class ICrud(YCappuccinoComponent, ABC):
    async def get_one(self, item_id: str, id: str, params: dict | None = None,
                      subject: dict | None = None) -> dict
    async def get_many(self, item_id: str, params: dict | None = None,
                       subject: dict | None = None) -> dict           # {"items": [dict], "total": int}
    async def create(self, item_id: str, fields: dict, subject: dict | None = None) -> dict
    async def update(self, item_id: str, id: str, fields: dict, subject: dict | None = None) -> dict
    async def delete(self, item_id: str, id: str, subject: dict | None = None) -> None
    async def delete_many(self, item_id: str, filter: dict, subject: dict | None = None) -> int


class IDrafts(YCappuccinoComponent, ABC):
    async def get_one(self, item_id: str, id: str, draft: str, params: dict | None = None,
                      subject: dict | None = None) -> dict
    async def get_many(self, item_id: str, draft: str, params: dict | None = None,
                       subject: dict | None = None) -> dict           # {"items": [dict], "total": int}
    async def save(self, item_id: str, id: str, draft: str, fields: dict,
                   subject: dict | None = None) -> dict
    async def publish(self, item_id: str, id: str, draft: str, subject: dict | None = None) -> dict
    async def discard(self, item_id: str, id: str, draft: str, subject: dict | None = None) -> None


class IItemCatalog(YCappuccinoComponent, ABC):
    async def get_items(self, subject: dict | None = None) -> list
    async def get_item(self, item_id: str, subject: dict | None = None) -> dict
    async def get_item_by_plural(self, plural: str, subject: dict | None = None) -> dict
    async def get_schema(self, item_id: str, subject: dict | None = None) -> dict
    async def get_empty(self, item_id: str, subject: dict | None = None) -> dict | None


class IAuthorization(YCappuccinoComponent, ABC):
    async def is_authorized(self, subject: dict, action: str, item_id: str) -> bool
        """action parmi "read", "write", "delete", "private" """
```

`params` accepte les clés de `IManager` (`filter`, `sort`, `limit`, `offset`, `expand`, `content`), sous forme de texte ou déjà typées.

## 2. Autorisation (`endpoints_storage/access.py`)

`Access(items: IItemManager, authorizations: list)` est une classe interne, instanciée par chaque service avec ses propres dépendances. Elle n'est pas un composant.

### 2.1 Injection du port

Chaque service reçoit `authorizations: list[IAuthorization]`, liste vivante du core, et utilise son premier élément. Une dépendance `IAuthorization | None` ne convient pas : le core ne la lit qu'à la validation, donc une `IAuthorization` démarrée après le service ne lui parviendrait jamais.

### 2.2 Actions

| Opérations | Action |
|---|---|
| `ICrud.get_one`, `ICrud.get_many`, `IDrafts.get_one`, `IDrafts.get_many`, toutes les méthodes d'`IItemCatalog` | `read` |
| `ICrud.create`, `ICrud.update`, `IDrafts.save`, `IDrafts.publish`, `IDrafts.discard` | `write` |
| `ICrud.delete`, `ICrud.delete_many` | `delete` |
| `params["content"]` contenant `privateField` | `private`, contrôlée en plus de `read` |

### 2.3 `check(item_id, action, subject)`

Dans l'ordre :

1. `items.get_item(item_id)` ; un `KeyError` ou un item `abstract` lève `NotFound`.
2. `write` ou `delete` sur un item dont `isWritable` est faux lève `Forbidden`, quel que soit le sujet. Les composants back-end écrivent toujours via `IManager`.
3. L'action est sécurisée si c'est `private`, si c'est `read` et que `secureRead` est vrai, ou si c'est `write`/`delete` et que `secureWrite` est vrai. Une action non sécurisée est autorisée sans appeler `IAuthorization`.
4. Action sécurisée et `subject` à `None` : `NotAuthenticated`.
5. Action sécurisée et liste `authorizations` vide : `Forbidden`, avec un warning loggé.
6. `await authorizations[0].is_authorized(subject, action, item_id)` faux : `Forbidden`.

### 2.4 Contrôles liés aux paramètres

`check_read(item_id, params, subject)` applique `check(item_id, "read", subject)`, puis :

- `private` si `params["content"]` contient `privateField` ;
- `read` sur l'item de chaque segment d'`expand` (`author`, `author.country`...). Les noms sont lus avec `parse_expand` de `ycappuccino.storage.query`. Un `expand` invalide lève `InvalidRequest`.

Un nom d'`expand` est l'id de l'item référencé : c'est cet id qui est contrôlé.

### 2.5 Règles communes

- **Héritage** : lire `book` renvoie aussi les `novel` ; seul l'item demandé est contrôlé.
- **Tenant** : `subject` est transmis tel quel à `IManager`, dont les `IFilter` restreignent les documents. Un appel anonyme n'a aucun filtre de tenant.
- **Paramètres invalides** : un `ValueError` levé par le parsing des paramètres (JSON, entier) devient `InvalidRequest`.

## 3. Données (`endpoints_storage/crud.py`)

`Crud(ICrud)` : `__init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization])`.

Le résultat d'un modèle est une copie de `model.get_storage_model()`. Seuls `_id` et les propriétés déclarées y figurent : les champs stockés sans setter ne sont pas relus par `Model.on_read`.

### 3.1 Lecture

- Contrôle `check_read`.
- Le filtre de `params` (dict ou JSON) est combiné en `{"$and": [filtre, {"_draft": {"$exists": false}}]}` : les brouillons sont exclus.
- `get_one` : `manager.get_one` ; `None` lève `NotFound`.
- `get_many` : `{"items": manager.get_many(...), "total": manager.count(item_id, params, subject)}`. Le total ignore `offset` et `limit`.

### 3.2 Écriture

- Contrôle `write`.
- `fields` contenant `_draft` ou `_draft_of` lève `InvalidRequest`.
- `create` : l'id est `fields["_id"]` s'il est présent, sinon `str(uuid.uuid4())`. Le document est créé, ou mis à jour champ par champ s'il existe déjà (upsert partiel, comme le POST legacy).
- `update` : upsert partiel de l'id (comme le PUT legacy). Si `fields` contient un `_id` différent de `id`, `InvalidRequest`.
- Un id contenant `~` lève `InvalidRequest`.
- Renvoie le modèle stocké par `manager.up_sert`.

### 3.3 Suppression

- Contrôle `delete`.
- `delete` : l'original est relu sous le sujet ; absent, `NotFound`. Sinon `manager.delete(item_id, id, subject)` puis `manager.delete_many(item_id, {"_draft_of": id}, subject)`.
- `delete_many` : un filtre vide (`{}` ou `None`) lève `InvalidRequest`. Les ids des originaux correspondant au filtre (brouillons exclus) sont lus page par page (`limit` 1000), puis `manager.delete_many(item_id, {"_id": {"$in": ids}}, subject)` et `manager.delete_many(item_id, {"_draft_of": {"$in": ids}}, subject)`. Renvoie le nombre d'originaux supprimés.

## 4. Brouillons (`endpoints_storage/drafts.py`)

`Drafts(IDrafts)` : `__init__(self, items: IItemManager, manager: IManager, authorizations: list[IAuthorization])`.

### 4.1 Stockage

- Le brouillon `x` de l'original `dune` est un document du même item, d'id `dune~x`, avec les champs `_draft: "x"` et `_draft_of: "dune"`.
- Un nom de brouillon vide ou contenant `~` lève `InvalidRequest`, de même qu'un id contenant `~`.
- Un item `multipart` refuse les brouillons (`InvalidRequest`) : publier recopierait la clé du fichier du brouillon, que `discard` supprimerait ensuite.
- Dans les résultats, `_id` vaut toujours l'id de l'original ; la version brouillon porte en plus `_draft: "x"`.

### 4.2 Lecture

- Contrôle `check_read`.
- `get_one(id, x)` : `dune~x` s'il existe, sinon `dune` hors brouillons, sinon `NotFound`.
- `get_many(x, params)` :
  1. les ids des originaux ayant un brouillon `x` sont lus page par page (`filter {"_draft": "x"}`, `limit` 1000), en retirant le suffixe `~x` des `_id` ;
  2. la requête principale est `{"$and": [filtre, {"$or": [{"_draft": {"$exists": false}, "_id": {"$nin": ids}}, {"_draft": "x"}]}]}`, avec `sort`, `offset`, `limit` et `expand` de `params` ;
  3. le total est `manager.count` sur la même requête.

  Les brouillons sans original (item créé en brouillon) sont inclus.
- Limites documentées : un filtre sur `_id` ne trouve pas la version brouillon (son `_id` stocké est `dune~x`) ; le tri sur `_cat` et `_mat` utilise les dates du brouillon.

### 4.3 Écriture

Contrôle `write`, et `fields` contenant `_id`, `_draft` ou `_draft_of` lève `InvalidRequest`.

- `save(id, x, fields)` : si `dune~x` n'existe pas, les propriétés de l'original (s'il existe, sans `_id`) sont fusionnées sous `fields`. Puis `manager.up_sert(item_id, "dune~x", {...fusion, "_draft": x, "_draft_of": id}, subject)`. Renvoie la version brouillon.
- `publish(id, x)` : `dune~x` absent lève `NotFound`. Sinon `manager.up_sert(item_id, id, propriétés du brouillon sans _id, subject)`, qui déclenche les triggers `upsert` de l'original, puis `manager.delete(item_id, "dune~x", subject)`. Renvoie l'original publié.
- `discard(id, x)` : `dune~x` absent lève `NotFound`, sinon `manager.delete`.

## 5. Métadonnées (`endpoints_storage/catalog.py`)

`ItemCatalog(IItemCatalog)` : `__init__(self, items: IItemManager, authorizations: list[IAuthorization])`.

- La vue publique d'un item est un dict sérialisable : `id`, `plural`, `app`, `module`, `secure_read`, `secure_write`, `writable`, `multipart`, `refs`. Elle ne contient ni `_class_obj`, ni `_class`, ni `schema`, ni `empty`.
- `get_items` : items de `items.get_items()` dont `check(item_id, "read", subject)` passe ; les autres sont omis sans erreur.
- `get_item` : contrôle `read`, vue publique.
- `get_item_by_plural` : `items.get_item_by_plural` (`KeyError` devient `NotFound`), puis comme `get_item`.
- `get_schema` et `get_empty` : contrôle `read`, puis `items.get_schema` et `items.get_empty` (copies).

## 6. Évolution de `storage`

```python
class IStorage:
    async def count(self, collection: str, query: dict) -> int
        """number of documents matching the query"""

class IManager:
    async def count(self, item_id: str, params: dict | None = None,
                    subject: dict | None = None) -> int
        """number of documents get_many would return without offset and limit"""
```

- `MemoryStorage.count` : nombre de documents qui correspondent au filtre.
- `MongoStorage.count` : `count_documents(query)`.
- `Manager.count` : même périmètre que `get_many` (item et fils, `IFilter` du sujet, `filter` de `params`) ; les autres clés de `params` sont ignorées.
- Tests : un test `count` dans `storage_contract.py` (rejoué sur les deux backends) et un test dans `test_manager_read.py` ; une ligne au tableau du README.

## 7. Packaging, exemple et documentation

```
endpoints_storage/
  pyproject.toml
  README.md
  example/conf/application.yml
  example/library/__init__.py
  example/library/books.py
  src/main/python/ycappuccino/endpoints_storage/
    __init__.py
    access.py
    crud.py
    drafts.py
    catalog.py
  src/unittest/python/...
```

- **`pyproject.toml`** (uv, `uv_build`) : projet `ycappuccino-endpoints-storage`, module `ycappuccino.endpoints_storage`, racine `src/main/python`. Dépendances : `ycappuccino-api`, `ycappuccino-core`, `ycappuccino-storage` en sources locales éditables.
- **`.gitignore`** : `data`, `.venv`, `__pycache__`, `dist`, comme `storage`.
- **Supprimés** : `build.py`, `setup.py`, `bundles/`, `conf/config.yaml`, les tests vides, `src/unittest/__init__.py`, `src/unittest/python/__init__.py`, `example/__init__.py` et `example/models/`.
- **Exemple** : couche `ycappuccino_storage_memory` active, un modèle `Book` avec `secure_write=True`, une `IAuthorization` de démonstration qui autorise le sujet `alice`. Au démarrage, un composant crée un livre en tant qu'`alice`, lit la liste avec son total, sauve un brouillon et le publie, en loggant chaque étape. Il tente aussi une écriture anonyme et logge le `NotAuthenticated`.
- **README** : mise en place, les trois services, règles d'autorisation, brouillons et leurs limites, erreurs, test d'un composant avec `Manager` sur `MemoryStorage`.
- **`CLAUDE.md`** (racine du workspace) : le projet d'`endpoints_storage` devient `ycappuccino-endpoints-storage`, construit avec uv.

## 8. Tests

Commande : `uv run python -m unittest discover -s src/unittest/python`.

Les tests des services utilisent `IsolatedAsyncioTestCase`, un vrai `Manager` sur `MemoryStorage` et une fausse `IAuthorization` qui enregistre ses appels.

| Fichier | Contenu |
|---|---|
| `api` : `test_interfaces.py` | les quatre interfaces sont abstraites ; hiérarchie des erreurs |
| `storage` : `storage_contract.py`, `test_manager_read.py` | `count` sur les deux backends ; `Manager.count` avec fils, sujet et filtre |
| `test_access.py` | chaque étape de `check` ; `private` ; `expand` simple et imbriqué ; `expand` invalide ; `IAuthorization` arrivée après la construction |
| `test_crud.py` | lecture et total, exclusion des brouillons, `create` avec et sans `_id`, `update`, id avec `~`, champs de brouillon refusés, `delete` absent et en cascade, `delete_many` au filtre vide et en cascade, paramètres invalides |
| `test_drafts.py` | `get_one` avec retombée sur l'original, `get_many` (substitution, brouillon sans original, pagination, total), `save` avec et sans original, `publish` et ses triggers, `discard`, `NotFound`, refus multipart, noms invalides |
| `test_catalog.py` | filtrage par sujet, vue publique sérialisable (`json.dumps`), pluriel inconnu, schéma, empty |
| `test_endpoints_storage_framework.py` | framework démarré avec la couche mémoire : `ICrud`, `IDrafts` et `IItemCatalog` publiés et utilisables ; un item sécurisé devient accessible quand une `IAuthorization` est enregistrée après coup |
| `test_readme.py` | les exemples du README s'exécutent |

## 9. Hors périmètre

- L'adaptateur HTTP, le décodage des jetons et la traduction des erreurs en codes : sous-projet `http_server`.
- L'implémentation d'`IAuthorization` et le format des permissions : sous-projet `permissions_app`.
- La génération swagger à partir d'`IItemCatalog` : sous-projet `swagger`.
- L'upload multipart HTTP : l'adaptateur passe `content` ou `content64` dans `fields`, que `storage` gère déjà.
- Les brouillons d'items multipart, les brouillons par compte et l'historique des versions.

## 10. Risques

- **Pré-requête des brouillons** : `IDrafts.get_many` lit tous les ids de brouillons `x` avant la requête principale. C'est acceptable pour quelques milliers de brouillons ; au-delà, il faudrait un `$lookup` Mongo.
- **Champs non déclarés** : ils sont stockés mais absents des résultats, parce que `Model.on_read` ne relit que les propriétés déclarées. C'est le comportement actuel de `storage`, conservé.
- **Fermé par défaut** : sans `permissions_app`, les items sécurisés sont inaccessibles par ces services. C'est voulu ; l'exemple et le README fournissent une `IAuthorization` de démonstration.
- **Rupture pour les consommateurs legacy** : `hosts` (générateur `$resource`) et `swagger` s'appuient sur les anciennes URL ; ils sont déjà cassés et seront migrés dans leurs sous-projets.
