from . import registry
from .find_understaffed_modules import FIND_UNDERSTAFFED_MODULES_TOOL
from .get_module_roster import GET_MODULE_ROSTER_TOOL
from .list_modules import LIST_MODULES_TOOL

registry.register(LIST_MODULES_TOOL)
registry.register(GET_MODULE_ROSTER_TOOL)
registry.register(FIND_UNDERSTAFFED_MODULES_TOOL)
