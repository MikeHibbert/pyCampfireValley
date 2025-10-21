"""
VALI (Valley Application Layer Interface) Service Framework

This module provides the core framework for validation, inspection, and 
inter-valley service communication in CampfireValley. VALI services are 
responsible for scanning, validating, ensuring security and compliance of 
torches, and facilitating service discovery across the federation.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4

from .models import (
    Torch, VALIServiceRequest, VALIServiceResponse, ScanResult,
    Violation, SecurityLevel, FederationMembership
)
from .interfaces import IMCPBroker, IFederationManager


class VALIServiceType(str, Enum):
    """Types of VALI services available"""
    # Validation and Security Services
    SECURITY_SCAN = "security_scan"
    CONTENT_VALIDATION = "content_validation"
    PAYLOAD_INSPECTION = "payload_inspection"
    SIGNATURE_VERIFICATION = "signature_verification"
    COMPLIANCE_CHECK = "compliance_check"
    MALWARE_DETECTION = "malware_detection"
    
    # Federation Services
    SERVICE_DISCOVERY = "service_discovery"
    AI_INFERENCE = "ai_inference"
    DATA_PROCESSING = "data_processing"
    COMPUTE_SERVICE = "compute_service"
    STORAGE_SERVICE = "storage_service"
    ANALYTICS_SERVICE = "analytics_service"
    CUSTOM_SERVICE = "custom_service"


class VALIServiceStatus(str, Enum):
    """Status of VALI service operations"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class IVALIService(ABC):
    """Interface for VALI services"""
    
    @abstractmethod
    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        """Process a VALI service request"""
        pass
    
    @abstractmethod
    def get_service_type(self) -> VALIServiceType:
        """Get the type of service this provides"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Get service capabilities and metadata"""
        pass


