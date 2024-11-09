from supercog.engine.tool_factory import ToolFactory, ToolCategory
from typing import Any, Callable, Optional
import nmap
import json
import os

class NmapTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="nmap_connector",
            system_name="nmap",
            logo_url=super().logo_from_domain('nmap.org'),
            auth_config={},
            category=ToolCategory.CATEGORY_SECURITY,
            help="""
Use this tool to perform advanced port scans on the target system using Nmap.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.nmap_scan,
        ])

    @staticmethod
    def nmap_scan(
        target: str,
        ports: str = '1-1000',
        scan_type: str = '-sT',  # Changed default to -sT for non-root compatibility
        os_detection: bool = False,
        version_scan: bool = False,
        script_scan: str = None,
        timing_template: int = 3,
        output_format: str = 'normal'
    ) -> dict:
        """
        Perform an advanced network scan on specified target using Nmap.
        
        Args:
            target (str): The IP address, hostname, or network range to scan.
            ports (str): The range of ports to scan (default is '1-1000').
            scan_type (str): The type of scan to perform (e.g., '-sT' for TCP connect scan, '-sS' for SYN scan [requires root]).
            os_detection (bool): Enable OS detection.
            version_scan (bool): Enable version scanning.
            script_scan (str): Specify Nmap scripts to run (e.g., 'default', 'vuln', or specific script names).
            timing_template (int): Set timing template (0-5, higher is faster but noisier).
            output_format (str): Specify the output format ('normal', 'xml', or 'json').
        
        Returns:
            dict: A dictionary containing the scan information and results.
        """
        nm = nmap.PortScanner()
        
        # Check if root privileges are required but not available
        is_root = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
        if not is_root:
            if scan_type == '-sS':
                scan_type = '-sT'  # Fallback to TCP connect scan
            if os_detection:
                os_detection = False  # Disable OS detection as it requires root

        # Build the Nmap command arguments
        args = f"{scan_type} -p {ports} -T{timing_template}"
        if os_detection and is_root:
            args += " -O"
        if version_scan:
            args += " -sV"
        if script_scan:
            args += f" --script={script_scan}"
        
        try:
            # Perform the scan
            nm.scan(target, arguments=args)
            
            # Process and return the results based on the output format
            if output_format == 'xml':
                return {'xml_output': nm.get_nmap_last_output()}
            elif output_format == 'json':
                return json.loads(nm.get_nmap_last_output())
            else:
                # Default to 'normal' structured output
                scan_results = {
                    'scan_info': nm.scaninfo(),
                    'hosts': {}
                }
                
                for host in nm.all_hosts():
                    host_details = {
                        'state': nm[host].state(),
                        'protocols': list(nm[host].all_protocols()),
                        'ports': {}
                    }
                    
                    for proto in nm[host].all_protocols():
                        host_details['ports'][proto] = []
                        for port in nm[host][proto].keys():
                            port_info = nm[host][proto][port]
                            host_details['ports'][proto].append({
                                'port': port,
                                'state': port_info['state'],
                                'service': port_info['name'],
                                'product': port_info.get('product', ''),
                                'version': port_info.get('version', '')
                            })
                    
                    if 'osmatch' in nm[host]:
                        host_details['os_matches'] = nm[host]['osmatch']
                    
                    scan_results['hosts'][host] = host_details
                
                return scan_results

        except nmap.PortScannerError as e:
            return {
                'error': True,
                'message': str(e),
                'details': 'Consider using -sT scan type for non-root scans'
            }
