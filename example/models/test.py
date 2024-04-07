from src.main.python.models.decorators import Item, Property, Reference, Empty
from ycappuccino_storage import Model
from src.main.python.decorator_app import App


@Empty()
def empty():
    _empty = Test()
    _empty.id("test")

    return _empty


@App(name="test")
@Item(
    collection="tests", name="test", plural="tests", secure_write=True, secure_read=True
)
class Test(Model):
    """describe an account in the application"""

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._login = None
        self._name = None
        self._role = None

    @Property(name="name")
    def name(self, a_value):
        self._name = a_value

    @Reference(name="login")
    def login(self, a_value):
        self._login = a_value

    @Reference(name="role")
    def role(self, a_value):
        self._role = a_value


empty()
