/**
 * CampfireValley Node-based Visualization
 * ComfyUI-style interface for valley, campfires, and campers
 */

class ValleyVisualization {
    constructor() {
        this.canvas = document.getElementById('canvas');
        this.loading = document.getElementById('loading');
        this.nodeInfo = document.getElementById('nodeInfo');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.connectionText = document.getElementById('connectionText');
        
        // Visualization state
        this.nodes = new Map();
        this.connections = new Map();
        this.selectedNode = null;
        this.viewMode = 'overview';
        this.zoomLevel = 1.0;
        this.panOffset = { x: 0, y: 0 };
        this.isDragging = false;
        this.dragStart = { x: 0, y: 0 };
        
        // WebSocket connection
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        // Animation
        this.animationFrame = null;
        this.lastUpdate = 0;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.startAnimationLoop();
    }
    
    setupEventListeners() {
        // View mode controls
        document.getElementById('viewMode').addEventListener('change', (e) => {
            this.viewMode = e.target.value;
            this.updateView();
        });
        
        // Zoom controls
        document.getElementById('zoomIn').addEventListener('click', () => this.zoomIn());
        document.getElementById('zoomOut').addEventListener('click', () => this.zoomOut());
        document.getElementById('resetView').addEventListener('click', () => this.resetView());
        
        // Filter
        document.getElementById('filterInput').addEventListener('input', (e) => {
            this.filterNodes(e.target.value);
        });
        
        // Checkboxes
        document.getElementById('showConnections').addEventListener('change', (e) => {
            this.toggleConnections(e.target.checked);
        });
        
        document.getElementById('showTorchFlow').addEventListener('change', (e) => {
            this.toggleTorchFlow(e.target.checked);
        });
        
        document.getElementById('autoRefresh').addEventListener('change', (e) => {
            this.toggleAutoRefresh(e.target.checked);
        });
        
        // Canvas interactions
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.onMouseUp(e));
        this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
        this.canvas.addEventListener('click', (e) => this.onClick(e));
        
