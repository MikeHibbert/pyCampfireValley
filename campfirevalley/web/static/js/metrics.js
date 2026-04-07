/**
 * CampfireValley Metrics Dashboard
 * Handles fetching and displaying Prometheus metrics
 */

class MetricsDashboard {
    constructor() {
        this.isCollapsed = false;
        this.updateInterval = null;
        this.refreshRate = 5000; // 5 seconds
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.startMetricsUpdates();
    }
    
    setupEventListeners() {
        const toggleBtn = document.getElementById('toggleMetrics');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.togglePanel());
        }
    }
    
    togglePanel() {
        const panel = document.getElementById('metricsPanel');
        const toggleBtn = document.getElementById('toggleMetrics');
        
        if (this.isCollapsed) {
            panel.classList.remove('collapsed');
            toggleBtn.textContent = 'Hide';
            this.isCollapsed = false;
        } else {
            panel.classList.add('collapsed');
            toggleBtn.textContent = 'Show';
            this.isCollapsed = true;
        }
    }
    
    async fetchMetrics() {
        try {
            const response = await fetch('/metrics');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const metricsText = await response.text();
            return this.parsePrometheusMetrics(metricsText);
        } catch (error) {
            console.error('Failed to fetch metrics:', error);
            return null;
        }
    }

    async fetchDock() {
        try {
            const [mcpRes, dockRes, valleysRes] = await Promise.all([
                fetch('/api/mcp/status'),
                fetch('/api/dock/status'),
                fetch('/api/dock/valleys')
            ]);
            const mcp = mcpRes.ok ? await mcpRes.json() : null;
            const dock = dockRes.ok ? await dockRes.json() : null;
            const valleys = valleysRes.ok ? await valleysRes.json() : null;
            return { mcp, dock, valleys };
        } catch (e) {
            return { mcp: null, dock: null, valleys: null };
        }
    }
    
    parsePrometheusMetrics(metricsText) {
        const metrics = {};
        const lines = metricsText.split('\n');
        
        for (const line of lines) {
            if (line.startsWith('#') || line.trim() === '') {
                continue;
            }
            
            const match = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})?) (.+)$/);
            if (match) {
                const [, metricName, value] = match;
                
                // Extract metric name without labels
                const baseName = metricName.split('{')[0];
                
                if (!metrics[baseName]) {
                    metrics[baseName] = [];
                }
                
                metrics[baseName].push({
                    name: metricName,
                    value: parseFloat(value)
                });
            }
        }
        
        return metrics;
    }
    
    updateMetricsDisplay(metrics) {
        if (!metrics) return;
        
        // Update campfire performance metrics
        this.updateCampfireMetrics(metrics);
        
        // Update node metrics
        this.updateNodeMetrics(metrics);
    }

    updateDockDisplay(dockData) {
        const dockMetrics = document.getElementById('dockMetrics');
        const dockValleys = document.getElementById('dockValleys');
        const dockModeSelect = document.getElementById('dockMode');
        if (!dockMetrics || !dockValleys) return;

        dockMetrics.innerHTML = '';
        dockValleys.innerHTML = '';

        const mcp = dockData && dockData.mcp;
        const dock = dockData && dockData.dock;
        const valleys = dockData && dockData.valleys;

        const line = (label, value) => {
            const el = document.createElement('div');
            el.className = 'node-metric';
            const left = document.createElement('span');
            left.className = 'node-name';
            left.textContent = label;
            const right = document.createElement('span');
            right.className = 'node-status idle';
            right.textContent = value;
            el.appendChild(left);
            el.appendChild(right);
            return el;
        };

        if (!mcp || !dock) {
            dockMetrics.appendChild(line('MCP', 'Unavailable'));
            return;
        }

        dockMetrics.appendChild(line('MCP', mcp.connected ? 'Connected' : 'Disconnected'));
        dockMetrics.appendChild(line('Dock', dock.running ? `Running (${dock.mode || 'unknown'})` : 'Stopped'));
        dockMetrics.appendChild(line('Known Valleys', String(dock.known_valleys ?? 0)));
        if (dockModeSelect && dock.mode) {
            dockModeSelect.value = dock.mode;
        }

        const list = (valleys && valleys.valleys) || [];
        if (!Array.isArray(list) || list.length === 0) {
            const el = document.createElement('div');
            el.className = 'node-metric';
            const left = document.createElement('span');
            left.className = 'node-name';
            left.textContent = 'No remote valleys';
            el.appendChild(left);
            dockValleys.appendChild(el);
            return;
        }

        list.forEach((v) => {
            const el = document.createElement('div');
            el.className = 'node-metric';
            const left = document.createElement('span');
            left.className = 'node-name';
            left.textContent = v.name;
            const right = document.createElement('span');
            right.className = 'node-status active';
            right.textContent = `${(v.exposed_campfires || []).length} campfires`;
            el.appendChild(left);
            el.appendChild(right);
            dockValleys.appendChild(el);
        });
    }
    
    updateCampfireMetrics(metrics) {
        // Total requests
        if (metrics.campfire_requests_total) {
            const totalRequests = metrics.campfire_requests_total.reduce((sum, metric) => sum + metric.value, 0);
            this.updateElement('totalRequests', Math.round(totalRequests));
        }
        
        // Active connections
        if (metrics.campfire_active_connections) {
            const activeConnections = metrics.campfire_active_connections.reduce((sum, metric) => sum + metric.value, 0);
            this.updateElement('activeConnections', Math.round(activeConnections));
        }
        
        // Average processing time
        if (metrics.campfire_processing_time_seconds) {
            const processingTimes = metrics.campfire_processing_time_seconds;
            if (processingTimes.length > 0) {
                const avgTime = processingTimes.reduce((sum, metric) => sum + metric.value, 0) / processingTimes.length;
                this.updateElement('avgProcessingTime', `${(avgTime * 1000).toFixed(1)}ms`);
            }
        }
        
        // Error rate
        if (metrics.campfire_error_rate) {
            const errorRates = metrics.campfire_error_rate;
            if (errorRates.length > 0) {
                const avgErrorRate = errorRates.reduce((sum, metric) => sum + metric.value, 0) / errorRates.length;
                this.updateElement('errorRate', `${(avgErrorRate * 100).toFixed(1)}%`);
            }
        }
    }
    
    updateNodeMetrics(metrics) {
        const nodeMetricsContainer = document.getElementById('nodeMetrics');
        if (!nodeMetricsContainer) return;
        
        // Clear existing node metrics
        nodeMetricsContainer.innerHTML = '';
        
        // Collect node data from various metrics
        const nodeData = {};
        
        // Process torch queue size metrics
        if (metrics.campfire_torch_queue_size) {
            metrics.campfire_torch_queue_size.forEach(metric => {
                const campfireId = this.extractLabelValue(metric.name, 'campfire_id');
                if (campfireId) {
                    if (!nodeData[campfireId]) nodeData[campfireId] = {};
                    nodeData[campfireId].queueSize = metric.value;
                }
            });
        }
        
        // Process camper count metrics
        if (metrics.campfire_camper_count) {
            metrics.campfire_camper_count.forEach(metric => {
                const campfireId = this.extractLabelValue(metric.name, 'campfire_id');
                if (campfireId) {
                    if (!nodeData[campfireId]) nodeData[campfireId] = {};
                    nodeData[campfireId].camperCount = metric.value;
                }
            });
        }
        
        // Process throughput metrics
        if (metrics.campfire_throughput) {
            metrics.campfire_throughput.forEach(metric => {
                const campfireId = this.extractLabelValue(metric.name, 'campfire_id');
                if (campfireId) {
                    if (!nodeData[campfireId]) nodeData[campfireId] = {};
                    nodeData[campfireId].throughput = metric.value;
                }
            });
        }
        
        // Create node metric elements
        Object.entries(nodeData).forEach(([nodeId, data]) => {
            const nodeElement = this.createNodeMetricElement(nodeId, data);
            nodeMetricsContainer.appendChild(nodeElement);
        });
        
        // If no nodes, show placeholder
        if (Object.keys(nodeData).length === 0) {
            nodeMetricsContainer.innerHTML = '<div class="node-metric"><span class="node-name">No active nodes</span></div>';
        }
    }
    
    extractLabelValue(metricName, labelName) {
        const match = metricName.match(new RegExp(`${labelName}="([^"]+)"`));
        return match ? match[1] : null;
    }
    
    createNodeMetricElement(nodeId, data) {
        const element = document.createElement('div');
        element.className = 'node-metric';
        
        const nodeName = document.createElement('span');
        nodeName.className = 'node-name';
        nodeName.textContent = nodeId;
        
        const nodeStatus = document.createElement('span');
        nodeStatus.className = 'node-status';
        
        // Determine status based on metrics
        if (data.throughput > 0) {
            nodeStatus.className += ' active';
            nodeStatus.textContent = 'Active';
        } else if (data.queueSize > 0) {
            nodeStatus.className += ' idle';
            nodeStatus.textContent = 'Queued';
        } else {
            nodeStatus.className += ' idle';
            nodeStatus.textContent = 'Idle';
        }
        
        element.appendChild(nodeName);
        element.appendChild(nodeStatus);
        
        // Add tooltip with detailed info
        const details = [];
        if (data.queueSize !== undefined) details.push(`Queue: ${data.queueSize}`);
        if (data.camperCount !== undefined) details.push(`Campers: ${data.camperCount}`);
        if (data.throughput !== undefined) details.push(`Throughput: ${data.throughput.toFixed(2)}/s`);
        
        if (details.length > 0) {
            element.title = details.join(', ');
        }
        
        return element;
    }
    
    updateElement(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }
    
    startMetricsUpdates() {
        // Initial fetch
        this.updateMetrics();
        
        // Set up periodic updates
        this.updateInterval = setInterval(() => {
            this.updateMetrics();
        }, this.refreshRate);
    }
    
    async updateMetrics() {
        const metrics = await this.fetchMetrics();
        this.updateMetricsDisplay(metrics);

        const dockData = await this.fetchDock();
        this.updateDockDisplay(dockData);
    }
    
    stopMetricsUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    destroy() {
        this.stopMetricsUpdates();
    }
}

