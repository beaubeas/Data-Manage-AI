from supercog.engine.tool_factory import ToolFactory, ToolCategory
import json
import time
from bs4 import BeautifulSoup
import requests
from pprint import pprint

from typing import Any, Callable, Optional

from zapv2 import ZAPv2
import traceback

class ZapTool(ToolFactory):
    api_key: str=""
    zap_port: str=""
    zap: ZAPv2  = None
    
    class Config:
        arbitrary_types_allowed = True
        
    def __init__(self):
        super().__init__(
            id = "zap_connector",
            system_name = "zap",
            logo_url=super().logo_from_domain('zaproxy.org'),
            auth_config = {
                "strategy_token": {
                    "api_key":  "API KEY - set and find this in the app under tools-.options->API key",
                    "zap_port":     "The local  port that zap is configured to in options->network->local proxy",
                    "help": """
Create this in the app under tools-.options->API key and set the value here."""
               
                }
            },
            category=ToolCategory.CATEGORY_SECURITY,
            help="""
Use this tool to test the security of web applications.
"""
        )
    
    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.zap_scan,
            self.get_high_risk_alerts,
            self.get_medium_risk_alerts,
        ])
                                        
    @staticmethod
    def summarize_alerts(alerts):
        """ Summarize alerts by risk levels """
        summary = {
            'High': 0,
            'Medium': 0,
            'Low': 0,
            'Informational': 0,
            'Total': len(alerts)
        }
        for alert in alerts:
            risk = alert.get('risk', 'Informational')
            summary[risk] += 1

        return summary

    @staticmethod
    def summary_of_alerts(alerts):
        # Example summarization function; modify as needed
        summary = []
        for alert in alerts:
            summary.append({
                'sourceid': alert['sourceid'],
                'pluginId': alert['pluginId'],
                'risk': alert['risk'],
                'description': alert['description'],
                'url': alert['url'],
            })
        return summary

    @staticmethod
    def generate_report(file_path, findings):
        """ Convert findings to a JSON string for a readable format """
        findings_json = json.dumps(findings, indent=4)
    
        # Write the JSON string to the specified file path
        with open(file_path, 'w') as file:
            file.write(findings_json)

    def get_high_risk_alerts(self, count=None):
        """
        Return a JSON string with the high risk alerts.

        Args:
            count (int, optional): The number of alerts to retrieve. Defaults to 20 if not specified.

        Returns:
            str: A JSON-formatted string of alerts with high risk.
        """
        # Initialize ZAP connection if not already done
        if self.zap is None:
            self.api_key = self.credentials['api_key']
            self.zap_port = self.credentials['zap_port']
            self.zap = ZAPv2(apikey=self.api_key, proxies={
                'http': f'http://127.0.0.1:{self.zap_port}',
                'https': f'http://127.0.0.1:{self.zap_port}'
            })

        if count is None:
            count = 20  # Set default count if None is provided

        alerts = self.zap.core.alerts(start=0, count=5000)  # Get all alerts to filter through

        # Ensuring the risk level check is case-insensitive and matches 'High'
        high_risk_alerts = [alert for alert in alerts if alert.get('risk', '').lower() == 'high']
        
        # Limit to requested count after filtering
        if count:
            high_risk_alerts = high_risk_alerts[:count]
            
        high_risk_alerts_str = json.dumps(high_risk_alerts, indent=4)
        return high_risk_alerts_str

    def get_medium_risk_alerts(self, count=None):
        """
        Return a JSON string with the medium risk alerts.

        Args:
            count (int, optional): The number of alerts to retrieve. Defaults to 20 if not specified.

        Returns:
            str: A JSON-formatted string of alerts with medium risk.
        """
        # Initialize ZAP connection if not already done
        if self.zap is None:
            self.api_key = self.credentials['api_key']
            self.zap_port = self.credentials['zap_port']
            self.zap = ZAPv2(apikey=self.api_key, proxies={
                'http': f'http://127.0.0.1:{self.zap_port}',
                'https': f'http://127.0.0.1:{self.zap_port}'
            })

        if count is None:
            count = 20  # Set default count if None is provided

        alerts = self.zap.core.alerts(start=0, count=5000)  # Get all alerts to filter through

        # Ensuring the risk level check is case-insensitive and matches 'Medium'
        medium_risk_alerts = [alert for alert in alerts if alert.get('risk', '').lower() == 'medium']
        
        # Limit to requested count after filtering
        if count:
            medium_risk_alerts = medium_risk_alerts[:count]
            
        # Print for debugging
        print(f"Found {len(medium_risk_alerts)} medium risk alerts")
        if medium_risk_alerts:
            print("First medium risk alert sample:", json.dumps(medium_risk_alerts[0], indent=2))
            
        medium_risk_alerts_str = json.dumps(medium_risk_alerts, indent=4)
        return medium_risk_alerts_str

    def zap_scan(self, target: str) -> str:
        """
        Initiates a comprehensive security scan on the specified target using OWASP ZAP,
        performing spidering, passive scanning, and active scanning processes.

        This function executes a full security assessment by:
        1. Creating a context and setting the target scope
        2. Spidering the target URL to gather site structure
        3. Running passive scans on discovered URLs
        4. Performing active scans using the default policy
        
        Args:
            target (str): The URL of the web application to be scanned.
            
        Returns:
            str: A summary string that includes:
                - A list of hosts scanned
                - A JSON string representation of security alerts found during the scan
                - Additionally, generates a JSON report file with detailed alerts information
        """
        self.api_key = self.credentials['api_key']
        self.zap_port = self.credentials['zap_port']

        self.zap = ZAPv2(apikey=self.api_key, proxies={
            'http': f'http://127.0.0.1:{self.zap_port}',
            'https': f'http://127.0.0.1:{self.zap_port}'
        })

        print('Configuring context and scope...')
        scan_completed = False
        
        try:
            # Clear any existing contexts and create new one
            existing_contexts = self.zap.context.context_list
            for context in existing_contexts:
                if 'scan_context' in str(context):
                    self.zap.context.remove_context('scan_context')
                    
            context_id = self.zap.context.new_context('scan_context')
            print(f'Created context with ID: {context_id}')
            
            # Include target in context - make sure the regex is correct
            include_regex = f".*{target.replace('https://', '').replace('http://', '')}.*"
            self.zap.context.include_in_context('scan_context', include_regex)
            
            print(f'Accessing target {target}')
            self.zap.urlopen(target)
            time.sleep(10)  # Increased wait time to ensure page loads

            # Spider scan with better monitoring
            print(f'Starting spider scan on {target}')
            scanid = self.zap.spider.scan(
                url=target,
                maxchildren=None,  # Add this to ensure complete crawl
                contextname='scan_context'
            )
            print(f'Spider scan ID: {scanid}')
            
            # Monitor spider progress
            start_time = time.time()
            last_progress = 0
            while int(time.time() - start_time) < 600:
                status = self.zap.spider.status(scanid)
                if not status.isdigit():
                    print(f"Spider returned invalid status: {status}")
                    break
                    
                progress = int(status)
                if progress > last_progress:
                    print(f'Spider progress: {progress}%')
                    urls = self.zap.spider.all_urls
                    print(f'URLs found: {len(urls)}')
                    if len(urls) > 0:
                        print(f'Sample URLs: {urls[:3]}')  # Print first 3 URLs for verification
                    last_progress = progress
                    
                if progress >= 100:
                    print('Spider completed')
                    break
                time.sleep(5)

            # Passive scan monitoring
            print('Monitoring passive scan')
            while int(time.time() - start_time) < 600:
                records = int(self.zap.pscan.records_to_scan)
                if records > 0:
                    print(f'Records to scan: {records}')
                    time.sleep(5)
                else:
                    print('Passive scan completed')
                    break

            # Active scan with corrected parameters
            print('Starting active scan...')
            try:
                # First verify the policy exists
                policies = self.zap.ascan.scan_policy_names
                print(f'Available scan policies: {policies}')
                
                ascan_id = self.zap.ascan.scan(
                    url=target,
                    recurse=True,
                    inscopeonly=True,  # Only scan URLs in scope
                    scanpolicyname=None,  # Use default policy for now
                    contextid=context_id
                )
                
                if not str(ascan_id).isdigit():
                    print(f"Warning: Unexpected scan ID format: {ascan_id}")
                    return f"Active scan failed to start properly: {ascan_id}"
                    
                print(f'Active scan ID: {ascan_id}')

                # Monitor active scan with more detailed progress
                while int(time.time() - start_time) < 1800:
                    status = self.zap.ascan.status(ascan_id)
                    progress = self.zap.ascan.scan_progress(ascan_id)
                    
                    if not status.isdigit():
                        print(f"Active scan returned invalid status: {status}")
                        break
                        
                    status_int = int(status)
                    print(f'Active scan status: {status_int}%')
                    print(f'Scan progress details: {progress}')
                    
                    if status_int >= 100:
                        print('Active scan completed')
                        scan_completed = True
                        break
                        
                    current_alerts = len(self.zap.core.alerts())
                    print(f'Current alert count: {current_alerts}')
                    time.sleep(10)

            except Exception as e:
                print(f"Error during active scan: {str(e)}")
                traceback.print_exc()

            # Generate results only if scan completed
            if scan_completed:
                hosts = [host for host in self.zap.core.hosts if host is not None]
                return_string = 'Hosts: {}'.format(', '.join(hosts))
                
                # Get alerts with more detailed filtering
                alerts = self.zap.core.alerts(baseurl=target, start=0, count=5000)
                
                # Print some sample alerts for debugging
                if alerts:
                    print(f"Sample alert: {json.dumps(alerts[0], indent=2)}")
                    
                alerts_summary = ZapTool.summarize_alerts(alerts)
                alerts_summary_str = json.dumps(alerts_summary, indent=4)
                summary = ZapTool.summary_of_alerts(alerts)
                summary_str = json.dumps(summary, indent=4)
                
                ZapTool.generate_report('zap_scan_report.json', summary_str)
                
                return return_string + '\n' + alerts_summary_str
            else:
                return "Scan did not complete successfully"

        except Exception as e:
            print(f"An error occurred during the scan: {str(e)}")
            traceback.print_exc()
            return f"Scan failed with error: {str(e)}"
