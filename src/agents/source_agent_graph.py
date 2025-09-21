from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
import os 
from dotenv import load_dotenv
load_dotenv()
from loguru import logger

from src.tools.config import endpoints


from src.agents.prompts import (simillar_prompt, relevance_input_prompt,post_creator_prompt,
                                rewiritter_prompt, relevance_prompt, image_selection_prompt,theme_prompt,
                                FORBIDDEN_ANSWER)

from src.agents.agent_schemas import SourceAgentGraph
from src.tools.ddgs_web_search import retriever
from src.tgbot.cache import cache_db
from src.agents.utils import measure_time, redis_update_links
from src.tools.google_web_search import get_google_image_links
from src.llms.open_router import OpenRouterChat


llm = OpenRouterChat(api_key=os.getenv('OPEN_ROUTER_API_KEY'),
                     model_name=os.getenv('TEXT_GENERATION_MODEL'))

text_image_llm = OpenRouterChat(api_key=os.getenv('OPEN_ROUTER_API_KEY'),
                               model_name=os.getenv('TEXT_IMAGE_MODEL'))

relevance_query_agent = relevance_input_prompt | llm | StrOutputParser()
news_classifier_agent = relevance_prompt | llm | StrOutputParser()
simillar_agent = simillar_prompt | llm | StrOutputParser()
rewriter_agent = rewiritter_prompt | llm | StrOutputParser()
post_creator_agent = post_creator_prompt | llm | StrOutputParser()
search_query_gen_agent = theme_prompt | llm | StrOutputParser()

image_selection_agent = image_selection_prompt | text_image_llm | StrOutputParser()

ckpt = InMemorySaver()

@measure_time
def router(state):

    replyed = state.get('is_replyed_message', False)
    selected = state.get('is_selected_channels', False)
    decision = state.get('decision', False)
    web_ctx = state.get('add_web_parsing_as_ctx', False)

    if not web_ctx:
        if (replyed or selected) and not decision:
            return '👀⁉️ClassifierReactionNode'
        if (not replyed and not selected) and not decision:
            return '✅RelevanceQueryNode'
        if (not replyed and not selected) and decision:
            return '👀⁉️ClassifierReactionNode'
    else:
        return "🕸️🌏FindContextinWebNode"

@measure_time
def relevance_query_node(state):
    user_message = state['user_message']
    answer = relevance_query_agent.invoke({'themes': endpoints,
                                           'user_message': user_message})
    if FORBIDDEN_ANSWER in answer:
        state['generation'] = FORBIDDEN_ANSWER
        state['decision'] = False
    else:
        state['decision'] = True
    return state

@measure_time
def relevance_router(state):
    if state['decision']:
        return '📱FindSimillarThemeNode'
    else:
        return END

@measure_time
def simillar_node(state):

    user_message = state['user_message']
    state['endpoint'] = simillar_agent.invoke({'endpoints': endpoints,
                                               'user_message': user_message})
    return state



@measure_time
def web_ctx_router(state):
    web_ctx = state.get('add_web_parsing_as_ctx', False)
    post = state.get('post', None)
    
    if web_ctx:
        return '🕸️🌏FindContextinWebNode'
    if not web_ctx and post:
        return '👀⁉️ClassifierReactionNode'
    else:
        return END


@measure_time
def classifier_node(state):
    post = state['post']
    emoji_reactions = state['emoji_reactions']
    grade = news_classifier_agent.invoke({'post': post,
                                          'emoji_reactions':emoji_reactions})
    
    return {**state, 'grade': grade}


@measure_time
def web_ctx_node(state):
    search_query = state['user_message']
    web_ctx = retriever(search_query)
    state['add_web_parsing_as_ctx'] = state['decision'] = False
    return {**state, 'web_ctx':web_ctx}


@measure_time
def creator_post_node(state):

    query = state['user_message']
    web_ctx = state['web_ctx']
    generation = post_creator_agent.invoke({'query':query,'web_ctx': web_ctx})
    state['web_ctx'] = None
    return {**state, 'generation': generation}


