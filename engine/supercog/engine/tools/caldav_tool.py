from supercog.engine.tool_factory import ToolFactory, ToolCategory, TOOL_REGISTRY
from supercog.shared.services import config
from typing import List, Callable, Dict, Optional, Tuple, ClassVar
import json
from datetime import datetime
import caldav
from caldav.elements import dav, cdav
from caldav.lib.namespace import ns
import caldav.elements.ical
from caldav.elements.ical import CalendarColor
import caldav.elements.dav


from icalendar import Calendar, Event as ICalEvent
import pytz
import uuid
from supercog.shared.logging import logger
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

class CalDAVTool(ToolFactory):
    """
    A tool for interacting with CalDAV-compatible calendar servers.
    Includes special support for iCloud Calendar integration.
    """
    
    # Class constants for iCloud
    ICLOUD_CALDAV_URL: ClassVar[str] = "https://caldav.icloud.com"
    ICLOUD_PRINCIPAL_PATH: ClassVar[str] = "/{}/"  # Format with username
    ICLOUD_CALENDAR_PATH: ClassVar[str] = "/{}/calendars/{}"  # Format with username and calendar name
    
    client: Optional[caldav.DAVClient] = None
    principal: Optional[caldav.Principal] = None
    
    def __init__(self):
        """Initialize the CalDAV connector tool."""
        super().__init__(
            id="caldav_connector",
            system_name="CaldavCalendar",
            logo_url="https://logo.clearbit.com/icloud.com",
            category=ToolCategory.CATEGORY_CALENDAR,
            help=(
                "Use this tool to interact with CalDAV-compatible calendar servers.\n"
            ),
            auth_config={
                "strategy_token": {
                    "caldav_url": "For iCloud, use: https://caldav.icloud.com",
                    "username": "For iCloud: Your Apple ID email (e.g., username@icloud.com)",
                    "password": "For iCloud: Generate an app-specific password at appleid.apple.com > Sign-In and Security > App-Specific Passwords",
                    "help": (
                        "iCloud Calendar Connection Instructions:\n"
                        "1. URL: Use https://caldav.icloud.com\n"
                        "2. Username: Your complete Apple ID email\n"
                        "3. Password: You MUST use an app-specific password, not your Apple ID password\n"
                        "   - Go to appleid.apple.com\n"
                        "   - Sign in with your Apple ID\n"
                        "   - Go to Sign-In and Security > App-Specific Passwords\n"
                        "   - Click '+' to generate a new password\n"
                        "   - Use this generated password here\n\n"
                        "For other CalDAV servers, use their specific URL and credentials."
                    )
                }
            }
        )
        print("=== CALDAV TOOL INIT END ===\n")


    def _is_icloud_url(self, url: str) -> bool:
        """Check if the provided URL is an iCloud CalDAV URL"""
        return "icloud.com" in url.lower()

    def _sanitize_calendar_name(self, name: str) -> str:
        """Sanitize calendar name for URL usage"""
        return re.sub(r'[^a-zA-Z0-9-]', '-', name)

    def _clean_app_specific_password(self, password: str) -> str:
        """Clean an app-specific password by removing hyphens and converting to lowercase"""
        cleaned = password.replace('-', '').lower()
        print(f"App password cleaning:")
        print(f"  Original: {password}")
        print(f"  Cleaned: {cleaned}")
        print(f"  Length: {len(cleaned)}")
        return cleaned

    def _get_principal_url(self, base_url: str, username: str) -> str:
        """
        Get the correct principal URL for the CalDAV server
        
        :param base_url: Base CalDAV URL
        :param username: Username/email for authentication
        :return: Formatted principal URL
        """
        if self._is_icloud_url(base_url):
            # Instead of /username/calendars, try just /
            url = f"{base_url.rstrip('/')}"
            
            print("iCloud URL components:")
            print(f"  Base URL: {base_url}")
            print(f"  Username for auth: {username}")
            print(f"  Final URL: {url}")
            
            return url
        return base_url.rstrip('/')

    def test_credentials(self, cred, secrets: dict) -> str:
        """Test that the given credential secrets are valid."""
        if not all(k in secrets for k in ["caldav_url", "username", "password"]):
            return "Missing required credentials: caldav_url, username, and password are required"
            
        try:
            if self._is_icloud_url(secrets["caldav_url"]):
                # iCloud-specific validation
                if '@' not in secrets["username"]:
                    return "iCloud requires a valid Apple ID email as username"
                
                # Clean the password and check length
                cleaned_password = self._clean_app_specific_password(secrets["password"])
                if len(cleaned_password) != 16:
                    return f"iCloud requires an app-specific password (16 characters without hyphens) but got {len(cleaned_password)} characters"
                    
                principal_url = self._get_principal_url(secrets["caldav_url"], secrets["username"])
            else:
                principal_url = secrets["caldav_url"]
                cleaned_password = secrets["password"]

            logger.debug(f"Testing connection with URL: {principal_url}")
            
            client = caldav.DAVClient(
                url=principal_url,
                username=secrets["username"],
                password=cleaned_password,
                ssl_verify=True
            )
            
            # Now try to get principal
            principal = client.principal()
            calendars = principal.calendars()
            if len(calendars) == 0:
                logger.warning("Connection successful but no calendars found")
                
            return None
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Response status: {e.response.status}")
                logger.error(f"Response headers: {e.response.headers}")
            return f"Failed to authenticate with CalDAV server: {str(e)}"

    def get_tools(self) -> List[Callable]:
        """Retrieves the list of available CalDAV tool functions"""
        tools = [
            self.list_calendars,
            self.list_events,
            self.create_event,
            self.update_event,
            self.delete_event
        ]

        print("=" * 50)
        print("CalDAV Tool Initialization")
        print("=" * 50)

        try:
            if not self.credentials:
                print("ERROR: No credentials available")
                return self.wrap_tool_functions(tools)
                    
            print("Available credential keys:", list(self.credentials.keys()))
            print("Credentials (sanitized):", {
                k: v if k != 'password' else f"[{len(v)} chars]" 
                for k, v in self.credentials.items()
            })

            if 'caldav_url' not in self.credentials:
                print("ERROR: Missing caldav_url in credentials")
                return self.wrap_tool_functions(tools)

            # Initialize the client during tool setup
            self._ensure_client()

            if self._is_icloud_url(self.credentials["caldav_url"]):
                tools.extend([
                    self.create_icloud_calendar,
                    self.share_icloud_calendar,
                    self.get_icloud_calendar_sharing,
                    self.set_icloud_calendar_color,
                    self.get_icloud_free_busy
                ])
                logger.info("Added iCloud-specific calendar tools")

        except Exception as e:
            print(f"\nFATAL ERROR in get_tools:")
            print(f"Error type: {type(e)}")
            print(f"Error message: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response details:")
                print(f"  Status: {e.response.status_code}")
                print(f"  Headers: {e.response.headers}")
                
        print("\nFinished initialization attempt")
        print("=" * 50)
        
        return self.wrap_tool_functions(tools)
    
    def _get_server_url_from_calendar_url(self, calendar_url: str) -> str | None:
        """
        Extract the server URL (scheme://host:port) from a full calendar URL.
        Only does this for iCloud calendars, returns None for other CalDAV servers.
        
        :param calendar_url: Full calendar URL
        :return: Server base URL for iCloud, None for other servers
        """
        # Only process for iCloud URLs
        if not any(domain in calendar_url.lower() for domain in ['icloud.com', 'p-cloudkit.com']):
            print("Not an iCloud calendar URL, skipping server URL extraction")
            return None
            
        print(f"Extracting server URL from iCloud calendar URL: {calendar_url}")
        parsed = urlparse(calendar_url)
        server_url = f"{parsed.scheme}://{parsed.netloc}"
        print(f"Extracted iCloud server URL: {server_url}")
        return server_url
        
    def _ensure_principal(self) -> None:
        """Ensures we have a valid principal"""
        if self.principal is None:
            print("Getting principal...")
            self._ensure_client()
            self.principal = self.client.principal()

    def _ensure_client(self, calendar_url: str = None) -> None:
        """
        Ensures the CalDAV client is initialized and connected.
        Handles iCloud and non-iCloud calendars differently.
        For iCloud: Uses server URL from calendar_url if available
        For others: Uses the original configured URL
        
        :param calendar_url: Optional calendar URL to extract server from (for iCloud)
        """
        if self.client is not None:
            print("Using existing client")
            return

        print("\n=== INITIALIZING NEW CALDAV CLIENT ===")
        try:
            is_icloud = self._is_icloud_url(self.credentials["caldav_url"])
            print(f"Server type: {'iCloud' if is_icloud else 'Generic CalDAV'}")

            if is_icloud:
                print("Setting up iCloud client...")
                if calendar_url:
                    server_url = self._get_server_url_from_calendar_url(calendar_url)
                if not calendar_url or not server_url:  # If no calendar_url or not an iCloud URL
                    server_url = self.credentials["caldav_url"]
                    print(f"Using default iCloud URL: {server_url}")

                cleaned_password = self._clean_app_specific_password(self.credentials["password"])
                
                self.client = caldav.DAVClient(
                    url=server_url,
                    username=self.credentials["username"],
                    password=cleaned_password
                )
            else:
                print("Setting up generic CalDAV client...")
                # For non-iCloud, always use the original configured URL
                self.client = caldav.DAVClient(
                    url=self.credentials["caldav_url"],
                    username=self.credentials["username"],
                    password=self.credentials["password"]
                )

            print("Client initialized successfully")

        except Exception as e:
            self.client = None
            self.principal = None
            error_msg = f"Failed to initialize CalDAV client: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            raise RuntimeError(error_msg)

        print("=== CLIENT INITIALIZATION COMPLETE ===\n")
        
