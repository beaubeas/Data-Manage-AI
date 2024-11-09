# Intro

The Dashboard is implementeed in 99% Python using the Reflex web framework. That framework works
by having you write your web pages and components in Python, which it then transpiles into
React/Javascript.

Everything that isn't UI code is left as Python and bundled into a FastAPI server app.

Client to server communication is handled via wiring up backend Python functions as "event handlers" to
events that happen in the browser. Communucation between the client and the server happens over a websocket.

All UI state is kept in instances of `State` classes on the server. Whenever this state changes it gets
serialized to JSON and sent over the websocket to the frontend which then redraws the React components
with the new state. This all happens pretty seamlessly.

## State by pages

Since the state is constantly getting serialized over the websocket it pays to keep it as small as possible.
One way we can do that is to break up the State by page into separate classes. The trick is that we need
to keep a BaseState class that holds any global state like the user's login info:

GlobalState
    - user login tokens
    - logo
    - service_status

    LoginState
        - login form fields

    IndexState
        - folders
        - current folder
        - current agent lists
        - tool factories
        - credentials

    EditState
        - folders
        - current agent
        - all the tools info
        - current Run and runlogs
        - all the modal window flags

    FilesState
        - file listings

    ConnectionsState
        - credentials
        