        // Toolbar buttons
        document.getElementById('fullscreenBtn').addEventListener('click', () => this.toggleFullscreen());
        document.getElementById('exportBtn').addEventListener('click', () => this.exportView());
        document.getElementById('settingsBtn').addEventListener('click', () => this.showSettings());
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.onKeyDown(e));
        
        // Window resize
        window.addEventListener('resize', () => this.onResize());
    }
    
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.connectionText.textContent = 'Connected';
                this.connectionStatus.className = 'connection-status connected';
                this.reconnectAttempts = 0;
                this.requestInitialState();
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.connectionText.textContent = 'Disconnected';
                this.connectionStatus.className = 'connection-status disconnected';
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.connectionText.textContent = 'Connection Error';
                this.connectionStatus.className = 'connection-status disconnected';
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.connectionText.textContent = 'Connection Failed';
            this.connectionStatus.className = 'connection-status disconnected';
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            setTimeout(() => this.connectWebSocket(), delay);
        }
    }
    
    requestInitialState() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'get_state',
                data: {}
            }));
        }
    }
    
    handleWebSocketMessage(message) {
        switch (message.type) {
            case 'state_update':
                this.updateVisualizationState(message.data);
                break;
            case 'node_update':
                this.updateNode(message.data);
                break;
            case 'connection_update':
                this.updateConnection(message.data);
                break;
            case 'error':
                console.error('Server error:', message.data);
                break;
            default:
                console.warn('Unknown message type:', message.type);
        }
    }
    
    updateVisualizationState(state) {
        this.loading.style.display = 'none';
        
        // Update nodes
        this.nodes.clear();
        state.nodes.forEach(nodeData => {
            this.nodes.set(nodeData.id, nodeData);
        });
        
        // Update connections
        this.connections.clear();
        state.connections.forEach(connData => {
            this.connections.set(connData.id, connData);
        });
        
        this.renderVisualization();
    }
    
    updateNode(nodeUpdate) {
        if (this.nodes.has(nodeUpdate.id)) {
            const node = this.nodes.get(nodeUpdate.id);
            Object.assign(node, nodeUpdate);
            this.renderNode(node);
        }
    }
    
    updateConnection(connectionUpdate) {
        if (this.connections.has(connectionUpdate.id)) {
            const connection = this.connections.get(connectionUpdate.id);
            Object.assign(connection, connectionUpdate);
            this.renderConnection(connection);
        }
    }
    
    renderVisualization() {
        // Clear canvas
        this.canvas.innerHTML = '';
        
        // Create SVG for connections
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.style.position = 'absolute';
        svg.style.top = '0';
        svg.style.left = '0';
        svg.style.width = '100%';
        svg.style.height = '100%';
        svg.style.pointerEvents = 'none';
        svg.style.zIndex = '1';
        this.canvas.appendChild(svg);
        
        // Render connections first (behind nodes)
        this.connections.forEach(connection => {
            this.renderConnection(connection, svg);
        });
        
        // Render nodes
        this.nodes.forEach(node => {
            if (this.shouldShowNode(node)) {
                this.renderNode(node);
            }
        });
        
        this.updateMinimap();
    }
    
    shouldShowNode(node) {
        switch (this.viewMode) {
            case 'overview':
                return node.type === 'valley' || node.type === 'campfire';
            case 'campfires':
                return node.type === 'valley' || node.type === 'campfire';
            case 'campers':
                return true;
            default:
                return true;
        }
    }
    
    renderNode(node) {
        const nodeElement = document.createElement('div');
        nodeElement.className = 'node';
        nodeElement.id = `node-${node.id}`;
        nodeElement.dataset.nodeId = node.id;
        
        // Apply positioning and styling
        const transform = this.getNodeTransform(node.position);
        nodeElement.style.transform = transform;
        nodeElement.style.width = `${node.size || 50}px`;
        nodeElement.style.height = `${node.size || 50}px`;
        nodeElement.style.backgroundColor = node.color || '#50E3C2';
        nodeElement.style.zIndex = '10';
        
        // Add status classes
        nodeElement.classList.add(`status-${node.status.toLowerCase()}`);
        
        // Add icon
        nodeElement.textContent = node.icon || '🔥';
        
        // Add label
        const label = document.createElement('div');
        label.className = 'node-label';
        label.textContent = node.label;
        nodeElement.appendChild(label);
        
        // Add click handler
        nodeElement.addEventListener('click', (e) => {
            e.stopPropagation();
            this.selectNode(node);
        });
        
        this.canvas.appendChild(nodeElement);
    }
    
    renderConnection(connection, svg) {
        if (!document.getElementById('showConnections').checked && connection.type !== 'torch_flow') {
            return;
        }
        
        if (!document.getElementById('showTorchFlow').checked && connection.type === 'torch_flow') {
            return;
        }
        
        const sourceNode = this.nodes.get(connection.source_id);
        const targetNode = this.nodes.get(connection.target_id);
        
        if (!sourceNode || !targetNode) return;
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        
        const sourcePos = this.transformPosition(sourceNode.position);
        const targetPos = this.transformPosition(targetNode.position);
        
        line.setAttribute('x1', sourcePos.x);
        line.setAttribute('y1', sourcePos.y);
        line.setAttribute('x2', targetPos.x);
        line.setAttribute('y2', targetPos.y);
        line.setAttribute('stroke', connection.color || '#888888');
        line.setAttribute('stroke-width', connection.width || 2);
        line.setAttribute('opacity', '0.8');
        
        if (connection.animated) {
            line.classList.add('connection-animated');
        }
        
        svg.appendChild(line);
    }
    
    getNodeTransform(position) {
        const transformed = this.transformPosition(position);
        return `translate(${transformed.x - 25}px, ${transformed.y - 25}px) scale(${this.zoomLevel})`;
    }
    
    transformPosition(position) {
        const canvasRect = this.canvas.getBoundingClientRect();
        const centerX = canvasRect.width / 2;
        const centerY = canvasRect.height / 2;
        
        return {
            x: centerX + (position.x + this.panOffset.x) * this.zoomLevel,
            y: centerY + (position.y + this.panOffset.y) * this.zoomLevel
        };
    }
    
    selectNode(node) {
        // Remove previous selection
        const prevSelected = this.canvas.querySelector('.node.selected');
        if (prevSelected) {
            prevSelected.classList.remove('selected');
        }
        
        // Select new node
        const nodeElement = document.getElementById(`node-${node.id}`);
        if (nodeElement) {
            nodeElement.classList.add('selected');
        }
        
        this.selectedNode = node;
        this.showNodeDetails(node);
    }
    
    showNodeDetails(node) {
        const nodeTitle = document.getElementById('nodeTitle');
        const nodeDetails = document.getElementById('nodeDetails');
        
        nodeTitle.textContent = `${node.icon} ${node.label}`;
        
        let detailsHTML = '';
        
        // Common details
        detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.type}</span></div>`;
        detailsHTML += `<div class="info-item"><span>Status:</span><span><span class="status-indicator status-${node.status.toLowerCase()}"></span>${node.status}</span></div>`;
        
        // Type-specific details
        if (node.type === 'valley') {
            detailsHTML += `<div class="info-item"><span>Campfires:</span><span>${node.active_campfires}/${node.total_campfires}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Health:</span><span>${Math.round(node.health_score * 100)}%</span></div>`;
            detailsHTML += `<div class="info-item"><span>Federation:</span><span>${node.federation_status}</span></div>`;
        } else if (node.type === 'campfire') {
            detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.campfire_type}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Campers:</span><span>${node.active_campers}/${node.camper_count}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Queue:</span><span>${node.torch_queue_size}</span></div>`;
            if (node.processing_time_avg > 0) {
                detailsHTML += `<div class="info-item"><span>Avg Time:</span><span>${node.processing_time_avg.toFixed(2)}ms</span></div>`;
            }
        } else if (node.type === 'camper') {
            detailsHTML += `<div class="info-item"><span>Type:</span><span>${node.camper_type}</span></div>`;
            detailsHTML += `<div class="info-item"><span>Tasks:</span><span>${node.tasks_completed}</span></div>`;
            if (node.current_task) {
                detailsHTML += `<div class="info-item"><span>Current:</span><span>${node.current_task}</span></div>`;
            }
            detailsHTML += `<div class="info-item"><span>CPU:</span><span>${Math.round(node.cpu_usage)}%</span></div>`;
            detailsHTML += `<div class="info-item"><span>Memory:</span><span>${Math.round(node.memory_usage)}%</span></div>`;
        }
        
        nodeDetails.innerHTML = detailsHTML;
        this.nodeInfo.style.display = 'block';
    }
    
    // Interaction handlers
    onMouseDown(e) {
        if (e.target === this.canvas) {
            this.isDragging = true;
            this.dragStart = { x: e.clientX, y: e.clientY };
            this.canvas.style.cursor = 'grabbing';
        }
    }
    
    onMouseMove(e) {
        if (this.isDragging) {
            const deltaX = e.clientX - this.dragStart.x;
            const deltaY = e.clientY - this.dragStart.y;
            
            this.panOffset.x += deltaX / this.zoomLevel;
            this.panOffset.y += deltaY / this.zoomLevel;
            
            this.dragStart = { x: e.clientX, y: e.clientY };
            this.renderVisualization();
        }
    }
    
    onMouseUp(e) {
        this.isDragging = false;
        this.canvas.style.cursor = 'grab';
    }
    
    onWheel(e) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        this.zoomLevel = Math.max(0.1, Math.min(5.0, this.zoomLevel * delta));
        this.renderVisualization();
    }
    
    onClick(e) {
        if (e.target === this.canvas) {
            this.selectedNode = null;
            this.nodeInfo.style.display = 'none';
            
            const prevSelected = this.canvas.querySelector('.node.selected');
            if (prevSelected) {
                prevSelected.classList.remove('selected');
            }
        }
    }
    
    onKeyDown(e) {
        switch (e.key) {
            case 'Escape':
                this.selectedNode = null;
                this.nodeInfo.style.display = 'none';
                break;
            case '+':
            case '=':
                this.zoomIn();
                break;
            case '-':
                this.zoomOut();
                break;
            case '0':
                this.resetView();
                break;
        }
    }
    
    onResize() {
        this.renderVisualization();
    }
    
    // Control methods
    zoomIn() {
        this.zoomLevel = Math.min(5.0, this.zoomLevel * 1.2);
        this.renderVisualization();
    }
    
    zoomOut() {
        this.zoomLevel = Math.max(0.1, this.zoomLevel * 0.8);
        this.renderVisualization();
    }
    
    resetView() {
        this.zoomLevel = 1.0;
        this.panOffset = { x: 0, y: 0 };
        this.renderVisualization();
    }
    
    filterNodes(query) {
        const lowerQuery = query.toLowerCase();
        this.nodes.forEach((node, id) => {
            const nodeElement = document.getElementById(`node-${id}`);
            if (nodeElement) {
                const matches = node.label.toLowerCase().includes(lowerQuery) ||
                               node.type.toLowerCase().includes(lowerQuery);
                nodeElement.style.display = matches ? 'block' : 'none';
            }
        });
    }
    
    toggleConnections(show) {
        this.renderVisualization();
    }
    
    toggleTorchFlow(show) {
        this.renderVisualization();
    }
    
    toggleAutoRefresh(enabled) {
        // Implementation for auto-refresh toggle
        console.log('Auto refresh:', enabled);
    }
    
    updateView() {
        this.renderVisualization();
    }
    
    updateMinimap() {
        // Simplified minimap implementation
        const minimap = document.getElementById('minimap');
        const canvas = minimap.querySelector('canvas');
        const ctx = canvas.getContext('2d');
        
        ctx.clearRect(0, 0, 200, 150);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.1)';
        ctx.fillRect(0, 0, 200, 150);
        
        // Draw simplified nodes
        this.nodes.forEach(node => {
            if (this.shouldShowNode(node)) {
                ctx.fillStyle = node.color || '#50E3C2';
                const x = (node.position.x + 500) / 10; // Scale down
                const y = (node.position.y + 500) / 10;
                ctx.fillRect(x - 2, y - 2, 4, 4);
            }
        });
    }
    
    // Toolbar methods
    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }
    
    exportView() {
        // Implementation for exporting the current view
        console.log('Export view');
    }
    
    showSettings() {
        // Implementation for settings dialog
        console.log('Show settings');
    }
    
    startAnimationLoop() {
        const animate = (timestamp) => {
            if (timestamp - this.lastUpdate > 16) { // ~60fps
                this.updateAnimations();
                this.lastUpdate = timestamp;
            }
            this.animationFrame = requestAnimationFrame(animate);
        };
        this.animationFrame = requestAnimationFrame(animate);
    }
    
    updateAnimations() {
        // Update any animated elements
        const animatedConnections = this.canvas.querySelectorAll('.connection-animated');
        // Animation is handled by CSS, but we could add more complex animations here
    }
    
    destroy() {
        if (this.ws) {
            this.ws.close();
        }
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
    }
}

// Initialize the visualization when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.valleyViz = new ValleyVisualization();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.valleyViz) {
        window.valleyViz.destroy();
    }
});