// LiteGraph Integration for CampfireValley
// This file manages the LiteGraph canvas and integrates it with the existing CampfireValley functionality

class CampfireValleyLiteGraph {
    constructor() {
        this.graph = null;
        this.canvas = null;
        this.nodes = {};
        this.websocket = null;
        this.isInitialized = false;
        
        // Initialize gamification engine
        if (typeof CampfireGameEngine !== 'undefined') {
            window.CampfireGameEngine = new CampfireGameEngine();
            console.log("Gamification engine initialized");
        }
        
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
            
            // Enable multi-selection and group movement
            this.canvas.allow_multi_selection = true;
            this.canvas.multi_select_key = "ctrl"; // Use Ctrl key for multi-selection
            this.canvas.allow_dragcanvas = true;
            this.canvas.allow_dragnodes = true;
            
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
        
        // Layout configuration for DAG system and vertical UI panel
        const LAYOUT_CONFIG = {
            // DAG Layout area (main graph) - positioned to the right of UI panel
            DAG_START_X: 400,      // Start DAG to the right of UI panel
            DAG_START_Y: 100,      // Start DAG higher up
            RANK_SEP: 350,         // Horizontal separation between ranks
            NODE_SEP: 180,         // Vertical separation between nodes in same rank
            NODE_WIDTH: 200,
            NODE_HEIGHT: 100,
            
            // Vertical UI Control Panel (left side) - compact stacked layout
            UI_PANEL_X: 20,        // Left edge of screen
            UI_PANEL_Y: 20,        // Start near top
            UI_PANEL_WIDTH: 320,   // Fixed width for all UI nodes
            UI_PANEL_HEIGHT: 80,   // Compact height for each UI node
            UI_PANEL_SPACING: 10,  // Small gap between UI nodes
            UI_PANEL_MARGIN: 90,   // Total height per UI node (height + spacing)
            
            // Disconnected nodes area (far right)
            DISCONNECTED_X: 1200,  // Far right side
            DISCONNECTED_Y: 50,    
            DISCONNECTED_SPACING: 180,
            
            // Legacy values for compatibility
            START_X: 400,          // Point to new DAG area
            START_Y: 100,          // Point to new DAG Y position
            UI_AREA_HEIGHT: 0      // No longer needed
        };

        // Track placed UI nodes for collision detection
        const placedUINodes = [];
        
        // Helper functions for different positioning systems
        const getUIControlPos = (index, nodeSize = [LAYOUT_CONFIG.UI_PANEL_WIDTH, LAYOUT_CONFIG.UI_PANEL_HEIGHT]) => {
            // Vertical stacking layout - ignore col/row, use index for vertical position
            const basePos = [
                LAYOUT_CONFIG.UI_PANEL_X,
                LAYOUT_CONFIG.UI_PANEL_Y + (index * LAYOUT_CONFIG.UI_PANEL_MARGIN)
            ];
            
            // Use collision detection if available
            if (typeof CollisionDetection !== 'undefined' && placedUINodes.length > 0) {
                const tempNode = { pos: basePos, size: nodeSize };
                const finalPos = CollisionDetection.findNonCollidingPosition(tempNode, placedUINodes, 10);
                placedUINodes.push({ pos: finalPos, size: nodeSize });
                return finalPos;
            } else {
                placedUINodes.push({ pos: basePos, size: nodeSize });
                return basePos;
            }
        };

        const getDisconnectedNodePos = (index, nodeSize = [200, 100]) => {
            const basePos = [
                LAYOUT_CONFIG.DISCONNECTED_X,
                LAYOUT_CONFIG.DISCONNECTED_Y + (index * LAYOUT_CONFIG.DISCONNECTED_SPACING)
            ];
            
            // Use collision detection if available
            if (typeof CollisionDetection !== 'undefined' && placedUINodes.length > 0) {
                const tempNode = { pos: basePos, size: nodeSize };
                return CollisionDetection.findNonCollidingPosition(tempNode, placedUINodes, 20);
            }
            return basePos;
        };

        // Legacy function for backward compatibility
        const getUIGridPos = (index, nodeSize) => getUIControlPos(index, nodeSize);

        // DAG Layout System - assigns ranks and positions based on dependencies
        class DAGLayout {
            constructor(config) {
                this.config = config;
                this.nodes = new Map();
                this.edges = [];
                this.ranks = new Map(); // node -> rank (level)
                this.rankNodes = new Map(); // rank -> [nodes]
            }

            addNode(id, type, properties = {}) {
                this.nodes.set(id, { id, type, properties, inEdges: [], outEdges: [] });
            }

            addEdge(from, to) {
                this.edges.push({ from, to });
                if (this.nodes.has(from) && this.nodes.has(to)) {
                    this.nodes.get(from).outEdges.push(to);
                    this.nodes.get(to).inEdges.push(from);
                }
            }

            // Assign ranks using topological sort (Kahn's algorithm)
            assignRanks() {
                const inDegree = new Map();
                const queue = [];
                
                // Initialize in-degrees
                for (const [id, node] of this.nodes) {
                    inDegree.set(id, node.inEdges.length);
                    if (node.inEdges.length === 0) {
                        queue.push(id);
                        this.ranks.set(id, 0);
                    }
                }

                // Process nodes level by level
                while (queue.length > 0) {
                    const current = queue.shift();
                    const currentRank = this.ranks.get(current);
                    
                    // Add to rank group
                    if (!this.rankNodes.has(currentRank)) {
                        this.rankNodes.set(currentRank, []);
                    }
                    this.rankNodes.get(currentRank).push(current);

                    // Process outgoing edges
                    for (const neighbor of this.nodes.get(current).outEdges) {
                        inDegree.set(neighbor, inDegree.get(neighbor) - 1);
                        
                        if (inDegree.get(neighbor) === 0) {
                            this.ranks.set(neighbor, currentRank + 1);
                            queue.push(neighbor);
                        }
                    }
                }
            }

            // Calculate positions for all nodes with collision detection
            calculatePositions() {
                this.assignRanks();
                const positions = new Map();
                const placedNodes = [];

                for (const [rank, nodeIds] of this.rankNodes) {
                    const nodesInRank = nodeIds.length;
                    const startY = this.config.DAG_START_Y;
                    
                    nodeIds.forEach((nodeId, index) => {
                        const x = this.config.DAG_START_X + (rank * this.config.RANK_SEP);
                        const y = startY + (index * this.config.NODE_SEP);
                        
                        // Create a temporary node object for collision detection
                        const tempNode = {
                            pos: [x, y],
                            size: [this.config.NODE_WIDTH, this.config.NODE_HEIGHT]
                        };
                        
                        // Use collision detection to find a non-overlapping position
                        let finalPos = [x, y];
                        if (placedNodes.length > 0 && typeof CollisionDetection !== 'undefined') {
                            finalPos = CollisionDetection.findNonCollidingPosition(tempNode, placedNodes, 30);
                        }
                        
                        // Add to placed nodes for future collision checks
                        placedNodes.push({
                            pos: finalPos,
                            size: [this.config.NODE_WIDTH, this.config.NODE_HEIGHT]
                        });
                        
                        positions.set(nodeId, finalPos);
                    });
                }

                return positions;
            }
        }

        // Initialize DAG layout
        const dagLayout = new DAGLayout(LAYOUT_CONFIG);
        
        // Old UI control panel suppressed: do not render legacy stacked controls
        // This intentionally disables the left-side legacy UI to prevent panel rendering
        // and allow the hex-only interface. All references are removed.
        
        // Define DAG structure - nodes and their dependencies
        // Add all nodes to the DAG layout system first
        dagLayout.addNode('valley', 'campfire/valley', {
            name: "Main Valley",
            total_campfires: 4,
            total_campers: 9
        });
        
        dagLayout.addNode('dock', 'campfire/dock', {
            name: "Valley Gateway", 
            torch_throughput: 150
        });
        
        dagLayout.addNode('regularCampfire', 'campfire/campfire', {
            name: "Processing Campfire",
            type: "processing",
            camper_count: 3,
            torch_queue: 8,
            config_source: "processing.yaml"
        });
        
        dagLayout.addNode('dockmaster', 'campfire/dockmaster_campfire', {
            name: "Dockmaster",
            torch_queue: 25,
            routing_efficiency: 95
        });
        
        dagLayout.addNode('sanitizer', 'campfire/sanitizer_campfire', {
            name: "Sanitizer", 
            threats_detected: 3,
            quarantine_count: 1
        });
        
        dagLayout.addNode('justice', 'campfire/justice_campfire', {
            name: "Justice",
            violations_detected: 2,
            sanctions_applied: 1
        });

        // Add camper nodes to DAG
        // Dockmaster campers
        dagLayout.addNode('loader', 'campfire/loader_camper', {
            torches_loaded: 45,
            validation_rate: 100
        });
        dagLayout.addNode('router', 'campfire/router_camper', {
            routes_processed: 38,
            routing_accuracy: 98
        });
        dagLayout.addNode('packer', 'campfire/packer_camper', {
            torches_packed: 42,
            compression_ratio: 75
        });

        // Sanitizer campers
        dagLayout.addNode('scanner', 'campfire/scanner_camper', {
            scans_completed: 67,
            threats_found: 3
        });
        dagLayout.addNode('filterCamper', 'campfire/filter_camper', {
            content_filtered: 12,
            filter_accuracy: 99
        });
        dagLayout.addNode('quarantine', 'campfire/quarantine_camper', {
            quarantine_capacity: 100,
            items_quarantined: 1
        });

        // Justice campers
        dagLayout.addNode('detector', 'campfire/detector_camper', {
            violations_detected: 2,
            detection_accuracy: 97
        });
        dagLayout.addNode('enforcer', 'campfire/enforcer_camper', {
            sanctions_applied: 1,
            enforcement_rate: 100
        });
        dagLayout.addNode('governor', 'campfire/governor_camper', {
            policies_managed: 15,
            compliance_rate: 95
        });

        // Regular campfire campers
        dagLayout.addNode('camper1', 'campfire/camper', {
            type: "processor",
            current_task: "analyzing",
            tasks_completed: 23
        });
        dagLayout.addNode('camper2', 'campfire/camper', {
            type: "processor", 
            current_task: "processing",
            tasks_completed: 19
        });
        dagLayout.addNode('camper3', 'campfire/camper', {
            type: "processor",
            current_task: "idle", 
            tasks_completed: 31
        });

        // Define dependencies (edges) - this determines the layout
        dagLayout.addEdge('valley', 'dock');
        dagLayout.addEdge('valley', 'regularCampfire');
        dagLayout.addEdge('dock', 'dockmaster');
        dagLayout.addEdge('dock', 'sanitizer');
        dagLayout.addEdge('dock', 'justice');

        // Camper dependencies
        dagLayout.addEdge('dockmaster', 'loader');
        dagLayout.addEdge('dockmaster', 'router');
        dagLayout.addEdge('dockmaster', 'packer');
        
        dagLayout.addEdge('sanitizer', 'scanner');
        dagLayout.addEdge('sanitizer', 'filterCamper');
        dagLayout.addEdge('sanitizer', 'quarantine');
        
        dagLayout.addEdge('justice', 'detector');
        dagLayout.addEdge('justice', 'enforcer');
        dagLayout.addEdge('justice', 'governor');
        
        dagLayout.addEdge('regularCampfire', 'camper1');
        dagLayout.addEdge('regularCampfire', 'camper2');
        dagLayout.addEdge('regularCampfire', 'camper3');

        // Calculate optimal positions using DAG layout
        const positions = dagLayout.calculatePositions();

        // Create actual LiteGraph nodes with calculated positions
        const valleyNode = LiteGraph.createNode("campfire/valley");
        valleyNode.pos = positions.get('valley');
        valleyNode.properties = valleyNode.properties || {};
        Object.assign(valleyNode.properties, dagLayout.nodes.get('valley').properties);
        this.graph.add(valleyNode);
        this.nodes.valley = valleyNode;
        
        const dockNode = LiteGraph.createNode("campfire/dock");
        dockNode.pos = positions.get('dock');
        dockNode.properties = dockNode.properties || {};
        Object.assign(dockNode.properties, dagLayout.nodes.get('dock').properties);
        this.graph.add(dockNode);
        this.nodes.dock = dockNode;
        
        const regularCampfireNode = LiteGraph.createNode("campfire/campfire");
        regularCampfireNode.pos = positions.get('regularCampfire');
        regularCampfireNode.properties = regularCampfireNode.properties || {};
        Object.assign(regularCampfireNode.properties, dagLayout.nodes.get('regularCampfire').properties);
        this.graph.add(regularCampfireNode);
        this.nodes.regularCampfire = regularCampfireNode;
        
        const dockmasterNode = LiteGraph.createNode("campfire/dockmaster_campfire");
        dockmasterNode.pos = positions.get('dockmaster');
        dockmasterNode.properties = dockmasterNode.properties || {};
        Object.assign(dockmasterNode.properties, dagLayout.nodes.get('dockmaster').properties);
        this.graph.add(dockmasterNode);
        this.nodes.dockmaster = dockmasterNode;
        
        const sanitizerNode = LiteGraph.createNode("campfire/sanitizer_campfire");
        sanitizerNode.pos = positions.get('sanitizer');
        sanitizerNode.properties = sanitizerNode.properties || {};
        Object.assign(sanitizerNode.properties, dagLayout.nodes.get('sanitizer').properties);
        this.graph.add(sanitizerNode);
        this.nodes.sanitizer = sanitizerNode;
        
        const justiceNode = LiteGraph.createNode("campfire/justice_campfire");
        justiceNode.pos = positions.get('justice');
        justiceNode.properties = justiceNode.properties || {};
        Object.assign(justiceNode.properties, dagLayout.nodes.get('justice').properties);
        this.graph.add(justiceNode);
        this.nodes.justice = justiceNode;
        
        // Level 3: Specialized campers using DAG layout positions
        // Dockmaster campers
        const loaderNode = LiteGraph.createNode("campfire/loader_camper");
        loaderNode.pos = positions.get('loader');
        loaderNode.properties = loaderNode.properties || {};
        Object.assign(loaderNode.properties, dagLayout.nodes.get('loader').properties);
        this.graph.add(loaderNode);
        this.nodes.loader = loaderNode;
        
        const routerNode = LiteGraph.createNode("campfire/router_camper");
        routerNode.pos = positions.get('router');
        routerNode.properties = routerNode.properties || {};
        Object.assign(routerNode.properties, dagLayout.nodes.get('router').properties);
        this.graph.add(routerNode);
        this.nodes.router = routerNode;
        
        const packerNode = LiteGraph.createNode("campfire/packer_camper");
        packerNode.pos = positions.get('packer');
        packerNode.properties = packerNode.properties || {};
        Object.assign(packerNode.properties, dagLayout.nodes.get('packer').properties);
        this.graph.add(packerNode);
        this.nodes.packer = packerNode;
        
        // Sanitizer campers
        const scannerNode = LiteGraph.createNode("campfire/scanner_camper");
        scannerNode.pos = positions.get('scanner');
        scannerNode.properties = scannerNode.properties || {};
        Object.assign(scannerNode.properties, dagLayout.nodes.get('scanner').properties);
        this.graph.add(scannerNode);
        this.nodes.scanner = scannerNode;
        
        const filterCamperNode = LiteGraph.createNode("campfire/filter_camper");
        filterCamperNode.pos = positions.get('filterCamper');
        filterCamperNode.properties = filterCamperNode.properties || {};
        Object.assign(filterCamperNode.properties, dagLayout.nodes.get('filterCamper').properties);
        this.graph.add(filterCamperNode);
        this.nodes.filterCamper = filterCamperNode;
        
        const quarantineNode = LiteGraph.createNode("campfire/quarantine_camper");
        quarantineNode.pos = positions.get('quarantine');
        quarantineNode.properties = quarantineNode.properties || {};
        Object.assign(quarantineNode.properties, dagLayout.nodes.get('quarantine').properties);
        this.graph.add(quarantineNode);
        this.nodes.quarantine = quarantineNode;
        
        // Justice campers
        const detectorNode = LiteGraph.createNode("campfire/detector_camper");
        detectorNode.pos = positions.get('detector');
        detectorNode.properties = detectorNode.properties || {};
        Object.assign(detectorNode.properties, dagLayout.nodes.get('detector').properties);
        this.graph.add(detectorNode);
        this.nodes.detector = detectorNode;
        
        const enforcerNode = LiteGraph.createNode("campfire/enforcer_camper");
        enforcerNode.pos = positions.get('enforcer');
        enforcerNode.properties = enforcerNode.properties || {};
        Object.assign(enforcerNode.properties, dagLayout.nodes.get('enforcer').properties);
        this.graph.add(enforcerNode);
        this.nodes.enforcer = enforcerNode;
        
        const governorNode = LiteGraph.createNode("campfire/governor_camper");
        governorNode.pos = positions.get('governor');
        governorNode.properties = governorNode.properties || {};
        Object.assign(governorNode.properties, dagLayout.nodes.get('governor').properties);
        this.graph.add(governorNode);
        this.nodes.governor = governorNode;
        
        // Regular campfire campers using DAG layout
        const camperNode1 = LiteGraph.createNode("campfire/camper");
        camperNode1.pos = positions.get('camper1');
        camperNode1.properties = camperNode1.properties || {};
        Object.assign(camperNode1.properties, dagLayout.nodes.get('camper1').properties);
        this.graph.add(camperNode1);
        this.nodes.camper1 = camperNode1;
        
        const camperNode2 = LiteGraph.createNode("campfire/camper");
        camperNode2.pos = positions.get('camper2');
        camperNode2.properties = camperNode2.properties || {};
        Object.assign(camperNode2.properties, dagLayout.nodes.get('camper2').properties);
        this.graph.add(camperNode2);
        this.nodes.camper2 = camperNode2;
        
        const camperNode3 = LiteGraph.createNode("campfire/camper");
        camperNode3.pos = positions.get('camper3');
        camperNode3.properties = camperNode3.properties || {};
        Object.assign(camperNode3.properties, dagLayout.nodes.get('camper3').properties);
        this.graph.add(camperNode3);
        this.nodes.camper3 = camperNode3;
        
        // Demo hexagonal valley nodes removed per request
        
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
    
    // Add a node with collision detection
    addNodeWithCollisionDetection(nodeType, targetPosition, nodeId = null) {
        const newNode = LiteGraph.createNode(nodeType);
        
        // Get all existing nodes for collision detection
        const existingNodes = this.graph._nodes.map(node => ({
            pos: [...node.pos],
            size: [...node.size]
        }));
        
        // Set initial position
        newNode.pos = targetPosition ? [...targetPosition] : [100, 100];
        
        // Use collision detection to find a safe position
        if (typeof CollisionDetection !== 'undefined' && existingNodes.length > 0) {
            const tempNode = {
                pos: [...newNode.pos],
                size: [...newNode.size]
            };
            const safePosition = CollisionDetection.findNonCollidingPosition(tempNode, existingNodes, 20);
            newNode.pos = safePosition;
        }
        
        // Add to graph
        this.graph.add(newNode);
        
        // Store reference if ID provided
        if (nodeId) {
            this.nodes[nodeId] = newNode;
        }
        
        return newNode;
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