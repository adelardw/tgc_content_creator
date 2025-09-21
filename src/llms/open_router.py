from langchain_core.runnables import Runnable
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.messages import SystemMessage, HumanMessage
from openai import OpenAI
import typing as tp
from pydantic import BaseModel
import json
import typing as tp
import json
# Импортируем правильные классы из LangChain
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun



class OpenRouterChat(BaseChatModel):
    """
    Класс-обертка для работы с чат-моделями через API OpenRouter,
    совместимый с экосистемой LangChain и поддерживающий структурированный вывод.
    """

    def __init__(self,
                 api_key: str,
                 generation_kwargs: dict = None,
                 model_name: str = "qwen/qwen3-235b-a22b-2507"):
        super().__init__()

        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self._model_name = model_name

        default_kwargs = {
            "temperature": 1e-3,
            "max_tokens": 1024,
        }
        self._generation_kwargs = default_kwargs if not generation_kwargs else generation_kwargs

    @property
    def _llm_type(self) -> str:
        return "openrouter-chat"

    def _generate(
        self,
        messages: tp.List[BaseMessage],
        stop: tp.Optional[tp.List[str]] = None,
        run_manager: tp.Optional[CallbackManagerForLLMRun] = None,
        **kwargs: tp.Any,
    ) -> ChatResult:
        """
        Основной метод для вызова API, который принимает список сообщений
        и поддерживает structured output через tools.
        """
        message_dicts = [self._convert_message_to_dict(m) for m in messages]

        # Объединяем параметры генерации
        final_generation_kwargs = {**self._generation_kwargs, **kwargs}
        if stop:
            final_generation_kwargs['stop'] = stop

        completion = self._client.chat.completions.create(
            messages=message_dicts,
            model=self._model_name,
            **final_generation_kwargs
        )


        response_message = self._convert_dict_to_message(completion.choices[0].message.dict())
        generation = ChatGeneration(message=response_message)
        return ChatResult(generations=[generation])

    def _convert_message_to_dict(self, message: BaseMessage) -> dict:
        """Конвертирует сообщение LangChain в словарь для API."""
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            raise TypeError(f"Неподдерживаемый тип сообщения: {type(message)}")


        if isinstance(message, AIMessage) and message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": message.tool_calls
            }

        return {"role": role, "content": message.content}

    def bind_tools(
        self,
        tools: tp.List[tp.Union[tp.Dict[str, tp.Any], tp.Type[BaseModel]]],
        **kwargs: tp.Any,
    ) -> Runnable:
        """
        Привязывает инструменты к модели в формате, совместимом с OpenAI.
        """

        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]


        return self.bind(tools=formatted_tools, **kwargs)

    def _convert_dict_to_message(self, message_dict: dict) -> AIMessage:
        """Конвертирует ответ от API (словарь) в AIMessage."""
        if tool_calls := message_dict.get("tool_calls"):
            parsed_tool_calls = []
            invalid_tool_calls = []

            for call in tool_calls:
                try:
                    function_args = json.loads(call["function"]["arguments"])
                    parsed_tool_calls.append(
                        {
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "args": function_args,
                        }
                    )
                except json.JSONDecodeError:
                    invalid_tool_calls.append(
                        {
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "args": call["function"]["arguments"],
                            "error": "Failed to decode JSON from arguments string.",
                        }
                    )
            return AIMessage(
                content=message_dict.get("content") or "",
                tool_calls=parsed_tool_calls,
                invalid_tool_calls=invalid_tool_calls,
            )
        else:
            return AIMessage(content=message_dict.get("content", ""))

    def with_structured_output(self, schema, *, include_raw = False, **kwargs):
        """Привязывает Pydantic схему для структурированного вывода."""
        return super().with_structured_output(schema, include_raw=include_raw, **kwargs)
