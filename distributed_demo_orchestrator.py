#!/usr/bin/env python3
"""
Distributed CampfireValley Demo Orchestrator

This orchestrator coordinates a distributed demo where:
1. A local marketing team generates website ideas
2. A dockerized development team receives and processes these ideas
3. Both teams communicate via MCP (Model Context Protocol)
4. A comprehensive HTML report is generated showing the collaboration

Author: CampfireValley Team
Date: 2024
"""

import asyncio
import logging
import os
import subprocess
import time
import json
import aiohttp
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from demo_marketing_team import MarketingTeamDemo


class DistributedDemoOrchestrator:
    """Orchestrates the distributed CampfireValley demo."""
    
    def __init__(self, 
                 docker_compose_path: str = "docker-compose.yml",
                 dev_team_url: str = "http://localhost:8080",
                 reports_dir: str = "reports"):
        """
        Initialize the distributed demo orchestrator.
        
        Args:
            docker_compose_path: Path to the docker-compose.yml file
            dev_team_url: URL of the dockerized development team
            reports_dir: Directory to store reports
        """
        self.docker_compose_path = docker_compose_path
        self.dev_team_url = dev_team_url
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Demo state
        self.demo_start_time = None
        self.demo_end_time = None
        self.marketing_results = {}
        self.development_results = {}
        self.docker_container_id = None
        
    async def start_docker_development_team(self) -> bool:
        """Start the dockerized development team."""
        self.logger.info("Starting dockerized development team...")
        
        try:
            # Check if docker-compose file exists
            if not os.path.exists(self.docker_compose_path):
                self.logger.error(f"Docker compose file not found: {self.docker_compose_path}")
                return False
            
            # Start the docker services
            result = subprocess.run(
                ["docker-compose", "up", "-d", "--build"],
                cwd=os.path.dirname(os.path.abspath(self.docker_compose_path)),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.logger.error(f"Failed to start docker services: {result.stderr}")
                return False
            
            self.logger.info("Docker services started successfully")
            
            # Wait for the development team to be ready
            return await self._wait_for_development_team_ready()
            
        except Exception as e:
            self.logger.error(f"Error starting docker development team: {e}")
            return False
    
    async def _wait_for_development_team_ready(self, max_wait_time: int = 120) -> bool:
        """Wait for the development team to be ready."""
        self.logger.info("Waiting for development team to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.dev_team_url}/health", timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("status") == "healthy":
                                self.logger.info("Development team is ready!")
                                return True
            except Exception as e:
                self.logger.debug(f"Development team not ready yet: {e}")
            
            await asyncio.sleep(5)
        
        self.logger.error("Development team failed to become ready within timeout")
        return False
    
    async def stop_docker_development_team(self):
        """Stop the dockerized development team."""
        self.logger.info("Stopping dockerized development team...")
        
        try:
            result = subprocess.run(
                ["docker-compose", "down"],
                cwd=os.path.dirname(os.path.abspath(self.docker_compose_path)),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info("Docker services stopped successfully")
            else:
                self.logger.warning(f"Docker stop had issues: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"Error stopping docker development team: {e}")
    
    async def run_marketing_team_demo(self) -> Dict[str, Any]:
        """Run the local marketing team demo."""
        self.logger.info("Starting marketing team demo...")
        
        try:
            marketing_demo = MarketingTeamDemo(
                dev_team_url=self.dev_team_url,
                reports_dir=str(self.reports_dir)
            )
            
            # Run the marketing team demo
            results = await marketing_demo.run_demo()
            self.marketing_results = results
            
            self.logger.info(f"Marketing team demo completed: {results['status']}")
            return results
            
        except Exception as e:
            self.logger.error(f"Error running marketing team demo: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_development_team_results(self) -> Dict[str, Any]:
        """Get results from the development team."""
        self.logger.info("Retrieving development team results...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.dev_team_url}/api/results") as response:
                    if response.status == 200:
                        results = await response.json()
                        self.development_results = results
                        return results
                    else:
                        error_msg = f"Failed to get development results: {response.status}"
                        self.logger.error(error_msg)
                        return {"status": "error", "error": error_msg}
                        
        except Exception as e:
            self.logger.error(f"Error getting development team results: {e}")
            return {"status": "error", "error": str(e)}
    
    async def generate_combined_report(self) -> str:
        """Generate a comprehensive HTML report showing both teams' work."""
        self.logger.info("Generating combined report...")
        
        try:
            # Get development team's HTML report
            dev_report_html = ""
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.dev_team_url}/api/report") as response:
                        if response.status == 200:
                            dev_report_html = await response.text()
                        else:
                            dev_report_html = f"<p>Error retrieving development report: {response.status}</p>"
            except Exception as e:
                dev_report_html = f"<p>Error retrieving development report: {e}</p>"
            
            # Generate combined HTML
            combined_html = self._generate_combined_html_report(dev_report_html)
            
            # Save the report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"distributed_demo_report_{timestamp}.html"
            report_path = self.reports_dir / report_filename
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(combined_html)
            
            self.logger.info(f"Combined report saved to: {report_path}")
            return str(report_path)
            
        except Exception as e:
            self.logger.error(f"Error generating combined report: {e}")
            return ""
    
    def _generate_combined_html_report(self, dev_report_html: str) -> str:
        """Generate the combined HTML report."""
        demo_duration = ""
        if self.demo_start_time and self.demo_end_time:
            duration = self.demo_end_time - self.demo_start_time
            demo_duration = f"{duration.total_seconds():.1f} seconds"
        
        marketing_ideas_count = len(self.marketing_results.get("results", {}).get("marketing_ideas", []))
        dev_requests_count = len(self.marketing_results.get("results", {}).get("development_requests", []))
        
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Distributed CampfireValley Demo Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header p {{
            margin: 10px 0 0 0;
            font-size: 1.2em;
            opacity: 0.9;
        }}
        .overview {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        .overview h2 {{
            color: #2c3e50;
            margin-bottom: 20px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
        }}
        .stat-label {{
            color: #7f8c8d;
            margin-top: 5px;
        }}
        .team-section {{
            padding: 30px;
            border-bottom: 1px solid #e9ecef;
        }}
        .team-section h2 {{
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #3498db;
        }}
        .team-section.marketing h2 {{
            border-bottom-color: #e74c3c;
        }}
        .team-section.development h2 {{
            border-bottom-color: #27ae60;
        }}
        .workflow-diagram {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: center;
        }}
        .workflow-step {{
            display: inline-block;
            background: white;
            padding: 15px 25px;
            margin: 10px;
            border-radius: 25px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
            position: relative;
        }}
        .workflow-step:not(:last-child)::after {{
            content: '→';
            position: absolute;
            right: -25px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 1.5em;
            color: #3498db;
        }}
        .footer {{
            padding: 30px;
            text-align: center;
            background: #2c3e50;
            color: white;
        }}
        .timestamp {{
            color: #95a5a6;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Distributed CampfireValley Demo</h1>
            <p>Marketing Team ↔ Development Team Collaboration via MCP</p>
        </div>
        
        <div class="overview">
            <h2>Demo Overview</h2>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{marketing_ideas_count}</div>
                    <div class="stat-label">Website Ideas Generated</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{dev_requests_count}</div>
                    <div class="stat-label">Development Requests</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{demo_duration}</div>
                    <div class="stat-label">Demo Duration</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">2</div>
                    <div class="stat-label">Teams Collaborated</div>
                </div>
            </div>
            
            <div class="workflow-diagram">
                <h3>Collaboration Workflow</h3>
                <div class="workflow-step">Local Marketing Team</div>
                <div class="workflow-step">Generate Ideas</div>
                <div class="workflow-step">MCP Communication</div>
                <div class="workflow-step">Dockerized Dev Team</div>
                <div class="workflow-step">Development Results</div>
            </div>
        </div>
        
        <div class="team-section marketing">
            <h2>🎯 Marketing Team (Local)</h2>
            <p><strong>Status:</strong> {self.marketing_results.get('status', 'Unknown')}</p>
            <p><strong>Report:</strong> {self.marketing_results.get('report_path', 'Not available')}</p>
            <p>The local marketing team consisting of Marketing Strategist, Creative Director, and UX Researcher collaborated to generate innovative website ideas and sent them to the development team for implementation.</p>
        </div>
        
        <div class="team-section development">
            <h2>💻 Development Team (Dockerized)</h2>
            {dev_report_html}
        </div>
        
        <div class="footer">
            <p>Generated by CampfireValley Distributed Demo Orchestrator</p>
            <p class="timestamp">Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
        """
    
    async def run_distributed_demo(self) -> Dict[str, Any]:
        """Run the complete distributed demo."""
        self.logger.info("Starting distributed CampfireValley demo...")
        self.demo_start_time = datetime.now()
        
        try:
            # Step 1: Start the dockerized development team
            if not await self.start_docker_development_team():
                return {
                    "status": "error",
                    "error": "Failed to start dockerized development team"
                }
            
            # Step 2: Run the marketing team demo
            marketing_results = await self.run_marketing_team_demo()
            if marketing_results.get("status") != "success":
                await self.stop_docker_development_team()
                return {
                    "status": "error",
                    "error": f"Marketing team demo failed: {marketing_results.get('error', 'Unknown error')}"
                }
            
            # Step 3: Get development team results
            dev_results = await self.get_development_team_results()
            
            # Step 4: Generate combined report
            self.demo_end_time = datetime.now()
            report_path = await self.generate_combined_report()
            
            # Step 5: Stop the dockerized development team
            await self.stop_docker_development_team()
            
            return {
                "status": "success",
                "demo_duration": (self.demo_end_time - self.demo_start_time).total_seconds(),
                "marketing_results": marketing_results,
                "development_results": dev_results,
                "combined_report_path": report_path,
                "summary": {
                    "ideas_generated": len(marketing_results.get("results", {}).get("marketing_ideas", [])),
                    "development_requests": len(marketing_results.get("results", {}).get("development_requests", [])),
                    "teams_involved": 2
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error in distributed demo: {e}")
            await self.stop_docker_development_team()
            return {
                "status": "error",
                "error": str(e)
            }


async def main():
    """Main function to run the distributed demo."""
    orchestrator = DistributedDemoOrchestrator()
    
    print("🔥 Starting Distributed CampfireValley Demo...")
    print("=" * 60)
    
    results = await orchestrator.run_distributed_demo()
    
    print("\n" + "=" * 60)
    print("📊 Demo Results:")
    print(f"Status: {results['status']}")
    
    if results['status'] == 'success':
        print(f"Duration: {results['demo_duration']:.1f} seconds")
        print(f"Ideas Generated: {results['summary']['ideas_generated']}")
        print(f"Development Requests: {results['summary']['development_requests']}")
        print(f"Combined Report: {results['combined_report_path']}")
    else:
        print(f"Error: {results.get('error', 'Unknown error')}")
    
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())