from supercog.engine.tool_factory import ToolFactory, ToolCategory
from contextlib import contextmanager
import json
import requests
from dateutil.relativedelta import relativedelta
from typing import Any, Callable, List, Dict, Optional
import time
from fastapi import FastAPI
from supercog.shared.services import get_service_host

import importlib
import inspect
import functools
from datetime import datetime
from git import Repo, GitCommandError
import os


class GitTool(ToolFactory):
    repo_dir: str = "~/source"  # Local path to store the git repos

    def __init__(self):
        super().__init__(
            id="git_connector",
            system_name="Github",
            logo_url="https://logo.clearbit.com/github.com",
            auth_config={
                "strategy_token": {
                    "git_api_key": "API KEY - find this at https://github.com/settings/tokens",
                    "help": "Create a GIT personal access token (classic), and set the value here."
                }
            },
            category=ToolCategory.CATEGORY_SAAS,
            help="""
Use this tool to manipulate git repositories
"""
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            #self.clone_repository,
            #self.fetch_changes,
            #self.create_commit,
            #self.push_changes,
            #self.pull_changes,
            #self.list_branches,
            #self.checkout_branch,
            #self.create_branch,
            #self.delete_branch,
            #self.list_tags,
            #self.create_tag,
            #self.repository_status,
            
            self.search_repositories,
            self.create_github_issue,
            self.get_github_issues,
            self.create_pull_request,
            self.get_pull_requests,
            self.add_comment_to_issue,
            self.get_repository_contents,
            self.create_repository,
            self.delete_repository,
            self.get_user_info,
            self.list_user_repositories,
            self.list_repository_pull_requests,
        ])

    def clone_repository(self, repo_url: str) -> str:
        """
        Clone a git repository from the given URL.
        :param repo_url: str
            The URL of the repository to clone.
        :return: str
            Status message.
        """
        try:
            Repo.clone_from(repo_url, os.path.join(self.repo_dir, self.run_context.tenant_id))
            return "Repository cloned successfully."
        except GitCommandError as e:
            return f"Error cloning repository: {str(e)}"

    def fetch_changes(self, repo_path: str) -> str:
        """
        Fetch changes from the remote repository.
        :param repo_path: str
            Path to the local repository.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            repo.git.fetch()
            return "Fetched changes successfully."
        except GitCommandError as e:
            return f"Error fetching changes: {str(e)}"

    def create_commit(self, repo_path: str, message: str, files: Optional[List[str]] = None) -> str:
        """
        Create a commit in the local repository.
        :param repo_path: str
            Path to the local repository.
        :param message: str
            Commit message.
        :param files: Optional[List[str]]
            List of file paths to commit. Commits all changes if None.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            if files:
                repo.index.add(files)
            else:
                repo.git.add(A=True)
            repo.index.commit(message)
            return "Commit created successfully."
        except GitCommandError as e:
            return f"Error creating commit: {str(e)}"

    def push_changes(self, repo_path: str, branch: str = "master") -> str:
        """
        Push changes from the local repository to the remote repository.
        :param repo_path: str
            Path to the local repository.
        :param branch: str
            Branch to push.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            origin = repo.remote(name='origin')
            origin.push(branch)
            return "Changes pushed successfully."
        except GitCommandError as e:
            return f"Error pushing changes: {str(e)}"

    def pull_changes(self, repo_path: str, branch: str = "master") -> str:
        """
        Pull changes from the remote repository to the local repository.
        :param repo_path: str
            Path to the local repository.
        :param branch: str
            Branch to pull.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            origin = repo.remote(name='origin')
            origin.pull(branch)
            return "Changes pulled successfully."
        except GitCommandError as e:
            return f"Error pulling changes: {str(e)}"

    def list_branches(self, repo_path: str) -> List[str]:
        """
        List all branches in the local repository.

        :param repo_path: str
            Path to the local repository.
        :return: List[str]
            List of branch names or an error message in a list.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            return [str(branch) for branch in repo.branches]
        except GitCommandError as e:
            return [f"Error listing branches: {str(e)}"]

    def checkout_branch(self, repo_path: str, branch_name: str) -> str:
        """
        Checkout a branch in the local repository.
        :param repo_path: str
            Path to the local repository.
        :param branch_name: str
            Branch to checkout.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            repo.git.checkout(branch_name)
            return f"Checked out branch {branch_name} successfully."
        except GitCommandError as e:
            return f"Error checking out branch {branch_name}: {str(e)}"

    def create_branch(self, repo_path: str, branch_name: str) -> str:
        """
        Create a new branch in the local repository.
        :param repo_path: str
            Path to the local repository.
        :param branch_name: str
            Name of the new branch to create.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            repo.git.branch(branch_name)
            return f"Branch {branch_name} created successfully."
        except GitCommandError as e:
            return f"Error creating branch {branch_name}: {str(e)}"

    def delete_branch(self, repo_path: str, branch_name: str) -> str:
        """
        Delete a branch in the local repository.
        :param repo_path: str
            Path to the local repository.
        :param branch_name: str
            Name of the branch to delete.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            repo.git.branch('-d', branch_name)
            return f"Branch {branch_name} deleted successfully."
        except GitCommandError as e:
            return f"Error deleting branch {branch_name}: {str(e)}"

    def list_tags(self, repo_path: str) -> List[str]:
        """
        List all tags in the local repository.

        :param repo_path: str
            Path to the local repository.
        :return: List[str]
            List of tag names or an error message in a list.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            return [str(tag) for tag in repo.tags]
        except GitCommandError as e:
            return [f"Error listing tags: {str(e)}"]  # Return the error message as a single-element list

    def create_tag(self, repo_path: str, tag_name: str, commit: str = 'HEAD') -> str:
        """
        Create a new tag in the local repository.
        :param repo_path: str
            Path to the local repository.
        :param tag_name: str
            Name of the new tag to create.
        :param commit: str
            Commit at which to create the tag, defaults to 'HEAD'.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            repo.create_tag(tag_name, ref=commit)
            return f"Tag {tag_name} created successfully at {commit}."
        except GitCommandError as e:
            return f"Error creating tag {tag_name}: {str(e)}"

    def repository_status(self, repo_path: str) -> str:
        """
        Get the current status of the local repository.
        :param repo_path: str
            Path to the local repository.
        :return: str
            Status message.
        """
        try:
            repo = Repo(os.path.join(self.repo_dir, repo_path))
            status = repo.git.status(porcelain=True)
            if status:
                return f"Repository status:\n{status}"
            else:
                return "No changes."
        except GitCommandError as e:
            return f"Error getting repository status: {str(e)}"


    ####################################
    # Below are the GITRestAPI functions
    ####################################
        
    def search_repositories(self,
                            query: str,
                            language: Optional[str] = None,
                            sort: str = 'stars',
                            order: str = 'desc')  -> dict:
        """
        Search for GitHub repositories.
        Args:
            query: Search keywords.
            language: Filter repositories by programming language.
            sort: Criteria to sort the results ('stars', 'forks', 'updated').
            order: Order of the results ('asc', 'desc').
        Returns:
            A list of dictionaries, each representing a repository.
        """
        url = f"https://api.github.com/search/repositories"
        api_key = self.credentials['git_api_key']
        headers = {'Authorization': f'token {api_key}'}
        params = {
            'q': f"{query}+language:{language}" if language else query,
            'sort': sort,
            'order': order
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()['items']
        else:
            return {'status': 'error', 'message': f"Failed to search repositories: {response.content}"}
        

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """

        try:
            # Get the API key from the secrets
            api_key = secrets.get("git_api_key")
            
            # Make a request to the GitHub API to check the validity of the API key
            url = "https://api.github.com/user"
            headers = {"Authorization": f"token {api_key}"}
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                print("Connection tested OK!")
                return None
            else:
                return f"Invalid GitHub API key. Status code: {response.status_code}"

        except requests.RequestException as e:
            return f"Error testing GitHub credentials: {str(e)}"

        except Exception as e:
            return str(e)
        
        
    def _github_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Helper method to make GitHub API requests.
        """
        url = f"https://api.github.com{endpoint}"
        headers = {
            'Authorization': f'token {self.credentials["git_api_key"]}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.request(method, url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            return {'status': 'error', 'message': f"API request failed: {response.content}"}


    def create_github_issue(self, repo_owner: str, repo_name: str, title: str, body: str, labels: List[str] = None) -> Dict[str, Any]:
        """
        Create a new issue in a GitHub repository.
        :param repo_owner: str
            The owner of the repository (username or organization name)
        :param repo_name: str
            The name of the repository
        :param title: str
            The title of the issue
        :param body: str
            The body text of the issue
        :param labels: List[str], optional
            A list of labels to apply to the issue
        :return: dict
            The created issue data or an error message
        """
        endpoint = f'/repos/{repo_owner}/{repo_name}/issues'
        data = {
            'title': title,
            'body': body,
            'labels': labels or []
        }
        return self._github_request('POST', endpoint, data)

    
    def get_github_issues(self, repo_owner: str, repo_name: str, state: str = 'open') -> List[Dict[str, Any]]:
        """
        Get a list of issues for a repository.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :param state: State of issues to return. Can be either 'open', 'closed', or 'all'
        :return: List of issues
        """
        return self._github_request('GET', f'/repos/{repo_owner}/{repo_name}/issues?state={state}')

    def create_pull_request(self, repo_owner: str, repo_name: str, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        """
        Create a new pull request.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :param title: Title of the pull request
        :param body: Body of the pull request
        :param head: The name of the branch where your changes are implemented
        :param base: The name of the branch you want the changes pulled into
        :return: Created pull request data
        """
        data = {
            'title': title,
            'body': body,
            'head': head,
            'base': base
        }
        return self._github_request('POST', f'/repos/{repo_owner}/{repo_name}/pulls', data)

    def get_pull_requests(self, repo_owner: str, repo_name: str, state: str = 'open') -> List[Dict[str, Any]]:
        """
        Get a list of pull requests for a repository.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :param state: State of pull requests to return. Can be either 'open', 'closed', or 'all'
        :return: List of pull requests
        """
        return self._github_request('GET', f'/repos/{repo_owner}/{repo_name}/pulls?state={state}')

    def add_comment_to_issue(self, repo_owner: str, repo_name: str, issue_number: int, body: str) -> Dict[str, Any]:
        """
        Add a comment to an issue.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :param issue_number: Issue number
        :param body: Comment body
        :return: Created comment data
        """
        data = {'body': body}
        return self._github_request('POST', f'/repos/{repo_owner}/{repo_name}/issues/{issue_number}/comments', data)

    def get_repository_contents(self, repo_owner: str, repo_name: str, path: str = '') -> List[Dict[str, Any]]:
        """
        Get contents of a repository.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :param path: Path to the content
        :return: List of contents
        """
        return self._github_request('GET', f'/repos/{repo_owner}/{repo_name}/contents/{path}')

    def create_repository(self, name: str, description: str = '', private: bool = False) -> Dict[str, Any]:
        """
        Create a new repository.
        :param name: The name of the repository
        :param description: A short description of the repository
        :param private: Whether the repository should be private
        :return: Created repository data
        """
        data = {
            'name': name,
            'description': description,
            'private': private
        }
        return self._github_request('POST', '/user/repos', data)

    def delete_repository(self, repo_owner: str, repo_name: str) -> Dict[str, Any]:
        """
        Delete a repository.
        :param repo_owner: Repository owner
        :param repo_name: Repository name
        :return: Status of the operation
        """
        return self._github_request('DELETE', f'/repos/{repo_owner}/{repo_name}')

    def get_user_info(self, username: str) -> Dict[str, Any]:
        """
        Get information about a GitHub user.
        :param username: GitHub username
        :return: User information
        """
        return self._github_request('GET', f'/users/{username}')
    
    def list_user_repositories(self, username: str, sort: str = 'updated', direction: str = 'desc') -> List[Dict[str, Any]]:
        """
        List repositories for a user.
        :param username: The GitHub username
        :param sort: The property to sort the repositories by. Can be one of: created, updated, pushed, full_name. (Default: 'updated')
        :param direction: The direction of the sort. Can be either 'asc' or 'desc'. (Default: 'desc')
        :return: List of repositories
        """
        endpoint = f'/users/{username}/repos'
        params = f'?sort={sort}&direction={direction}'
        return self._github_request('GET', f'{endpoint}{params}')

    def list_repository_pull_requests(self, repo_owner: str, repo_name: str, state: str = 'open', sort: str = 'created', direction: str = 'desc') -> List[Dict[str, Any]]:
        """
        List pull requests for a specific repository.
        :param repo_owner: The owner of the repository
        :param repo_name: The name of the repository
        :param state: State of pull requests to return. Can be either 'open', 'closed', or 'all'. (Default: 'open')
        :param sort: What to sort results by. Can be either 'created', 'updated', 'popularity' (comment count) or 'long-running' (age, filtering by pulls updated in the last month). (Default: 'created')
        :param direction: The direction of the sort. Can be either 'asc' or 'desc'. (Default: 'desc')
        :return: List of pull requests
        """
        endpoint = f'/repos/{repo_owner}/{repo_name}/pulls'
        params = f'?state={state}&sort={sort}&direction={direction}'
        return self._github_request('GET', f'{endpoint}{params}')
