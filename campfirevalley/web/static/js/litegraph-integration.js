// LiteGraph Integration for CampfireValley
// This file manages the LiteGraph canvas and integrates it with the existing CampfireValley functionality

class CampfireValleyLiteGraph {
    constructor() {
        this.graph = null;
        this.canvas = null;
        this.nodes = {};
        this.websocket = null;
        this.isInitialized = false;
        
        // Bind methods
        this.init = this.init.bind(this);
        this.createDefaultNodes = this.createDefaultNodes.bind(this);
        this.connectWebSocket = this.connectWebSocket.bind(this);
        this.updateFromWebSocket = this.updateFromWebSocket.bind(this);
    }
    
    init(canvasElement) {
        if (this.isInitialized) return;
        
        try {
            // Create LiteGraph instance
            this.graph = new LGraph();
            this.canvas = new LGraphCanvas(canvasElement, this.graph);
            
            // Configure canvas
            this.canvas.background_image = null;
            this.canvas.render_shadows = false;
            this.canvas.render_canvas_border = false;
            this.canvas.render_connections_shadows = false;
            this.canvas.render_connections_border = false;
            this.canvas.highquality_render = true;
            this.canvas.use_gradients = true;
            
            // Set canvas size
            this.canvas.resize();
            
            // Create default node layout
            this.createDefaultNodes();
            
            // Connect to WebSocket
            this.connectWebSocket();
            
            // Start graph execution
            this.graph.start();
            
            this.isInitialized = true;
            console.log("CampfireValley LiteGraph initialized successfully");
            
        } catch (error) {
            console.error("Failed to initialize LiteGraph:", error);
        }
    }
    
