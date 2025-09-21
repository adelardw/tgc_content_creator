from typing_extensions import TypedDict
import typing as tp

class SourceAgentGraph(TypedDict):

    user_message: str
    endpoint: str
    post: str
    grade: str
    decision: bool
    emoji_reactions: dict[str, str]
    is_replyed_message: bool
    is_selected_channels: bool
    add_web_parsing_as_ctx: bool
    generation: str
    web_ctx: str
    search_query: str
    image_url: tp.Optional[str]
    image_num: int