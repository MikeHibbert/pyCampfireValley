#!/usr/bin/env python3
"""
Docker build and publish script for CampfireValley.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and return the result."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error running command: {cmd}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    return result

def build_docker_images():
    """Build Docker images for CampfireValley."""
    
    # Ensure we're in the right directory
    os.chdir(Path(__file__).parent)
    
    # Docker image name and tag
    image_name = "campfirevalley"
    version = "1.1.0"
    
    print("🐳 Building CampfireValley Docker Images")
    print("=" * 50)
    
    # Build the main image
    print(f"\n📦 Building {image_name}:{version}")
    run_command(f"docker build -t {image_name}:{version} .")
    
    # Tag as latest
    print(f"\n🏷️  Tagging as {image_name}:latest")
    run_command(f"docker tag {image_name}:{version} {image_name}:latest")
    
    # List built images
    print("\n📋 Built images:")
    run_command("docker images | findstr campfirevalley", check=False)
    
    print("\n✅ Docker images built successfully!")
    print("\nTo publish to Docker Hub:")
    print(f"1. docker login")
    print(f"2. docker tag {image_name}:{version} yourusername/{image_name}:{version}")
    print(f"3. docker tag {image_name}:latest yourusername/{image_name}:latest")
    print(f"4. docker push yourusername/{image_name}:{version}")
    print(f"5. docker push yourusername/{image_name}:latest")

def test_docker_compose():
    """Test the Docker Compose setup."""
    print("\n🧪 Testing Docker Compose setup")
    print("=" * 50)
    
    # Check if docker-compose.yml exists
    if not Path("docker-compose.yml").exists():
        print("❌ docker-compose.yml not found!")
        return
    
    # Validate docker-compose file
    print("🔍 Validating docker-compose.yml")
    result = run_command("docker-compose config", check=False)
    if result.returncode == 0:
        print("✅ docker-compose.yml is valid")
    else:
        print("❌ docker-compose.yml has issues")
        print(result.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_docker_compose()
    else:
        build_docker_images()
        test_docker_compose()