    createDefaultNodes() {
        // Clear existing nodes
        this.graph.clear();
        this.nodes = {};
        
        // Create control nodes in top area
        const wsNode = LiteGraph.createNode("campfire/websocket_data");
        wsNode.pos = [50, 50];
        this.graph.add(wsNode);
        this.nodes.websocket = wsNode;
        
        const taskNode = LiteGraph.createNode("campfire/task_input");
        taskNode.pos = [300, 50];
        this.graph.add(taskNode);
        this.nodes.taskInput = taskNode;
        
        const viewNode = LiteGraph.createNode("campfire/view_mode");
        viewNode.pos = [550, 50];
        this.graph.add(viewNode);
        this.nodes.viewMode = viewNode;
        
        const filterNode = LiteGraph.createNode("campfire/filter");
        filterNode.pos = [800, 50];
        this.graph.add(filterNode);
        this.nodes.filter = filterNode;
        
        const zoomNode = LiteGraph.createNode("campfire/zoom_control");
        zoomNode.pos = [1050, 50];
        this.graph.add(zoomNode);
        this.nodes.zoomControl = zoomNode;
        
        const displayNode = LiteGraph.createNode("campfire/display_options");
        displayNode.pos = [50, 200];
        this.graph.add(displayNode);
        this.nodes.displayOptions = displayNode;
        
        const detailsNode = LiteGraph.createNode("campfire/node_details");
        detailsNode.pos = [300, 200];
        this.graph.add(detailsNode);
        this.nodes.nodeDetails = detailsNode;
        
        const legendNode = LiteGraph.createNode("campfire/status_legend");
        legendNode.pos = [550, 200];
        this.graph.add(legendNode);
        this.nodes.statusLegend = legendNode;
        
        // Create hierarchical structure starting with Valley at top
        const valleyNode = LiteGraph.createNode("campfire/valley");
        valleyNode.pos = [600, 400]; // Center top of hierarchy
        valleyNode.properties = valleyNode.properties || {};
        valleyNode.properties.name = "Main Valley";
        valleyNode.properties.total_campfires = 4; // 3 dock + 1 regular
        valleyNode.properties.total_campers = 9; // 3 per dock campfire
        this.graph.add(valleyNode);
        this.nodes.valley = valleyNode;
        
        // Create Dock node below Valley
        const dockNode = LiteGraph.createNode("campfire/dock");
        dockNode.pos = [600, 580];
        dockNode.properties = dockNode.properties || {};
        dockNode.properties.name = "Valley Gateway";
        dockNode.properties.torch_throughput = 150;
        this.graph.add(dockNode);
        this.nodes.dock = dockNode;
        
        // Create the three specialized dock campfires
        const dockmasterNode = LiteGraph.createNode("campfire/dockmaster_campfire");
        dockmasterNode.pos = [200, 760];
        dockmasterNode.properties = dockmasterNode.properties || {};
        dockmasterNode.properties.name = "Dockmaster";
        dockmasterNode.properties.torch_queue = 25;
        dockmasterNode.properties.routing_efficiency = 95;
        this.graph.add(dockmasterNode);
        this.nodes.dockmaster = dockmasterNode;
        
        const sanitizerNode = LiteGraph.createNode("campfire/sanitizer_campfire");
        sanitizerNode.pos = [600, 760];
        sanitizerNode.properties = sanitizerNode.properties || {};
        sanitizerNode.properties.name = "Sanitizer";
        sanitizerNode.properties.threats_detected = 3;
        sanitizerNode.properties.quarantine_count = 1;
        this.graph.add(sanitizerNode);
        this.nodes.sanitizer = sanitizerNode;
        
        const justiceNode = LiteGraph.createNode("campfire/justice_campfire");
        justiceNode.pos = [1000, 760];
        justiceNode.properties = justiceNode.properties || {};
        justiceNode.properties.name = "Justice";
        justiceNode.properties.violations_detected = 2;
        justiceNode.properties.sanctions_applied = 1;
        this.graph.add(justiceNode);
        this.nodes.justice = justiceNode;
        
        // Create specialized campers for Dockmaster
        const loaderNode = LiteGraph.createNode("campfire/loader_camper");
        loaderNode.pos = [50, 940];
        loaderNode.properties = loaderNode.properties || {};
        loaderNode.properties.torches_loaded = 45;
        loaderNode.properties.validation_rate = 100;
        this.graph.add(loaderNode);
        this.nodes.loader = loaderNode;
        
        const routerNode = LiteGraph.createNode("campfire/router_camper");
        routerNode.pos = [250, 940];
        routerNode.properties = routerNode.properties || {};
        routerNode.properties.routes_processed = 38;
        routerNode.properties.routing_accuracy = 98;
        this.graph.add(routerNode);
        this.nodes.router = routerNode;
        
        const packerNode = LiteGraph.createNode("campfire/packer_camper");
        packerNode.pos = [450, 940];
        packerNode.properties = packerNode.properties || {};
        packerNode.properties.torches_packed = 42;
        packerNode.properties.compression_ratio = 75;
        this.graph.add(packerNode);
        this.nodes.packer = packerNode;
        
        // Create specialized campers for Sanitizer
        const scannerNode = LiteGraph.createNode("campfire/scanner_camper");
        scannerNode.pos = [450, 940];
        scannerNode.properties = scannerNode.properties || {};
        scannerNode.properties.scans_completed = 67;
        scannerNode.properties.threats_found = 3;
        this.graph.add(scannerNode);
        this.nodes.scanner = scannerNode;
        
        const filterCamperNode = LiteGraph.createNode("campfire/filter_camper");
        filterCamperNode.pos = [650, 940];
        filterCamperNode.properties = filterCamperNode.properties || {};
        filterCamperNode.properties.content_filtered = 12;
        filterCamperNode.properties.filter_accuracy = 99;
        this.graph.add(filterCamperNode);
        this.nodes.filterCamper = filterCamperNode;
        
        const quarantineNode = LiteGraph.createNode("campfire/quarantine_camper");
        quarantineNode.pos = [850, 940];
        quarantineNode.properties = quarantineNode.properties || {};
        quarantineNode.properties.items_quarantined = 1;
        quarantineNode.properties.quarantine_capacity = 100;
        this.graph.add(quarantineNode);
        this.nodes.quarantine = quarantineNode;
        
        // Create specialized campers for Justice
        const detectorNode = LiteGraph.createNode("campfire/detector_camper");
        detectorNode.pos = [850, 940];
        detectorNode.properties = detectorNode.properties || {};
        detectorNode.properties.violations_detected = 2;
        detectorNode.properties.detection_accuracy = 97;
        this.graph.add(detectorNode);
        this.nodes.detector = detectorNode;
        
        const enforcerNode = LiteGraph.createNode("campfire/enforcer_camper");
        enforcerNode.pos = [1050, 940];
        enforcerNode.properties = enforcerNode.properties || {};
        enforcerNode.properties.sanctions_applied = 1;
        enforcerNode.properties.enforcement_rate = 100;
        this.graph.add(enforcerNode);
        this.nodes.enforcer = enforcerNode;
        
        const governorNode = LiteGraph.createNode("campfire/governor_camper");
        governorNode.pos = [1250, 940];
        governorNode.properties = governorNode.properties || {};
        governorNode.properties.policies_managed = 15;
        governorNode.properties.compliance_rate = 95;
        this.graph.add(governorNode);
        this.nodes.governor = governorNode;
        
        // Create a regular campfire from config
        const regularCampfireNode = LiteGraph.createNode("campfire/campfire");
        regularCampfireNode.pos = [1200, 580];
        regularCampfireNode.properties = regularCampfireNode.properties || {};
        regularCampfireNode.properties.name = "Processing Campfire";
        regularCampfireNode.properties.type = "processing";
        regularCampfireNode.properties.camper_count = 3;
        regularCampfireNode.properties.torch_queue = 8;
        regularCampfireNode.properties.config_source = "processing.yaml";
        this.graph.add(regularCampfireNode);
        this.nodes.regularCampfire = regularCampfireNode;
        
        // Create regular campers for the processing campfire
        const camper1Node = LiteGraph.createNode("campfire/camper");
        camper1Node.pos = [1050, 760];
        camper1Node.properties = camper1Node.properties || {};
        camper1Node.properties.name = "Worker 1";
        camper1Node.properties.type = "processor";
        camper1Node.properties.current_task = "analyzing";
        camper1Node.properties.tasks_completed = 23;
        this.graph.add(camper1Node);
        this.nodes.camper1 = camper1Node;
        
        const camper2Node = LiteGraph.createNode("campfire/camper");
        camper2Node.pos = [1250, 760];
        camper2Node.properties = camper2Node.properties || {};
        camper2Node.properties.name = "Worker 2";
        camper2Node.properties.type = "processor";
        camper2Node.properties.current_task = "processing";
        camper2Node.properties.tasks_completed = 19;
        this.graph.add(camper2Node);
        this.nodes.camper2 = camper2Node;
        
        const camper3Node = LiteGraph.createNode("campfire/camper");
        camper3Node.pos = [1450, 760];
        camper3Node.properties = camper3Node.properties || {};
        camper3Node.properties.name = "Worker 3";
        camper3Node.properties.type = "processor";
        camper3Node.properties.current_task = "idle";
        camper3Node.properties.tasks_completed = 31;
        this.graph.add(camper3Node);
        this.nodes.camper3 = camper3Node;
        
        // Connect nodes logically
        this.connectNodes();
        
        // Set up event handlers
        this.setupEventHandlers();
    }
    
