from supercog.engine.tool_factory import ToolFactory, ToolCategory


from jira import JIRA
import pandas as pd

from typing import Any, Callable


class JIRATool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "jira_connector",
            system_name = "JIRA",
            logo_url=super().logo_from_domain("atlassian.com"),
            category=ToolCategory.CATEGORY_SAAS,
            auth_config = {
                "strategy_token": {
                    "jira_username": "EMAIL for personal access token",
                    "jira_token": "TOKEN for personal access token",
                    "jira_url": "https://myproject.atlassian.net",
                    "help": """
Create a personal access token and set the email and token value here."""
                },
            },
            help="""
Access JIRA issues and projects
""",
        )

    def get_tools(self) -> list[Callable]:
        # Merges the supplied credentials as preset params
        # to our tool function and returns a LangChain compatible
        # tool function.
        return self.wrap_tool_functions([
            self.list_projects,
            self.create_jira_ticket,
            self.create_multiple_jira_tickets,
            self.search_jira_issues,
        ])

    def list_projects(self) -> list[dict]:
        """ List all projects in JIRA """
        # Your JIRA instance URL
        jira_url = self.credentials.get("jira_url")

        # Authentication
        jira = JIRA(basic_auth=(self.credentials["jira_username"],
                                self.credentials["jira_token"]),
                                options={'server': jira_url})

        # Retrieve a list of projects from JIRA
        return [p.raw for p in jira.projects()]
    
    def create_jira_ticket(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task"
    ) -> dict[str,str]:
        """ Creates a JIRA in the indicated project and returns a status message as JSON """
        # Your JIRA instance URL
        jira_url = self.credentials.get("jira_url")

        # Authentication
        jira = JIRA(basic_auth=(self.credentials["jira_username"],
                                self.credentials["jira_token"]),
                                options={'server': jira_url})

        # Issue fields
        issue_dict = {
            'project': {'key': project_key},  # Replace with your project key
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type},  # Replace with your issue type, e.g., Task, Bug, Story
        }

        # Create the issue
        new_issue = jira.create_issue(fields=issue_dict)
        msg = f"Issue {new_issue.key} created successfully."
        print(new_issue)
        return {"status": "success", "message": msg, "issue_key": new_issue.key, "link": new_issue.permalink()}
    
    async def create_multiple_jira_tickets(
        self,
        project_key: str,
        dataframe_var: str,
        issue_type: str = "Task"
    ) -> list[dict] | dict:
        """ Creates a JIRA issue from each row of the indicated dataframe. The dataframe
            should include columns for 'summary' and 'description' 
        """
        jira_url = self.credentials.get("jira_url")

        df, _ = self.get_dataframe_from_handle(dataframe_var)
        if 'summary' not in df.columns or 'description' not in df.columns:
            return {"status": "error", "message": "Dataframe must include 'summary' and 'description' columns."}

        # Authentication
        jira = JIRA(basic_auth=(self.credentials["jira_username"],
                                self.credentials["jira_token"]),
                                options={'server': jira_url})

        results: list[dict] = []
        for index, row in df.iterrows():
            await self.log(f"{index}: creating issue '{row['summary']}'")
            # Issue fields
            issue_dict = {
                'project': {'key': project_key},  # Replace with your project key
                'summary': row['summary'],
                'description': row['description'],
                'issuetype': {'name': issue_type},  # Replace with your issue type, e.g., Task, Bug, Story
            }
            # Create the issue
            new_issue = jira.create_issue(fields=issue_dict)
            results.append({"issue_key": new_issue.key, "link": new_issue.permalink()})

        return results

    def search_jira_issues(
        self,
        jql: str,
        fields: str="key,summary,description,priority,project,created,updated,reporter,assignee",
        preview_results: int = 20,
    ):
        """ Searches JIRA for issues (tickets) based on the JQL query and returns a list of issues 
            as a dataframe preview. Pass 'preview_results' count to set the number of results
            returned in the preview."""
        # Your JIRA instance URL
        jira_url = self.credentials.get("jira_url")

        # Authentication
        jira = JIRA(basic_auth=(self.credentials["jira_username"],
                                self.credentials["jira_token"]),
                                options={'server': jira_url, "version": 3})

        # Search JIRA
        issues = jira.search_issues(jql, fields=fields)
        issues = [i.raw for i in issues]
        df = pd.json_normalize(issues)
        return self.get_dataframe_preview(df, name_hint="jira_issues",max_rows=preview_results)
    
    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """

        try:
            jira_url = secrets.get("jira_url")
            jira_username = secrets.get("jira_username")
            jira_token = secrets.get("jira_token")

            jira = JIRA(basic_auth=(jira_username, jira_token),
                        options={'server': jira_url, "version": 3})

            # Perform a simple API call to check the connection
            # Retrieve a list of projects from JIRA
            projects = jira.projects()

            # Check if the list of projects is not empty
            if len(projects) > 0:
                print("Connection tested OK!")
                return None
            else:
                return "No projects found in JIRA. Please check your credentials and permissions."

        except Exception as e:
            return str(e)