@measure_time
def rewriter_node(state):
    post = state['post']
    grade = state['grade']
    generation = rewriter_agent.invoke({'post': post,'grade':grade})
    # Сбрасываем состояния
    state['is_replyed_message'] = state['is_selected_channels'] = state['decision'] = False

    return {**state, 'generation': generation}

@measure_time
def select_search_query_node(state):
    
    gen_post = state['generation']
    query = search_query_gen_agent.invoke({'post': gen_post})
    state['search_query'] = query
    
    return state

@measure_time
def select_image_to_post_node(state):
 
    search_query = state['search_query']
    generated_post = state['generation']
    
    #cached_links = redis_img_find(cache_db)    
    finded_links =  get_google_image_links(search_query, max_num=5)
    #finded_links = links_filter(finded_links)
    #finded_links += cached_links

    if finded_links:        
        try:
            link_ind = image_selection_agent.invoke({'query': "Какая картинка лучше всего подходит под следующий пост?",
                                                     "post":generated_post,
                                                     "image_url": finded_links})

            link_ind = int(link_ind)
            
            if link_ind != -1:
                url = finded_links.pop(link_ind)
                if finded_links:
                    redis_update_links(finded_links,cache_db, ttl=60*60)
                    
                return {**state, 'image_url': url}
        
        except Exception as e:
            redis_update_links(finded_links,cache_db ,ttl=60*60)
            logger.info(f'Случилась какая - то ошибка при выборе картинки к посту {e}')
    
    return {**state, 'image_url': None}
    

    
workflow = StateGraph(SourceAgentGraph)
workflow.add_node("✅RelevanceQueryNode", relevance_query_node)
workflow.add_node('🕸️🌏FindContextinWebNode', web_ctx_node)
workflow.add_node('👀⁉️ClassifierReactionNode', classifier_node)
workflow.add_node('📄✍️RewriterNode', rewriter_node)
workflow.add_node("📱FindSimillarThemeNode", simillar_node)
workflow.add_node("✈️🕸️🌏CreatePostFromWebSearchNode", creator_post_node)
workflow.add_node("👀🕸️🌏MakeSearchQuery", select_search_query_node)
workflow.add_node('👀🖼️SelectImage4Post', select_image_to_post_node)



workflow.add_conditional_edges(START,
                               router,
                               {"✅RelevanceQueryNode":"✅RelevanceQueryNode",
                               "👀⁉️ClassifierReactionNode": "👀⁉️ClassifierReactionNode",
                               "🕸️🌏FindContextinWebNode":"🕸️🌏FindContextinWebNode"})

workflow.add_conditional_edges(
    '✅RelevanceQueryNode',
    relevance_router,
    {"📱FindSimillarThemeNode": "📱FindSimillarThemeNode",
     END:END})

workflow.add_conditional_edges(
    '📱FindSimillarThemeNode',
    web_ctx_router,
    {
        '🕸️🌏FindContextinWebNode': '🕸️🌏FindContextinWebNode',
        '👀⁉️ClassifierReactionNode':'👀⁉️ClassifierReactionNode',
        END: END})

workflow.add_edge('🕸️🌏FindContextinWebNode', '✈️🕸️🌏CreatePostFromWebSearchNode')
workflow.add_edge('✈️🕸️🌏CreatePostFromWebSearchNode', "👀🕸️🌏MakeSearchQuery")


workflow.add_edge("👀⁉️ClassifierReactionNode","📄✍️RewriterNode")
workflow.add_edge("📄✍️RewriterNode", "👀🕸️🌏MakeSearchQuery")

workflow.add_edge("👀🕸️🌏MakeSearchQuery", "👀🖼️SelectImage4Post")
workflow.add_edge("👀🖼️SelectImage4Post", END)

graph = workflow.compile(debug=False, checkpointer=ckpt)
