from . import registry
from .create_event_with_schedule import CREATE_EVENT_WITH_SCHEDULE_TOOL
from .create_module_from_template import CREATE_MODULE_FROM_TEMPLATE_TOOL
from .current_user_context import CURRENT_USER_CONTEXT_TOOL
from .find_module_by_name import FIND_MODULE_BY_NAME_TOOL
from .find_understaffed_modules import FIND_UNDERSTAFFED_MODULES_TOOL
from .get_module_roster import GET_MODULE_ROSTER_TOOL
from .list_modules import LIST_MODULES_TOOL
from .move_participant import MOVE_PARTICIPANT_TOOL
from .nudge_understaffed_module import NUDGE_UNDERSTAFFED_MODULE_TOOL
from .participant_history import PARTICIPANT_HISTORY_TOOL
from .quarters import (
    CREATE_QUARTER_TOOL,
    LIST_QUARTERS_TOOL,
    UPDATE_QUARTER_TOOL,
)
from .send_reminder_email import SEND_REMINDER_EMAIL_TOOL
from .signup_stats_for_week import SIGNUP_STATS_FOR_WEEK_TOOL
from .signup_trend import SIGNUP_TREND_TOOL

registry.register(LIST_MODULES_TOOL)
registry.register(GET_MODULE_ROSTER_TOOL)
registry.register(FIND_UNDERSTAFFED_MODULES_TOOL)
registry.register(PARTICIPANT_HISTORY_TOOL)
registry.register(SIGNUP_STATS_FOR_WEEK_TOOL)
registry.register(SIGNUP_TREND_TOOL)
registry.register(FIND_MODULE_BY_NAME_TOOL)
registry.register(CURRENT_USER_CONTEXT_TOOL)
registry.register(SEND_REMINDER_EMAIL_TOOL)
registry.register(NUDGE_UNDERSTAFFED_MODULE_TOOL)
registry.register(CREATE_MODULE_FROM_TEMPLATE_TOOL)
registry.register(CREATE_EVENT_WITH_SCHEDULE_TOOL)
registry.register(MOVE_PARTICIPANT_TOOL)

# Settings / Quarters. An event can only exist inside a quarter, so the
# copilot needs to be able to see the calendar and extend it — not just
# report the wall it hit.
registry.register(LIST_QUARTERS_TOOL)
registry.register(CREATE_QUARTER_TOOL)
registry.register(UPDATE_QUARTER_TOOL)
