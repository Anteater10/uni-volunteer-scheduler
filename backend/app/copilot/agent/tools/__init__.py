from . import registry
from .get_module_roster import GET_MODULE_ROSTER_TOOL
from .list_modules import LIST_MODULES_TOOL

registry.register(LIST_MODULES_TOOL)
registry.register(GET_MODULE_ROSTER_TOOL)
