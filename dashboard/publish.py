import redis
import json

def redis_publish():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    from streetlamp.state_models import AgentTrigger
    from streetlamp.engine.triggers import TRIGGER_FORMAT, REDIS_TOPIC

    at = AgentTrigger(
        type="Email",
        variables=dict(**{'from': 'Scott Persinger <scottpersinger@gmail.com>', 'subject': 'get this great message', 'body': 'at exactly 3:23\r\n'}),
        format_str=TRIGGER_FORMAT
    )

    print("publishiing: ", at)
    r.publish(REDIS_TOPIC, at.json())

def ollama():
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
    from langchain_community.chat_models import ChatOllama
    from langchain_core.output_parsers import StrOutputParser
    llm = ChatOllama(model="mistral:latest")
    prompt = ChatPromptTemplate.from_template("the question is: {input}")
    chain = prompt | llm | StrOutputParser()
    input = """
Given a javascript function called "create_jira_ticket" with a single argument:
  - options
where 'options' is a hash with these keys:
  - project_name
  - subject
  - description
Generate a function call, with this comments, to this function, where
the project is "AB", the summary is "There is a bug in Winners"
and the description is "The bug is really bad but i can't reproduce.".
"""
    print(chain.invoke({"input": input}))

def simpleg():
    import simplegmail
    gmail = simplegmail.Gmail()

if __name__ == "__main__":
    simpleg()
