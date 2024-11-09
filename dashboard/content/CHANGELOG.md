6-25-2024
1. Added agent reflection and memory! Including slash commands to manage.
1. Added admin page for monitoring

5-26-2024
1. Conversation is preserved when adding or removing tools from an agent now.
1. Last chat is loadded automatically when you open an agent.

5-1-2024
1. Added built-in Email triggers using a system mailbox.
1. Added temperature and Max exec time settings to agents.

4-24-2024
1. Introducing **Folders**! Organize your agents into muliple private and shared folders.

4-16-2024
1. Agents can now be attached as tools to other agents
1. New tool: DuckDB tool for data manipulation and in-memory SQL operations
1. New tool: Pandas tool is a v1 for Pandas support
1. New tool: Snowflake tool allows access to Snowflake, including admin and data loading
1. Save and use multiple "user prompts"
1. Add a "Welcome message" to your agent
1. Native DataFrame support for tabular data
1. Added inline File Uploads to the chat


03-28-2024
1. Added "Copy this agent" function
1. Export Agent to a file, create Agent from file

03-20-2024
1. Login with email/password now available
1. Sub-agents log now displayed in the calling agent's window
1. Password reset is now available
1. Override avatar generation hints using "Image: ..." syntax in your description.

03-11-2024
1. New Tools popup box makes it easier to manage your assistant tools
1. New Google News tool

03-11-2024
1. Basic support for Salesforce sandbox accounts
1. Search for email messages with the GMailAPI tool
1. More triggers: by schedule, email, Slack bot, database

03-10-2024

1. Chat history. You can now resume a prior chat and the chat history will be
remembered by the agent.
1. Added product icons for connections.

03-06-2024

1. New Image Generation tool which uses Dall*e to generate images. There is also
support in the GMail tool for attaching such an email to an outgoing email.
1. New GMail tool which uses Google Oauth and the Gmail API. Currently only supports
sending outgoing email.
1. Chat history now available on the Assistant runner page (click the title of
the Assistant to get there). This will show past chats including ones that were triggered
async (like via Slack bot or email message).

02-28-2024

1. Added new Salesforce tool, with Oauth support, for creating Leads. More
functions coming soon.
1. Added Slack Bot trigger for assistants. Trigger your assistant and interact
with it in Slack.
1. Added File Download tool.
1. Added Database trigger - activate your assistant when a new record appears in a table.
 

0.5.1

1. Added Getting Started popup
1. Added waitlist signup

0.5.0

1. Refactored all the tool functions into tool_factory.py
1. Fixed web browsing tool to work with no credential
1. Added home Login page. Must be logged in to access.
1. Tenants created based on user's email domain.
1. Assistants list tied to your specific Tenant. 
1. Separated "Shared" vs. "Private" assistants
1. Added _test prompts_ feature so you can record and re-use a test prompt.
1. Added a `New Agent` page with descriptions of some common types of Agents
you can build
1. Implemented Dall*e generation of Assistant logos.
1. Fixed render bug on "Run App" page with initial chat bubble obscured