###############################################################################################################################
# Icloud specific caldav methods:
#

    def create_icloud_calendar(self, calendar_name: str, color: str = None) -> str:
        """
        Create a new calendar in iCloud
        
        :param calendar_name: Name of the new calendar
        :param color: Optional calendar color in hex format (e.g., '#FF0000' for red)
        :return: A formatted string containing the created calendar details
        """
        try:
            print("\n=== CREATE ICLOUD CALENDAR START ===")
            if not self._is_icloud_url(self.credentials["caldav_url"]):
                return "This method is only available for iCloud calendars"

            self._ensure_client()
            self._ensure_principal()

            print(f"Creating new calendar: {calendar_name}")
            sanitized_name = self._sanitize_calendar_name(calendar_name)
            
            # Create calendar
            new_cal = self.principal.make_calendar(name=calendar_name)
            
            # Set color if provided
            if color:
                print(f"Setting calendar color to: {color}")
                new_cal.set_properties([
                    dav.DisplayName(calendar_name),
                    caldav.CalendarColor(color)
                ])
            
            print("Calendar created successfully")
            return json.dumps({
                'status': 'success',
                'calendar': {
                    'name': calendar_name,
                    'url': str(new_cal.url),
                    'color': color
                }
            }, indent=2)
        except Exception as e:
            error_msg = f"Error creating iCloud calendar: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg

    def share_icloud_calendar(self, calendar_url: str, email: str, 
                            permission: str = "read-only") -> str:
        """
        Share an iCloud calendar with another user
        
        :param calendar_url: URL of the calendar to share
        :param email: Email address of the user to share with
        :param permission: Either "read-only" or "read-write"
        :return: A formatted string containing the sharing status
        """
        try:
            print("\n=== SHARE ICLOUD CALENDAR START ===")
            if not self._is_icloud_url(self.credentials["caldav_url"]):
                return "This method is only available for iCloud calendars"

            self._ensure_client()
            
            print(f"Getting calendar object for URL: {calendar_url}")
            calendar = self.client.calendar(url=calendar_url)
            
            # Set sharing properties
            privilege = "read" if permission == "read-only" else "write"
            print(f"Sharing calendar with {email} (privilege: {privilege})")
            calendar.share(email, privilege=privilege)
            
            print("Calendar shared successfully")
            return json.dumps({
                'status': 'success',
                'sharing': {
                    'calendar': str(calendar.url),
                    'shared_with': email,
                    'permission': permission
                }
            }, indent=2)
        except Exception as e:
            error_msg = f"Error sharing iCloud calendar: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg


    def get_icloud_calendar_sharing(self, calendar_url: str) -> str:
        """
        Get sharing information for an iCloud calendar

        :param calendar_url: URL of the calendar
        :return: A formatted string containing the sharing information
        """
        try:
            print("\n=== GET ICLOUD CALENDAR SHARING START ===")
            if not self._is_icloud_url(self.credentials["caldav_url"]):
                return "This method is only available for iCloud calendars"

            # Extract the server URL from the calendar URL
            print(f"Parsing calendar URL: {calendar_url}")
            parsed = urlparse(calendar_url)
            server_url = f"{parsed.scheme}://{parsed.netloc}"
            print(f"Using server URL: {server_url}")

            # Create a new client with the correct server URL
            print("Initializing client with correct server URL...")
            cleaned_password = self._clean_app_specific_password(self.credentials["password"])
            client = caldav.DAVClient(
                url=server_url,
                username=self.credentials["username"],
                password=cleaned_password
            )

            print(f"Getting calendar object for URL: {calendar_url}")
            calendar = client.calendar(url=calendar_url)

            print("Getting calendar properties...")

            # Define properties using caldav elements
            props = [
                dav.DisplayName(),
                CalendarColor(),
                dav.ResourceType(),
                dav.CurrentUserPrincipal(),
                # Owner(),    # Remove if not working
                # GetETag(),  # Remove if not working
            ]

            print(f"Requesting properties: {props}")
            properties = calendar.get_properties(props)
            print("Retrieved properties:", properties)

            # Format properties for readable output
            formatted_props = {}
            for prop_key, value in properties.items():
                readable_key = prop_key  # prop_key is a string
                formatted_props[readable_key] = str(value)
                print(f"Property {readable_key}: {formatted_props[readable_key]}")

            result = {
                'calendar': {
                    'url': str(calendar_url),
                    'name': str(properties.get('{DAV:}displayname', '')),
                    'color': str(properties.get('{http://apple.com/ns/ical/}calendar-color', '')),
                    'current_user_principal': str(properties.get('{DAV:}current-user-principal', '')),
                    'resource_type': str(properties.get('{DAV:}resourcetype', '')),
                    'raw_properties': formatted_props
                }
            }

            print("Final result:", json.dumps(result, indent=2))
            return json.dumps(result, indent=2)

        except Exception as e:
            error_msg = f"Error getting iCloud calendar sharing info: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            if hasattr(e, 'raw'):
                print(f"Raw response: {e.raw}")
            return error_msg


    def set_icloud_calendar_color(self, calendar_url: str, color: str) -> str:
            """
            Set the color of an iCloud calendar
            
            :param calendar_url: URL of the calendar
            :param color: Calendar color in hex format (e.g., '#FF0000' for red)
            :return: A formatted string confirming the color change
            """
            try:
                print("\n=== SET ICLOUD CALENDAR COLOR START ===")
                if not self._is_icloud_url(self.credentials["caldav_url"]):
                    return "This method is only available for iCloud calendars"

                # Extract the server URL from the calendar URL
                print(f"Parsing calendar URL: {calendar_url}")
                parsed = urlparse(calendar_url)
                server_url = f"{parsed.scheme}://{parsed.netloc}"
                print(f"Using server URL: {server_url}")

                # Create a new client with the correct server URL
                print("Initializing client with correct server URL...")
                cleaned_password = self._clean_app_specific_password(self.credentials["password"])
                client = caldav.DAVClient(
                    url=server_url,
                    username=self.credentials["username"],
                    password=cleaned_password
                )
                
                print(f"Getting calendar object for URL: {calendar_url}")
                calendar = client.calendar(url=calendar_url)
                
                print(f"Setting calendar color to: {color}")
                
                # Convert hex color to the format iCloud expects
                # Remove '#' if present and ensure uppercase
                color = color.strip('#').upper()
                # Add required alpha channel if not present
                if len(color) == 6:
                    color = color + "FF"
                formatted_color = f"#{color}"  # Add back the # as seen in current properties
                print(f"Formatted color value: {formatted_color}")
                
                # Get current properties including etag
                print("Getting current calendar properties...")
                current_props = calendar.get_properties([
                    caldav.elements.ical.CalendarColor(),
                    dav.GetEtag()
                ])
                print(f"Current properties: {current_props}")
                
                etag = current_props.get('{DAV:}getetag')
                print(f"Current ETag: {etag}")
                
                # Set the new color
                print("Setting new color property...")
                if etag:
                    # Add If-Match header to the calendar's client
                    calendar.client.headers['If-Match'] = etag
                
                try:
                    calendar.set_properties([caldav.elements.ical.CalendarColor(formatted_color)])
                finally:
                    # Clean up the header after the request
                    if etag and 'If-Match' in calendar.client.headers:
                        del calendar.client.headers['If-Match']
                
                # Verify the change
                new_props = calendar.get_properties([caldav.elements.ical.CalendarColor()])
                print(f"New properties: {new_props}")
                
                print("Calendar color updated successfully")
                return json.dumps({
                    'status': 'success',
                    'calendar': {
                        'url': str(calendar.url),
                        'color': formatted_color,
                        'previous_color': current_props.get('{http://apple.com/ns/ical/}calendar-color')
                    }
                }, indent=2)
            except Exception as e:
                error_msg = f"Error setting iCloud calendar color: {str(e)}"
                print(f"ERROR: {error_msg}")
                if hasattr(e, 'response'):
                    print(f"Response status: {e.response.status}")
                    print(f"Response headers: {e.response.headers}")
                return error_msg
        
    def get_icloud_free_busy(self, calendar_url: str, start_date: str, end_date: str) -> str:
        """
        Get free/busy information for an iCloud calendar
        
        :param calendar_url: URL of the calendar
        :param start_date: Start date in ISO format
        :param end_date: End date in ISO format
        :return: A formatted string containing free/busy information
        """
        try:
            print("\n=== GET ICLOUD FREE/BUSY START ===")
            if not self._is_icloud_url(self.credentials["caldav_url"]):
                return "This method is only available for iCloud calendars"

            # Extract the server URL from the calendar URL and initialize client
            print(f"Parsing calendar URL: {calendar_url}")
            parsed = urlparse(calendar_url)
            server_url = f"{parsed.scheme}://{parsed.netloc}"
            print(f"Using server URL: {server_url}")

            # Create a new client with the correct server URL
            print("Initializing client with correct server URL...")
            cleaned_password = self._clean_app_specific_password(self.credentials["password"])
            client = caldav.DAVClient(
                url=server_url,
                username=self.credentials["username"],
                password=cleaned_password
            )
            
            print(f"Getting calendar object for URL: {calendar_url}")
            calendar = client.calendar(url=calendar_url)
            
            print(f"Converting dates: {start_date} to {end_date}")
            start = datetime.fromisoformat(start_date).replace(tzinfo=pytz.UTC)
            end = datetime.fromisoformat(end_date).replace(tzinfo=pytz.UTC)
            
            print("Searching for events...")
            events = calendar.date_search(
                start=start,
                end=end,
                expand=True
            )
            
            # Process the events into busy periods
            busy_periods = []
            for event in events:
                try:
                    vcal = Calendar.from_ical(event.data)
                    for component in vcal.walk('VEVENT'):
                        dtstart = component.get('dtstart').dt
                        # Handle case where dtend is not present
                        if 'dtend' in component:
                            dtend = component.get('dtend').dt
                        elif 'duration' in component:
                            duration = component.get('duration').dt
                            dtend = dtstart + duration
                        else:
                            # If no end time or duration, assume 1 hour duration
                            dtend = dtstart + timedelta(hours=1)
                            
                        if isinstance(dtstart, datetime):
                            if not dtstart.tzinfo:
                                dtstart = dtstart.replace(tzinfo=pytz.UTC)
                            if not dtend.tzinfo:
                                dtend = dtend.replace(tzinfo=pytz.UTC)
                            
                            # Only include events that intersect with our search period
                            if dtstart <= end and dtend >= start:
                                busy_periods.append({
                                    'start': dtstart.isoformat(),
                                    'end': dtend.isoformat(),
                                    'summary': str(component.get('summary', 'No Title'))
                                })
                except Exception as parse_error:
                    print(f"Warning: Could not parse event: {parse_error}")
                    continue
                
            print(f"Found {len(busy_periods)} busy periods")
            return json.dumps({
                'calendar': str(calendar.url),
                'busy_periods': busy_periods,
                'time_range': {
                    'start': start.isoformat(),
                    'end': end.isoformat()
                }
            }, indent=2)
            
        except Exception as e:
            error_msg = f"Error getting iCloud free/busy info: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
                if hasattr(e.response, 'content'):
                    print(f"Response content: {e.response.content}")
            return error_msg