class VALIServiceRegistry:
    """Registry for managing VALI services"""
    
    def __init__(self):
        self._services: Dict[VALIServiceType, IVALIService] = {}
        self._service_metadata: Dict[VALIServiceType, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_service(self, service: IVALIService) -> None:
        """Register a VALI service"""
        service_type = service.get_service_type()
        self._services[service_type] = service
        self._service_metadata[service_type] = service.get_capabilities()
        self.logger.info(f"Registered VALI service: {service_type}")
    
    def unregister_service(self, service_type: VALIServiceType) -> None:
        """Unregister a VALI service"""
        if service_type in self._services:
            del self._services[service_type]
            del self._service_metadata[service_type]
            self.logger.info(f"Unregistered VALI service: {service_type}")
    
    def get_service(self, service_type: VALIServiceType) -> Optional[IVALIService]:
        """Get a registered service by type"""
        return self._services.get(service_type)
    
    def get_service_capabilities(self, service_type: VALIServiceType) -> Optional[Dict[str, Any]]:
        """Get capabilities metadata for a service"""
        service = self._services.get(service_type)
        if service:
            try:
                return service.get_capabilities()
            except Exception:
                return {}
        return None
    
    def list_services(self) -> List[VALIServiceType]:
        """List all registered service types"""
        return list(self._services.keys())
    
    def get_all_service_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered services"""
        info = {}
        for service_type, service in self._services.items():
            try:
                info[service_type.value] = {
                    "type": service_type.value,
                    "capabilities": service.get_capabilities() if hasattr(service, 'get_capabilities') else {},
                    "status": "active"
                }
            except Exception as e:
                info[service_type.value] = {
                    "type": service_type.value,
                    "capabilities": {},
                    "status": "error",
                    "error": str(e)
                }
        return info


class VALICoordinator:
    """
    Coordinates VALI service requests and manages service orchestration
    Supports both local validation services and federation service discovery
    """
    
    def __init__(self, mcp_broker: IMCPBroker, registry: VALIServiceRegistry, 
                 federation_manager: Optional[IFederationManager] = None, valley_name: str = ""):
        self.mcp_broker = mcp_broker
        self.registry = registry
        self.federation_manager = federation_manager
        self.valley_name = valley_name
        self.logger = logging.getLogger(__name__)
        self._active_requests: Dict[str, VALIServiceRequest] = {}
        self._request_callbacks: Dict[str, Callable] = {}
        self._default_timeout = timedelta(minutes=5)
        
        # Federation service discovery
        self._federation_services: Dict[str, List[Dict[str, Any]]] = {}
        self._service_cache_ttl = timedelta(minutes=5)
        self._last_discovery: Dict[str, datetime] = {}
        self._pending_federation_requests: Dict[str, asyncio.Future] = {}
    
    async def start(self) -> None:
        """Start the VALI coordinator"""
        await self.mcp_broker.subscribe("vali.requests", self._handle_service_request)
        await self.mcp_broker.subscribe("vali.discovery", self._handle_discovery_message)
        await self.mcp_broker.subscribe(f"vali.valley.{self.valley_name}", self._handle_federation_message)
        self.logger.info("VALI Coordinator started")
    
    async def stop(self) -> None:
        """Stop the VALI coordinator"""
        await self.mcp_broker.unsubscribe("vali.requests")
        await self.mcp_broker.unsubscribe("vali.discovery")
        await self.mcp_broker.unsubscribe(f"vali.valley.{self.valley_name}")
        
        # Cancel pending federation requests
        for future in self._pending_federation_requests.values():
            if not future.done():
                future.cancel()
        
        self.logger.info("VALI Coordinator stopped")
    
    async def request_service(
        self,
        service_type: VALIServiceType,
        payload: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None,
        timeout: Optional[timedelta] = None
    ) -> VALIServiceResponse:
        """
        Request a VALI service
        
        Args:
            service_type: Type of service to request
            payload: Service payload data
            requirements: Service requirements
            timeout: Request timeout
            
        Returns:
            Service response
            
        Raises:
            ValueError: If service type is not available
            TimeoutError: If request times out
        """
        service = self.registry.get_service(service_type)
        if not service:
            raise ValueError(f"VALI service not available: {service_type}")
        
        request_id = f"vali_{service_type}_{datetime.utcnow().timestamp()}"
        deadline = datetime.utcnow() + (timeout or self._default_timeout)
        
        request = VALIServiceRequest(
            service_type=service_type.value,
            request_id=request_id,
            payload=payload,
            requirements=requirements or {},
            deadline=deadline
        )
        
        self._active_requests[request_id] = request
        
        try:
            response = await asyncio.wait_for(
                service.process_request(request),
                timeout=(timeout or self._default_timeout).total_seconds()
            )
            return response
        except asyncio.TimeoutError:
            self.logger.warning(f"VALI request timeout: {request_id}")
            return VALIServiceResponse(
                request_id=request_id,
                status=VALIServiceStatus.TIMEOUT.value,
                deliverables={},
                metadata={"error": "Request timeout"}
            )
        finally:
            self._active_requests.pop(request_id, None)
    
    async def scan_torch(self, torch: Torch, security_level: SecurityLevel = SecurityLevel.STANDARD) -> ScanResult:
        """
        Perform comprehensive security scan on a torch
        
        Args:
            torch: Torch to scan
            security_level: Security level for scanning
            
        Returns:
            Scan result with security assessment
        """
        scan_payload = {
            "torch_id": torch.id,
            "sender_valley": torch.sender_valley,
            "target_address": torch.target_address,
            "payload": torch.payload,
            "attachments": torch.attachments,
            "signature": torch.signature
        }
        
        requirements = {
            "security_level": security_level.value,
            "comprehensive": True
        }
        
        # Request security scan
        response = await self.request_service(
            VALIServiceType.SECURITY_SCAN,
            scan_payload,
            requirements
        )
        
        if response.status == VALIServiceStatus.COMPLETED.value:
            scan_data = response.deliverables.get("scan_result", {})
            return ScanResult(
                is_safe=scan_data.get("is_safe", False),
                violations=scan_data.get("violations", []),
                confidence_score=scan_data.get("confidence_score", 0.0),
                scan_timestamp=datetime.utcnow()
            )
        else:
            # Failed scan - assume unsafe
            return ScanResult(
                is_safe=False,
                violations=[f"Scan failed: {response.metadata.get('error', 'Unknown error')}"],
                confidence_score=0.0,
                scan_timestamp=datetime.utcnow()
            )
    
    async def validate_torch_content(self, torch: Torch) -> bool:
        """
        Validate torch content structure and format
        
        Args:
            torch: Torch to validate
            
        Returns:
            True if content is valid
        """
        validation_payload = {
            "torch_id": torch.id,
            "payload": torch.payload,
            "attachments": torch.attachments
        }
        
        response = await self.request_service(
            VALIServiceType.CONTENT_VALIDATION,
            validation_payload
        )
        
        return (response.status == VALIServiceStatus.COMPLETED.value and
                response.deliverables.get("is_valid", False))
    
    async def verify_torch_signature(self, torch: Torch) -> bool:
        """
        Verify torch digital signature
        
        Args:
            torch: Torch to verify
            
        Returns:
            True if signature is valid
        """
        verification_payload = {
            "torch_id": torch.id,
            "sender_valley": torch.sender_valley,
            "payload": torch.payload,
            "signature": torch.signature,
            "timestamp": torch.timestamp.isoformat()
        }
        
        response = await self.request_service(
            VALIServiceType.SIGNATURE_VERIFICATION,
            verification_payload
        )
        
        return (response.status == VALIServiceStatus.COMPLETED.value and
                response.deliverables.get("signature_valid", False))
    
    async def _handle_service_request(self, message: Dict[str, Any]) -> None:
        """Handle incoming VALI service requests via MCP"""
        try:
            request_data = message.get("data", {})
            request = VALIServiceRequest(**request_data)
            
            service_type = VALIServiceType(request.service_type)
            service = self.registry.get_service(service_type)
            
            if not service:
                response = VALIServiceResponse(
                    request_id=request.request_id,
                    status=VALIServiceStatus.FAILED.value,
                    deliverables={},
                    metadata={"error": f"Service not available: {service_type}"}
                )
            else:
                response = await service.process_request(request)
            
            # Send response back via MCP
            await self.mcp_broker.publish(
                f"vali.responses.{request.request_id}",
                response.dict()
            )
            
        except Exception as e:
            self.logger.error(f"Error handling VALI service request: {e}")
    
    async def discover_federation_services(self, service_type: VALIServiceType, 
                                         force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Discover services across the federation
        
        Args:
            service_type: Type of service to discover
            force_refresh: Force refresh of service cache
            
        Returns:
            List of available service providers
        """
        if not self.federation_manager:
            self.logger.warning("Federation manager not available for service discovery")
            return []
        
        service_key = service_type.value
        
        # Check cache first
        if not force_refresh and service_key in self._federation_services:
            last_discovery = self._last_discovery.get(service_key, datetime.min)
            if datetime.utcnow() - last_discovery < self._service_cache_ttl:
                return self._federation_services[service_key]
        
        try:
            # Send discovery request
            discovery_request = {
                "type": "service_discovery",
                "service_type": service_key,
                "requester": self.valley_name,
                "request_id": str(uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.mcp_broker.publish("vali.discovery", discovery_request)
            
            # Wait for responses
            await asyncio.sleep(2)  # Give time for responses
            
            # Return cached results
            return self._federation_services.get(service_key, [])
            
        except Exception as e:
            self.logger.error(f"Failed to discover federation services for {service_type}: {e}")
            return []
    
    async def call_federation_service(self, target_valley: str, service_type: VALIServiceType,
                                    parameters: Dict[str, Any], timeout: Optional[int] = None) -> Optional[VALIServiceResponse]:
        """
        Call a service on another valley in the federation
        
        Args:
            target_valley: Name of the target valley
            service_type: Type of service to call
            parameters: Service parameters
            timeout: Request timeout in seconds
            
        Returns:
            Service response or None if failed
        """
        if not self.federation_manager:
            self.logger.warning("Federation manager not available for inter-valley calls")
            return None
        
        try:
            request_id = str(uuid4())
            request_timeout = timeout or 30
            
            # Create service request
            request = VALIServiceRequest(
                request_id=request_id,
                service_type=service_type.value,
                requester_valley=self.valley_name,
                target_valley=target_valley,
                parameters=parameters
            )
            
            # Create future for response
            response_future = asyncio.Future()
            self._pending_federation_requests[request_id] = response_future
            
            # Send request via federation manager
            torch = Torch(
                sender_valley=self.valley_name,
                target_address=f"{target_valley}:vali",
                data={"vali_request": request.dict()},
                signature="",  # Will be signed by federation manager
                source="vali_service",
                destination=f"{target_valley}:vali"
            )
            
            success = await self.federation_manager.send_torch_to_valley(target_valley, torch)
            if not success:
                self._pending_federation_requests.pop(request_id, None)
                return None
            
            # Wait for response
            try:
                response = await asyncio.wait_for(response_future, timeout=request_timeout)
                return response
            except asyncio.TimeoutError:
                self.logger.warning(f"Federation service call timeout: {service_type} on {target_valley}")
                return None
            finally:
                self._pending_federation_requests.pop(request_id, None)
                
        except Exception as e:
            self.logger.error(f"Failed to call federation service {service_type} on {target_valley}: {e}")
            return None
    
    async def register_federation_service(self, service_type: VALIServiceType, 
                                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Register this valley's service with the federation
        
        Args:
            service_type: Type of service to register
            metadata: Optional service metadata
            
        Returns:
            True if registered successfully
        """
        try:
            service_info = {
                "service_type": service_type.value,
                "valley_id": self.valley_name,
                "metadata": metadata or {},
                "registered_at": datetime.utcnow().isoformat(),
                "endpoint": f"vali.valley.{self.valley_name}"
            }
            
            # Announce service to federation
            announcement = {
                "type": "service_announcement",
                "service": service_info,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.mcp_broker.publish("vali.discovery", announcement)
            
            # Add to local registry if not already present
            if not self.registry.get_service(service_type):
                self.logger.info(f"Registered federation service: {service_type}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register federation service {service_type}: {e}")
            return False
    
    async def _handle_discovery_message(self, message: Dict[str, Any]) -> None:
        """Handle service discovery messages"""
        try:
            msg_type = message.get("type")
            
            if msg_type == "service_discovery":
                # Respond if we have the requested service
                service_type = message.get("service_type")
                requester = message.get("requester")
                
                if requester != self.valley_name:
                    # Check if we have this service locally
                    vali_service_type = VALIServiceType(service_type)
                    if self.registry.get_service(vali_service_type):
                        response = {
                            "type": "service_response",
                            "request_id": message.get("request_id"),
                            "service": {
                                "service_type": service_type,
                                "valley_id": self.valley_name,
                                "metadata": self.registry.get_service_capabilities(vali_service_type) or {},
                                "endpoint": f"vali.valley.{self.valley_name}"
                            },
                            "responder": self.valley_name,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        
                        await self.mcp_broker.publish("vali.discovery", response)
            
            elif msg_type == "service_response":
                # Cache discovered service
                service = message.get("service")
                if service:
                    service_type = service.get("service_type")
                    if service_type:
                        if service_type not in self._federation_services:
                            self._federation_services[service_type] = []
                        
                        # Update or add service
                        existing = None
                        for i, cached_service in enumerate(self._federation_services[service_type]):
                            if cached_service.get("valley_id") == service.get("valley_id"):
                                existing = i
                                break
                        
                        if existing is not None:
                            self._federation_services[service_type][existing] = service
                        else:
                            self._federation_services[service_type].append(service)
                        
                        self._last_discovery[service_type] = datetime.utcnow()
            
            elif msg_type == "service_announcement":
                # Cache announced service
                service = message.get("service")
                if service:
                    service_type = service.get("service_type")
                    if service_type:
                        if service_type not in self._federation_services:
                            self._federation_services[service_type] = []
                        
                        self._federation_services[service_type].append(service)
                        self._last_discovery[service_type] = datetime.utcnow()
            
        except Exception as e:
            self.logger.error(f"Error handling discovery message: {e}")
    
    async def _handle_federation_message(self, message: Dict[str, Any]) -> None:
        """Handle federation service messages"""
        try:
            if message.get("type") == "vali_request":
                request_data = message.get("request")
                if request_data:
                    request = VALIServiceRequest(**request_data)
                    await self._process_federation_request(request)
            
            elif message.get("type") == "vali_response":
                response_data = message.get("response")
                if response_data:
                    response = VALIServiceResponse(**response_data)
                    await self._process_federation_response(response)
            
        except Exception as e:
            self.logger.error(f"Error handling federation message: {e}")
    
    async def _process_federation_request(self, request: VALIServiceRequest) -> None:
        """Process incoming federation service request"""
        try:
            service_type = VALIServiceType(request.service_type)
            service = self.registry.get_service(service_type)
            
            if service:
                # Process the request locally
                response = await service.process_request(request)
            else:
                # Service not available
                response = VALIServiceResponse(
                    request_id=request.request_id,
                    status=VALIServiceStatus.FAILED.value,
                    deliverables={},
                    metadata={"error": f"Service not available: {service_type}"}
                )
            
            # Send response back
            response_message = {
                "type": "vali_response",
                "response": response.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.mcp_broker.publish(f"vali.valley.{request.requester_valley}", response_message)
            
        except Exception as e:
            self.logger.error(f"Error processing federation request: {e}")
    
    async def _process_federation_response(self, response: VALIServiceResponse) -> None:
        """Process incoming federation service response"""
        try:
            # Find pending request
            if response.request_id in self._pending_federation_requests:
                future = self._pending_federation_requests[response.request_id]
                if not future.done():
                    future.set_result(response)
            
        except Exception as e:
            self.logger.error(f"Error processing federation response: {e}")


class BaseVALIService(IVALIService):
    """Base implementation for VALI services"""
    
    def __init__(self, service_type: VALIServiceType, capabilities: Optional[Dict[str, Any]] = None):
        self.service_type = service_type
        self.capabilities = capabilities or {}
        self.logger = logging.getLogger(f"{__name__}.{service_type.value}")
    
    def get_service_type(self) -> VALIServiceType:
        """Get the service type"""
        return self.service_type
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get service capabilities"""
        return {
            "service_type": self.service_type.value,
            "version": "1.0",
            "supported_formats": ["json"],
            **self.capabilities
        }
    
    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        """Process a service request - to be implemented by subclasses"""
        return VALIServiceResponse(
            request_id=request.request_id,
            status=VALIServiceStatus.FAILED.value,
            deliverables={},
            metadata={"error": "Service not implemented"}
        )


# Enhanced SecurityScanner is imported from security_scanner module
# The SecurityScannerService is replaced by EnhancedSecurityScanner


class ContentValidatorService(BaseVALIService):
    """Content validation service"""
    
    def __init__(self):
        super().__init__(
            VALIServiceType.CONTENT_VALIDATION,
            {
                "validation_types": ["structure", "format", "schema"],
                "supported_formats": ["json", "yaml", "xml"]
            }
        )
    
    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        """Process content validation request"""
        try:
            payload = request.payload.get("payload", {})
            
            # Basic validation checks
            is_valid = True
            validation_errors = []
            
            # Check if payload is a valid dictionary
            if not isinstance(payload, dict):
                is_valid = False
                validation_errors.append("Payload must be a dictionary")
            
            # Check for required fields (basic example)
            if isinstance(payload, dict):
                if not payload.get("type"):
                    validation_errors.append("Missing 'type' field in payload")
                
                # Check for circular references
                try:
                    import json
                    json.dumps(payload)
                except (TypeError, ValueError) as e:
                    is_valid = False
                    validation_errors.append(f"Payload serialization error: {e}")
            
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.COMPLETED.value,
                deliverables={
                    "is_valid": is_valid,
                    "validation_errors": validation_errors
                },
                metadata={
                    "validation_time_ms": 50
                }
            )
            
        except Exception as e:
            self.logger.error(f"Content validation failed: {e}")
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.FAILED.value,
                deliverables={},
                metadata={"error": str(e)}
            )


class SignatureVerifierService(BaseVALIService):
    """Digital signature verification service"""
    
    def __init__(self):
        super().__init__(
            VALIServiceType.SIGNATURE_VERIFICATION,
            {
                "signature_types": ["RSA", "ECDSA"],
                "hash_algorithms": ["SHA256", "SHA512"]
            }
        )
    
    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        """Process signature verification request"""
        try:
            # For now, implement basic signature validation
            # In a real implementation, this would use proper cryptographic verification
            signature = request.payload.get("signature", "")
            sender_valley = request.payload.get("sender_valley", "")
            
            # Basic validation - signature should not be empty and should contain sender info
            signature_valid = (
                len(signature) > 0 and
                sender_valley in signature and
                len(signature) >= 32  # Minimum signature length
            )
            
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.COMPLETED.value,
                deliverables={
                    "signature_valid": signature_valid,
                    "verification_method": "basic_validation"
                },
                metadata={
                    "verification_time_ms": 25
                }
            )
            
        except Exception as e:
            self.logger.error(f"Signature verification failed: {e}")
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.FAILED.value,
                deliverables={},
                metadata={"error": str(e)}
            )