    connectNodes() {
        // Connect WebSocket to Valley
        if (this.nodes.websocket && this.nodes.valley) {
            this.nodes.websocket.connect(0, this.nodes.valley, 0);
        }
        
        // Connect the hierarchical structure
        // Valley -> Dock
        if (this.nodes.valley && this.nodes.dock) {
            this.nodes.valley.connect(0, this.nodes.dock, 0);
        }
        
        // Valley -> Regular Campfire
        if (this.nodes.valley && this.nodes.regularCampfire) {
            this.nodes.valley.connect(1, this.nodes.regularCampfire, 0);
        }
        
        // Dock -> Specialized Campfires
        if (this.nodes.dock && this.nodes.dockmaster) {
            this.nodes.dock.connect(0, this.nodes.dockmaster, 0);
        }
        if (this.nodes.dock && this.nodes.sanitizer) {
            this.nodes.dock.connect(1, this.nodes.sanitizer, 0);
        }
        if (this.nodes.dock && this.nodes.justice) {
            this.nodes.dock.connect(2, this.nodes.justice, 0);
        }
        
        // Dockmaster -> Specialized Campers
        if (this.nodes.dockmaster && this.nodes.loader) {
            this.nodes.dockmaster.connect(0, this.nodes.loader, 0);
        }
        if (this.nodes.dockmaster && this.nodes.router) {
            this.nodes.dockmaster.connect(1, this.nodes.router, 0);
        }
        if (this.nodes.dockmaster && this.nodes.packer) {
            this.nodes.dockmaster.connect(2, this.nodes.packer, 0);
        }
        
        // Sanitizer -> Specialized Campers
        if (this.nodes.sanitizer && this.nodes.scanner) {
            this.nodes.sanitizer.connect(0, this.nodes.scanner, 0);
        }
        if (this.nodes.sanitizer && this.nodes.filterCamper) {
            this.nodes.sanitizer.connect(1, this.nodes.filterCamper, 0);
        }
        if (this.nodes.sanitizer && this.nodes.quarantine) {
            this.nodes.sanitizer.connect(2, this.nodes.quarantine, 0);
        }
        
        // Justice -> Specialized Campers
        if (this.nodes.justice && this.nodes.detector) {
            this.nodes.justice.connect(0, this.nodes.detector, 0);
        }
        if (this.nodes.justice && this.nodes.enforcer) {
            this.nodes.justice.connect(1, this.nodes.enforcer, 0);
        }
        if (this.nodes.justice && this.nodes.governor) {
            this.nodes.justice.connect(2, this.nodes.governor, 0);
        }
        
        // Regular Campfire -> Regular Campers
        if (this.nodes.regularCampfire && this.nodes.camper1) {
            this.nodes.regularCampfire.connect(0, this.nodes.camper1, 0);
        }
        if (this.nodes.regularCampfire && this.nodes.camper2) {
            this.nodes.regularCampfire.connect(0, this.nodes.camper2, 0);
        }
        if (this.nodes.regularCampfire && this.nodes.camper3) {
            this.nodes.regularCampfire.connect(0, this.nodes.camper3, 0);
        }
    }
    
