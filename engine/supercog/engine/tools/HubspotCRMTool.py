from supercog.engine.tool_factory import ToolFactory, ToolCategory, TOOL_REGISTRY
from typing import List, Callable, Optional, Dict, Any
import json
from hubspot import HubSpot
from hubspot.crm.deals     import ApiException as DealsApiException
from hubspot.crm.tickets   import ApiException as TicketsApiException
from hubspot.crm.companies import ApiException as CompaniesApiException
from hubspot.crm.contacts  import ApiException as ContactsApiException
from hubspot.crm.objects   import SimplePublicObjectInput, ApiException
from hubspot.crm.objects   import PublicObjectSearchRequest
from datetime import datetime, timedelta

class HubspotCRMTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="hubspot_crm_tool",
            system_name="Hubspot",
            logo_url="https://logo.clearbit.com/hubspot.com",
            category=ToolCategory.CATEGORY_SAAS,
            help="""
Use this tool to interact with HubSpot CRM, view email engagement
statistics, perform batch operations on companies, and retrieve contacts
""",
            auth_config={
                "strategy_token": {
                    "hubspot_access_token": "HubSpot Private App Access Token",
                    "help": """
Create a private app in HubSpot and generate an access token. 
Set the access token value here."""
                },
            }
        )
        self._hubspot_client = None

    def get_tools(self) -> List[Callable]:
        """
        Wraps the tool functions
        :return: A list of callable functions that the tool provides.
        """
        return self.wrap_tool_functions([
            self.get_recent_email_engagements,
            self.get_email_engagement_stats,
            self.get_all_companies,
            self.get_all_contacts,
            
            self.search_companies,
            self.search_contacts,
            self.search_deals,
            self.search_tickets,
            
            self.upsert_company,
            self.upsert_contact,
            self.upsert_ticket,
            self.upsert_deal,
        ])

    def _ensure_hubspot_client(self):
        """
        Ensures that the HubSpot client is initialized.
        """
        if self._hubspot_client is None:
            access_token = self.credentials.get("hubspot_access_token")
            if not access_token:
                raise ValueError("HubSpot access token is not set in the auth_config.")
            self._hubspot_client = HubSpot(access_token=access_token)
        return self._hubspot_client

    def get_recent_email_engagements(self, limit: int = 20) -> str:
        """
        Retrieves recent email-related engagements from HubSpot.

        :param limit: Number of recent engagements to retrieve (default is 20)
        :return: A JSON string containing recent email engagement data
        """
        try:
            client = self._ensure_hubspot_client()
            
            search_request = PublicObjectSearchRequest(
                sorts=[{"propertyName": "hs_timestamp", "direction": "DESCENDING"}],
                properties=["hs_email_direction", "hs_email_status", "hs_email_subject", "hs_timestamp"],
                limit=min(limit, 200)  # Ensure we don't exceed the API limit
            )
            
            engagements = client.crm.objects.search_api.do_search("emails", public_object_search_request=search_request)

            formatted_engagements = [{
                "id": engagement.id,
                "type": engagement.properties.get("hs_email_direction"),
                "status": engagement.properties.get("hs_email_status"),
                "subject": engagement.properties.get("hs_email_subject"),
                "timestamp": engagement.properties.get("hs_timestamp")
            } for engagement in engagements.results]

            return json.dumps(formatted_engagements, indent=2)
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ObjectsApiException as e:
            return json.dumps({"error": f"Failed to retrieve recent email engagements: {str(e)}"})

    def get_email_engagement_stats(self, days: int = 30) -> str:
        """
        Retrieves email engagement statistics from HubSpot for a specified number of days.

        :param days: Number of days to look back for statistics (default is 30)
        :return: A JSON string containing email engagement statistics
        """
        try:
            client = self._ensure_hubspot_client()
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            start_timestamp = int(start_date.timestamp() * 1000)
            end_timestamp = int(end_date.timestamp() * 1000)

            stats = {
                "total": 0,
                "sent": 0,
                "opened": 0,
                "clicked": 0,
                "bounced": 0
            }

            after = 0
            while True:
                search_request = PublicObjectSearchRequest(
                    filter_groups=[
                        {
                            "filters": [
                                {
                                    "propertyName": "hs_timestamp",
                                    "operator": "GTE",
                                    "value": str(start_timestamp)
                                },
                                {
                                    "propertyName": "hs_timestamp",
                                    "operator": "LTE",
                                    "value": str(end_timestamp)
                                }
                            ]
                        }
                    ],
                    properties=["hs_email_status"],
                    limit=200,
                    after=after
                )

                engagements = client.crm.objects.search_api.do_search("emails", public_object_search_request=search_request)

                for engagement in engagements.results:
                    stats["total"] += 1
                    status = engagement.properties.get("hs_email_status")
                    if status == "SENT":
                        stats["sent"] += 1
                    elif status == "OPEN":
                        stats["opened"] += 1
                    elif status == "CLICKED":
                        stats["clicked"] += 1
                    elif status == "BOUNCED":
                        stats["bounced"] += 1

                if not engagements.paging or not engagements.paging.next.after:
                    break

                after = engagements.paging.next.after

            return json.dumps({
                "period": f"Last {days} days",
                "total_emails": stats["total"],
                "sent": stats["sent"],
                "opened": stats["opened"],
                "clicked": stats["clicked"],
                "bounced": stats["bounced"],
                "open_rate": f"{(stats['opened'] / stats['sent'] * 100):.2f}%" if stats['sent'] > 0 else "0%",
                "click_rate": f"{(stats['clicked'] / stats['opened'] * 100):.2f}%" if stats['opened'] > 0 else "0%",
                "bounce_rate": f"{(stats['bounced'] / stats['sent'] * 100):.2f}%" if stats['sent'] > 0 else "0%"
            }, indent=2)
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ObjectsApiException as e:
            return json.dumps({"error": f"Failed to retrieve email engagement stats: {str(e)}"})

    def search_companies(
        self, 
        search_inputs: List[Dict[str, str]],
        properties: Optional[List[str]] = None,
        properties_with_history: Optional[List[str]] = None,
        archived: bool = False
    ) -> str:
        """
        Searches for companies using flexible criteria and retrieves specified properties.

        :param search_inputs: List of dictionaries, each containing property-value pairs to search for.
                              Example: [{"domain": "company1.com"}, {"hs_object_id": "1234"}, {"name": "Company XYZ"}]
        :param properties: List of properties to retrieve for each company (optional)
        :param properties_with_history: List of properties to retrieve with their change history (optional)
        :param archived: Whether to include archived companies in the search (optional, default False)
        :return: A JSON string containing the search results
        """
        try:
            client = self._ensure_hubspot_client()
            
            all_results = []
            
            for search_input in search_inputs:
                filters = []
                for prop, value in search_input.items():
                    filters.append({
                        "propertyName": prop,
                        "operator": "EQ",
                        "value": value
                    })
                
                if archived:
                    filters.append({
                        "propertyName": "archived",
                        "operator": "EQ",
                        "value": "true"
                    })
                
                search_request = PublicObjectSearchRequest(
                    filter_groups=[{"filters": filters}],
                    properties=properties or [],
                    limit=1
                )
                
                search_result = client.crm.companies.search_api.do_search(public_object_search_request=search_request)
                
                if search_result.results:
                    company = search_result.results[0]
                    formatted_result = {
                        "id": company.id,
                        "properties": company.properties,
                        "created_at": company.created_at.isoformat() if company.created_at else None,
                        "updated_at": company.updated_at.isoformat() if company.updated_at else None,
                        "archived": company.archived
                    }
                    
                    # Fetch properties with history if requested
                    if properties_with_history:
                        history_result = client.crm.companies.basic_api.get_by_id(
                            company_id=company.id,
                            properties=properties_with_history,
                            properties_with_history=properties_with_history,
                            archived=archived
                        )
                        formatted_result["properties_with_history"] = history_result.properties_with_history
                    
                    all_results.append(formatted_result)
                else:
                    all_results.append({
                        "error": f"No company found for criteria: {search_input}"
                    })
            
            return json.dumps(all_results, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except CompaniesApiException as e:
            return json.dumps({"error": f"Failed to search companies: {str(e)}"})


    def get_all_companies(self, properties: Optional[List[str]] = None, limit: int = 100) -> str:
        """
        Retrieves all companies from the HubSpot account.

        :param properties: List of company properties to retrieve (optional)
        :param limit: Maximum number of companies to retrieve (default is 100, use 0 for all)
        :return: A JSON string containing the list of companies
        """
        try:
            client = self._ensure_hubspot_client()
            
            all_companies = []
            after = None
            while True:
                companies_page = client.crm.companies.basic_api.get_page(
                    limit=100,  # HubSpot's max page size
                    after=after,
                    properties=properties,
                    archived=False
                )
                
                all_companies.extend([
                    {
                        "id": company.id,
                        "properties": company.properties,
                        "created_at": company.created_at.isoformat() if company.created_at else None,
                        "updated_at": company.updated_at.isoformat() if company.updated_at else None
                    } for company in companies_page.results
                ])
                
                if not companies_page.paging or not companies_page.paging.next:
                    break
                
                after = companies_page.paging.next.after

                if limit > 0 and len(all_companies) >= limit:
                    all_companies = all_companies[:limit]
                    break

            return json.dumps(all_companies, indent=2)

        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except CompaniesApiException as e:
            return json.dumps({"error": f"Failed to retrieve companies: {str(e)}"})


    def get_all_contacts(self, limit: int = 100, properties: List[str] = None) -> str:
        """
        Retrieves all contacts from HubSpot, up to the specified limit.

        :param limit: The maximum number of contacts to retrieve (default is 100)
        :param properties: A list of contact properties to retrieve (default is None, which retrieves all properties)
        :return: A JSON string containing the list of contacts
        """
        try:
            client = self._ensure_hubspot_client()
            
            all_contacts = []
            after = None
            while len(all_contacts) < limit:
                contacts_page = client.crm.contacts.basic_api.get_page(
                    limit=min(100, limit - len(all_contacts)),  # HubSpot's max page size is 100
                    after=after,
                    properties=properties
                )
                
                all_contacts.extend([
                    {
                        "id": contact.id,
                        "properties": contact.properties,
                        "created_at": contact.created_at.isoformat() if contact.created_at else None,
                        "updated_at": contact.updated_at.isoformat() if contact.updated_at else None
                    } for contact in contacts_page.results
                ])
                
                if not contacts_page.paging or not contacts_page.paging.next:
                    break
                
                after = contacts_page.paging.next.after

            return json.dumps(all_contacts[:limit], indent=2)

        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ContactsApiException as e:
            return json.dumps({"error": f"Failed to retrieve contacts: {str(e)}"})

    def search_contacts(
        self, 
        search_inputs: List[Dict[str, str]],
        properties: Optional[List[str]] = None,
        properties_with_history: Optional[List[str]] = None,
        limit: int = 100,
        archived: bool = False
    ) -> str:
        """
        Searches for contacts using flexible criteria and retrieves specified properties.

        :param search_inputs: List of dictionaries, each containing property-value pairs to search for.
                              Example: [{"email": "john@example.com"}, {"hs_object_id": "1234"}, {"firstname": "John"}]
        :param properties: List of properties to retrieve for each contact (optional)
        :param properties_with_history: List of properties to retrieve with their change history (optional)
        :param limit: Maximum number of contacts to return per search input (default is 100, use 0 for all)
        :param archived: Whether to include archived contacts in the search (optional, default False)
        :return: A JSON string containing the search results
        """
        try:
            client = self._ensure_hubspot_client()
            
            all_results = []
            
            for search_input in search_inputs:
                filters = []
                for prop, value in search_input.items():
                    filters.append({
                        "propertyName": prop,
                        "operator": "EQ",
                        "value": value
                    })
                
                if archived:
                    filters.append({
                        "propertyName": "archived",
                        "operator": "EQ",
                        "value": "true"
                    })
                
                search_request = PublicObjectSearchRequest(
                    filter_groups=[{"filters": filters}],
                    properties=properties or [],
                    limit=100  # Max limit per page
                )
                
                contacts_found = []
                after = None
                while True:
                    search_request.after = after
                    search_result = client.crm.contacts.search_api.do_search(public_object_search_request=search_request)
                    
                    for contact in search_result.results:
                        formatted_result = {
                            "id": contact.id,
                            "properties": contact.properties,
                            "created_at": contact.created_at.isoformat() if contact.created_at else None,
                            "updated_at": contact.updated_at.isoformat() if contact.updated_at else None,
                            "archived": contact.archived
                        }
                        
                        # Fetch properties with history if requested
                        if properties_with_history:
                            history_result = client.crm.contacts.basic_api.get_by_id(
                                contact_id=contact.id,
                                properties=properties_with_history,
                                properties_with_history=properties_with_history,
                                archived=archived
                            )
                            formatted_result["properties_with_history"] = history_result.properties_with_history
                        
                        contacts_found.append(formatted_result)
                    
                    if not search_result.paging or not search_result.paging.next.after:
                        break
                    
                    after = search_result.paging.next.after
                    
                    if limit > 0 and len(contacts_found) >= limit:
                        contacts_found = contacts_found[:limit]
                        break
                
                if contacts_found:
                    all_results.append({
                        "search_criteria": search_input,
                        "contacts_found": contacts_found,
                        "total_found": len(contacts_found)
                    })
                else:
                    all_results.append({
                        "search_criteria": search_input,
                        "error": "No contacts found for this criteria",
                        "total_found": 0
                    })
            
            return json.dumps(all_results, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ContactsApiException as e:
            return json.dumps({"error": f"Failed to search contacts: {str(e)}"})

    def search_deals(self, 
                     filter_groups: Optional[List[Dict[str, Any]]] = None, 
                     properties: Optional[List[str]] = None, 
                     limit: int = 100, 
                     after: Optional[str] = None,
                     sorts: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Searches for deals in HubSpot based on the provided criteria.

        :param filter_groups: List of filter groups to apply in the search
        :param properties: List of deal properties to retrieve
        :param limit: Maximum number of deals to retrieve (default is 100)
        :param after: The paging cursor token of the last successfully read resource
        :param sorts: List of sort criteria to apply to the results
        :return: A JSON string containing the list of deals matching the search criteria
        """
        try:
            client = self._ensure_hubspot_client()

            search_request = PublicObjectSearchRequest(
                filter_groups=filter_groups or [],
                properties=properties or [],
                limit=limit,
                after=after,
                sorts=sorts or []
            )

            deals_page = client.crm.deals.search_api.do_search(
                public_object_search_request=search_request
            )

            formatted_deals = [{
                "id": deal.id,
                "properties": deal.properties,
                "created_at": deal.created_at.isoformat() if deal.created_at else None,
                "updated_at": deal.updated_at.isoformat() if deal.updated_at else None
            } for deal in deals_page.results]

            result = {
                "deals": formatted_deals,
                "paging": {
                    "next": deals_page.paging.next.after if deals_page.paging and deals_page.paging.next else None
                }
            }

            return json.dumps(result, indent=2)

        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except DealsApiException as e:
            return json.dumps({"error": f"Failed to search deals: {str(e)}"})

    def search_tickets(self, 
                       filter_groups: Optional[List[Dict[str, Any]]] = None, 
                       properties: Optional[List[str]] = None, 
                       limit: int = 100, 
                       after: Optional[str] = None,
                       sorts: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Searches for tickets in HubSpot based on the provided criteria.

        :param filter_groups: List of filter groups to apply in the search
        :param properties: List of ticket properties to retrieve
        :param limit: Maximum number of tickets to retrieve (default is 100)
        :param after: The paging cursor token of the last successfully read resource
        :param sorts: List of sort criteria to apply to the results
        :return: A JSON string containing the list of tickets matching the search criteria
        """
        try:
            client = self._ensure_hubspot_client()

            search_request = PublicObjectSearchRequest(
                filter_groups=filter_groups or [],
                properties=properties or [],
                limit=limit,
                after=after,
                sorts=sorts or []
            )

            tickets_page = client.crm.tickets.search_api.do_search(
                public_object_search_request=search_request
            )

            formatted_tickets = [{
                "id": ticket.id,
                "properties": ticket.properties,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None
            } for ticket in tickets_page.results]

            result = {
                "tickets": formatted_tickets,
                "paging": {
                    "next": tickets_page.paging.next.after if tickets_page.paging and tickets_page.paging.next else None
                }
            }

            return json.dumps(result, indent=2)

        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except TicketsApiException as e:
            return json.dumps({"error": f"Failed to search tickets: {str(e)}"})

    def upsert_company(self, properties: Dict[str, Any], unique_property: str = "domain") -> str:
        """
        Creates a new company or updates an existing one in HubSpot.

        :param properties: Dictionary of company properties
        :param unique_property: The property to use for identifying existing companies (default is "domain")
        :return: A JSON string containing the created or updated company data
        """
        try:
            client = self._ensure_hubspot_client()
            
            # Check if the company exists
            search_request = PublicObjectSearchRequest(
                filter_groups=[
                    {
                        "filters": [
                            {
                                "propertyName": unique_property,
                                "operator": "EQ",
                                "value": properties.get(unique_property)
                            }
                        ]
                    }
                ],
                limit=1
            )
            search_result = client.crm.companies.search_api.do_search(public_object_search_request=search_request)

            company_input = SimplePublicObjectInput(properties=properties)

            if search_result.results:
                # Update existing company
                company_id = search_result.results[0].id
                print(f"Found existing company {company_id} doing an update")
                updated_company = client.crm.companies.basic_api.update(company_id=company_id, simple_public_object_input=company_input)
                action = "updated"
            else:
                # Create new company
                print(f"Unable to find  company {search_request} doing an insert")
                updated_company = client.crm.companies.basic_api.create(simple_public_object_input_for_create=company_input)
                action = "created"
            
            result = {
                "action": action,
                "id": updated_company.id,
                "properties": updated_company.properties,
                "created_at": updated_company.created_at.isoformat() if updated_company.created_at else None,
                "updated_at": updated_company.updated_at.isoformat() if updated_company.updated_at else None
            }
            
            return json.dumps(result, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ApiException as e:
            return json.dumps({"error": f"Failed to upsert company: {str(e)}"})

    def upsert_contact(self, properties: Dict[str, Any], unique_property: str = "email") -> str:
        """
        Creates a new contact or updates an existing one in HubSpot.

        :param properties: Dictionary of contact properties
        :param unique_property: The property to use for identifying existing contacts (default is "email")
        :return: A JSON string containing the created or updated contact data
        """
        try:
            client = self._ensure_hubspot_client()
            
            # Check if the contact exists
            search_request = PublicObjectSearchRequest(
                filter_groups=[
                    {
                        "filters": [
                            {
                                "propertyName": unique_property,
                                "operator": "EQ",
                                "value": properties.get(unique_property)
                            }
                        ]
                    }
                ],
                limit=1
            )
            search_result = client.crm.contacts.search_api.do_search(public_object_search_request=search_request)

            contact_input = SimplePublicObjectInput(properties=properties)

            if search_result.results:
                # Update existing contact
                contact_id = search_result.results[0].id
                updated_contact = client.crm.contacts.basic_api.update(contact_id=contact_id, simple_public_object_input=contact_input)
                action = "updated"
            else:
                # Create new contact
                updated_contact = client.crm.contacts.basic_api.create(simple_public_object_input_for_create=contact_input)
                action = "created"
            
            result = {
                "action": action,
                "id": updated_contact.id,
                "properties": updated_contact.properties,
                "created_at": updated_contact.created_at.isoformat() if updated_contact.created_at else None,
                "updated_at": updated_contact.updated_at.isoformat() if updated_contact.updated_at else None
            }
            
            return json.dumps(result, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ApiException as e:
            return json.dumps({"error": f"Failed to upsert contact: {str(e)}"})

    def upsert_ticket(self, properties: Dict[str, Any], unique_property: str = "subject") -> str:
        """
        Creates a new ticket or updates an existing one in HubSpot.

        :param properties: Dictionary of ticket properties
        :param unique_property: The property to use for identifying existing tickets (default is "subject")
        :return: A JSON string containing the created or updated ticket data
        """
        try:
            client = self._ensure_hubspot_client()
            
            # Check if the ticket exists
            search_request = PublicObjectSearchRequest(
                filter_groups=[
                    {
                        "filters": [
                            {
                                "propertyName": unique_property,
                                "operator": "EQ",
                                "value": properties.get(unique_property)
                            }
                        ]
                    }
                ],
                limit=1
            )
            search_result = client.crm.tickets.search_api.do_search(public_object_search_request=search_request)

            ticket_input = SimplePublicObjectInput(properties=properties)

            if search_result.results:
                # Update existing ticket
                ticket_id = search_result.results[0].id
                updated_ticket = client.crm.tickets.basic_api.update(ticket_id=ticket_id, simple_public_object_input=ticket_input)
                action = "updated"
            else:
                # Create new ticket
                updated_ticket = client.crm.tickets.basic_api.create(simple_public_object_input_for_create=ticket_input)
                action = "created"
            
            result = {
                "action": action,
                "id": updated_ticket.id,
                "properties": updated_ticket.properties,
                "created_at": updated_ticket.created_at.isoformat() if updated_ticket.created_at else None,
                "updated_at": updated_ticket.updated_at.isoformat() if updated_ticket.updated_at else None
            }
            
            return json.dumps(result, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ApiException as e:
            return json.dumps({"error": f"Failed to upsert ticket: {str(e)}"})

    def upsert_deal(self, properties: Dict[str, Any], unique_property: str = "dealname") -> str:
        """
        Creates a new deal or updates an existing one in HubSpot.

        :param properties: Dictionary of deal properties
        :param unique_property: The property to use for identifying existing deals (default is "dealname")
        :return: A JSON string containing the created or updated deal data
        """
        try:
            client = self._ensure_hubspot_client()
            
            # Check if the deal exists
            search_request = PublicObjectSearchRequest(
                filter_groups=[
                    {
                        "filters": [
                            {
                                "propertyName": unique_property,
                                "operator": "EQ",
                                "value": properties.get(unique_property)
                            }
                        ]
                    }
                ],
                limit=1
            )
            search_result = client.crm.deals.search_api.do_search(public_object_search_request=search_request)

            deal_input = SimplePublicObjectInput(properties=properties)

            if search_result.results:
                # Update existing deal
                deal_id = search_result.results[0].id
                updated_deal = client.crm.deals.basic_api.update(deal_id=deal_id, simple_public_object_input=deal_input)
                action = "updated"
            else:
                # Create new deal
                updated_deal = client.crm.deals.basic_api.create(simple_public_object_input_for_create=deal_input)
                action = "created"
            
            result = {
                "action": action,
                "id": updated_deal.id,
                "properties": updated_deal.properties,
                "created_at": updated_deal.created_at.isoformat() if updated_deal.created_at else None,
                "updated_at": updated_deal.updated_at.isoformat() if updated_deal.updated_at else None
            }
            
            return json.dumps(result, indent=2)
        
        except ValueError as e:
            return json.dumps({"error": f"Authentication failed: {str(e)}"})
        except ApiException as e:
            return json.dumps({"error": f"Failed to upsert deal: {str(e)}"})
