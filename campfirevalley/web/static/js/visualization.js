/**
 * CampfireValley Interactive Canvas Visualization
 * Similar to ComfyUI with proper pan/zoom and SVG-like rendering
 */

class CampfireCanvas {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.minimap = document.getElementById('minimapCanvas');
        this.minimapCtx = this.minimap.getContext('2d');
        
        // Canvas state
        this.scale = 1.0;
        this.offsetX = 0;
        this.offsetY = 0;
        this.isDragging = false;
        this.dragStart = { x: 0, y: 0 };
        this.lastPanPoint = { x: 0, y: 0 };
        
        // Node data
        this.nodes = [];
        this.connections = [];
        this.selectedNode = null;
        this.hoveredNode = null;
        
        // Animation
        this.animationId = null;
        this.lastFrameTime = 0;
        
        // WebSocket
        this.ws = null;
        this.connectionStatus = 'disconnected';
        
        this.setupCanvas();
        this.setupEventListeners();
        this.setupWebSocket();
        this.startRenderLoop();
    }
    
    setupCanvas() {
        // Set canvas size to match container
        this.resizeCanvas();
        
        // Enable high DPI support
        const dpr = window.devicePixelRatio || 1;
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.ctx.scale(dpr, dpr);
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';
        
        // Set initial view to center
        this.offsetX = this.canvas.width / 2;
        this.offsetY = this.canvas.height / 2;
    }
    
    resizeCanvas() {
        const container = this.canvas.parentElement;
        this.canvas.width = container.clientWidth;
        this.canvas.height = container.clientHeight;
    }
    
    setupEventListeners() {
        // Mouse events for pan/zoom
        this.canvas.addEventListener('mousedown', this.onMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.onMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.onMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.onWheel.bind(this));
        this.canvas.addEventListener('click', this.onClick.bind(this));
        
        // Touch events for mobile
        this.canvas.addEventListener('touchstart', this.onTouchStart.bind(this));
        this.canvas.addEventListener('touchmove', this.onTouchMove.bind(this));
        this.canvas.addEventListener('touchend', this.onTouchEnd.bind(this));
        
        // Window resize
        window.addEventListener('resize', this.onResize.bind(this));
        
        // UI controls
        document.getElementById('zoomIn').addEventListener('click', () => this.zoomIn());
        document.getElementById('zoomOut').addEventListener('click', () => this.zoomOut());
        document.getElementById('resetView').addEventListener('click', () => this.resetView());
        
        // Prevent context menu
        this.canvas.addEventListener('contextmenu', e => e.preventDefault());
    }
    
    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.connectionStatus = 'connected';
            this.updateConnectionStatus();
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.connectionStatus = 'disconnected';
            this.updateConnectionStatus();
            // Attempt to reconnect after 3 seconds
            setTimeout(() => this.setupWebSocket(), 3000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.connectionStatus = 'error';
            this.updateConnectionStatus();
        };
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'state_update':
                this.updateVisualizationState(data.data);
                break;
            case 'node_update':
                this.updateNode(data.data);
                break;
            case 'connection_update':
                this.updateConnections(data.data);
                break;
            case 'task_update':
                this.updateTaskStatus(data.data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    updateVisualizationState(state) {
        this.nodes = state.nodes || [];
        this.connections = state.connections || [];
        
        // Auto-layout nodes if they don't have positions
        this.autoLayoutNodes();
    }
    
    autoLayoutNodes() {
        const centerX = 0;
        const centerY = 0;
        const radius = 300;
        
        // Find valley node and place it at center
        const valleyNode = this.nodes.find(n => n.type === 'valley');
        if (valleyNode) {
            valleyNode.position = { x: centerX, y: centerY };
        }
        
        // Arrange campfire nodes in a circle around valley
        const campfireNodes = this.nodes.filter(n => n.type === 'campfire');
        campfireNodes.forEach((node, index) => {
            const angle = (index / campfireNodes.length) * 2 * Math.PI;
            node.position = {
                x: centerX + Math.cos(angle) * radius,
                y: centerY + Math.sin(angle) * radius
            };
        });
        
        // Arrange camper nodes around their campfires
        const camperNodes = this.nodes.filter(n => n.type === 'camper');
        camperNodes.forEach((node, index) => {
            const parentCampfire = campfireNodes.find(cf => cf.id === node.parent_id);
            if (parentCampfire) {
                const angle = (index / camperNodes.length) * 2 * Math.PI;
                const camperRadius = 80;
                node.position = {
                    x: parentCampfire.position.x + Math.cos(angle) * camperRadius,
                    y: parentCampfire.position.y + Math.sin(angle) * camperRadius
                };
            }
        });
    }
    
    updateNode(nodeData) {
        const existingNode = this.nodes.find(n => n.id === nodeData.id);
        if (existingNode) {
            Object.assign(existingNode, nodeData);
        } else {
            this.nodes.push(nodeData);
        }
    }
    
    updateConnections(connectionData) {
        this.connections = connectionData;
    }
    
    updateTaskStatus(taskData) {
        const statusElement = document.getElementById('taskStatus');
        if (statusElement) {
            statusElement.innerHTML = `<span class="status-text">${taskData.status}</span>`;
        }
    }
    
    updateConnectionStatus() {
        const statusElement = document.getElementById('connectionText');
        const statusColors = {
            'connected': '#4CAF50',
            'disconnected': '#f44336',
            'error': '#ff9800'
        };
        
        if (statusElement) {
            statusElement.textContent = this.connectionStatus.charAt(0).toUpperCase() + this.connectionStatus.slice(1);
            statusElement.style.color = statusColors[this.connectionStatus] || '#ccc';
        }
    }
    
    // Coordinate transformation
    screenToWorld(screenX, screenY) {
        return {
            x: (screenX - this.offsetX) / this.scale,
            y: (screenY - this.offsetY) / this.scale
        };
    }
    
    worldToScreen(worldX, worldY) {
        return {
            x: worldX * this.scale + this.offsetX,
            y: worldY * this.scale + this.offsetY
        };
    }
    
    // Event handlers
    onMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const worldPos = this.screenToWorld(x, y);
        const clickedNode = this.getNodeAtPosition(worldPos.x, worldPos.y);
        
        if (clickedNode) {
            this.selectNode(clickedNode);
        } else {
            this.isDragging = true;
            this.dragStart = { x, y };
            this.lastPanPoint = { x: this.offsetX, y: this.offsetY };
            this.canvas.style.cursor = 'grabbing';
        }
    }
    
    onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        if (this.isDragging) {
            const dx = x - this.dragStart.x;
            const dy = y - this.dragStart.y;
            this.offsetX = this.lastPanPoint.x + dx;
            this.offsetY = this.lastPanPoint.y + dy;
        } else {
            // Update hovered node
            const worldPos = this.screenToWorld(x, y);
            const hoveredNode = this.getNodeAtPosition(worldPos.x, worldPos.y);
            
            if (hoveredNode !== this.hoveredNode) {
                this.hoveredNode = hoveredNode;
                this.canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
            }
            
            // Store mouse position for tooltip rendering
            this.mousePos = { x, y, worldX: worldPos.x, worldY: worldPos.y };
        }
    }
    
    onMouseUp(e) {
        this.isDragging = false;
        this.canvas.style.cursor = 'grab';
    }
    
    onWheel(e) {
        e.preventDefault();
        
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.max(0.1, Math.min(5.0, this.scale * zoomFactor));
        
        // Zoom towards mouse position
        const worldPos = this.screenToWorld(x, y);
        this.scale = newScale;
        const newScreenPos = this.worldToScreen(worldPos.x, worldPos.y);
        
        this.offsetX += x - newScreenPos.x;
        this.offsetY += y - newScreenPos.y;
    }
    
    onClick(e) {
        // Handle node selection
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const worldPos = this.screenToWorld(x, y);
        const clickedNode = this.getNodeAtPosition(worldPos.x, worldPos.y);
        
        if (clickedNode) {
            this.selectNode(clickedNode);
        } else {
            this.selectedNode = null;
            this.hideNodeDetails();
        }
    }
    
    onTouchStart(e) {
        e.preventDefault();
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            this.onMouseDown({ clientX: touch.clientX, clientY: touch.clientY });
        }
    }
    
    onTouchMove(e) {
        e.preventDefault();
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            this.onMouseMove({ clientX: touch.clientX, clientY: touch.clientY });
        }
    }
    
    onTouchEnd(e) {
        e.preventDefault();
        this.onMouseUp(e);
    }
    
    onResize() {
        this.setupCanvas();
    }
    
    // Utility methods
    getNodeAtPosition(worldX, worldY) {
        for (let node of this.nodes) {
            if (!node.position) continue;
            
            const nodeSize = this.getNodeSize(node);
            const dx = worldX - node.position.x;
            const dy = worldY - node.position.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance <= nodeSize / 2) {
                return node;
            }
        }
        return null;
    }
    
    getNodeSize(node) {
        switch (node.type) {
            case 'valley': return 120;
            case 'campfire': return 80;
            case 'camper': return 50;
            default: return 60;
        }
    }
    
    getNodeColor(node) {
        const statusColors = {
            'active': '#4CAF50',
            'busy': '#FF9800',
            'error': '#F44336',
            'offline': '#757575'
        };
        
        const typeColors = {
            'valley': '#2196F3',
            'campfire': '#FF6B35',
            'camper': '#9C27B0'
        };
        
        return statusColors[node.status] || typeColors[node.type] || '#666';
    }
    
    selectNode(node) {
        this.selectedNode = node;
        this.showNodeDetails(node);
    }
    
    showNodeDetails(node) {
        const nodeTitle = document.getElementById('nodeTitle');
        const nodeDetails = document.getElementById('nodeDetails');
        const nodeInfo = document.getElementById('nodeInfo');
        
        if (!nodeTitle || !nodeDetails || !nodeInfo) return;
        
        nodeTitle.textContent = `${node.icon || '🔥'} ${node.label}`;
        
        let detailsHTML = '';
        
        // Common details
        detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.type}</span></div>`;
        detailsHTML += `<div class="info-item"><span>Status:</span><span><span class="status-indicator status-${node.status?.toLowerCase()}"></span>${node.status}</span></div>`;
        
        // Type-specific details
        if (node.type === 'valley') {
            detailsHTML += `<div class="info-item"><span>Campfires:</span><span>${node.active_campfires}/${node.total_campfires}</span></div>`;
            const healthPercent = Math.round((node.health_score || 0) * 100);
            detailsHTML += `<div class="info-item"><span>Health:</span><span>${healthPercent}%</span></div>`;
            detailsHTML += `<div class="info-item"><span>Federation:</span><span>${node.federation_status}</span></div>`;
        } else if (node.type === 'campfire') {
            detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.campfire_type}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Campers:</span><span>${node.active_campers}/${node.camper_count}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Queue:</span><span>${node.torch_queue_size}</span></div>`;
            
            if (node.processing_time_avg > 0) {
                detailsHTML += `<div class="info-item"><span>Avg Time:</span><span>${node.processing_time_avg.toFixed(2)}ms</span></div>`;
            }
            
            // Enhanced details
            if (node.current_jobs && node.current_jobs.length > 0) {
                detailsHTML += `<div class="info-section"><h4>Current Jobs (${node.current_jobs.length})</h4>`;
                node.current_jobs.slice(0, 3).forEach(job => {
                    detailsHTML += `<div class="info-item"><span>${job.type}:</span><span>${job.status}</span></div>`;
                });
                detailsHTML += `</div>`;
            }
            
            if (node.party_box_data && node.party_box_data.total_items > 0) {
                detailsHTML += `<div class="info-section"><h4>Party Box</h4>`;
                detailsHTML += `<div class="info-item"><span>Items:</span><span>${node.party_box_data.total_items}</span></div>`;
                if (node.party_box_data.data_types.length > 0) {
                    detailsHTML += `<div class="info-item"><span>Types:</span><span>${node.party_box_data.data_types.join(', ')}</span></div>`;
                }
                detailsHTML += `</div>`;
            }
            
            if (node.performance_metrics) {
                const metrics = node.performance_metrics;
                detailsHTML += `<div class="info-section"><h4>Performance</h4>`;
                if (metrics.throughput > 0) {
                    detailsHTML += `<div class="info-item"><span>Throughput:</span><span>${metrics.throughput.toFixed(2)}/s</span></div>`;
                }
                detailsHTML += `<div class="info-item"><span>Success Rate:</span><span>${Math.round((node.success_rate || 1) * 100)}%</span></div>`;
                if (node.error_count > 0) {
                    detailsHTML += `<div class="info-item"><span>Errors:</span><span>${node.error_count}</span></div>`;
                }
                detailsHTML += `</div>`;
            }
        } else if (node.type === 'camper') {
            detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.camper_type}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Tasks:</span><span>${node.tasks_completed}</span></div>`;
            if (node.current_task) {
                detailsHTML += `<div class="info-item"><span>Current:</span><span>${node.current_task}</span></div>`;
            }
            detailsHTML += `<div class="info-item"><span>CPU:</span><span>${Math.round(node.cpu_usage || 0)}%</span></div>`;
            detailsHTML += `<div class="info-item"><span>Memory:</span><span>${Math.round(node.memory_usage || 0)}%</span></div>`;
        }
        
        nodeDetails.innerHTML = detailsHTML;
        nodeInfo.style.display = 'block';
    }
    
    hideNodeDetails() {
        const nodeInfo = document.getElementById('nodeInfo');
        if (nodeInfo) {
            nodeInfo.style.display = 'none';
        }
    }
    
    // Zoom controls
    zoomIn() {
        this.scale = Math.min(5.0, this.scale * 1.2);
    }
    
    zoomOut() {
        this.scale = Math.max(0.1, this.scale / 1.2);
    }
    
    resetView() {
        this.scale = 1.0;
        this.offsetX = this.canvas.width / 2;
        this.offsetY = this.canvas.height / 2;
    }
    
    // Rendering
    startRenderLoop() {
        const render = (timestamp) => {
            this.render(timestamp);
            this.animationId = requestAnimationFrame(render);
        };
        this.animationId = requestAnimationFrame(render);
    }
    
    render(timestamp) {
        // Clear canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Save context
        this.ctx.save();
        
        // Apply transform
        this.ctx.translate(this.offsetX, this.offsetY);
        this.ctx.scale(this.scale, this.scale);
        
        // Draw grid
        this.drawGrid();
        
        // Draw connections
        this.drawConnections();
        
        // Draw nodes
        this.drawNodes();
        
        // Restore context
        this.ctx.restore();
        
        // Draw UI elements (not transformed)
        this.drawUI();
        
        // Draw tooltips
        this.drawTooltips();
        
        // Update minimap
        this.updateMinimap();
    }
    
    drawGrid() {
        const gridSize = 50;
        const startX = Math.floor(-this.offsetX / this.scale / gridSize) * gridSize;
        const startY = Math.floor(-this.offsetY / this.scale / gridSize) * gridSize;
        const endX = startX + (this.canvas.width / this.scale) + gridSize;
        const endY = startY + (this.canvas.height / this.scale) + gridSize;
        
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
        this.ctx.lineWidth = 1 / this.scale;
        
        this.ctx.beginPath();
        for (let x = startX; x <= endX; x += gridSize) {
            this.ctx.moveTo(x, startY);
            this.ctx.lineTo(x, endY);
        }
        for (let y = startY; y <= endY; y += gridSize) {
            this.ctx.moveTo(startX, y);
            this.ctx.lineTo(endX, y);
        }
        this.ctx.stroke();
    }
    
    drawConnections() {
        if (!document.getElementById('showConnections').checked) return;
        
        this.connections.forEach(connection => {
            const sourceNode = this.nodes.find(n => n.id === connection.source_id);
            const targetNode = this.nodes.find(n => n.id === connection.target_id);
            
            if (sourceNode && targetNode && sourceNode.position && targetNode.position) {
                this.drawConnection(sourceNode.position, targetNode.position, connection);
            }
        });
    }
    
    drawConnection(start, end, connection) {
        this.ctx.strokeStyle = connection.color || '#666';
        this.ctx.lineWidth = (connection.width || 2) / this.scale;
        this.ctx.globalAlpha = 0.7;
        
        this.ctx.beginPath();
        this.ctx.moveTo(start.x, start.y);
        
        // Draw curved connection
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const cp1x = start.x + dx * 0.5;
        const cp1y = start.y;
        const cp2x = end.x - dx * 0.5;
        const cp2y = end.y;
        
        this.ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, end.x, end.y);
        this.ctx.stroke();
        
        // Draw arrow
        this.drawArrow(end.x, end.y, Math.atan2(dy, dx));
        
        this.ctx.globalAlpha = 1.0;
    }
    
    drawArrow(x, y, angle) {
        const arrowSize = 10 / this.scale;
        
        this.ctx.save();
        this.ctx.translate(x, y);
        this.ctx.rotate(angle);
        
        this.ctx.beginPath();
        this.ctx.moveTo(-arrowSize, -arrowSize / 2);
        this.ctx.lineTo(0, 0);
        this.ctx.lineTo(-arrowSize, arrowSize / 2);
        this.ctx.stroke();
        
        this.ctx.restore();
    }
    
    drawNodes() {
        if (this.nodes.length === 0) {
            this.drawEmptyState();
            return;
        }
        
        this.nodes.forEach(node => {
            if (node.position) {
                this.drawNode(node);
            }
        });
    }
    
    drawEmptyState() {
        // Draw empty state within the canvas coordinate system
        this.ctx.save();
        
        // Center the empty state message
        const centerX = 0;
        const centerY = 0;
        
        // Draw background circle
        this.ctx.fillStyle = 'rgba(100, 100, 100, 0.3)';
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, 80 / this.scale, 0, 2 * Math.PI);
        this.ctx.fill();
        
        // Draw border
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
        this.ctx.lineWidth = 2 / this.scale;
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, 80 / this.scale, 0, 2 * Math.PI);
        this.ctx.stroke();
        
        // Draw mountain icon
        this.ctx.fillStyle = '#FFF';
        this.ctx.font = `${40 / this.scale}px Arial`;
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText('🏔️', centerX, centerY - 20 / this.scale);
        
        // Draw "Empty Valley" text
        this.ctx.font = `${16 / this.scale}px Arial`;
        this.ctx.fillText('Empty Valley', centerX, centerY + 20 / this.scale);
        
        // Draw subtitle
        this.ctx.font = `${12 / this.scale}px Arial`;
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        this.ctx.fillText('Start a task to populate the valley', centerX, centerY + 40 / this.scale);
        
        this.ctx.restore();
    }
    
    drawNode(node) {
        const size = this.getNodeSize(node);
        const color = this.getNodeColor(node);
        const x = node.position.x;
        const y = node.position.y;
        
        // Node shadow
        this.ctx.save();
        this.ctx.shadowColor = 'rgba(0, 0, 0, 0.3)';
        this.ctx.shadowBlur = 10 / this.scale;
        this.ctx.shadowOffsetX = 2 / this.scale;
        this.ctx.shadowOffsetY = 2 / this.scale;
        
        // Node background
        this.ctx.fillStyle = color;
        this.ctx.beginPath();
        this.ctx.arc(x, y, size / 2, 0, 2 * Math.PI);
        this.ctx.fill();
        
        this.ctx.restore();
        
        // Node border
        this.ctx.strokeStyle = node === this.selectedNode ? '#FF6B35' : 
                             node === this.hoveredNode ? '#FFF' : 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = (node === this.selectedNode ? 3 : 2) / this.scale;
        this.ctx.beginPath();
        this.ctx.arc(x, y, size / 2, 0, 2 * Math.PI);
        this.ctx.stroke();
        
        // Node icon/text
        this.ctx.fillStyle = '#FFF';
        this.ctx.font = `${Math.max(12, size * 0.3) / this.scale}px Arial`;
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        const icon = node.icon || this.getNodeIcon(node.type);
        this.ctx.fillText(icon, x, y - 5 / this.scale);
        
        // Node label
        if (this.scale > 0.5) {
            this.ctx.font = `${Math.max(10, size * 0.2) / this.scale}px Arial`;
            this.ctx.fillText(node.label || node.id, x, y + size / 2 + 15 / this.scale);
        }
        
        // Status indicator
        if (node.status && node.status !== 'active') {
            this.drawStatusIndicator(x + size / 3, y - size / 3, node.status);
        }
    }
    
    getNodeIcon(type) {
        const icons = {
            'valley': '🏔️',
            'campfire': '🔥',
            'camper': '👤'
        };
        return icons[type] || '⚪';
    }
    
    drawStatusIndicator(x, y, status) {
        const colors = {
            'busy': '#FF9800',
            'error': '#F44336',
            'offline': '#757575'
        };
        
        this.ctx.fillStyle = colors[status] || '#666';
        this.ctx.beginPath();
        this.ctx.arc(x, y, 8 / this.scale, 0, 2 * Math.PI);
        this.ctx.fill();
    }
    
    drawUI() {
        // Draw overlay background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.fillRect(10, 10, 200, 80);
        
        // Draw border
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(10, 10, 200, 80);
        
        // Draw information text
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        this.ctx.font = '12px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`Zoom: ${Math.round(this.scale * 100)}%`, 20, 30);
        this.ctx.fillText(`Nodes: ${this.nodes.length}`, 20, 50);
        this.ctx.fillText(`Position: ${Math.round(-this.offsetX / this.scale)}, ${Math.round(-this.offsetY / this.scale)}`, 20, 70);
        
        // Draw connection status
        const statusColor = this.connectionStatus === 'connected' ? '#4CAF50' : 
                           this.connectionStatus === 'error' ? '#f44336' : '#ff9800';
        this.ctx.fillStyle = statusColor;
        this.ctx.fillText(`● ${this.connectionStatus}`, 120, 30);
        
        // Draw instructions for empty state
        if (this.nodes.length === 0) {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
            this.ctx.fillRect(this.canvas.width / 2 - 150, this.canvas.height - 100, 300, 60);
            
            this.ctx.strokeStyle = 'rgba(255, 107, 53, 0.8)';
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(this.canvas.width / 2 - 150, this.canvas.height - 100, 300, 60);
            
            this.ctx.fillStyle = '#FFF';
            this.ctx.font = '14px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText('💡 Enter a task in the sidebar and click "Start Task"', this.canvas.width / 2, this.canvas.height - 75);
            this.ctx.fillText('to see campfires appear and process your request', this.canvas.width / 2, this.canvas.height - 55);
        }
    }
    
    drawTooltips() {
        if (!this.hoveredNode || !this.mousePos) return;
        
        const node = this.hoveredNode;
        const tooltipWidth = 200;
        const tooltipHeight = 120;
        const padding = 10;
        
        // Position tooltip near mouse but keep it on screen
        let tooltipX = this.mousePos.x + 15;
        let tooltipY = this.mousePos.y - tooltipHeight - 15;
        
        // Adjust if tooltip would go off screen
        if (tooltipX + tooltipWidth > this.canvas.width) {
            tooltipX = this.mousePos.x - tooltipWidth - 15;
        }
        if (tooltipY < 0) {
            tooltipY = this.mousePos.y + 15;
        }
        
        // Draw tooltip background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
        this.ctx.fillRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);
        
        // Draw tooltip border
        this.ctx.strokeStyle = this.getNodeColor(node);
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);
        
        // Draw tooltip content
        this.ctx.fillStyle = '#FFF';
        this.ctx.font = '14px Arial';
        this.ctx.textAlign = 'left';
        
        let textY = tooltipY + 20;
        const lineHeight = 16;
        
        // Title
        this.ctx.font = 'bold 14px Arial';
        this.ctx.fillText(`${node.icon || this.getNodeIcon(node.type)} ${node.label || node.id}`, tooltipX + padding, textY);
        textY += lineHeight + 5;
        
        // Details
        this.ctx.font = '12px Arial';
        this.ctx.fillStyle = '#CCC';
        this.ctx.fillText(`Type: ${node.type}`, tooltipX + padding, textY);
        textY += lineHeight;
        
        this.ctx.fillText(`Status: ${node.status || 'unknown'}`, tooltipX + padding, textY);
        textY += lineHeight;
        
        // Type-specific info
        if (node.type === 'campfire') {
            this.ctx.fillText(`Campers: ${node.active_campers || 0}/${node.camper_count || 0}`, tooltipX + padding, textY);
            textY += lineHeight;
            if (node.torch_queue_size > 0) {
                this.ctx.fillText(`Queue: ${node.torch_queue_size}`, tooltipX + padding, textY);
            }
        } else if (node.type === 'camper') {
            this.ctx.fillText(`Tasks: ${node.tasks_completed || 0}`, tooltipX + padding, textY);
            textY += lineHeight;
            if (node.current_task) {
                this.ctx.fillText(`Current: ${node.current_task.substring(0, 20)}...`, tooltipX + padding, textY);
            }
        } else if (node.type === 'valley') {
            this.ctx.fillText(`Campfires: ${node.active_campfires || 0}/${node.total_campfires || 0}`, tooltipX + padding, textY);
        }
    }
    
    updateMinimap() {
        if (!this.minimap) return;
        
        const ctx = this.minimapCtx;
        ctx.clearRect(0, 0, this.minimap.width, this.minimap.height);
        
        // Draw minimap background
        ctx.fillStyle = '#222';
        ctx.fillRect(0, 0, this.minimap.width, this.minimap.height);
        
        // Calculate minimap scale
        const mapScale = Math.min(this.minimap.width / 1000, this.minimap.height / 1000);
        
        ctx.save();
        ctx.translate(this.minimap.width / 2, this.minimap.height / 2);
        ctx.scale(mapScale, mapScale);
        
        // Draw nodes on minimap
        this.nodes.forEach(node => {
            if (node.position) {
                ctx.fillStyle = this.getNodeColor(node);
                ctx.beginPath();
                ctx.arc(node.position.x, node.position.y, 5, 0, 2 * Math.PI);
                ctx.fill();
            }
        });
        
        // Draw viewport indicator
        const viewX = -this.offsetX / this.scale;
        const viewY = -this.offsetY / this.scale;
        const viewW = this.canvas.width / this.scale;
        const viewH = this.canvas.height / this.scale;
        
        ctx.strokeStyle = '#FF6B35';
        ctx.lineWidth = 2;
        ctx.strokeRect(viewX, viewY, viewW, viewH);
        
        ctx.restore();
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.campfireCanvas = new CampfireCanvas('mainCanvas');
    
    // Setup task controls
    const startTaskBtn = document.getElementById('startTaskBtn');
    const stopTaskBtn = document.getElementById('stopTaskBtn');
    const taskInput = document.getElementById('taskInput');
    
    if (startTaskBtn && stopTaskBtn && taskInput) {
        startTaskBtn.addEventListener('click', () => {
            const task = taskInput.value.trim();
            if (task && window.campfireCanvas.ws && window.campfireCanvas.ws.readyState === WebSocket.OPEN) {
                window.campfireCanvas.ws.send(JSON.stringify({
                    type: 'start_task',
                    data: { description: task }
                }));
                
                startTaskBtn.disabled = true;
                stopTaskBtn.disabled = false;
                taskInput.disabled = true;
            }
        });
        
        stopTaskBtn.addEventListener('click', () => {
            if (window.campfireCanvas.ws && window.campfireCanvas.ws.readyState === WebSocket.OPEN) {
                window.campfireCanvas.ws.send(JSON.stringify({
                    type: 'stop_task',
                    data: {}
                }));
                
                startTaskBtn.disabled = false;
                stopTaskBtn.disabled = true;
                taskInput.disabled = false;
            }
        });
    }
    
    // Setup fullscreen toggle
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', () => {
            const mainArea = document.querySelector('.main-area');
            if (!document.fullscreenElement) {
                mainArea.requestFullscreen().then(() => {
                    // Hide sidebar in fullscreen
                    document.querySelector('.sidebar').style.display = 'none';
                    // Resize canvas to fill screen
                    window.campfireCanvas.resizeCanvas();
                }).catch(err => {
                    console.log('Error attempting to enable fullscreen:', err);
                });
            } else {
                document.exitFullscreen().then(() => {
                    // Show sidebar when exiting fullscreen
                    document.querySelector('.sidebar').style.display = 'block';
                    // Resize canvas back to normal
                    window.campfireCanvas.resizeCanvas();
                });
            }
        });
    }
    
    // Listen for fullscreen changes
    document.addEventListener('fullscreenchange', () => {
        const sidebar = document.querySelector('.sidebar');
        if (document.fullscreenElement) {
            sidebar.style.display = 'none';
        } else {
            sidebar.style.display = 'block';
        }
        // Always resize canvas when fullscreen state changes
        setTimeout(() => window.campfireCanvas.resizeCanvas(), 100);
    });
});