// Initialize metrics dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.metricsDashboard = new MetricsDashboard();
    window.metricsDashboard.startMetricsUpdates();

    const dockEnable = document.getElementById('dockEnable');
    const dockMode = document.getElementById('dockMode');
    const dockBroadcast = document.getElementById('dockBroadcast');
    if (dockEnable) {
        dockEnable.addEventListener('click', async () => {
            try {
                dockEnable.textContent = 'Enabling...';
                const res = await fetch('/api/dock/enable', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                if (!res.ok) {
                    dockEnable.textContent = 'Enable failed';
                    return;
                }
                await res.json();
                dockEnable.textContent = 'Enabled';
                setTimeout(() => {
                    dockEnable.textContent = 'Enable Dock';
                }, 2000);
                window.metricsDashboard.updateMetrics();
                if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.syncBackendCampfireNodes) {
                    window.campfireValleyLiteGraph.syncBackendCampfireNodes();
                }
            } catch (e) {
                dockEnable.textContent = 'Enable failed';
            }
        });
    }

    if (dockMode) {
        dockMode.addEventListener('change', async () => {
            try {
                const mode = dockMode.value;
                await fetch('/api/dock/mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                window.metricsDashboard.updateMetrics();
                if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.syncBackendCampfireNodes) {
                    window.campfireValleyLiteGraph.syncBackendCampfireNodes();
                }
            } catch (e) {
            }
        });
    }

    if (dockBroadcast) {
        dockBroadcast.addEventListener('click', async () => {
            try {
                dockBroadcast.textContent = 'Broadcasting...';
                const res = await fetch('/api/dock/broadcast', { method: 'POST' });
                if (!res.ok) {
                    dockBroadcast.textContent = 'Broadcast failed';
                    return;
                }
                dockBroadcast.textContent = 'Broadcasted';
                setTimeout(() => {
                    dockBroadcast.textContent = 'Broadcast Discovery';
                }, 2000);
                window.metricsDashboard.updateMetrics();
                if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.syncBackendCampfireNodes) {
                    window.campfireValleyLiteGraph.syncBackendCampfireNodes();
                }
            } catch (e) {
                dockBroadcast.textContent = 'Broadcast failed';
            }
        });
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (window.metricsDashboard) {
        window.metricsDashboard.destroy();
    }
});