    setupEventHandlers() {
        // Handle node selection for details display
        this.canvas.onNodeSelected = (node) => {
            if (this.nodes.nodeDetails) {
                this.nodes.nodeDetails.properties.node_title = node.title || "Unknown Node";
                this.nodes.nodeDetails.properties.node_details = this.getNodeDetails(node);
                this.nodes.nodeDetails.setDirtyCanvas(true, true);
            }
        };
        
        // Handle task control events
        if (this.nodes.taskInput) {
            this.nodes.taskInput.onAction = (action, param) => {
                if (action === "task_started") {
                    this.handleTaskStart(param);
                } else if (action === "task_stopped") {
                    this.handleTaskStop();
                }
            };
        }
        
        // Handle view mode changes
        if (this.nodes.viewMode) {
            this.nodes.viewMode.onExecute = () => {
                const mode = this.nodes.viewMode.properties.current_mode;
                this.handleViewModeChange(mode);
            };
        }
        
        // Handle zoom control
        if (this.nodes.zoomControl) {
            this.nodes.zoomControl.onAction = (action) => {
                if (action === "zoom_in") {
                    this.canvas.setZoom(this.canvas.ds.scale * 1.2);
                } else if (action === "zoom_out") {
                    this.canvas.setZoom(this.canvas.ds.scale / 1.2);
                } else if (action === "reset_view") {
                    this.canvas.setZoom(1.0);
                    this.canvas.ds.offset = [0, 0];
                }
            };
        }
        
        // Handle display options
        if (this.nodes.displayOptions) {
            this.nodes.displayOptions.onExecute = () => {
                const showConnections = this.nodes.displayOptions.properties.connections;
                const showTorchFlow = this.nodes.displayOptions.properties.torch_flow;
                const autoRefresh = this.nodes.displayOptions.properties.refresh;
                
                this.canvas.render_connections = showConnections;
                // Handle other display options as needed
            };
        }
    }
    
    getNodeDetails(node) {
        let details = `Type: ${node.type}\n`;
        details += `Position: (${Math.round(node.pos[0])}, ${Math.round(node.pos[1])})\n`;
        details += `Size: ${node.size[0]}x${node.size[1]}\n`;
        
        if (node.properties) {
            details += "Properties:\n";
            for (const [key, value] of Object.entries(node.properties)) {
                details += `  ${key}: ${value}\n`;
            }
        }
        
        return details;
    }
    
