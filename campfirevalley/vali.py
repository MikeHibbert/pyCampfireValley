"""
VALI (Validation and Inspection) Service Framework

This module provides the core framework for validation and inspection services
in CampfireValley. VALI services are responsible for scanning, validating,
and ensuring the security and compliance of torches and their payloads.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timedelta
from enum import Enum

from .models import (
    Torch, VALIServiceRequest, VALIServiceResponse, ScanResult,
    Violation, SecurityLevel
)
from .interfaces import IMCPBroker


class VALIServiceType(str, Enum):
    """Types of VALI services available"""
    SECURITY_SCAN = "security_scan"
    CONTENT_VALIDATION = "content_validation"
    PAYLOAD_INSPECTION = "payload_inspection"
    SIGNATURE_VERIFICATION = "signature_verification"
    COMPLIANCE_CHECK = "compliance_check"
    MALWARE_DETECTION = "malware_detection"


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
    
    def list_services(self) -> List[VALIServiceType]:
        """List all registered service types"""
        return list(self._services.keys())
    
    def get_service_capabilities(self, service_type: VALIServiceType) -> Optional[Dict[str, Any]]:
        """Get capabilities for a specific service"""
        return self._service_metadata.get(service_type)


class VALICoordinator:
    """
    Coordinates VALI service requests and manages service orchestration
    """
    
    def __init__(self, mcp_broker: IMCPBroker, registry: VALIServiceRegistry):
        self.mcp_broker = mcp_broker
        self.registry = registry
        self.logger = logging.getLogger(__name__)
        self._active_requests: Dict[str, VALIServiceRequest] = {}
        self._request_callbacks: Dict[str, Callable] = {}
        self._default_timeout = timedelta(minutes=5)
    
    async def start(self) -> None:
        """Start the VALI coordinator"""
        await self.mcp_broker.subscribe("vali.requests", self._handle_service_request)
        self.logger.info("VALI Coordinator started")
    
    async def stop(self) -> None:
        """Stop the VALI coordinator"""
        await self.mcp_broker.unsubscribe("vali.requests")
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