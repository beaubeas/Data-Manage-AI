from supercog.engine.tool_factory import ToolFactory, ToolCategory
from typing import List, Callable, Optional, Dict
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from supercog.shared.services import config
import json
from .gmail_tool import GAuthCommon
import pandas as pd


SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'openid'
]

class GoogleCalendarTool(ToolFactory, GAuthCommon):
    """Google Calendar API integration tool."""
    
    def __init__(self):
        """Initialize the Google Calendar tool with proper OAuth configuration."""
        super().__init__(
            id="google_calendar_connector",
            system_name="Google Calendar",
            logo_url=self.logo_from_domain("google.com"),
            category=ToolCategory.CATEGORY_CALENDAR,
            help="Use this tool to manage Google Calendar events",
            auth_config={
                "strategy_oauth": {
                    "help": "Login to Google to connect your calendar."
                }
            },
            oauth_scopes=SCOPES,
        )

    def get_scopes(self) -> list[str]:
        """Return the OAuth scopes required by this tool."""
        return SCOPES

    def get_tools(self) -> List[Callable]:
        """Return the list of available calendar tools."""
        return self.wrap_tool_functions([
            self.list_upcoming_events,
            self.get_events_by_date_range,
            self.create_event,
            self.update_event,
            self.get_event_details,
            self.get_attendee_status,
            self.count_events_in_range,
        ])

    def count_events_in_range(self,
                            start_date: str,
                            end_date: str,
                            group_by: str = "none",
                            calendar_id: str = 'primary') -> Dict:
        """
        Count events within a specific date range, with grouping of "none", "daily", "weekly", "monthly"
        
        Args:
            start_date (str): Start date in ISO format (YYYY-MM-DD)
            end_date (str): End date in ISO format (YYYY-MM-DD)
            group_by (str): How to group the counts. Options:
                          - "none": Simple total count (default)
                          - "daily": Count events per day
                          - "weekly": Count events per week
                          - "monthly": Count events per month
            calendar_id (str): Calendar ID to fetch events from (default: 'primary')
            
        Returns:
            Dict: Contains count information and optional breakdown
        """
        try:
            service = self.get_service()
            
            # Convert dates to datetime and add time components
            start_datetime = f"{start_date}T00:00:00Z"
            end_datetime = f"{end_date}T23:59:59Z"
            
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=start_datetime,
                timeMax=end_datetime,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return {
                    "status": "success",
                    "total_count": 0,
                    "message": f"No events found between {start_date} and {end_date}",
                }

            # Initialize response
            response = {
                "status": "success",
                "total_count": len(events),
                "date_range": f"{start_date} to {end_date}"
            }

            # Handle grouping if requested
            if group_by != "none":
                counts_by_period = {}
                
                for event in events:
                    # Get event start time
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    event_date = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    
                    # Generate the appropriate key based on grouping
                    if group_by == "daily":
                        key = event_date.strftime('%Y-%m-%d')
                    elif group_by == "weekly":
                        # Get the Monday of the week
                        monday = event_date - timedelta(days=event_date.weekday())
                        key = monday.strftime('%Y-%m-%d')
                    elif group_by == "monthly":
                        key = event_date.strftime('%Y-%m')
                    
                    counts_by_period[key] = counts_by_period.get(key, 0) + 1

                # Convert to list of dicts for DataFrame
                breakdown_data = [
                    {"period": period, "count": count}
                    for period, count in sorted(counts_by_period.items())
                ]
                
                # Create DataFrame and add to response
                df = pd.DataFrame(breakdown_data)
                df_preview = self.get_dataframe_preview(df, name_hint="event_counts")
                response["breakdown"] = df_preview
                
                # Add text summary
                response["summary"] = f"Found {len(events)} total events.\n\n"
                for period, count in sorted(counts_by_period.items()):
                    response["summary"] += f"{period}: {count} events\n"

            return response
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error counting events: {str(e)}",
            }

    def get_oauth_client_id_and_secret(self) -> tuple[str|None, str|None]:
        """Return the OAuth client credentials from global config."""
        return config.get_global("GCAL_CLIENT_ID"), config.get_global("GCAL_CLIENT_SECRET")

    def get_service(self):
        """Get an authorized Google Calendar service instance."""
        tokens = self.credentials['tokens']
        if isinstance(tokens, str):
            tokens = json.loads(tokens)
        return build(
            'calendar', 
            'v3',
            credentials=GoogleCalendarTool.setup_credentials(
                tokens, 
                SCOPES, 
                self.get_oauth_client_id_and_secret(),
            )
        )

    def format_event_details(self, event: dict) -> str:
        """Helper method to format event details including attendees."""
        result = f"- {event.get('summary', 'No title')}\n"
        
        # Start and end times
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        result += f"  Time: {start} to {end}\n"
        
        # Location
        if 'location' in event:
            result += f"  Location: {event['location']}\n"
            
        # Description
        if 'description' in event:
            result += f"  Description: {event['description']}\n"
            
        # Organizer
        if 'organizer' in event:
            result += f"  Organizer: {event['organizer'].get('email', 'Unknown')}\n"
            
        # Attendees
        if 'attendees' in event:
            result += "  Attendees:\n"
            for attendee in event['attendees']:
                email = attendee.get('email', 'No email')
                response = attendee.get('responseStatus', 'No response')
                optional = ' (Optional)' if attendee.get('optional', False) else ''
                result += f"    - {email}: {response}{optional}\n"
        
        # Meeting link
        if 'conferenceData' in event:
            for entry in event.get('conferenceData', {}).get('entryPoints', []):
                if entry.get('entryPointType') == 'video':
                    result += f"  Meeting Link: {entry.get('uri', 'No link')}\n"
        
        result += f"  Event ID: {event['id']}\n"
        return result

    def _extract_event_data(self, event: dict) -> dict:
        """Helper method to extract relevant event data for DataFrame conversion."""
        # Get start and end times
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        
        # Get meeting link if available
        meeting_link = None
        if 'conferenceData' in event:
            for entry in event.get('conferenceData', {}).get('entryPoints', []):
                if entry.get('entryPointType') == 'video':
                    meeting_link = entry.get('uri')
                    break
        
        # Get attendee counts and statuses
        attendee_info = {'accepted': 0, 'declined': 0, 'tentative': 0, 'pending': 0, 'total': 0}
        if 'attendees' in event:
            attendee_info['total'] = len(event['attendees'])
            for attendee in event['attendees']:
                status = attendee.get('responseStatus', 'needsAction')
                if status == 'accepted':
                    attendee_info['accepted'] += 1
                elif status == 'declined':
                    attendee_info['declined'] += 1
                elif status == 'tentative':
                    attendee_info['tentative'] += 1
                elif status == 'needsAction':
                    attendee_info['pending'] += 1
        
        return {
            'Event ID': event['id'],
            'Summary': event.get('summary', 'No title'),
            'Start Time': start,
            'End Time': end,
            'Location': event.get('location', ''),
            'Description': event.get('description', ''),
            'Organizer': event.get('organizer', {}).get('email', ''),
            'Meeting Link': meeting_link,
            'Total Attendees': attendee_info['total'],
            'Accepted': attendee_info['accepted'],
            'Declined': attendee_info['declined'],
            'Tentative': attendee_info['tentative'],
            'Pending Response': attendee_info['pending']
        }

    def list_upcoming_events(self, max_results: int = 10, calendar_id: str = 'primary') -> dict:
        """
        List upcoming events from the specified calendar.
        
        Args:
            max_results (int): Maximum number of events to return (default: 10)
            calendar_id (str): Calendar ID to fetch events from (default: 'primary')
            
        Returns:
            dict: Contains status, message, DataFrame preview of upcoming events, and formatted text
        """
        try:
            service = self.get_service()
            
            now = datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            if not events:
                return {
                    "status": "success",
                    "message": "No upcoming events found",
                    "dataframe": None,
                    "formatted_text": "No upcoming events found."
                }
                
            # Create formatted text version
            formatted_text = "Upcoming events:\n\n"
            for event in events:
                formatted_text += self.format_event_details(event) + "\n"
            
            # Convert events to list of dictionaries for DataFrame
            events_data = [self._extract_event_data(event) for event in events]
            
            # Create DataFrame
            df = pd.DataFrame(events_data)
            
            return {
                "status": "success",
                "message": f"Successfully retrieved {len(events)} upcoming events",
                "dataframe": self.get_dataframe_preview(df),
                "formatted_text": formatted_text
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error retrieving events: {str(e)}",
                "dataframe": None,
                "formatted_text": f"Error retrieving events: {str(e)}"
            }

    def get_events_by_date_range(self, 
                               start_date: str,
                               end_date: str,
                               calendar_id: str = 'primary') -> dict:
        """
        Get events within a specific date range.
        
        Args:
            start_date (str): Start date in ISO format (YYYY-MM-DD)
            end_date (str): End date in ISO format (YYYY-MM-DD)
            calendar_id (str): Calendar ID to fetch events from (default: 'primary')
            
        Returns:
            dict: Contains status, message, DataFrame preview of events, and formatted text
        """
        try:
            service = self.get_service()
            
            # Convert dates to datetime and add time components
            start_datetime = f"{start_date}T00:00:00Z"
            end_datetime = f"{end_date}T23:59:59Z"
            
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=start_datetime,
                timeMax=end_datetime,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            if not events:
                return {
                    "status": "success",
                    "message": f"No events found between {start_date} and {end_date}",
                    "dataframe": None,
                    "formatted_text": f"No events found between {start_date} and {end_date}."
                }
            
            # Create formatted text version
            formatted_text = f"Events from {start_date} to {end_date}:\n\n"
            for event in events:
                formatted_text += self.format_event_details(event) + "\n"
            
            # Convert events to list of dictionaries for DataFrame
            events_data = [self._extract_event_data(event) for event in events]
            
            # Create DataFrame
            df = pd.DataFrame(events_data)
            
            return {
                "status": "success",
                "message": f"Successfully retrieved {len(events)} events between {start_date} and {end_date}",
                "dataframe": self.get_dataframe_preview(df),
                "formatted_text": formatted_text
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error retrieving events: {str(e)}",
                "dataframe": None,
                "formatted_text": f"Error retrieving events: {str(e)}"
            }

    def create_event(self, 
                    summary: str,
                    start_time: str,
                    end_time: str,
                    description: str = None,
                    location: str = None,
                    attendees: List[str] = None,
                    calendar_id: str = 'primary') -> str:
        """
        Create a new calendar event.

        Args:
            summary (str): Event title
            start_time (str): Start time in ISO format. Must include timezone information either:
                             - As 'Z' suffix for UTC (e.g., "2024-11-06T09:00:00Z")
                             - As offset (e.g., "2024-11-06T09:00:00-08:00")
            end_time (str): End time in ISO format with timezone information
            description (str, optional): Event description
            location (str, optional): Event location
            attendees (List[str], optional): List of attendee email addresses
            calendar_id (str): Calendar ID to create event in (default: 'primary')

        Returns:
            str: Confirmation message with event details

        Example:
            >>> # UTC time
            >>> create_event(summary="Meeting", start_time="2024-11-06T09:00:00Z", end_time="2024-11-06T10:00:00Z")
            >>> # Pacific Time
            >>> create_event(summary="Meeting", start_time="2024-11-06T09:00:00-08:00", end_time="2024-11-06T10:00:00-08:00")
        """
        # Add 'Z' suffix for UTC if no timezone information is present
        if not any(x in start_time for x in ['Z', '+', '-']):
            start_time = f"{start_time}Z"
        if not any(x in end_time for x in ['Z', '+', '-']):
            end_time = f"{end_time}Z"

        service = self.get_service()

        event = {
            'summary': summary,
            'start': {'dateTime': start_time},
            'end': {'dateTime': end_time},
        }

        if description:
            event['description'] = description
        if location:
            event['location'] = location
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='all'
        ).execute()

        return f"Event created successfully:\n\n" + self.format_event_details(event)

    def get_event_details(self, event_id: str, calendar_id: str = 'primary') -> str:
        """
        Get detailed information about a specific event.
        
        Args:
            event_id (str): ID of the event to retrieve
            calendar_id (str): Calendar ID containing the event (default: 'primary')
            
        Returns:
            str: Formatted string containing detailed event information
        """
        service = self.get_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return self.format_event_details(event)

    def get_attendee_status(self, event_id: str, calendar_id: str = 'primary') -> str:
        """
        Get the attendance status for all attendees of a specific event.
        
        Args:
            event_id (str): ID of the event to check
            calendar_id (str): Calendar ID containing the event (default: 'primary')
            
        Returns:
            str: Formatted string containing attendee status information
        """
        service = self.get_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        if 'attendees' not in event:
            return "This event has no attendees."
            
        result = f"Attendee status for: {event.get('summary', 'No title')}\n\n"
        
        # Group attendees by response status
        status_groups = {
            'accepted': [],
            'declined': [],
            'tentative': [],
            'needsAction': [],
        }
        
        for attendee in event['attendees']:
            email = attendee.get('email', 'No email')
            status = attendee.get('responseStatus', 'needsAction')
            optional = attendee.get('optional', False)
            status_groups[status].append((email, optional))
            
        # Format the results
        if status_groups['accepted']:
            result += "Accepted:\n"
            for email, optional in status_groups['accepted']:
                result += f"  - {email}" + (" (Optional)" if optional else "") + "\n"
                
        if status_groups['tentative']:
            result += "\nTentative:\n"
            for email, optional in status_groups['tentative']:
                result += f"  - {email}" + (" (Optional)" if optional else "") + "\n"
                
        if status_groups['declined']:
            result += "\nDeclined:\n"
            for email, optional in status_groups['declined']:
                result += f"  - {email}" + (" (Optional)" if optional else "") + "\n"
                
        if status_groups['needsAction']:
            result += "\nNo Response:\n"
            for email, optional in status_groups['needsAction']:
                result += f"  - {email}" + (" (Optional)" if optional else "") + "\n"
                
        return result

    def update_event(self,
                    event_id: str,
                    summary: str = None,
                    start_time: str = None,
                    end_time: str = None,
                    description: str = None,
                    location: str = None,
                    add_attendees: List[str] = None,
                    remove_attendees: List[str] = None,
                    calendar_id: str = 'primary') -> str:
        """
        Update an existing calendar event.
        
        Args:
            event_id (str): ID of the event to update
            summary (str, optional): New event title
            start_time (str, optional): New start time in ISO format
            end_time (str, optional): New end time in ISO format
            description (str, optional): New event description
            location (str, optional): New event location
            add_attendees (List[str], optional): List of attendee emails to add
            remove_attendees (List[str], optional): List of attendee emails to remove
            calendar_id (str): Calendar ID containing the event (default: 'primary')
            
        Returns:
            str: Confirmation message
        """
        service = self.get_service()
        
        # Get the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Update basic fields
        if summary:
            event['summary'] = summary
        if start_time:
            event['start'] = {'dateTime': start_time}
        if end_time:
            event['end'] = {'dateTime': end_time}
        if description:
            event['description'] = description
        if location:
            event['location'] = location
            
        # Update attendees
        current_attendees = event.get('attendees', [])
        if remove_attendees:
            current_attendees = [
                attendee for attendee in current_attendees 
                if attendee['email'] not in remove_attendees
            ]
        if add_attendees:
            current_attendees.extend([
                {'email': email} 
                for email in add_attendees 
                if email not in [a['email'] for a in current_attendees]
            ])
        event['attendees'] = current_attendees
            
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
            sendUpdates='all'
        ).execute()
        
        return f"Event updated successfully:\n\n" + self.format_event_details(updated_event)

    def delete_event(self, event_id: str, calendar_id: str = 'primary') -> str:
        """
        Delete a calendar event.
        
        Args:
            event_id (str): ID of the event to delete
            calendar_id (str): Calendar ID containing the event (default: 'primary')
            
        Returns:
            str: Confirmation message
        """
        service = self.get_service()
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates='all'
        ).execute()
        return f"Event {event_id} deleted successfully"

    
# FIXME: Need to add a scope to support this. The scope is:
# https://www.googleapis.com/auth/calendar
# but when we added that it got rejected.
    def get_calendar_list(self) -> str:
        """
        Get a list of available calendars.
        
        Returns:
            str: Formatted string containing the list of calendars
        """
        service = self.get_service()
        calendar_list = service.calendarList().list().execute()
        
        result = "Available Calendars:\n\n"
        for calendar in calendar_list['items']:
            result += f"- {calendar['summary']}\n"
            result += f"  ID: {calendar['id']}\n"
            if 'description' in calendar:
                result += f"  Description: {calendar['description']}\n"
            result += "\n"
            
        return result