###############################################################################################################################
# Generic caldav methods:
#

    def list_calendars(self) -> str:
        """List all available calendars"""
        print("\n=== LIST CALENDARS START ===")
        print(f"Client exists: {self.client is not None}")
        print(f"Principal exists: {self.principal is not None}")
        
        try:
            print("\nAttempting to get principal...")
            self.principal = self.client.principal()
            print("Principal obtained successfully")
            
            print("\nAttempting to get calendars...")
            calendars = self.principal.calendars()
            print(f"Found {len(calendars)} calendars")
            
            calendar_list = []
            for cal in calendars:
                try:
                    props = cal.get_properties([dav.DisplayName()])
                    calendar_info = {
                        'name': props.get('{DAV:}displayname', 'Unnamed Calendar'),
                        'url': str(cal.url)
                    }
                    print(f"Calendar found: {calendar_info['name']}")
                    calendar_list.append(calendar_info)
                except Exception as cal_error:
                    print(f"Error getting calendar properties: {str(cal_error)}")
                    if hasattr(cal_error, 'response'):
                        print(f"Response status: {cal_error.response.status}")
                        print(f"Response headers: {cal_error.response.headers}")
            
            if calendar_list:
                print(f"\nSuccessfully retrieved {len(calendar_list)} calendars")
                return json.dumps(calendar_list, indent=2)
            else:
                print("\nNo calendars found")
                return json.dumps({"message": "No calendars found"})
            
        except Exception as e:
            print(f"Error: {type(e)} - {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            
            error_msg = {
                "error": "Error accessing calendars",
                "details": {
                    "client_exists": self.client is not None,
                    "principal_exists": self.principal is not None,
                    "error": str(e)
                }
            }
            return json.dumps(error_msg)

    def list_calendars(self) -> str:
        """List all available calendars"""
        print("\n=== LIST CALENDARS START ===")
        print(f"Client exists: {self.client is not None}")
        print(f"Principal exists: {self.principal is not None}")
        
        try:
            # Initialize the client first - for initial list_calendars we use default URL
            self._ensure_client()
            
            print("\nAttempting to get calendars...")
            # Now get principal and calendars
            if self.principal is None:
                print("Getting principal...")
                self.principal = self.client.principal()
            
            calendars = self.principal.calendars()
            print(f"Found {len(calendars)} calendars")
            
            calendar_list = []
            for cal in calendars:
                try:
                    props = cal.get_properties([dav.DisplayName()])
                    calendar_info = {
                        'name': props.get('{DAV:}displayname', 'Unnamed Calendar'),
                        'url': str(cal.url)
                    }
                    print(f"Calendar found: {calendar_info['name']}")
                    calendar_list.append(calendar_info)
                except Exception as cal_error:
                    print(f"Error getting calendar properties: {str(cal_error)}")
                    if hasattr(cal_error, 'response'):
                        print(f"Response status: {cal_error.response.status}")
                        print(f"Response headers: {cal_error.response.headers}")
            
            if calendar_list:
                print(f"\nSuccessfully retrieved {len(calendar_list)} calendars")
                return json.dumps(calendar_list, indent=2)
            else:
                print("\nNo calendars found")
                return json.dumps({"message": "No calendars found"})
            
        except Exception as e:
            error_msg = f"Error listing calendars: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg


    def list_events(self, calendar_url: str, start_date: str = None, end_date: str = None) -> str:
        """
        List events from a specific calendar within the given date range
        
        :param calendar_url: URL of the calendar to fetch events from
        :param start_date: Start date in ISO format (optional)
        :param end_date: End date in ISO format (optional)
        :return: A formatted string containing the list of events
        """
        try:
            print("\n=== LIST EVENTS START ===")
            print(f"Calendar URL: {calendar_url}")
            print(f"Date range: {start_date} to {end_date}")
            
            self._ensure_client()
            
            print("Getting calendar object...")
            calendar = self.client.calendar(url=calendar_url)
            
            # Convert dates if provided
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
            
            print(f"Searching for events between {start} and {end}")
            events = calendar.date_search(start=start, end=end)
            print(f"Found {len(events)} events")
            
            event_list = []
            for event in events:
                ical = Calendar.from_ical(event.data)
                for component in ical.walk('VEVENT'):
                    event_info = {
                        'summary': str(component.get('summary', 'No Title')),
                        'start': component.get('dtstart').dt.isoformat() if component.get('dtstart') else None,
                        'end': component.get('dtend').dt.isoformat() if component.get('dtend') else None,
                        'description': str(component.get('description', '')),
                        'location': str(component.get('location', '')),
                        'url': str(event.url)
                    }
                    print(f"Found event: {event_info['summary']}")
                    event_list.append(event_info)
            
            print("=== LIST EVENTS END ===\n")
            return json.dumps(event_list, indent=2)
            
        except Exception as e:
            error_msg = f"Error listing events: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg
        
    def create_event(self, calendar_url: str, summary: str, start_time: str, 
                    end_time: str, description: str = "", location: str = "") -> str:
        """
        Create a new calendar event
        
        :param calendar_url: URL of the calendar to create event in
        :param summary: Title of the event
        :param start_time: Start time in ISO format
        :param end_time: End time in ISO format
        :param description: Description of the event (optional)
        :param location: Location of the event (optional)
        :return: A formatted string containing the created event details
        """
        try:
            print("\n=== CREATE EVENT START ===")
            print(f"Calendar URL: {calendar_url}")
            print(f"Event: {summary} from {start_time} to {end_time}")
            
            self._ensure_client()
            
            print("Getting calendar object...")
            calendar = self.client.calendar(url=calendar_url)
            
            event = ICalEvent()
            event.add('summary', summary)
            event.add('description', description)
            event.add('dtstart', datetime.fromisoformat(start_time))
            event.add('dtend', datetime.fromisoformat(end_time))
            event.add('location', location)
            event.add('dtstamp', datetime.now(tz=pytz.UTC))
            event.add('uid', str(uuid.uuid4()))
            
            cal = Calendar()
            cal.add_component(event)
            
            print("Saving event...")
            calendar.save_event(cal.to_ical())
            print("Event saved successfully")
            
            return json.dumps({
                'status': 'success',
                'event': {
                    'summary': summary,
                    'start': start_time,
                    'end': end_time,
                    'description': description,
                    'location': location
                }
            }, indent=2)
        except Exception as e:
            error_msg = f"Error creating event: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg

    def update_event(self, calendar_url: str, event_url: str, summary: str = None, 
                    start_time: str = None, end_time: str = None, 
                    description: str = None, location: str = None) -> str:
        """
        Update an existing calendar event
        
        :param calendar_url: URL of the calendar containing the event
        :param event_url: URL of the event to update
        :param summary: New title of the event (optional)
        :param start_time: New start time in ISO format (optional)
        :param end_time: New end time in ISO format (optional)
        :param description: New description of the event (optional)
        :param location: New location of the event (optional)
        :return: A formatted string containing the updated event details
        """
        try:
            print("\n=== UPDATE EVENT START ===")
            print(f"Calendar URL: {calendar_url}")
            print(f"Event URL: {event_url}")
            
            self._ensure_client()
            
            print("Getting calendar and event objects...")
            calendar = self.client.calendar(url=calendar_url)
            event = calendar.event(url=event_url)
            
            # Parse existing event
            print("Parsing existing event...")
            ical = Calendar.from_ical(event.data)
            vevent = next(ical.walk('VEVENT'))
            
            # Update fields if provided
            if summary:
                print(f"Updating summary to: {summary}")
                vevent['summary'] = summary
            if description is not None:
                print(f"Updating description")
                vevent['description'] = description
            if location is not None:
                print(f"Updating location to: {location}")
                vevent['location'] = location
            if start_time:
                print(f"Updating start time to: {start_time}")
                vevent['dtstart'] = datetime.fromisoformat(start_time)
            if end_time:
                print(f"Updating end time to: {end_time}")
                vevent['dtend'] = datetime.fromisoformat(end_time)
            
            # Save updated event
            print("Saving updated event...")
            event.data = ical.to_ical()
            
            return json.dumps({
                'status': 'success',
                'message': 'Event updated successfully'
            }, indent=2)
        except Exception as e:
            error_msg = f"Error updating event: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg

    def delete_event(self, calendar_url: str, event_url: str) -> str:
        """
        Delete a calendar event
        
        :param calendar_url: URL of the calendar containing the event
        :param event_url: URL of the event to delete
        :return: A formatted string indicating success or failure
        """
        try:
            print("\n=== DELETE EVENT START ===")
            print(f"Calendar URL: {calendar_url}")
            print(f"Event URL: {event_url}")
            
            self._ensure_client()
            
            print("Getting calendar and event objects...")
            calendar = self.client.calendar(url=calendar_url)
            event = calendar.event(url=event_url)
            
            print("Deleting event...")
            event.delete()
            print("Event deleted successfully")
            
            return json.dumps({
                'status': 'success',
                'message': 'Event deleted successfully'
            }, indent=2)
        except Exception as e:
            error_msg = f"Error deleting event: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg
        
    def search_events(self, calendar_url: str, query: str) -> str:
        """
        Search for events in a calendar
        
        :param calendar_url: URL of the calendar to search in
        :param query: Search query string
        :return: A formatted string containing the search results
        """
        try:
            print("\n=== SEARCH EVENTS START ===")
            print(f"Calendar URL: {calendar_url}")
            print(f"Search query: {query}")
            
            self._ensure_client()
            
            print("Getting calendar object...")
            calendar = self.client.calendar(url=calendar_url)
            
            print("Performing search...")
            events = calendar.search(query)
            print(f"Found {len(events)} matching events")
            
            results = []
            for event in events:
                try:
                    ical = Calendar.from_ical(event.data)
                    for component in ical.walk('VEVENT'):
                        event_info = {
                            'summary': str(component.get('summary', 'No Title')),
                            'start': component.get('dtstart').dt.isoformat() if component.get('dtstart') else None,
                            'end': component.get('dtend').dt.isoformat() if component.get('dtend') else None,
                            'description': str(component.get('description', '')),
                            'url': str(event.url)
                        }
                        print(f"Found matching event: {event_info['summary']}")
                        results.append(event_info)
                except Exception as event_error:
                    print(f"Error processing event: {str(event_error)}")
                    # Continue processing other events even if one fails
                    continue
            
            print("=== SEARCH EVENTS END ===\n")
            return json.dumps(results, indent=2)
            
        except Exception as e:
            error_msg = f"Error searching events: {str(e)}"
            print(f"ERROR: {error_msg}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status}")
                print(f"Response headers: {e.response.headers}")
            return error_msg
