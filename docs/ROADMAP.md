# Product Roadmap

The most promising current direction is "styles" of agents including
"system facade agents", "task agents", and "copilot agents". 

## Use cases

- Meeting summarizer
    - Google Docs tool for downloading the meeting transcript
      (partial downloads for too big files?)
- [done] Email receiver
    - Create a custom mail receiver tool with Mailgun (or Cloudmainin), that allows
      a user to use trigger@mail.llmonster.ai as a forwarding 
      address for email. We will pull messages from this inbox
      and match the "FROM" address to the user's email address(es)
      on file. This should avoid security concerns from people that
      don't want us to read their email.
- Lead qualifier
  - Qualify lead emails
  - Record them in Salesforce, with scoring
  - Call another agent to send the outbound email
- Spreadsheet enricher
  - Load data from rows of a spreadsheet, invoke the LLM or an agent
    to get some rich data, and write the result back to the spreadsheet
    We should implement "file upload" as a trigger type
    and support "record mode" on the trigger. Thus
    when you upload the file it runs your agent 
    for every record. 
## TODO
1. [done] Fix Trigger loop
2. [done]  Email receiver
2.1 [done] File upload trigger
3. [done] Google Docs tool
4. [done] Invoke Agent function (via name, no GUI)
5. Create a "save_memory" function which allows an agent to add stuff
to its long-term context. A great example: prompt your agent with a Database
tool to remember that it's a Postgres database.
6. [done] Convert Connections select to "Dropdown" which would support icons
7. [done] Tools will soon need to distinguish which Connection to use, eg. connections to multiple Salesforce instances
8. [done] Enable sub-agent chat streaming in the parent chat
9. Need to rationlize Triggers as a type of Tool


## Agents

**Playground Agent**

I often find myself wanting to test something out, usually a tool, with a built-in "playground" agent. I don't
want to have to name this agent or give it an avatar. I just want to be able to activate it, give it a tool,
and test out the results. Another notion might be the "Agent Lab". 

**Persistent Memory**

Currently the only memory that agents have is the recorded history of a chat. You can return tomorrow
and resume a chat that you started yesterday. But there is no notion of "persistent memory" for an agent
that can last _across_ multiple sessions.

**Tabular data**

Alex wants to implement a "Salesforce data loader" agent. I think an agent
that can load data intelligently from a spreadsheet file would be cool, but
not something for processing 1m records.

For the spreadsheet loader we could have:

- A tool that can read a Google Spreadsheet
- A tool that can read an Excel spreadsheet
- File upload from a CSV file

The biggest issue is I think we need to "batch" records on input to the agent.
So we need some logic to send 20 records at a time into the agent in batches.

## Triggers

- Rationalize all the triggers together into a single service
- Rationalize Triggers as a type of Tool
- Extract Triggers a top-level model
    - a Trigger is configured to activate an agent
    - but the interface

## Tools

- Finish the "smart" Salesforce tool:
    - Creating records
    - Updating records
    - Custom objects?
    - searching for objects by name
    - record search
    - can we have a "new Salesforce record" trigger? Maybe just polling...

- Google Docs tool
    - search docs
    - download docs as text
    - download a secured link as text
    