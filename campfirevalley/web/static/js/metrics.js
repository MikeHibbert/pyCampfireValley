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
            const [mcpRes, dockRes, valleysRes, valleyRes] = await Promise.all([
                fetch('/api/mcp/status'),
                fetch('/api/dock/status'),
                fetch('/api/dock/valleys'),
                fetch('/api/valley/details')
            ]);
            const mcp = mcpRes.ok ? await mcpRes.json() : null;
            const dock = dockRes.ok ? await dockRes.json() : null;
            const valleys = valleysRes.ok ? await valleysRes.json() : null;
            const valley = valleyRes.ok ? await valleyRes.json() : null;
            return { mcp, dock, valleys, valley };
        } catch (e) {
            return { mcp: null, dock: null, valleys: null, valley: null };
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
        const valleySummary = document.getElementById('valleySummary');
        const dockMetrics = document.getElementById('dockMetrics');
        const dockValleys = document.getElementById('dockValleys');
        const dockModeSelect = document.getElementById('dockMode');
        const dockEnable = document.getElementById('dockEnable');
        if (!valleySummary || !dockMetrics || !dockValleys) return;

        valleySummary.innerHTML = '';
        dockMetrics.innerHTML = '';
        dockValleys.innerHTML = '';

        const mcp = dockData && dockData.mcp;
        const dock = dockData && dockData.dock;
        const valleys = dockData && dockData.valleys;
        const valley = dockData && dockData.valley && dockData.valley.valley ? dockData.valley.valley : null;

        if (valley) {
            valleySummary.appendChild(this.createValleySummaryCard(valley));
        } else {
            valleySummary.appendChild(this.createEmptyCard('Valley data unavailable'));
        }

        if (!mcp || !dock) {
            dockMetrics.appendChild(this.createStatusCard('MCP Broker', 'Unavailable', 'error', 'Could not load dock state from the backend.'));
            if (dockEnable) {
                dockEnable.disabled = false;
                dockEnable.textContent = 'Enable Dock';
            }
            return;
        }

        dockMetrics.appendChild(this.createStatusCard(
            'MCP Broker',
            mcp.connected ? 'Connected' : 'Disconnected',
            mcp.connected ? 'good' : 'warn',
            mcp.connected ? 'Dock messaging is available.' : 'Dock messaging is currently unavailable.'
        ));
        dockMetrics.appendChild(this.createDockStatusCard(dock));
        if (dockModeSelect && dock.mode) {
            dockModeSelect.value = dock.mode;
        }
        if (dockEnable) {
            dockEnable.disabled = !!dock.running;
            dockEnable.textContent = dock.running ? 'Dock Running' : 'Enable Dock';
        }

        const list = (valleys && valleys.valleys) || [];
        if (!Array.isArray(list) || list.length === 0) {
            dockValleys.appendChild(this.createEmptyCard('No remote valleys discovered yet.'));
            return;
        }

        list.forEach((v) => {
            dockValleys.appendChild(this.createRemoteValleyCard(v));
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
            nodeMetricsContainer.innerHTML = '';
            nodeMetricsContainer.appendChild(this.createEmptyCard('No campfire health metrics yet.'));
        }
    }
    
    extractLabelValue(metricName, labelName) {
        const match = metricName.match(new RegExp(`${labelName}="([^"]+)"`));
        return match ? match[1] : null;
    }
    
    createNodeMetricElement(nodeId, data) {
        const element = document.createElement('div');
        element.className = 'sidebar-card';

        const head = document.createElement('div');
        head.className = 'sidebar-card-head';

        const nodeName = document.createElement('div');
        nodeName.className = 'sidebar-card-title';
        nodeName.textContent = nodeId;

        const nodeStatus = document.createElement('span');
        nodeStatus.className = 'sidebar-badge';

        if (data.throughput > 0) {
            nodeStatus.className += ' good';
            nodeStatus.textContent = 'Active';
        } else if (data.queueSize > 0) {
            nodeStatus.className += ' warn';
            nodeStatus.textContent = 'Queued';
        } else {
            nodeStatus.className += ' warn';
            nodeStatus.textContent = 'Idle';
        }
        head.appendChild(nodeName);
        head.appendChild(nodeStatus);
        element.appendChild(head);

        const rows = [
            ['Queue', data.queueSize !== undefined ? String(data.queueSize) : '0'],
            ['Campers', data.camperCount !== undefined ? String(data.camperCount) : '0'],
            ['Throughput', data.throughput !== undefined ? `${data.throughput.toFixed(2)}/s` : '0.00/s']
        ];
        rows.forEach(([label, value]) => element.appendChild(this.createSidebarRow(label, value)));
        return element;
    }

    shortId(value) {
        const text = String(value || '').trim();
        if (!text) return '';
        if (text.length <= 18) return text;
        return `${text.slice(0, 8)}...${text.slice(-8)}`;
    }

    createSidebarRow(label, value) {
        const row = document.createElement('div');
        row.className = 'sidebar-row';
        const left = document.createElement('span');
        left.textContent = label;
        const right = document.createElement('span');
        right.textContent = value;
        row.appendChild(left);
        row.appendChild(right);
        return row;
    }

    createEmptyCard(text) {
        const card = document.createElement('div');
        card.className = 'sidebar-card warn';
        const body = document.createElement('div');
        body.className = 'sidebar-meta';
        body.textContent = text;
        card.appendChild(body);
        return card;
    }

    createStatusCard(title, statusText, tone, detail) {
        const card = document.createElement('div');
        card.className = 'sidebar-card';
        const head = document.createElement('div');
        head.className = 'sidebar-card-head';
        const name = document.createElement('div');
        name.className = 'sidebar-card-title';
        name.textContent = title;
        const badge = document.createElement('span');
        badge.className = `sidebar-badge ${tone || 'warn'}`;
        badge.textContent = statusText;
        head.appendChild(name);
        head.appendChild(badge);
        card.appendChild(head);
        if (detail) {
            const meta = document.createElement('div');
            meta.className = 'sidebar-meta';
            meta.textContent = detail;
            card.appendChild(meta);
        }
        return card;
    }

    createValleySummaryCard(valley) {
        const card = document.createElement('div');
        card.className = 'sidebar-card local';

        const head = document.createElement('div');
        head.className = 'sidebar-card-head';
        const title = document.createElement('div');
        title.className = 'sidebar-card-title';
        title.textContent = String(valley.name || 'Local Valley');
        const badge = document.createElement('span');
        badge.className = 'sidebar-badge local';
        badge.textContent = 'Local';
        head.appendChild(title);
        head.appendChild(badge);
        card.appendChild(head);

        const meta = document.createElement('div');
        meta.className = 'sidebar-meta';
        meta.textContent = `Stable ID: ${this.shortId(valley.identifier) || '(not set)'}`;
        card.appendChild(meta);

        const kpis = document.createElement('div');
        kpis.className = 'sidebar-kpi-grid';
        [
            ['Campfires', String(valley.campfire_total ?? 0)],
            ['Campers', String(valley.camper_total ?? 0)],
            ['Auditors', String((valley.auditor_campfires || []).length)]
        ].forEach(([label, value]) => {
            const item = document.createElement('div');
            item.className = 'sidebar-kpi';
            item.innerHTML = `<div class="sidebar-kpi-label">${label}</div><div class="sidebar-kpi-value">${value}</div>`;
            kpis.appendChild(item);
        });
        card.appendChild(kpis);

        const campfireNames = document.createElement('div');
        campfireNames.className = 'sidebar-list';
        const names = Array.isArray(valley.campfires) && valley.campfires.length ? valley.campfires.join(', ') : '(none)';
        campfireNames.textContent = `Campfires: ${names}`;
        card.appendChild(campfireNames);
        return card;
    }

    createDockStatusCard(dock) {
        const card = document.createElement('div');
        card.className = 'sidebar-card';

        const head = document.createElement('div');
        head.className = 'sidebar-card-head';
        const title = document.createElement('div');
        title.className = 'sidebar-card-title';
        title.textContent = 'Dock Routing';
        const badge = document.createElement('span');
        const running = !!dock.running;
        badge.className = `sidebar-badge ${running ? 'good' : 'warn'}`;
        badge.textContent = running ? 'Running' : 'Idle';
        head.appendChild(title);
        head.appendChild(badge);
        card.appendChild(head);

        card.appendChild(this.createSidebarRow('Mode', String(dock.mode || 'unknown')));
        card.appendChild(this.createSidebarRow('Known Valleys', String(dock.known_valleys ?? 0)));
        return card;
    }

    createRemoteValleyCard(valley) {
        const card = document.createElement('div');
        card.className = 'sidebar-card remote';

        const head = document.createElement('div');
        head.className = 'sidebar-card-head';
        const title = document.createElement('div');
        title.className = 'sidebar-card-title';
        title.textContent = String(valley.name || 'Remote Valley');
        const badge = document.createElement('span');
        badge.className = 'sidebar-badge remote';
        badge.textContent = 'Remote';
        head.appendChild(title);
        head.appendChild(badge);
        card.appendChild(head);

        const meta = document.createElement('div');
        meta.className = 'sidebar-meta';
        const route = String(valley.public_address || '').trim();
        meta.textContent = `Route: ${route || '(not advertised)'}`;
        card.appendChild(meta);

        card.appendChild(this.createSidebarRow('Stable ID', this.shortId(valley.valley_id) || '(not advertised)'));
        card.appendChild(this.createSidebarRow('Campfires', String((valley.exposed_campfires || []).length)));
        card.appendChild(this.createSidebarRow('Services', String((valley.exposed_services || []).length)));

        const visible = document.createElement('div');
        visible.className = 'sidebar-list';
        const campfires = Array.isArray(valley.exposed_campfires) && valley.exposed_campfires.length
            ? valley.exposed_campfires.slice(0, 4).join(', ')
            : '(none advertised)';
        visible.textContent = `Visible: ${campfires}`;
        card.appendChild(visible);
        return card;
    }
    
    updateElement(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }
    
    startMetricsUpdates() {
        if (this.updateInterval) {
            return;
        }
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
