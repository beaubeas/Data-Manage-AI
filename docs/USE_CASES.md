## Personal email productivity

**We have deempahasized personal use-cases for now**.

## Shared Email productivity

_Premise_: companies often have shared inboxes like info@, support@, ap@, legal@, etc...
There are lots of tools which can front these inboxes, but in smaller orgs they
may be monitored and actioned manually. They are also generally not "private" so
shared agents may be applicable.

- Listen for mail from a shared company inbox, and:
  - route messages to the right people internally
  - send messages to other systems, like Hubspot or JIRA
  - auto-respond to certain messages

Examples:

    Agent:
        (Customer opt-out bot)
        Trigger: Email received
        If the message references deleting customer data, then gather the
        details and create a JIRA ticket.

## Document productivity

## Knowledge search

Build various custom chatbots based on internal datasources.

Examples:
    Basic analytics bot.
    Agent:
        Answer the user's question by querying the database.

## LLM enrich a spreadsheet

A cool use case is if I have some list, say a list of companies, then I want to
program an agent to read that list from a spreadsheet, do web research on those
companies, then write the research back to the spreadsheet.

One way would be to have the "Loop agent" which reads the spreadsheet rows
and invokes a sub-agent to do the research for each row and save the results.

Maybe we could use "Pandas functional" style, something like:

    add_column(dataframe, source_column, target_column, action="run_research_agent")

This would assume that the native _add_column_ tool can invoke other agents. But maybe
this would be OK. We could expose a native function that allows any tool to call
any other tool (including another agent).

**Using DuckDB**

DuckDB supports adding Python-defined functions. So another approach would be
to allow the LLM to register any other tool's function as a DuckDB function, and
then you could use it inside a DuckDB `select`. 

So assume you attached the "call_research_company_agent" function to your agent,
then the LLM could do this:

    invoke: register_duckdb_function("call_research_company_agent")
    create a new dataframe:

        duckdb_execute("select *, call_research_company_agent(company_name) from companies_df")

    <-- returns a new DataFrame with the companies enriched

This could work, but lots would be happening inside that DuckDB engine and that single
function call could take a long time to run.