    handleTaskStart(taskDescription) {
        console.log("Starting task:", taskDescription);
        
        // Update campfire nodes to show they're processing
        Object.values(this.nodes).forEach(node => {
            if (node.type === "campfire/campfire") {
                node.properties.status = "busy";
                node.properties.current_task = taskDescription;
                node.setDirtyCanvas(true, true);
            }
        });
        
        // Send task to backend if WebSocket is connected
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: "start_task",
                task_description: taskDescription
            }));
        }
    }
    
    handleTaskStop() {
        console.log("Stopping task");
        
        // Update campfire nodes to show they're idle
        Object.values(this.nodes).forEach(node => {
            if (node.type === "campfire/campfire") {
                node.properties.status = "idle";
                node.properties.current_task = "";
                node.setDirtyCanvas(true, true);
            }
        });
        
        // Send stop command to backend
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: "stop_task"
            }));
        }
    }
    
    handleViewModeChange(mode) {
        console.log("View mode changed to:", mode);
        
        // Update visibility of nodes based on view mode
        Object.values(this.nodes).forEach(node => {
            if (mode === "campfires" && node.type !== "campfire/campfire") {
                node.flags.collapsed = true;
            } else if (mode === "campers" && node.type !== "campfire/camper") {
                node.flags.collapsed = true;
            } else if (mode === "overview") {
                node.flags.collapsed = false;
            }
            node.setDirtyCanvas(true, true);
        });
    }
    
    connectWebSocket() {
        const wsUrl = `ws://${window.location.host}/ws`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log("WebSocket connected to CampfireValley");
                if (this.nodes.websocket) {
                    this.nodes.websocket.properties.connection_status = "connected";
                    this.nodes.websocket.setDirtyCanvas(true, true);
                }
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.updateFromWebSocket(data);
                } catch (error) {
                    console.error("Error parsing WebSocket message:", error);
                }
            };
            
            this.websocket.onclose = () => {
                console.log("WebSocket disconnected");
                if (this.nodes.websocket) {
                    this.nodes.websocket.properties.connection_status = "disconnected";
                    this.nodes.websocket.setDirtyCanvas(true, true);
                }
                
                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.connectWebSocket(), 5000);
            };
            
            this.websocket.onerror = (error) => {
                console.error("WebSocket error:", error);
                if (this.nodes.websocket) {
                    this.nodes.websocket.properties.connection_status = "error";
                    this.nodes.websocket.setDirtyCanvas(true, true);
                }
            };
            
        } catch (error) {
            console.error("Failed to create WebSocket connection:", error);
        }
    }
    
    updateFromWebSocket(data) {
        // Update valley data
        if (data.valley && this.nodes.valley) {
            this.nodes.valley.properties.name = data.valley.name || "Valley";
            this.nodes.valley.properties.status = data.valley.status || "active";
            this.nodes.valley.properties.campfire_count = data.valley.campfire_count || 0;
            this.nodes.valley.properties.camper_count = data.valley.camper_count || 0;
            this.nodes.valley.setDirtyCanvas(true, true);
        }
        
        // Update campfire data
        if (data.campfires) {
            data.campfires.forEach((campfireData, index) => {
                const nodeKey = `campfire${index + 1}`;
                if (this.nodes[nodeKey]) {
                    this.nodes[nodeKey].properties.status = campfireData.status || "idle";
                    this.nodes[nodeKey].properties.current_task = campfireData.current_task || "";
                    this.nodes[nodeKey].setDirtyCanvas(true, true);
                }
            });
        }
        
        // Update camper data
        if (data.campers) {
            data.campers.forEach((camperData, index) => {
                const nodeKey = `camper${index + 1}`;
                if (this.nodes[nodeKey]) {
                    this.nodes[nodeKey].properties.status = camperData.status || "active";
                    this.nodes[nodeKey].properties.activity = camperData.activity || "idle";
                    this.nodes[nodeKey].setDirtyCanvas(true, true);
                }
            });
        }
    }
    
    // Public methods for external integration
    addCampfire(id, position) {
        const campfire = LiteGraph.createNode("campfire/campfire");
        campfire.pos = position || [Math.random() * 400 + 100, Math.random() * 300 + 400];
        campfire.properties.id = id;
        this.graph.add(campfire);
        this.nodes[`campfire_${id}`] = campfire;
        return campfire;
    }
    
    addCamper(id, position) {
        const camper = LiteGraph.createNode("campfire/camper");
        camper.pos = position || [Math.random() * 400 + 100, Math.random() * 300 + 600];
        camper.properties.id = id;
        this.graph.add(camper);
        this.nodes[`camper_${id}`] = camper;
        return camper;
    }
    
    removeCampfire(id) {
        const nodeKey = `campfire_${id}`;
        if (this.nodes[nodeKey]) {
            this.graph.remove(this.nodes[nodeKey]);
            delete this.nodes[nodeKey];
        }
    }
    
    removeCamper(id) {
        const nodeKey = `camper_${id}`;
        if (this.nodes[nodeKey]) {
            this.graph.remove(this.nodes[nodeKey]);
            delete this.nodes[nodeKey];
        }
    }
    
    resize() {
        if (this.canvas) {
            this.canvas.resize();
        }
    }
    
    destroy() {
        if (this.websocket) {
            this.websocket.close();
        }
        if (this.graph) {
            this.graph.stop();
        }
        this.isInitialized = false;
    }
}

// Global instance
window.campfireValleyLiteGraph = new CampfireValleyLiteGraph();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait for LiteGraph to be available
    if (typeof LiteGraph !== 'undefined') {
        console.log("LiteGraph is available, ready to initialize");
    } else {
        console.warn("LiteGraph not found, make sure litegraph.js is loaded");
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CampfireValleyLiteGraph;
}