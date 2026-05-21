// LiteGraph Integration for CampfireValley
// This file manages the LiteGraph canvas and integrates it with the existing CampfireValley functionality

class CampfireValleyLiteGraph {
    constructor() {
        this.buildId = "20260521-graph-link-rebuild-b2";
        this.graph = null;
        this.canvas = null;
        this.nodes = {};
        this.websocket = null;
        this.isInitialized = false;
        this.selectedNode = null;
        this.chatByNodeId = new Map();
        this.remoteInspectorState = new Map();
        this.chatUI = null;
        this.roundsUI = null;
        this.roundsState = { catalog: [], plans: [], rows: [], lastResult: null };
        this.speechRecognition = null;
        this.isListening = false;
        this.backendCampfiresCache = { ts: 0, items: [] };
        this.backendSyncPromise = null;
        this.connectorRefreshTimers = [];
        this.backendGraphRefreshTimers = [];
        
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
            this.canvas.render_connections_border = true;
            this.canvas.connections_width = 5;
            this.canvas.highquality_render = true;
            this.canvas.use_gradients = true;
            if (typeof LGraphCanvas !== "undefined" && LGraphCanvas.link_type_colors) {
                LGraphCanvas.link_type_colors.camper = "#FDE047";
                LGraphCanvas.link_type_colors.campfire = "#86EFAC";
                LGraphCanvas.link_type_colors.valley = "#7DD3FC";
                LGraphCanvas.link_type_colors.valley_connection = "#7DD3FC";
            }
            
            // Enable multi-selection and group movement
            this.canvas.allow_multi_selection = true;
            this.canvas.multi_select_key = "ctrl"; // Use Ctrl key for multi-selection
            this.canvas.allow_dragcanvas = true;
            this.canvas.allow_dragnodes = true;
            
            // Set canvas size
            this.canvas.resize();
            
            // Create default node layout
            this.createDefaultNodes();

            this.setupChatUI();
            
            // Connect to WebSocket
            this.connectWebSocket();

            this.sendUiDebugLog("ui_loaded", {
                build_id: this.buildId,
                href: window.location.href
            });
            
            // Start graph execution
            this.graph.start();
            
            this.isInitialized = true;
            console.log("CampfireValley LiteGraph initialized successfully");
            
        } catch (error) {
            console.error("Failed to initialize LiteGraph:", error);
        }
    }
    
    createDefaultNodes() {
        this.graph.clear();
        this.nodes = {};

        const rootValleyNode = LiteGraph.createNode("campfire/valley");
        rootValleyNode.pos = [80, 220];
        rootValleyNode.properties = rootValleyNode.properties || {};
        rootValleyNode.properties.name = "Local Valley";
        rootValleyNode.properties.display_name = "Local Valley";
        rootValleyNode.properties.origin_label = "LOCAL";
        rootValleyNode.properties.route_name = "(loading...)";
        rootValleyNode.properties.local = true;
        rootValleyNode.properties.remote = false;
        rootValleyNode.title = "Local Valley";
        this.graph.add(rootValleyNode);
        this.nodes.valley = rootValleyNode;

        this.setupEventHandlers();
        this.syncBackendCampfireNodes().catch(() => {});
        return;
        
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
        
        // Demo hexagonal valley nodes removed per request
        
        // Connect nodes logically
        this.connectNodes();
        
        // Set up event handlers
        this.setupEventHandlers();

        this.syncBackendCampfireNodes().catch(() => {});

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
        
        if (this.nodes.regularCampfire && Array.isArray(this.nodes.backendCampers)) {
            this.nodes.backendCampers.forEach((n) => {
                try {
                    this._connectNearestCampfireCamper(this.nodes.regularCampfire, n);
                } catch (e) {
                }
            });
        }
    }
    
    setupEventHandlers() {
        // Handle node selection for details display
        this.canvas.onNodeSelected = (node) => {
            this.setSelectedNode(node || null);
            if (this.nodes.nodeDetails) {
                this.nodes.nodeDetails.properties.node_title = node.title || "Unknown Node";
                this.nodes.nodeDetails.properties.node_details = this.getNodeDetails(node);
                this.nodes.nodeDetails.setDirtyCanvas(true, true);
            }
        };

        this.canvas.onNodeDeselected = () => {
            const selected = (this.canvas && this.canvas.selected_nodes) || {};
            if (!selected || Object.keys(selected).length === 0) {
                this.setSelectedNode(null);
            }
        };

        this.canvas.getExtraMenuOptions = () => {
            return [
                null,
                {
                    content: "New Campfire + Auditor",
                    callback: () => {
                        const pos = [this.canvas.graph_mouse[0], this.canvas.graph_mouse[1]];
                        this.createCampfireWithAuditorAt(pos);
                    }
                }
            ];
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

    setupChatUI() {
        const panel = document.getElementById("chatPanel");
        const actionBar = document.getElementById("chatActionBar");
        const title = document.getElementById("chatTitle");
        const freeze = document.getElementById("chatFreeze");
        const clearBeliefsBtn = document.getElementById("chatClearBeliefs");
        const logsBtn = document.getElementById("chatLogs");
        const exportBtn = document.getElementById("chatExport");
        const speakBtn = document.getElementById("chatSpeak");
        const stopSpeakBtn = document.getElementById("chatStopSpeak");
        const toolsBtn = document.getElementById("chatTools");
        const roundsBtn = document.getElementById("chatRounds");
        const messages = document.getElementById("chatMessages");
        const logsPanel = document.getElementById("chatLogsPanel");
        const input = document.getElementById("chatInput");
        const send = document.getElementById("chatSend");
        const mic = document.getElementById("chatMic");
        const close = document.getElementById("chatClose");
        const inputRow = panel.querySelector(".chat-input-row");
        if (!panel || !actionBar || !title || !freeze || !clearBeliefsBtn || !logsBtn || !exportBtn || !speakBtn || !stopSpeakBtn || !toolsBtn || !roundsBtn || !messages || !logsPanel || !input || !send || !mic || !close) {
            return;
        }
        const toolsPanel = document.createElement("div");
        toolsPanel.id = "chatToolsPanel";
        toolsPanel.className = "chat-tools-panel";
        toolsPanel.innerHTML = `
            <div class="chat-tools-row"><label>Enable Zeitgeist</label><input id="toolZeitgeistEnabled" type="checkbox"/></div>
            <div class="chat-tools-row"><label>Web Search</label><input id="toolWebSearch" type="checkbox"/></div>
            <div class="chat-tools-row"><label>Image OCR</label><input id="toolImageOCR" type="checkbox"/></div>
            <div class="chat-tools-row"><label>Ollama Model</label><select id="toolModelSelect"></select></div>
        `;
        document.body.appendChild(toolsPanel);
        const roundsPanel = document.createElement("div");
        roundsPanel.id = "roundsBuilderPanel";
        roundsPanel.className = "rounds-builder-panel";
        roundsPanel.innerHTML = `
            <div class="rounds-builder-head">
                <div class="rounds-builder-title">Rounds Builder</div>
                <button id="roundsClose" class="chat-close" type="button">✕</button>
            </div>
            <div class="rounds-builder-body">
                <div class="rounds-builder-grid">
                    <div class="rounds-builder-field">
                        <label>Saved Plan</label>
                        <select id="roundsSavedPlans"></select>
                    </div>
                    <div class="rounds-builder-field">
                        <label>Context Campfire</label>
                        <input id="roundsCampfire" type="text" placeholder="Optional campfire context" />
                    </div>
                    <div class="rounds-builder-field">
                        <label>Plan Name</label>
                        <input id="roundsPlanName" type="text" placeholder="e.g. Draft Then Review" />
                    </div>
                    <div class="rounds-builder-field">
                        <label>Description</label>
                        <input id="roundsDescription" type="text" placeholder="What this rounds chain is for" />
                    </div>
                    <div class="rounds-builder-field full">
                        <label>Task</label>
                        <textarea id="roundsTask" placeholder="Describe the task to run through the rounds chain"></textarea>
                    </div>
                </div>
                <div class="rounds-plan-tools">
                    <button id="roundsNewPlan" type="button">New</button>
                    <button id="roundsLoadPlan" type="button">Load</button>
                    <button id="roundsDeletePlan" type="button">Delete</button>
                    <button id="roundsRefreshCatalog" type="button">Refresh Catalog</button>
                </div>
                <div class="rounds-builder-actions">
                    <button id="roundsAddRow" type="button">+ Add Round</button>
                    <button id="roundsSavePlan" class="primary" type="button">Save Plan</button>
                    <button id="roundsPreview" type="button">Preview</button>
                    <button id="roundsRun" class="primary" type="button">Run</button>
                </div>
                <div id="roundsCatalogNote" class="rounds-builder-note"></div>
                <div id="roundsPlanMeta" class="rounds-builder-meta"></div>
                <div id="roundsRows" class="rounds-list"></div>
                <pre id="roundsOutput" class="rounds-output">Load a catalog, add one or more services, and save or run a rounds plan.</pre>
            </div>
        `;
        document.body.appendChild(roundsPanel);
        this.chatUI = { panel, actionBar, title, freeze, clearBeliefsBtn, logsBtn, exportBtn, speakBtn, stopSpeakBtn, toolsBtn, roundsBtn, toolsPanel, roundsPanel, messages, logsPanel, inputRow, input, send, mic, close };

        close.addEventListener("click", () => {
            this.hideChatPanel();
        });

        const sendCurrent = () => {
            const text = (input.value || "").trim();
            if (!text || !this.selectedNode) {
                return;
            }
            input.value = "";
            this.appendChatMessage(this.selectedNode, { role: "user", text, ts: Date.now() });
            this.sendChatToBackend(this.selectedNode, text);
        };

        send.addEventListener("click", sendCurrent);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                sendCurrent();
            }
        });

        mic.addEventListener("click", async () => {
            await this.toggleVoiceInput();
        });

        freeze.addEventListener("click", async () => {
            await this.freezeBeliefsForSelectedNode();
        });

        clearBeliefsBtn.addEventListener("click", async () => {
            await this.clearBeliefsForSelectedNode();
        });

        logsBtn.addEventListener("click", async () => {
            await this.toggleLogsForSelectedNode();
        });

        exportBtn.addEventListener("click", async () => {
            await this.exportSelectedNode();
        });

        speakBtn.addEventListener("click", () => {
            if (!this.selectedNode) {
                return;
            }
            this.selectedNode.properties = this.selectedNode.properties || {};
            const current = this.selectedNode.properties.tts_enabled;
            const next = current === false ? true : false;
            this.selectedNode.properties.tts_enabled = next;
            this.updateSpeakButtonForNode(this.selectedNode);
        });

        stopSpeakBtn.addEventListener("click", () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
        });

        toolsBtn.addEventListener("click", () => {
            if (!this.selectedNode) return;
            if (!this._nodeCanConfigureCamperTools(this.selectedNode)) {
                return;
            }
            const target = this.getNodeTarget(this.selectedNode);
            if (!target) return;
            const isVisible = !!(this.chatUI && this.chatUI.toolsPanel && this.chatUI.toolsPanel.classList.contains("visible"));
            if (isVisible) {
                this.toggleToolsPanel(false);
                return;
            }
            this.toggleToolsPanel(true);
            this.loadToolsForCampfire(target);
        });

        roundsBtn.addEventListener("click", async () => {
            const isVisible = !!(this.chatUI && this.chatUI.roundsPanel && this.chatUI.roundsPanel.classList.contains("visible"));
            if (isVisible) {
                this.toggleRoundsPanel(false);
                return;
            }
            await this.openRoundsBuilder();
        });

        const roundsClose = roundsPanel.querySelector("#roundsClose");
        if (roundsClose) {
            roundsClose.addEventListener("click", () => this.toggleRoundsPanel(false));
        }
    }

    setSelectedNode(node) {
        this.selectedNode = node;
        if (!node) {
            this.hideChatPanel();
            return;
        }
        this.showChatPanelForNode(node);
    }

    showChatPanelForNode(node) {
        if (!this.chatUI) {
            return;
        }
        const displayName = (node.properties && (node.properties.name || node.properties.id)) || node.title || "Node";
        this.chatUI.title.textContent = displayName;
        this.chatUI.panel.classList.remove("hidden");
        this.chatUI.actionBar.classList.remove("hidden");
        if (this.chatUI.input) {
            this.chatUI.input.placeholder = "Message this node...";
        }
        this.updateActionBarForNode(node);
        this.updateToolsButtonForNode(node);
        if (node.type === "campfire/campfire") {
            this.renderCampfireDetails(node);
        } else if (node.type === "campfire/valley") {
            this.renderValleyDetails(node);
        } else {
            if (this.chatUI.inputRow) this.chatUI.inputRow.style.display = "";
            this.renderChatHistory(node);
            this.chatUI.input.focus();
            this.updateSpeakButtonForNode(node);
            this.updateChatTitleFromBackend(node);
            this.refreshChatHistoryFromBackend(node);
        }
    }

    _escapeHtml(s) {
        const t = String(s == null ? "" : s);
        return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
    }

    _shortValleyId(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        if (text.length <= 18) return text;
        return `${text.slice(0, 8)}...${text.slice(-8)}`;
    }

    _isRemoteTarget(target) {
        return typeof target === "string" && target.startsWith("valley:");
    }

    _isRemoteNode(node) {
        if (!node) return false;
        if (node.properties && node.properties.remote === true) return true;
        return this._isRemoteTarget(this.getNodeTarget(node));
    }

    updateActionBarForNode(node) {
        if (!this.chatUI) return;
        const isRemote = this._isRemoteNode(node);
        const remoteReason = "Disabled for remote campfires.";
        const controls = [
            this.chatUI.freeze,
            this.chatUI.clearBeliefsBtn,
            this.chatUI.logsBtn,
            this.chatUI.exportBtn
        ];
        controls.forEach((btn) => {
            if (!btn) return;
            btn.disabled = isRemote;
            btn.title = isRemote ? remoteReason : "";
        });
    }

    _deriveRemoteValleySummary(valley) {
        const v = valley || {};
        const services = Array.isArray(v.exposed_services) ? v.exposed_services : [];
        const campfires = Array.isArray(v.exposed_campfires) ? v.exposed_campfires : [];
        const firstService = services.length ? services[0] : null;
        const addresses = firstService && firstService.addresses ? firstService.addresses : {};
        const publicAddress = String(v.public_address || "").trim();
        const remoteValleyId = String(v.valley_id || "").trim();
        const routeAddress = String(publicAddress || addresses.valley_id || addresses.valley_name || (remoteValleyId ? `valley:${remoteValleyId}` : (`valley:${v.name || "remote"}`))).trim();
        const routeKey = routeAddress.startsWith("valley:") ? routeAddress.slice(7).split("/")[0] : routeAddress;
        const identifier = remoteValleyId || (String(addresses.valley_id || "").trim().match(/^valley:([^/]+)/) || [null, ""])[1] || "";
        const serviceNames = services
            .map((s) => String((s && (s.name || s.service_id)) || "").trim())
            .filter(Boolean);
        return {
            displayName: String(v.name || "Remote Valley").trim(),
            originLabel: "REMOTE",
            routeAddress,
            routeKey,
            identifier,
            shortIdentifier: this._shortValleyId(identifier || routeKey),
            serviceCount: services.length,
            campfireCount: campfires.length,
            exposedCampfires: campfires,
            exposedServices: serviceNames,
            lastSeen: String(v.last_seen || "").trim(),
            trustLevel: String(v.trust_level || "").trim()
        };
    }

    _resolveSelectedRemoteValley(node, dockEntries) {
        const props = (node && node.properties) || {};
        const discovered = Array.isArray(dockEntries) ? dockEntries.map((entry) => this._deriveRemoteValleySummary(entry)) : [];
        const nodeIdentifier = String(props.identifier || "").trim();
        const nodeRoute = String(props.route_name || "").trim();
        const nodeRouteKey = String(props.route_key || "").trim();
        const nodeName = String(props.display_name || props.name || "").trim();
        const match = discovered.find((valley) => {
            return (nodeIdentifier && valley.identifier === nodeIdentifier) ||
                (nodeRoute && valley.routeAddress === nodeRoute) ||
                (nodeRouteKey && valley.routeKey === nodeRouteKey) ||
                (nodeName && valley.displayName === nodeName);
        });
        if (match) {
            return match;
        }
        return {
            displayName: nodeName || "Remote Valley",
            originLabel: "REMOTE",
            routeAddress: nodeRoute || (nodeIdentifier ? `valley:${nodeIdentifier}` : "valley:remote"),
            routeKey: nodeRouteKey || nodeIdentifier || nodeName || "remote",
            identifier: nodeIdentifier,
            shortIdentifier: this._shortValleyId(nodeIdentifier || nodeRouteKey || nodeName),
            serviceCount: 0,
            campfireCount: Number(props.total_campfires || 0),
            exposedCampfires: [],
            exposedServices: [],
            lastSeen: "",
            trustLevel: ""
        };
    }

    _resolveSelectedRemoteCampfire(node, dockEntries) {
        const target = String(this.getNodeTarget(node) || "").trim();
        const props = (node && node.properties) || {};
        const name = String(props.name || node.title || "").trim();
        const serviceId = String(props.service_id || "").trim();
        const routeName = String(props.route_name || target || "").trim();
        const remoteValleyName = String(props.remote_valley_name || "").trim();
        const remoteValleyId = String(props.remote_valley_id || "").trim();
        const valleys = Array.isArray(dockEntries) ? dockEntries : [];
        let matchedValley = null;
        let matchedService = null;

        valleys.forEach((entry) => {
            if (matchedService) return;
            const valleyName = String((entry && entry.name) || "").trim();
            const valleyId = String((entry && entry.valley_id) || "").trim();
            const publicAddress = String((entry && entry.public_address) || "").trim();
            const services = Array.isArray(entry && entry.exposed_services) ? entry.exposed_services : [];
            const valleyMatches = (remoteValleyId && remoteValleyId === valleyId) ||
                (remoteValleyName && remoteValleyName === valleyName) ||
                (publicAddress && target && target.startsWith(`${publicAddress}/`));
            services.forEach((service) => {
                if (matchedService) return;
                const addresses = (service && service.addresses) || {};
                const serviceAddress = String(addresses.valley_id || addresses.valley_name || "").trim();
                const serviceMatches = (serviceId && String((service && service.service_id) || "").trim() === serviceId) ||
                    (name && String((service && service.name) || "").trim() === name) ||
                    (serviceAddress && serviceAddress === target);
                if (valleyMatches && serviceMatches) {
                    matchedValley = entry;
                    matchedService = service;
                }
            });
        });

        const service = matchedService || {};
        const valley = matchedValley || {};
        const llm = (service && service.llm) || {};
        const addresses = (service && service.addresses) || {};
        const valleyAddress = String(valley.public_address || "").trim();
        const taskTypes = Array.isArray(service.task_types) ? service.task_types : [];
        const capabilities = Array.isArray(service.capabilities) ? service.capabilities : [];
        const visibleCampfires = Array.isArray(valley.exposed_campfires)
            ? valley.exposed_campfires.map((item) => String(item || "").trim()).filter(Boolean)
            : [];
        const visibleServiceEntries = Array.isArray(valley.exposed_services)
            ? valley.exposed_services.map((item) => {
                const service = item || {};
                return {
                    serviceId: String(service.service_id || "").trim(),
                    name: String(service.name || service.service_id || "").trim(),
                    kind: String(service.kind || "").trim(),
                    serviceKind: String(service.service_kind || service.kind || "").trim(),
                    summary: String(service.summary || "").trim(),
                    taskTypes: Array.isArray(service.task_types) ? service.task_types : [],
                    capabilities: Array.isArray(service.capabilities) ? service.capabilities : [],
                    supportsRounds: !!service.supports_rounds,
                    exposure: String(service.exposure || "").trim()
                };
            }).filter((item) => item.name)
            : [];
        const visibleCamperEntries = visibleServiceEntries.filter((item) => item.kind === "camper" || item.serviceKind === "camper");
        const visibleServices = Array.isArray(valley.exposed_services)
            ? valley.exposed_services
                .map((item) => String((item && (item.name || item.service_id)) || "").trim())
                .filter(Boolean)
            : [];
        return {
            displayName: name || String(service.name || "Remote Campfire").trim(),
            serviceId: String(service.service_id || serviceId || "").trim(),
            routeAddress: String(routeName || addresses.valley_id || addresses.valley_name || target || "(not advertised)").trim(),
            valleyName: String(valley.name || remoteValleyName || "Remote Valley").trim(),
            valleyId: String(valley.valley_id || remoteValleyId || "").trim(),
            valleyAddress: valleyAddress,
            kind: String(service.kind || props.backend_type || "campfire").trim(),
            type: String(service.type || "").trim(),
            summary: String(service.summary || props.service_summary || "").trim(),
            description: String(service.description || "").trim(),
            taskTypes,
            capabilities,
            supportsRounds: !!service.supports_rounds,
            exposure: String(service.exposure || "").trim(),
            llmProvider: String(llm.provider || "").trim(),
            llmModel: String(llm.model || "").trim(),
            visibleCampfires,
            visibleServices,
            visibleServiceEntries,
            visibleCamperEntries
        };
    }

    _remoteInspectorKey(node, remote) {
        return String((remote && remote.routeAddress) || this.getNodeTarget(node) || (node && node.id) || "").trim();
    }

    _selectedRemoteWorker(node, remote) {
        const serviceEntries = Array.isArray(remote && remote.visibleServiceEntries) ? remote.visibleServiceEntries : [];
        const camperEntries = Array.isArray(remote && remote.visibleCamperEntries) ? remote.visibleCamperEntries : [];
        const candidates = camperEntries.length ? camperEntries : serviceEntries;
        if (!candidates.length) return null;
        const selected = String(this.remoteInspectorState.get(this._remoteInspectorKey(node, remote)) || "").trim();
        return candidates.find((item) => String(item.serviceId || item.name || "").trim() === selected) || candidates[0] || null;
    }

    _findRemoteValleyNodeForCampfire(node, remote) {
        if (!this.graph || !Array.isArray(this.graph._nodes)) return null;
        const valleyId = String((remote && remote.valleyId) || (node && node.properties && node.properties.remote_valley_id) || "").trim();
        const valleyName = String((remote && remote.valleyName) || (node && node.properties && node.properties.remote_valley_name) || "").trim();
        return this.graph._nodes.find((candidate) => {
            if (!candidate || candidate.type !== "campfire/valley") return false;
            const props = candidate.properties || {};
            if (!props.remote) return false;
            const candidateId = String(props.identifier || "").trim();
            const candidateName = String(props.display_name || props.name || "").trim();
            return (valleyId && candidateId === valleyId) || (valleyName && candidateName === valleyName);
        }) || null;
    }

    async _queueRemoteCampfireInRounds(node, remote) {
        await this.openRoundsBuilder();
        const remoteTarget = String((remote && remote.routeAddress) || this.getNodeTarget(node) || "").trim();
        const remoteName = String((remote && remote.displayName) || (node && node.properties && node.properties.name) || node.title || "").trim();
        const remoteServiceId = String((remote && remote.serviceId) || (node && node.properties && node.properties.service_id) || "").trim();
        const match = (this.roundsState.catalog || []).find((service) => {
            if (!service || !service._remote) return false;
            const key = this._serviceOptionKey(service);
            return (remoteServiceId && String(service.service_id || "").trim() === remoteServiceId) ||
                (remoteTarget && key === remoteTarget) ||
                (remoteName && String(service.name || "").trim() === remoteName);
        });
        const row = match
            ? this._applyServiceToRow(this._emptyRoundRow(), match)
            : Object.assign(this._emptyRoundRow(), {
                label: remoteName,
                target_address: remoteTarget,
                service_id: remoteServiceId,
                task_type: String(((remote && remote.taskTypes) || [])[0] || "").trim()
            });
        const rows = Array.isArray(this.roundsState.rows) ? this.roundsState.rows : [];
        const emptyIdx = rows.findIndex((item) => {
            const r = item || {};
            return !String(r.label || "").trim() &&
                !String(r.target_address || "").trim() &&
                !String(r.service_id || "").trim() &&
                !String(r.task_type || "").trim() &&
                !String(r.instruction || "").trim();
        });
        if (emptyIdx >= 0) rows[emptyIdx] = row;
        else rows.push(row);
        this.roundsState.rows = rows.length ? rows : [row];
        this.renderRoundsBuilder();
        this._setRoundsOutput(`Added remote campfire "${remoteName || remoteTarget}" to the rounds chain.`, false);
    }

    async renderRemoteCampfireDetails(node) {
        if (!this.chatUI) return;
        const target = this.getNodeTarget(node);
        if (!target) return;
        if (this.chatUI.inputRow) this.chatUI.inputRow.style.display = "";
        this.chatUI.logsPanel.classList.add("hidden");
        this.toggleToolsPanel(false);
        this.chatUI.messages.innerHTML = `<div class="chat-details">Loading remote campfire details…</div>`;
        try {
            const res = await fetch("/api/dock/valleys");
            if (!res.ok) {
                this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load remote campfire details: ${res.status}</div>`;
                return;
            }
            const data = await res.json();
            const dock = (data && data.valleys) || [];
            const remote = this._resolveSelectedRemoteCampfire(node, dock);
            const taskTypes = (remote.taskTypes || []).join(", ") || "(not advertised)";
            const capabilities = (remote.capabilities || []).join(", ") || "(not advertised)";
            const visibleCampfires = (remote.visibleCampfires || []).join(", ") || "(none advertised)";
            const visibleServices = (remote.visibleServices || []).join(", ") || "(none advertised)";
            const visibleCampers = Array.isArray(remote.visibleCamperEntries) ? remote.visibleCamperEntries : [];
            const selectedWorker = this._selectedRemoteWorker(node, remote);
            const selectedWorkerTaskTypes = selectedWorker && Array.isArray(selectedWorker.taskTypes) && selectedWorker.taskTypes.length
                ? selectedWorker.taskTypes.join(", ")
                : "(not advertised)";
            const selectedWorkerCapabilities = selectedWorker && Array.isArray(selectedWorker.capabilities) && selectedWorker.capabilities.length
                ? selectedWorker.capabilities.join(", ")
                : "(not advertised)";
            const visibleCamperButtons = visibleCampers.length
                ? `<div class="chat-options">${visibleCampers.map((item) => {
                    const key = this._escapeHtml(String(item.serviceId || item.name || "").trim());
                    const selectedKey = String(selectedWorker && (selectedWorker.serviceId || selectedWorker.name) || "").trim();
                    const active = key === this._escapeHtml(selectedKey) ? " remote-worker-btn-active" : "";
                    return `<button type="button" class="chat-option-btn remote-worker-btn${active}" data-service-id="${key}">${this._escapeHtml(item.name)}</button>`;
                }).join("")}</div>`
                : `<div class="chat-details-text">No remote campers are advertised for this remote valley.</div>`;
            const llmText = [remote.llmProvider || "", remote.llmModel || ""].filter(Boolean).join(" / ") || "(not advertised)";
            const description = remote.description || remote.summary || "This remote campfire is visible through dock discovery. Remote admin controls are disabled here.";
            const body = `
                <div class="chat-details">
                    <div class="chat-details-block">
                        <div class="chat-details-h">Remote Campfire</div>
                        <div class="valley-card remote">
                            <div class="valley-card-head">
                                <span class="valley-badge remote">REMOTE</span>
                                <span class="valley-card-title">${this._escapeHtml(remote.displayName || "Remote Campfire")}</span>
                            </div>
                            <div class="valley-card-row"><span>Route</span><span>${this._escapeHtml(remote.routeAddress || target)}</span></div>
                            <div class="valley-card-row"><span>Remote Valley</span><span>${this._escapeHtml(remote.valleyName || "(unknown)")}</span></div>
                            <div class="valley-card-row"><span>Service ID</span><span>${this._escapeHtml(remote.serviceId || "(not advertised)")}</span></div>
                            <div class="valley-card-row"><span>Kind</span><span>${this._escapeHtml(remote.kind || "(not advertised)")}</span></div>
                            <div class="valley-card-row"><span>LLM</span><span>${this._escapeHtml(llmText)}</span></div>
                            <div class="valley-card-row"><span>Supports Rounds</span><span>${this._escapeHtml(remote.supportsRounds ? "yes" : "no")}</span></div>
                            <div class="valley-card-row"><span>Exposure</span><span>${this._escapeHtml(remote.exposure || "(not advertised)")}</span></div>
                        </div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Summary</div>
                        <div class="chat-details-text">${this._escapeHtml(description)}</div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Quick Actions</div>
                        <div class="chat-details-actions">
                            <button id="remoteCampfireMessageBtn" type="button">Message This Campfire</button>
                            <button id="remoteCampfireRoundsBtn" type="button">Use In Rounds</button>
                            <button id="remoteCampfireValleyBtn" type="button">Open Remote Valley</button>
                            <button id="remoteCampfireServicesBtn" type="button">Show Visible Services</button>
                        </div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Task Types</div>
                        <div class="chat-details-text">${this._escapeHtml(taskTypes)}</div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Capabilities</div>
                        <div class="chat-details-text">${this._escapeHtml(capabilities)}</div>
                    </div>
                    <div class="chat-details-block" id="remoteCampfireVisibleCampers">
                        <div class="chat-details-h">Visible Remote Campers</div>
                        ${visibleCamperButtons}
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Selected Remote Worker</div>
                        <div class="valley-card remote">
                            <div class="valley-card-row"><span>Name</span><span>${this._escapeHtml((selectedWorker && selectedWorker.name) || "(none advertised)")}</span></div>
                            <div class="valley-card-row"><span>Kind</span><span>${this._escapeHtml((selectedWorker && (selectedWorker.serviceKind || selectedWorker.kind)) || "(none advertised)")}</span></div>
                            <div class="valley-card-row"><span>Task Types</span><span>${this._escapeHtml(selectedWorkerTaskTypes)}</span></div>
                            <div class="valley-card-row"><span>Capabilities</span><span>${this._escapeHtml(selectedWorkerCapabilities)}</span></div>
                            <div class="valley-card-row"><span>Supports Rounds</span><span>${this._escapeHtml(selectedWorker ? (selectedWorker.supportsRounds ? "yes" : "no") : "(not advertised)")}</span></div>
                            <div class="valley-card-row"><span>Access</span><span>Inspect only</span></div>
                        </div>
                        <div class="chat-details-text">Remote workers can be inspected here, but direct access and admin functions still require permission from the owning valley.</div>
                    </div>
                    <div class="chat-details-block" id="remoteCampfireVisibleCampfires">
                        <div class="chat-details-h">Visible Campfires In Remote Valley</div>
                        <div class="chat-details-text">${this._escapeHtml(visibleCampfires)}</div>
                    </div>
                    <div class="chat-details-block" id="remoteCampfireVisibleServices">
                        <div class="chat-details-h">Visible Services In Remote Valley</div>
                        <div class="chat-details-text">${this._escapeHtml(visibleServices)}</div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Allowed Actions</div>
                        <div class="chat-details-text">You can message this remote campfire with the input box below or include it in rounds. Admin functions stay disabled because this campfire belongs to a remote valley.</div>
                    </div>
                </div>
            `;
            this.chatUI.messages.innerHTML = body;
            if (this.chatUI.input) {
                this.chatUI.input.placeholder = `Message remote campfire: ${remote.displayName || target}`;
            }
            const messageBtn = document.getElementById("remoteCampfireMessageBtn");
            const roundsBtn = document.getElementById("remoteCampfireRoundsBtn");
            const valleyBtn = document.getElementById("remoteCampfireValleyBtn");
            const servicesBtn = document.getElementById("remoteCampfireServicesBtn");
            const visibleServicesBlock = document.getElementById("remoteCampfireVisibleServices");
            const workerButtons = Array.from(document.querySelectorAll(".remote-worker-btn"));
            const remoteValleyNode = this._findRemoteValleyNodeForCampfire(node, remote);
            if (messageBtn) {
                messageBtn.onclick = () => {
                    if (this.chatUI && this.chatUI.inputRow) this.chatUI.inputRow.style.display = "";
                    if (this.chatUI && this.chatUI.input) this.chatUI.input.focus();
                };
            }
            if (roundsBtn) {
                roundsBtn.onclick = async () => {
                    roundsBtn.disabled = true;
                    try {
                        await this._queueRemoteCampfireInRounds(node, remote);
                    } finally {
                        roundsBtn.disabled = false;
                    }
                };
            }
            if (valleyBtn) {
                valleyBtn.disabled = !remoteValleyNode;
                valleyBtn.onclick = () => {
                    if (remoteValleyNode) this.setSelectedNode(remoteValleyNode);
                };
            }
            if (servicesBtn) {
                servicesBtn.onclick = () => {
                    if (visibleServicesBlock && visibleServicesBlock.scrollIntoView) {
                        visibleServicesBlock.scrollIntoView({ behavior: "smooth", block: "nearest" });
                    }
                };
            }
            workerButtons.forEach((btn) => {
                btn.onclick = async () => {
                    const key = String(btn.getAttribute("data-service-id") || "").trim();
                    this.remoteInspectorState.set(this._remoteInspectorKey(node, remote), key);
                    await this.renderRemoteCampfireDetails(node);
                };
            });
        } catch (e) {
            this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load remote campfire details.</div>`;
        }
    }

    async _loadLocalValleySummary() {
        let details = {};
        let identifier = "";
        try {
            const res = await fetch("/api/valley/details");
            if (res.ok) {
                details = await res.json();
            }
        } catch (e) {
        }
        try {
            const idRes = await fetch("/api/valley/identifier");
            if (idRes.ok) {
                const idData = await idRes.json();
                identifier = String((idData && idData.identifier) || "").trim();
            }
        } catch (e) {
        }
        const valley = (details && details.valley) || {};
        const displayName = String(valley.name || this.nodes.valley?.properties?.display_name || "Local Valley").trim();
        return {
            displayName,
            originLabel: "LOCAL",
            identifier,
            shortIdentifier: this._shortValleyId(identifier),
            routeAddress: identifier ? `valley:${identifier}` : `valley:${displayName}`,
            routeKey: identifier || displayName,
            campfireCount: Number(valley.campfire_total || 0),
            camperCount: Number(valley.camper_total || 0)
        };
    }

    _markdownToHtml(text) {
        const raw = String(text == null ? "" : text);
        const blocks = [];
        let src = raw.replace(/\r\n/g, "\n");
        src = src.replace(/```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g, (_m, lang, code) => {
            const i = blocks.length;
            const l = (lang || "").trim();
            const c = this._escapeHtml(code || "");
            const html = `<pre class="md-pre"><code class="md-code${l ? " language-" + this._escapeHtml(l) : ""}">${c}</code></pre>`;
            blocks.push(html);
            return `@@BLOCK_${i}@@`;
        });
        const lines = src.split("\n");
        let out = "";
        let listMode = null;
        const closeList = () => {
            if (listMode === "ul") out += "</ul>";
            if (listMode === "ol") out += "</ol>";
            listMode = null;
        };
        const inline = (s) => {
            let x = this._escapeHtml(s);
            x = x.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_m, t, u) => `<a href="${this._escapeHtml(u)}" target="_blank" rel="noopener noreferrer">${this._escapeHtml(t)}</a>`);
            x = x.replace(/`([^`]+)`/g, (_m, c) => `<code class="md-inline">${this._escapeHtml(c)}</code>`);
            x = x.replace(/\*\*([^*]+)\*\*/g, (_m, b) => `<strong>${this._escapeHtml(b)}</strong>`);
            return x;
        };
        for (const line of lines) {
            const l = line || "";
            const mH = l.match(/^(#{1,6})\s+(.*)$/);
            if (mH) {
                closeList();
                const level = mH[1].length;
                out += `<div class="md-h md-h${level}">${inline(mH[2] || "")}</div>`;
                continue;
            }
            const mUl = l.match(/^\s*[-*]\s+(.*)$/);
            if (mUl) {
                if (listMode !== "ul") {
                    closeList();
                    listMode = "ul";
                    out += "<ul class=\"md-ul\">";
                }
                out += `<li>${inline(mUl[1] || "")}</li>`;
                continue;
            }
            const mOl = l.match(/^\s*\d+\.\s+(.*)$/);
            if (mOl) {
                if (listMode !== "ol") {
                    closeList();
                    listMode = "ol";
                    out += "<ol class=\"md-ol\">";
                }
                out += `<li>${inline(mOl[1] || "")}</li>`;
                continue;
            }
            const mQ = l.match(/^\s*>\s+(.*)$/);
            if (mQ) {
                closeList();
                out += `<blockquote class="md-quote">${inline(mQ[1] || "")}</blockquote>`;
                continue;
            }
            if (!l.trim()) {
                closeList();
                out += "<div class=\"md-sp\"></div>";
                continue;
            }
            closeList();
            out += `<div class="md-p">${inline(l)}</div>`;
        }
        closeList();
        out = out.replace(/@@BLOCK_(\d+)@@/g, (_m, idx) => blocks[Number(idx)] || "");
        return out;
    }

    async renderCampfireDetails(node) {
        if (!this.chatUI) return;
        const target = this.getNodeTarget(node);
        if (!target) return;
        if (this._isRemoteNode(node)) {
            await this.renderRemoteCampfireDetails(node);
            return;
        }
        if (this.chatUI.inputRow) this.chatUI.inputRow.style.display = "none";
        this.chatUI.logsPanel.classList.add("hidden");
        this.toggleToolsPanel(false);
        this.chatUI.messages.innerHTML = `<div class="chat-details">Loading campfire details…</div>`;
        try {
            const res = await fetch(`/api/campfire/details?campfire=${encodeURIComponent(target)}`);
            if (!res.ok) {
                this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load: ${res.status}</div>`;
                return;
            }
            const data = await res.json();
            const pb = (data && data.party_box) || {};
            const cats = (pb && pb.categories) || {};
            const catLines = Object.keys(cats).map((k) => {
                const c = cats[k] || {};
                const count = typeof c.count === "number" ? c.count : 0;
                const items = (c.items || []).slice(0, 10).map((x) => `<li>${this._escapeHtml(x)}</li>`).join("");
                return `<div class="chat-details-block"><div class="chat-details-h">Party Box: ${this._escapeHtml(k)} (${count})</div><ul class="chat-details-list">${items}</ul></div>`;
            }).join("");
            const llm = (data && data.llm) || {};
            const dock = (data && data.dock) || {};
            const workflow = (data && data.workflow) || {};
            const schedule = (data && data.schedule) || {};
            const campers = (data && data.campers) || [];
            const body = `
                <div class="chat-details">
                    <div class="chat-details-block">
                        <div class="chat-details-h">Campfire</div>
                        <div class="chat-details-kv"><span>Name</span><span>${this._escapeHtml(target)}</span></div>
                        <div class="chat-details-kv"><span>Type</span><span>${this._escapeHtml(data.type || "")}</span></div>
                        <div class="chat-details-kv"><span>Running</span><span>${this._escapeHtml(String(!!data.running))}</span></div>
                        <div class="chat-details-kv"><span>LLM</span><span>${this._escapeHtml((llm.provider || "ollama") + " / " + (llm.model || "(default)"))}</span></div>
                        <div class="chat-details-kv"><span>Dock Identifier</span><span>${this._escapeHtml(dock.identifier || "")}</span></div>
                        <div class="chat-details-kv"><span>Dock Address</span><span>${this._escapeHtml(dock.address || "")}</span></div>
                        <div class="chat-details-actions">
                            <input id="campfireDockIdentifierInput" class="chat-input" type="text" placeholder="Set Dock Identifier (optional)" value="${this._escapeHtml(dock.identifier || "")}" autocomplete="off" />
                            <button id="campfireDockIdentifierSave" type="button">Save</button>
                            <button id="campfireDeleteBtn" type="button" class="danger">Delete Campfire</button>
                        </div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Campers</div>
                        <div class="chat-details-text">${this._escapeHtml((campers || []).join(", ") || "(none)")}</div>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Workflow</div>
                        <pre class="chat-details-pre">${this._escapeHtml(JSON.stringify(workflow || {}, null, 2))}</pre>
                    </div>
                    <div class="chat-details-block">
                        <div class="chat-details-h">Schedule</div>
                        <pre class="chat-details-pre">${this._escapeHtml(JSON.stringify(schedule || {}, null, 2))}</pre>
                    </div>
                    ${catLines}
                </div>
            `;
            this.chatUI.messages.innerHTML = body;
            const input = document.getElementById("campfireDockIdentifierInput");
            const btn = document.getElementById("campfireDockIdentifierSave");
            const deleteBtn = document.getElementById("campfireDeleteBtn");
            if (btn && input) {
                btn.onclick = async () => {
                    const v = String(input.value || "").trim();
                    btn.disabled = true;
                    try {
                        await fetch("/api/campfire/identifier", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ campfire: target, identifier: v })
                        });
                    } catch (e) {
                    }
                    btn.disabled = false;
                    this.renderCampfireDetails(node);
                };
                input.addEventListener("keydown", (e) => {
                    if (e.key === "Enter") {
                        e.preventDefault();
                        btn.click();
                    }
                });
            }
            if (deleteBtn) {
                deleteBtn.onclick = async () => {
                    const firstRes = await fetch("/api/campfire/delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ campfire: target, confirm: false })
                    });
                    const firstData = firstRes.ok ? await firstRes.json() : null;
                    const summary = (firstData && firstData.summary) || {};
                    const campfiresToDelete = Array.isArray(summary.campfires) ? summary.campfires : [];
                    const auditorsToDelete = Array.isArray(summary.auditors) ? summary.auditors : [];
                    const campersToDelete = Array.isArray(summary.campers) ? summary.campers : [];
                    const total = typeof summary.total === "number" ? summary.total : 0;
                    const confirmText =
                        `Delete '${target}'?\n\n` +
                        `This will also remove:\n` +
                        `- Campfires: ${campfiresToDelete.join(", ") || "(none)"}\n` +
                        `- Auditors: ${auditorsToDelete.join(", ") || "(none)"}\n` +
                        `- Campers: ${campersToDelete.join(", ") || "(none)"}\n\n` +
                        `Total nodes to delete: ${total}`;
                    if (!window.confirm(confirmText)) {
                        return;
                    }
                    deleteBtn.disabled = true;
                    try {
                        const res2 = await fetch("/api/campfire/delete", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ campfire: target, confirm: true })
                        });
                        const data2 = res2.ok ? await res2.json() : null;
                        const msg = (data2 && data2.message) || `Deleted '${target}'.`;
                        this.chatUI.messages.innerHTML = `<div class="chat-details">${this._escapeHtml(msg)}</div>`;
                        await this.fetchBackendCampfires(true);
                        await this.syncBackendCampfireNodes();
                        this.setSelectedNode(null);
                    } catch (e) {
                        this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to delete campfire.</div>`;
                    } finally {
                        deleteBtn.disabled = false;
                    }
                };
            }
        } catch (e) {
            this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load campfire details.</div>`;
        }
    }

    async renderValleyDetails(node) {
        if (!this.chatUI) return;
        if (this.chatUI.inputRow) this.chatUI.inputRow.style.display = "none";
        this.chatUI.logsPanel.classList.add("hidden");
        this.toggleToolsPanel(false);
        this.chatUI.messages.innerHTML = `<div class="chat-details">Loading valley details…</div>`;
        try {
            const res = await fetch(`/api/valley/details`);
            if (!res.ok) {
                this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load: ${res.status}</div>`;
                return;
            }
            const data = await res.json();
            const v = (data && data.valley) || {};
            let valleyId = v.identifier || "";
            try {
                const idRes = await fetch(`/api/valley/identifier`);
                if (idRes.ok) {
                    const idData = await idRes.json();
                    if (idData && idData.identifier) valleyId = idData.identifier;
                }
            } catch (e) {
            }
            const dock = (data && data.dock) || [];
            const schedules = (data && data.schedules) || [];
            let graphCampfireCount = 0;
            try {
                graphCampfireCount = (this.graph && this.graph._nodes ? this.graph._nodes.filter((n) => n && n.type === "campfire/campfire").length : 0);
            } catch (e) {
                graphCampfireCount = 0;
            }
            const backendCampfires = (v.campfires || []);
            const backendCampers = (v.campers || []);
            const auditorCampfires = (v.auditor_campfires || []);
            const localRouteAddress = valleyId ? `valley:${valleyId}` : `valley:${v.name || "local"}`;
            const discoveredValleys = Array.isArray(dock) ? dock.map((entry) => this._deriveRemoteValleySummary(entry)) : [];
            const isRemoteSelection = !!(node && node.properties && node.properties.remote);
            const selectedRemoteValley = isRemoteSelection ? this._resolveSelectedRemoteValley(node, dock) : null;
            const dockValleyHtml = discoveredValleys.length
                ? discoveredValleys.map((valley) => {
                    const campfireBits = valley.exposedCampfires.length ? valley.exposedCampfires.slice(0, 4).join(", ") : "(none)";
                    const serviceBits = valley.exposedServices.length ? valley.exposedServices.slice(0, 4).join(", ") : "(none)";
                    return `
                        <div class="valley-card remote">
                            <div class="valley-card-head">
                                <span class="valley-badge remote">${this._escapeHtml(valley.originLabel)}</span>
                                <span class="valley-card-title">${this._escapeHtml(valley.displayName)}</span>
                            </div>
                            <div class="valley-card-row"><span>Route</span><span>${this._escapeHtml(valley.routeAddress)}</span></div>
                            <div class="valley-card-row"><span>Stable ID</span><span>${this._escapeHtml(valley.shortIdentifier || "(not advertised)")}</span></div>
                            <div class="valley-card-row"><span>Alias</span><span>${this._escapeHtml(valley.displayName || "(unnamed)")}</span></div>
                            <div class="valley-card-row"><span>Trust</span><span>${this._escapeHtml(valley.trustLevel || "(unknown)")}</span></div>
                            <div class="valley-card-row"><span>Last Seen</span><span>${this._escapeHtml(valley.lastSeen || "(unknown)")}</span></div>
                            <div class="valley-card-row"><span>Visible Campfires</span><span>${this._escapeHtml(String(valley.campfireCount))}</span></div>
                            <div class="valley-card-row"><span>Visible Services</span><span>${this._escapeHtml(String(valley.serviceCount))}</span></div>
                            <div class="valley-card-meta">Campfires: ${this._escapeHtml(campfireBits)}</div>
                            <div class="valley-card-meta">Services: ${this._escapeHtml(serviceBits)}</div>
                        </div>
                    `;
                }).join("")
                : `<div class="chat-details-text">(none discovered)</div>`;
            const body = isRemoteSelection
                ? `
                    <div class="chat-details">
                        <div class="chat-details-block">
                            <div class="chat-details-h">Remote Valley</div>
                            <div class="valley-card remote">
                                <div class="valley-card-head">
                                    <span class="valley-badge remote">REMOTE</span>
                                    <span class="valley-card-title">${this._escapeHtml(selectedRemoteValley.displayName || "Remote Valley")}</span>
                                </div>
                                <div class="valley-card-row"><span>Route</span><span>${this._escapeHtml(selectedRemoteValley.routeAddress || "(not advertised)")}</span></div>
                                <div class="valley-card-row"><span>Stable ID</span><span>${this._escapeHtml(selectedRemoteValley.shortIdentifier || "(not advertised)")}</span></div>
                                <div class="valley-card-row"><span>Alias</span><span>${this._escapeHtml(selectedRemoteValley.displayName || "(unnamed)")}</span></div>
                                <div class="valley-card-row"><span>Visible Campfires</span><span>${this._escapeHtml(String(selectedRemoteValley.campfireCount || 0))}</span></div>
                                <div class="valley-card-row"><span>Visible Services</span><span>${this._escapeHtml(String(selectedRemoteValley.serviceCount || 0))}</span></div>
                                <div class="valley-card-row"><span>Trust</span><span>${this._escapeHtml(selectedRemoteValley.trustLevel || "(unknown)")}</span></div>
                                <div class="valley-card-row"><span>Last Seen</span><span>${this._escapeHtml(selectedRemoteValley.lastSeen || "(unknown)")}</span></div>
                            </div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Visible Campfires</div>
                            <div class="chat-details-text">${this._escapeHtml((selectedRemoteValley.exposedCampfires || []).join(", ") || "(none)")}</div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Visible Services</div>
                            <div class="chat-details-text">${this._escapeHtml((selectedRemoteValley.exposedServices || []).join(", ") || "(none)")}</div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Local Dock View</div>
                            ${dockValleyHtml}
                        </div>
                    </div>
                `
                : `
                    <div class="chat-details">
                        <div class="chat-details-block">
                            <div class="chat-details-h">Valley</div>
                            <div class="valley-card local">
                                <div class="valley-card-head">
                                    <span class="valley-badge local">LOCAL</span>
                                    <span class="valley-card-title">${this._escapeHtml(v.name || "Local Valley")}</span>
                                </div>
                                <div class="valley-card-row"><span>Route</span><span>${this._escapeHtml(localRouteAddress)}</span></div>
                                <div class="valley-card-row"><span>Stable ID</span><span>${this._escapeHtml(this._shortValleyId(valleyId) || "(not set)")}</span></div>
                                <div class="valley-card-row"><span>Graph Campfires</span><span>${this._escapeHtml(String(graphCampfireCount))}</span></div>
                                <div class="valley-card-row"><span>Backend Campfires</span><span>${this._escapeHtml(String(v.campfire_total || backendCampfires.length || 0))}</span></div>
                                <div class="valley-card-row"><span>Backend Campers</span><span>${this._escapeHtml(String(v.camper_total || backendCampers.length || 0))}</span></div>
                            </div>
                            <div class="chat-details-actions">
                                <input id="valleyIdentifierInput" class="chat-input" type="text" placeholder="Set Valley UUID" value="${this._escapeHtml(valleyId || "")}" autocomplete="off" />
                                <button id="valleyIdentifierSave" type="button">Save</button>
                            </div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Backend Campfire Names</div>
                            <div class="chat-details-text">${this._escapeHtml((backendCampfires || []).join(", ") || "(none)")}</div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Backend Camper Names</div>
                            <div class="chat-details-text">${this._escapeHtml((backendCampers || []).join(", ") || "(none)")}</div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Legacy Auditor Campfires</div>
                            <div class="chat-details-text">${this._escapeHtml((auditorCampfires || []).join(", ") || "(none)")}</div>
                            <div class="chat-details-actions"><button id="cleanupAuditorsBtn" type="button">Cleanup Legacy Auditors</button></div>
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Dock Valleys</div>
                            ${dockValleyHtml}
                        </div>
                        <div class="chat-details-block">
                            <div class="chat-details-h">Schedules</div>
                            <pre class="chat-details-pre">${this._escapeHtml(JSON.stringify(schedules || [], null, 2))}</pre>
                        </div>
                    </div>
                `;
            this.chatUI.messages.innerHTML = body;
            const btn = document.getElementById("cleanupAuditorsBtn");
            if (btn) {
                btn.disabled = !(auditorCampfires && auditorCampfires.length);
                btn.onclick = async () => {
                    try {
                        btn.disabled = true;
                        await fetch("/api/auditors/cleanup", { method: "POST" });
                    } catch (e) {
                    }
                    this.renderValleyDetails(node);
                    try {
                        this.syncBackendCampfireNodes();
                    } catch (e) {
                    }
                };
            }
            const idInput = document.getElementById("valleyIdentifierInput");
            const idSave = document.getElementById("valleyIdentifierSave");
            if (idInput && idSave) {
                idSave.onclick = async () => {
                    const v = String(idInput.value || "").trim();
                    idSave.disabled = true;
                    try {
                        await fetch("/api/valley/identifier", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ identifier: v })
                        });
                    } catch (e) {
                    }
                    idSave.disabled = false;
                    this.renderValleyDetails(node);
                };
                idInput.addEventListener("keydown", (e) => {
                    if (e.key === "Enter") {
                        e.preventDefault();
                        idSave.click();
                    }
                });
            }
        } catch (e) {
            this.chatUI.messages.innerHTML = `<div class="chat-details">Failed to load valley details.</div>`;
        }
    }

    updateSpeakButtonForNode(node) {
        if (!this.chatUI || !this.chatUI.speakBtn) {
            return;
        }
        const enabled = !(node && node.properties && node.properties.tts_enabled === false);
        this.chatUI.speakBtn.textContent = enabled ? "🔊 Speak: On" : "🔇 Speak: Off";
    }

    _nodeCanConfigureCamperTools(node) {
        if (!node) return false;
        if (node.type !== "campfire/camper") return false;
        if (node.properties && (node.properties.type === "auditor" || node.properties.auditor_mode)) return false;
        const target = this.getNodeTarget(node);
        if (!target) return false;
        if (typeof target === "string" && target.startsWith("valley:")) return false;
        return true;
    }

    updateToolsButtonForNode(node) {
        if (!this.chatUI || !this.chatUI.toolsBtn) return;
        const ok = this._nodeCanConfigureCamperTools(node);
        this.chatUI.toolsBtn.disabled = !ok;
        this.chatUI.toolsBtn.textContent = ok ? "🧰 Camper Tools" : "🧰 Camper Tools";
        if (!ok) this.toggleToolsPanel(false);
    }

    toggleToolsPanel(visible) {
        if (!this.chatUI || !this.chatUI.toolsPanel) return;
        if (visible) this.chatUI.toolsPanel.classList.add("visible");
        else this.chatUI.toolsPanel.classList.remove("visible");
    }

    toggleRoundsPanel(visible) {
        if (!this.chatUI || !this.chatUI.roundsPanel) return;
        if (visible) this.chatUI.roundsPanel.classList.add("visible");
        else this.chatUI.roundsPanel.classList.remove("visible");
    }

    _getRoundsElements() {
        const panel = this.chatUI && this.chatUI.roundsPanel;
        if (!panel) return {};
        return {
            panel,
            savedPlans: panel.querySelector("#roundsSavedPlans"),
            campfire: panel.querySelector("#roundsCampfire"),
            planName: panel.querySelector("#roundsPlanName"),
            description: panel.querySelector("#roundsDescription"),
            task: panel.querySelector("#roundsTask"),
            addRow: panel.querySelector("#roundsAddRow"),
            savePlan: panel.querySelector("#roundsSavePlan"),
            preview: panel.querySelector("#roundsPreview"),
            run: panel.querySelector("#roundsRun"),
            loadPlan: panel.querySelector("#roundsLoadPlan"),
            deletePlan: panel.querySelector("#roundsDeletePlan"),
            newPlan: panel.querySelector("#roundsNewPlan"),
            refreshCatalog: panel.querySelector("#roundsRefreshCatalog"),
            rows: panel.querySelector("#roundsRows"),
            output: panel.querySelector("#roundsOutput"),
            catalogNote: panel.querySelector("#roundsCatalogNote"),
            planMeta: panel.querySelector("#roundsPlanMeta")
        };
    }

    _roundsContextCampfire() {
        if (!this.selectedNode || this.selectedNode.type !== "campfire/campfire") return "";
        const target = this.getNodeTarget(this.selectedNode);
        return typeof target === "string" ? target : "";
    }

    _emptyRoundRow() {
        return { label: "", target_address: "", service_id: "", task_type: "", mode: "replace", instruction: "" };
    }

    _serviceOptionKey(service) {
        if (!service) return "";
        const addresses = service.addresses || {};
        return String(service.target_address || addresses.valley_id || addresses.valley_name || service.service_id || service.name || "").trim();
    }

    _serviceOptionLabel(service) {
        if (!service) return "(unknown service)";
        const name = String(service.name || service.service_id || "service").trim();
        const taskTypes = Array.isArray(service.task_types) ? service.task_types.filter(Boolean) : [];
        const valleyName = String(service._valley_name || (service._remote ? "remote" : "local")).trim();
        const suffix = taskTypes.length ? ` [${taskTypes.slice(0, 2).join(", ")}]` : "";
        return `${name}${suffix} - ${valleyName}`;
    }

    _applyServiceToRow(row, service) {
        const clone = Object.assign({}, row || this._emptyRoundRow());
        if (!service) return clone;
        const addresses = service.addresses || {};
        clone.label = String(service.name || service.service_id || clone.label || "").trim();
        clone.target_address = String(addresses.valley_id || addresses.valley_name || service.target_address || clone.target_address || "").trim();
        clone.service_id = String(service.service_id || clone.service_id || "").trim();
        const taskTypes = Array.isArray(service.task_types) ? service.task_types.filter(Boolean) : [];
        clone.task_type = String(clone.task_type || taskTypes[0] || "").trim();
        return clone;
    }

    async loadRoundsCatalog() {
        const res = await fetch("/api/rounds/catalog");
        if (!res.ok) throw new Error(`Failed to load rounds catalog (${res.status})`);
        const data = await res.json();
        const local = Array.isArray(data && data.local) ? data.local : [];
        const remote = Array.isArray(data && data.remote) ? data.remote : [];
        this.roundsState.catalog = []
            .concat(local.map((service) => Object.assign({ _remote: false, _valley_name: "local" }, service || {})))
            .concat(remote.map((service) => Object.assign({ _remote: true }, service || {})));
        this.roundsState.catalogMeta = (data && data.dock) || {};
    }

    async loadRoundsPlans() {
        const res = await fetch("/api/rounds/plans");
        if (!res.ok) throw new Error(`Failed to load rounds plans (${res.status})`);
        const data = await res.json();
        this.roundsState.plans = Array.isArray(data && data.plans) ? data.plans : [];
    }

    _setRoundsOutput(text, isError) {
        const els = this._getRoundsElements();
        if (!els.output) return;
        els.output.textContent = String(text == null ? "" : text);
        els.output.classList.toggle("error", !!isError);
    }

    _resetRoundsBuilder() {
        this.roundsState.rows = [this._emptyRoundRow()];
        this.roundsState.activePlanName = "";
        const els = this._getRoundsElements();
        if (els.savedPlans) els.savedPlans.value = "";
        if (els.planName) els.planName.value = "";
        if (els.description) els.description.value = "";
        if (els.task) els.task.value = "";
        if (els.campfire) els.campfire.value = this._roundsContextCampfire();
        if (els.planMeta) els.planMeta.textContent = "";
        this._setRoundsOutput("Load a catalog, add one or more services, and save or run a rounds plan.", false);
        this.renderRoundsRows();
    }

    async openRoundsBuilder() {
        this.toggleToolsPanel(false);
        this.toggleRoundsPanel(true);
        this.bindRoundsBuilderEvents();
        const els = this._getRoundsElements();
        if (els.campfire && !els.campfire.value) els.campfire.value = this._roundsContextCampfire();
        try {
            await Promise.all([this.loadRoundsCatalog(), this.loadRoundsPlans()]);
            if (!Array.isArray(this.roundsState.rows) || !this.roundsState.rows.length) {
                this.roundsState.rows = [this._emptyRoundRow()];
            }
            this.renderRoundsBuilder();
        } catch (e) {
            this.renderRoundsBuilder();
            this._setRoundsOutput(`Failed to load rounds builder data.\n${e}`, true);
        }
    }

    bindRoundsBuilderEvents() {
        if (this.roundsState.boundRoundsUi) return;
        const els = this._getRoundsElements();
        if (!els.panel) return;
        if (els.addRow) {
            els.addRow.addEventListener("click", () => {
                this.roundsState.rows.push(this._emptyRoundRow());
                this.renderRoundsRows();
            });
        }
        if (els.newPlan) els.newPlan.addEventListener("click", () => this._resetRoundsBuilder());
        if (els.refreshCatalog) {
            els.refreshCatalog.addEventListener("click", async () => {
                try {
                    await Promise.all([this.loadRoundsCatalog(), this.loadRoundsPlans()]);
                    this.renderRoundsBuilder();
                    this._setRoundsOutput("Rounds catalog refreshed.", false);
                } catch (e) {
                    this._setRoundsOutput(`Failed to refresh rounds catalog.\n${e}`, true);
                }
            });
        }
        if (els.loadPlan) {
            els.loadPlan.addEventListener("click", async () => {
                const name = String((els.savedPlans && els.savedPlans.value) || "").trim();
                if (!name) return;
                try {
                    const res = await fetch(`/api/rounds/plans/${encodeURIComponent(name)}`);
                    if (!res.ok) throw new Error(`Failed to load plan (${res.status})`);
                    const data = await res.json();
                    this.populateRoundsBuilderFromPlan((data && data.plan) || null);
                    this._setRoundsOutput(`Loaded rounds plan "${name}".`, false);
                } catch (e) {
                    this._setRoundsOutput(`Failed to load rounds plan.\n${e}`, true);
                }
            });
        }
        if (els.deletePlan) {
            els.deletePlan.addEventListener("click", async () => {
                const name = String((els.savedPlans && els.savedPlans.value) || (els.planName && els.planName.value) || "").trim();
                if (!name) return;
                if (!window.confirm(`Delete saved rounds plan "${name}"?`)) return;
                try {
                    const res = await fetch(`/api/rounds/plans/${encodeURIComponent(name)}`, { method: "DELETE" });
                    if (!res.ok) throw new Error(`Failed to delete plan (${res.status})`);
                    await this.loadRoundsPlans();
                    this._resetRoundsBuilder();
                    this.renderRoundsBuilder();
                    this._setRoundsOutput(`Deleted rounds plan "${name}".`, false);
                } catch (e) {
                    this._setRoundsOutput(`Failed to delete rounds plan.\n${e}`, true);
                }
            });
        }
        if (els.savePlan) {
            els.savePlan.addEventListener("click", async () => {
                try {
                    const payload = this.collectRoundsPlanPayload();
                    const res = await fetch("/api/rounds/plans", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                    if (!res.ok) {
                        const msg = await res.text();
                        throw new Error(msg || `Failed to save plan (${res.status})`);
                    }
                    const data = await res.json();
                    await this.loadRoundsPlans();
                    this.populateRoundsBuilderFromPlan((data && data.plan) || payload);
                    this.renderRoundsBuilder();
                    this._setRoundsOutput(`Saved rounds plan "${payload.name}".`, false);
                } catch (e) {
                    this._setRoundsOutput(`Failed to save rounds plan.\n${e}`, true);
                }
            });
        }
        if (els.preview) els.preview.addEventListener("click", async () => { await this.runRoundsBuilder(true); });
        if (els.run) els.run.addEventListener("click", async () => { await this.runRoundsBuilder(false); });
        this.roundsState.boundRoundsUi = true;
    }

    populateRoundsBuilderFromPlan(plan) {
        const els = this._getRoundsElements();
        const p = plan || {};
        this.roundsState.activePlanName = String(p.name || "").trim();
        if (els.savedPlans) els.savedPlans.value = this.roundsState.activePlanName;
        if (els.planName) els.planName.value = String(p.name || "").trim();
        if (els.description) els.description.value = String(p.description || "").trim();
        if (els.task && p.task) els.task.value = String(p.task || "").trim();
        if (els.campfire) els.campfire.value = String(p.campfire || this._roundsContextCampfire() || "").trim();
        this.roundsState.rows = Array.isArray(p.rounds) && p.rounds.length ? p.rounds.map((row) => Object.assign(this._emptyRoundRow(), row || {})) : [this._emptyRoundRow()];
        this.renderRoundsBuilder();
    }

    collectRoundsPlanPayload(requireName = true) {
        const els = this._getRoundsElements();
        const name = String((els.planName && els.planName.value) || "").trim();
        const description = String((els.description && els.description.value) || "").trim();
        const task = String((els.task && els.task.value) || "").trim();
        const campfire = String((els.campfire && els.campfire.value) || "").trim();
        const rounds = (this.roundsState.rows || []).map((row, idx, arr) => {
            const current = Object.assign(this._emptyRoundRow(), row || {});
            return {
                label: current.label || "",
                target_address: current.target_address || "",
                service_id: current.service_id || "",
                task_type: current.task_type || "",
                mode: idx === arr.length - 1 ? "final" : (current.mode || "replace"),
                instruction: current.instruction || ""
            };
        }).filter((row) => row.target_address || row.service_id || row.label);
        if (requireName && !name) throw new Error("Plan name is required.");
        if (!rounds.length) throw new Error("Add at least one round.");
        return { name: name || "Ad Hoc Rounds", description, task, campfire, rounds };
    }

    async runRoundsBuilder(preview) {
        try {
            const payload = this.collectRoundsPlanPayload(false);
            if (!payload.task) throw new Error("Task is required.");
            const res = await fetch("/api/rounds/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ rounds: payload.rounds, text: payload.task, preview: !!preview })
            });
            if (!res.ok) {
                const msg = await res.text();
                throw new Error(msg || `Failed to ${preview ? "preview" : "run"} rounds (${res.status})`);
            }
            const data = await res.json();
            this.roundsState.lastResult = data;
            this._setRoundsOutput(preview ? JSON.stringify({ correlation_id: data.correlation_id, rounds: data.rounds }, null, 2) : JSON.stringify(data, null, 2), false);
            if (!preview && this.selectedNode) {
                const response = data && data.response ? data.response : {};
                const textOut = response.text || response.llm_response || JSON.stringify(response || {}, null, 2);
                this.appendChatMessage(this.selectedNode, { role: "system", text: `Rounds run completed.\n\n${textOut}`, ts: Date.now() });
            }
        } catch (e) {
            this._setRoundsOutput(`Failed to ${preview ? "preview" : "run"} rounds.\n${e}`, true);
        }
    }

    renderRoundsBuilder() {
        const els = this._getRoundsElements();
        if (!els.panel) return;
        if (els.savedPlans) {
            const current = String(this.roundsState.activePlanName || "");
            const options = [`<option value="">(select saved plan)</option>`];
            (this.roundsState.plans || []).forEach((plan) => {
                const name = String((plan && plan.name) || "").trim();
                if (!name) return;
                options.push(`<option value="${this._escapeHtml(name)}"${name === current ? " selected" : ""}>${this._escapeHtml(name)}</option>`);
            });
            els.savedPlans.innerHTML = options.join("");
        }
        if (els.catalogNote) {
            const catalog = this.roundsState.catalog || [];
            const localCount = catalog.filter((service) => !service._remote).length;
            const remoteCount = catalog.filter((service) => !!service._remote).length;
            const dock = this.roundsState.catalogMeta || {};
            els.catalogNote.textContent = `Catalog: ${localCount} local service(s), ${remoteCount} remote service(s). Dock running: ${dock.running ? "yes" : "no"}. Known valleys: ${dock.known_valleys || 0}.`;
        }
        if (els.planMeta) {
            const match = (this.roundsState.plans || []).find((plan) => String(plan.name || "") === String(this.roundsState.activePlanName || ""));
            els.planMeta.textContent = match ? `Saved plan updated: ${match.updated_at || "unknown"}` : "Last round is always treated as final when saved or run.";
        }
        this.renderRoundsRows();
    }

    renderRoundsRows() {
        const els = this._getRoundsElements();
        if (!els.rows) return;
        const rows = Array.isArray(this.roundsState.rows) ? this.roundsState.rows : [];
        if (!rows.length) {
            els.rows.innerHTML = `<div class="rounds-builder-empty">No rounds yet. Add a service to start building a chain.</div>`;
            return;
        }
        const options = [`<option value="">(select a service)</option>`];
        (this.roundsState.catalog || []).forEach((service) => {
            const key = this._serviceOptionKey(service);
            if (!key) return;
            options.push(`<option value="${this._escapeHtml(key)}">${this._escapeHtml(this._serviceOptionLabel(service))}</option>`);
        });
        els.rows.innerHTML = "";
        rows.forEach((row, idx) => {
            const wrap = document.createElement("div");
            wrap.className = "rounds-row";
            const isLast = idx === rows.length - 1;
            wrap.innerHTML = `
                <div class="rounds-row-index">${idx + 1}</div>
                <div class="rounds-row-service"><select data-round-field="service">${options.join("")}</select></div>
                <div class="rounds-row-mode">
                    <select data-round-field="mode">
                        <option value="replace">replace</option>
                        <option value="augment">augment</option>
                        <option value="merge">merge</option>
                        <option value="final">final</option>
                    </select>
                </div>
                <div class="rounds-row-instruction"><input data-round-field="instruction" type="text" placeholder="Optional round instruction" value="${this._escapeHtml(row.instruction || "")}" /></div>
                <div class="rounds-row-instruction"><input data-round-field="task_type" type="text" placeholder="Task type" value="${this._escapeHtml(row.task_type || "")}" /></div>
                <div class="rounds-row-remove"><button type="button" data-round-field="remove">Remove</button></div>
            `;
            const serviceSel = wrap.querySelector('select[data-round-field="service"]');
            const modeSel = wrap.querySelector('select[data-round-field="mode"]');
            const instructionInput = wrap.querySelector('input[data-round-field="instruction"]');
            const taskTypeInput = wrap.querySelector('input[data-round-field="task_type"]');
            const removeBtn = wrap.querySelector('button[data-round-field="remove"]');
            if (serviceSel) {
                serviceSel.value = this._serviceOptionKey(row);
                serviceSel.addEventListener("change", (e) => {
                    const selected = (this.roundsState.catalog || []).find((service) => this._serviceOptionKey(service) === e.target.value);
                    this.roundsState.rows[idx] = this._applyServiceToRow(this.roundsState.rows[idx], selected);
                    this.renderRoundsRows();
                });
            }
            if (modeSel) {
                modeSel.value = isLast ? "final" : (row.mode || "replace");
                modeSel.disabled = isLast;
                modeSel.addEventListener("change", (e) => {
                    this.roundsState.rows[idx].mode = e.target.value;
                });
            }
            if (instructionInput) {
                instructionInput.addEventListener("input", (e) => {
                    this.roundsState.rows[idx].instruction = e.target.value || "";
                });
            }
            if (taskTypeInput) {
                taskTypeInput.addEventListener("input", (e) => {
                    this.roundsState.rows[idx].task_type = e.target.value || "";
                });
            }
            if (removeBtn) {
                removeBtn.disabled = rows.length <= 1;
                removeBtn.addEventListener("click", () => {
                    this.roundsState.rows.splice(idx, 1);
                    if (!this.roundsState.rows.length) this.roundsState.rows = [this._emptyRoundRow()];
                    this.renderRoundsRows();
                });
            }
            els.rows.appendChild(wrap);
        });
    }

    _nodeCenter(node) {
        const x = Array.isArray(node.pos) ? node.pos[0] : 0;
        const y = Array.isArray(node.pos) ? node.pos[1] : 0;
        const w = (node.size && node.size[0]) ? node.size[0] : 160;
        const h = (node.size && node.size[1]) ? node.size[1] : 120;
        return [x + w / 2, y + h / 2];
    }

    _ensureCampfireCamperSlots() {
        if (!this.graph || !Array.isArray(this.graph._nodes)) return;
        this.graph._nodes.forEach((n) => {
            if (!n) return;
            if (n.type === "campfire/campfire") {
                const outs = Array.isArray(n.outputs) ? n.outputs : [];
                const need = 6 - outs.length;
                for (let i = 0; i < need; i++) {
                    try {
                        n.addOutput("", "camper");
                    } catch (e) {
                    }
                }
                try {
                    const o = Array.isArray(n.outputs) ? n.outputs : [];
                    for (let i = 1; i < o.length; i++) {
                        if (o[i]) o[i].name = "";
                    }
                } catch (e) {
                }
            }
            if (n.type === "campfire/camper") {
                const ins = Array.isArray(n.inputs) ? n.inputs : [];
                const need = 6 - ins.length;
                for (let i = 0; i < need; i++) {
                    try {
                        n.addInput("", "camper");
                    } catch (e) {
                    }
                }
                try {
                    const it = Array.isArray(n.inputs) ? n.inputs : [];
                    for (let i = 1; i < it.length; i++) {
                        if (it[i]) it[i].name = "";
                    }
                } catch (e) {
                }
            }
        });
    }

    _connectNearestCampfireCamper(campfireNode, camperNode) {
        if (!campfireNode || !camperNode) return false;
        const outSlots = [];
        const inSlots = [];
        const outs = Array.isArray(campfireNode.outputs) ? campfireNode.outputs : [];
        const ins = Array.isArray(camperNode.inputs) ? camperNode.inputs : [];
        for (let i = 0; i < outs.length; i++) {
            const t = outs[i] && outs[i].type;
            if (!t || t === "camper") outSlots.push(i);
        }
        for (let i = 0; i < ins.length; i++) {
            const t = ins[i] && ins[i].type;
            if (!t || t === "camper") inSlots.push(i);
        }
        if (!outSlots.length) outSlots.push(0);
        if (!inSlots.length) inSlots.push(0);
        let best = null;
        for (const o of outSlots) {
            let op = null;
            try {
                op = campfireNode.getConnectionPos ? campfireNode.getConnectionPos(false, o) : null;
            } catch (e) {
                op = null;
            }
            if (!op) op = this._nodeCenter(campfireNode);
            for (const t of inSlots) {
                let tp = null;
                try {
                    tp = camperNode.getConnectionPos ? camperNode.getConnectionPos(true, t) : null;
                } catch (e) {
                    tp = null;
                }
                if (!tp) tp = this._nodeCenter(camperNode);
                const dx = op[0] - tp[0];
                const dy = op[1] - tp[1];
                const d2 = dx * dx + dy * dy;
                if (!best || d2 < best.d2) best = { o, t, d2 };
            }
        }
        if (!best) return false;
        try {
            return !!campfireNode.connect(best.o, camperNode, best.t);
        } catch (e) {
            return false;
        }
    }

    _rerouteCampfireCamperLinksNearest() {
        if (!this.graph || !this.graph.links) return;
        this._ensureCampfireCamperSlots();
        const linkIds = Object.keys(this.graph.links);
        const toReconnect = [];
        for (const id of linkIds) {
            const link = this.graph.links[id];
            if (!link) continue;
            const origin = this.graph.getNodeById ? this.graph.getNodeById(link.origin_id) : null;
            const target = this.graph.getNodeById ? this.graph.getNodeById(link.target_id) : null;
            if (!origin || !target) continue;
            if (origin.type !== "campfire/campfire") continue;
            if (target.type !== "campfire/camper") continue;
            toReconnect.push({ id: link.id || id, origin, target });
        }
        for (const r of toReconnect) {
            try {
                this.graph.removeLink(r.id);
            } catch (e) {
            }
            this._connectNearestCampfireCamper(r.origin, r.target);
        }
        this._refreshStructuralLinkStyles();
    }

    _removeCampfireCamperLinks(originNode, targetNodes) {
        if (!this.graph || !this.graph.links || !originNode || !Array.isArray(targetNodes) || !targetNodes.length) return;
        const targetIds = new Set(targetNodes.filter(Boolean).map((n) => String(n.id)));
        const linkIds = Object.keys(this.graph.links || {});
        linkIds.forEach((id) => {
            const link = this.graph.links[id];
            if (!link) return;
            if (String(link.origin_id) !== String(originNode.id)) return;
            if (!targetIds.has(String(link.target_id))) return;
            try {
                this.graph.removeLink(link.id || id);
            } catch (e) {
            }
        });
    }

    _removeMatchingLinks(matchFn) {
        if (!this.graph || !this.graph.links || typeof matchFn !== "function") return;
        const linkIds = Object.keys(this.graph.links || {});
        linkIds.forEach((id) => {
            const link = this.graph.links[id];
            if (!link) return;
            const origin = this.graph.getNodeById ? this.graph.getNodeById(link.origin_id) : null;
            const target = this.graph.getNodeById ? this.graph.getNodeById(link.target_id) : null;
            if (!matchFn(link, origin, target)) return;
            try {
                this.graph.removeLink(link.id || id);
            } catch (e) {
            }
        });
    }

    _rebuildCampfireTeamLinks(campfireNode, targetNodes) {
        if (!campfireNode || !Array.isArray(targetNodes)) return;
        this._removeMatchingLinks((link, origin, target) => {
            return origin === campfireNode && !!(target && target.type === "campfire/camper");
        });
        targetNodes.filter(Boolean).forEach((targetNode) => {
            try {
                this._connectNearestCampfireCamper(campfireNode, targetNode);
            } catch (e) {
            }
        });
    }

    _rebuildLocalValleyCampfireLinks(localValleyNode, campfireNodes) {
        if (!localValleyNode || !Array.isArray(campfireNodes)) return;
        const targetSet = new Set(campfireNodes.filter(Boolean).map((node) => String(node.id)));
        this._removeMatchingLinks((link, origin, target) => {
            return origin === localValleyNode && !!(target && target.type === "campfire/campfire" && (!target.properties || target.properties.remote !== true));
        });
        campfireNodes.filter(Boolean).forEach((node) => {
            if (!targetSet.has(String(node.id))) return;
            try {
                localValleyNode.connect(1, node, 0);
            } catch (e) {
            }
        });
    }

    _refreshStructuralLinkStyles() {
        if (!this.graph || !this.graph.links) return;
        const links = Object.values(this.graph.links || {});
        links.forEach((link) => {
            if (!link) return;
            const origin = this.graph.getNodeById ? this.graph.getNodeById(link.origin_id) : null;
            const target = this.graph.getNodeById ? this.graph.getNodeById(link.target_id) : null;
            if (!origin || !target) return;
            if (origin.type === "campfire/campfire" && target.type === "campfire/camper") {
                const isAuditor = !!(target.properties && target.properties.type === "auditor");
                link.color = isAuditor ? "#C084FC" : "#FDE047";
                link.type = "camper";
                return;
            }
            if (origin.type === "campfire/valley" && target.type === "campfire/campfire") {
                link.color = origin.properties && origin.properties.remote ? "#60A5FA" : "#86EFAC";
                link.type = "campfire";
            }
        });
        if (this.canvas) this.canvas.setDirty(true, true);
    }

    _scheduleStructuralLinkRefresh(delays = [0, 250, 900]) {
        this.connectorRefreshTimers.forEach((timerId) => {
            try {
                clearTimeout(timerId);
            } catch (e) {
            }
        });
        this.connectorRefreshTimers = [];
        delays.forEach((delay) => {
            const timerId = setTimeout(() => {
                try {
                    this._refreshStructuralLinkStyles();
                } catch (e) {
                }
            }, delay);
            this.connectorRefreshTimers.push(timerId);
        });
    }

    _scheduleBackendGraphSync(delays = [250, 900, 1800]) {
        this.backendGraphRefreshTimers.forEach((timerId) => {
            try {
                clearTimeout(timerId);
            } catch (e) {
            }
        });
        this.backendGraphRefreshTimers = [];
        delays.forEach((delay) => {
            const timerId = setTimeout(() => {
                try {
                    this.syncBackendCampfireNodes();
                } catch (e) {
                }
            }, delay);
            this.backendGraphRefreshTimers.push(timerId);
        });
    }

    _layoutPositionsAround(center, count, baseRadius = 220, ringPad = 140) {
        const [cx, cy] = center;
        const slotsPerRing = 6;
        const out = [];
        for (let i = 0; i < count; i++) {
            const ring = Math.floor(i / slotsPerRing);
            const idxInRing = i % slotsPerRing;
            const angleDeg = 60 * idxInRing - 90; // top first
            const angle = angleDeg * Math.PI / 180;
            const r = baseRadius + ring * ringPad;
            const x = Math.round(cx + r * Math.cos(angle));
            const y = Math.round(cy + r * Math.sin(angle));
            out.push([x, y]);
        }
        return out;
    }

    _layoutHexTerminalsAround(node, count, minRadius = 260, ringPad = 220, rotationDeg = 0) {
        const center = this._nodeCenter(node);
        const [cx, cy] = center;
        const w = (node.size && node.size[0]) ? node.size[0] : 160;
        const h = (node.size && node.size[1]) ? node.size[1] : 120;
        const r0 = Math.max(minRadius, Math.max(w, h) * 0.55);
        const angles = [0, 60, 120, 180, 240, 300].map((a) => (a + rotationDeg) * Math.PI / 180);
        const out = [];
        for (let i = 0; i < count; i++) {
            const ring = Math.floor(i / 6);
            const idx = i % 6;
            const r = r0 + ring * ringPad;
            const a = angles[idx];
            out.push([Math.round(cx + r * Math.cos(a)), Math.round(cy + r * Math.sin(a))]);
        }
        return out;
    }

    _avoidOverlap(pos, existing, minDist = 80) {
        let [x, y] = pos;
        for (let tries = 0; tries < 8; tries++) {
            let ok = true;
            for (const n of existing) {
                if (!n || !Array.isArray(n.pos)) continue;
                const c = this._nodeCenter(n);
                const dx = x - c[0];
                const dy = y - c[1];
                const d2 = dx * dx + dy * dy;
                if (d2 < (minDist * minDist)) {
                    ok = false;
                    break;
                }
            }
            if (ok) return [x, y];
            x += 30 * Math.cos(tries * Math.PI / 3);
            y += 30 * Math.sin(tries * Math.PI / 3);
        }
        return [x, y];
    }

    _placeChildrenRadially(parentNode, childNodes) {
        if (!parentNode || !Array.isArray(childNodes) || childNodes.length === 0) return;
        let maxChild = 180;
        try {
            childNodes.forEach((n) => {
                const w = (n.size && n.size[0]) ? n.size[0] : 160;
                const h = (n.size && n.size[1]) ? n.size[1] : 120;
                maxChild = Math.max(maxChild, w, h);
            });
        } catch (e) {
        }
        const minRadius = Math.round(Math.max(maxChild * 1.35, 340));
        const ringPad = Math.round(Math.max(maxChild * 1.15, 280));
        const positions = this._layoutHexTerminalsAround(parentNode, childNodes.length, minRadius, ringPad, 0);
        const existing = (this.graph && Array.isArray(this.graph._nodes)) ? this.graph._nodes : [];
        childNodes.forEach((n, i) => {
            const p = this._avoidOverlap(positions[i], existing, Math.max(110, Math.floor(maxChild * 0.55)));
            const w = (n.size && n.size[0]) ? n.size[0] : 160;
            const h = (n.size && n.size[1]) ? n.size[1] : 120;
            n.pos = [p[0] - w / 2, p[1] - h / 2];
        });
    }

    _graphChildrenFor(parentNode) {
        const kids = [];
        if (!parentNode || !this.graph) return kids;
        const links = this.graph.links || {};
        for (const k in links) {
            const link = links[k];
            if (!link) continue;
            if (String(link.origin_id) !== String(parentNode.id)) continue;
            const childId = link.target_id;
            const child = this.graph.getNodeById ? this.graph.getNodeById(childId) : null;
            if (!child) continue;
            if (child.type && child.type.indexOf("campfire/camper") === 0) kids.push(child);
        }
        return kids;
    }

    autoArrangeRadial() {
        if (!this.graph) return;
        this._ensureCampfireCamperSlots();
        const nodes = Array.isArray(this.graph._nodes) ? this.graph._nodes : [];
        const valley = nodes.find((n) => n && n.type === "campfire/valley") || null;
        const center = valley ? this._nodeCenter(valley) : [400, 220];
        const campfires = nodes.filter((n) => n && n.type === "campfire/campfire");
        let maxCampfire = 220;
        try {
            campfires.forEach((n) => {
                const w = (n.size && n.size[0]) ? n.size[0] : 160;
                const h = (n.size && n.size[1]) ? n.size[1] : 120;
                maxCampfire = Math.max(maxCampfire, w, h);
            });
        } catch (e) {
        }
        let cfMinRadius = Math.round(Math.max(maxCampfire * 1.7, 520));
        let cfRingPad = Math.round(Math.max(maxCampfire * 1.25, 360));
        if (campfires.length === 1) {
            cfMinRadius += 220;
        }
        const positions = valley ? this._layoutHexTerminalsAround(valley, campfires.length, cfMinRadius, cfRingPad, 0) : this._layoutPositionsAround(center, campfires.length, 420, 240);
        campfires.forEach((cf, i) => {
            const w = (cf.size && cf.size[0]) ? cf.size[0] : 160;
            const h = (cf.size && cf.size[1]) ? cf.size[1] : 120;
            const p = positions[i];
            cf.pos = [p[0] - w / 2, p[1] - h / 2];
        });
        campfires.forEach((cf) => {
            const kids = this._graphChildrenFor(cf);
            this._placeChildrenRadially(cf, kids);
        });
        try {
            this._rerouteCampfireCamperLinksNearest();
        } catch (e) {
        }
        this._scheduleStructuralLinkRefresh();
        if (this.canvas) this.canvas.setDirty(true, true);
    }

    async loadToolsForCampfire(campfireId) {
        try {
            let enabled = false;
            let ws = false;
            let ocr = false;
            const res = await fetch(`/api/campfire/tools?campfire=${encodeURIComponent(campfireId)}`);
            if (res.ok) {
                const data = await res.json();
                const z = (data.tools || {});
                enabled = !!z.enabled;
                ws = !!z.web_search;
                ocr = !!z.image_ocr;
            }
            const enabledEl = document.getElementById("toolZeitgeistEnabled");
            const wsEl = document.getElementById("toolWebSearch");
            const ocrEl = document.getElementById("toolImageOCR");
            if (enabledEl) enabledEl.checked = enabled;
            if (wsEl) wsEl.checked = ws;
            if (ocrEl) ocrEl.checked = ocr;
            this.bindToolsPanelEvents(campfireId);
            await this.loadLlmModelForCampfire(campfireId);
        } catch (e) {
        }
    }

    async loadLlmModelForCampfire(campfireId) {
        const sel = document.getElementById("toolModelSelect");
        if (!sel) return;
        let currentModel = "";
        let provider = "ollama";
        try {
            const r = await fetch(`/api/campfire/llm?campfire=${encodeURIComponent(campfireId)}`);
            if (r.ok) {
                const d = await r.json();
                provider = (d && d.provider) || "ollama";
                currentModel = (d && d.model) || "";
            }
        } catch (e) {
        }
        let models = [];
        try {
            const r = await fetch(`/api/ollama/models`);
            if (r.ok) {
                const d = await r.json();
                models = (d && d.models) || [];
            }
        } catch (e) {
        }
        sel.textContent = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = "(default)";
        sel.appendChild(opt0);
        (models || []).forEach((m) => {
            if (typeof m !== "string") return;
            const mm = m.trim();
            if (!mm) return;
            const o = document.createElement("option");
            o.value = mm;
            o.textContent = mm;
            sel.appendChild(o);
        });
        sel.disabled = String(provider).toLowerCase() !== "ollama";
        if (currentModel) {
            sel.value = currentModel;
        } else {
            sel.value = "";
        }
        sel.onchange = async () => {
            const v = (sel.value || "").trim();
            if (!v) return;
            try {
                await fetch("/api/campfire/llm", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ campfire: campfireId, provider: "ollama", model: v })
                });
            } catch (e) {
            }
        };
    }

    bindToolsPanelEvents(campfireId) {
        const enabledEl = document.getElementById("toolZeitgeistEnabled");
        const wsEl = document.getElementById("toolWebSearch");
        const ocrEl = document.getElementById("toolImageOCR");
        const sendUpdate = async () => {
            const payload = {
                campfire: campfireId,
                zeitgeist: {
                    enabled: !!enabledEl.checked,
                    web_search: !!wsEl.checked,
                    image_ocr: !!ocrEl.checked
                }
            };
            try {
                await fetch("/api/campfire/tools", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
            } catch (e) {
            }
        };
        enabledEl.onchange = sendUpdate;
        wsEl.onchange = sendUpdate;
        ocrEl.onchange = sendUpdate;
    }

    hideChatPanel() {
        if (!this.chatUI) {
            return;
        }
        this.chatUI.panel.classList.add("hidden");
        this.chatUI.actionBar.classList.add("hidden");
        this.chatUI.logsPanel.classList.add("hidden");
        if (this.chatUI.inputRow) this.chatUI.inputRow.style.display = "";
        this.toggleToolsPanel(false);
        this.toggleRoundsPanel(false);
    }

    getChatKeyForNode(node) {
        return String(node.id);
    }

    getNodeTarget(node) {
        if (!node) return null;
        if (node.properties && node.properties.target) return node.properties.target;
        if (node.properties && node.properties.name) return node.properties.name;
        return node.title || null;
    }

    renderChatHistory(node) {
        if (!this.chatUI) {
            return;
        }
        const key = this.getChatKeyForNode(node);
        const history = this.chatByNodeId.get(key) || [];
        const container = this.chatUI.messages;
        container.textContent = "";
        history.forEach((m) => {
            const el = document.createElement("div");
            el.className = `chat-message ${m.role === "user" ? "user" : "system"}`;
            el.innerHTML = this._markdownToHtml(m.text);
            container.appendChild(el);
            const options = m && Array.isArray(m.options) ? m.options : null;
            if (options && options.length) {
                const row = document.createElement("div");
                row.className = "chat-options";
                const action = m.options_action || "remove";
                options.forEach((opt) => {
                    const name = (typeof opt === "string" ? opt : (opt && opt.name ? String(opt.name) : "")).trim();
                    if (!name) return;
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "chat-option-btn";
                    btn.textContent = name;
                    btn.addEventListener("click", () => {
                        if (action === "rename") {
                            if (this.chatUI && this.chatUI.input) {
                                this.chatUI.input.value = `rename camper \"${name}\" to `;
                                this.chatUI.input.focus();
                            }
                            return;
                        }
                        if (action === "delete_campfire_confirm") {
                            const cmd = `confirm delete campfire "${name}"`;
                            this.appendChatMessage(node, { role: "user", text: cmd, ts: Date.now() });
                            this.sendChatToBackend(node, cmd);
                            return;
                        }
                        const cmd = `remove camper ${name}`;
                        this.appendChatMessage(node, { role: "user", text: cmd, ts: Date.now() });
                        this.sendChatToBackend(node, cmd);
                    });
                    row.appendChild(btn);
                });
                container.appendChild(row);
            }
        });
        container.scrollTop = container.scrollHeight;
    }

    async toggleLogsForSelectedNode() {
        if (!this.chatUI || !this.selectedNode) {
            return;
        }
        const hidden = this.chatUI.logsPanel.classList.contains("hidden");
        if (!hidden) {
            this.chatUI.logsPanel.classList.add("hidden");
            return;
        }
        await this.loadLogsForNode(this.selectedNode);
        this.chatUI.logsPanel.classList.remove("hidden");
    }

    async loadLogsForNode(node) {
        if (!this.chatUI) {
            return;
        }
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        this.chatUI.logsPanel.textContent = "";
        try {
            const res = await fetch(`/api/logs/${encodeURIComponent(target)}?limit=200`);
            if (!res.ok) {
                const err = document.createElement("div");
                err.className = "log-entry assistant";
                err.textContent = `Failed to load logs (${res.status}).`;
                this.chatUI.logsPanel.appendChild(err);
                return;
            }
            const data = await res.json();
            const entries = (data && data.entries) || [];
            entries.forEach((e) => {
                const role = (e.role || "assistant").toLowerCase();
                const text = e.text || "";
                const ts = e.ts || "";
                const wrap = document.createElement("div");
                wrap.className = `log-entry ${role}`;
                const meta = document.createElement("div");
                meta.className = "meta";
                meta.textContent = `${ts} • ${role}`;
                const body = document.createElement("div");
                body.textContent = text;
                wrap.appendChild(meta);
                wrap.appendChild(body);
                wrap.addEventListener("click", () => {
                    this.chatUI.input.value = text;
                    this.chatUI.input.focus();
                });
                this.chatUI.logsPanel.appendChild(wrap);
            });
            this.chatUI.logsPanel.scrollTop = this.chatUI.logsPanel.scrollHeight;
        } catch (e) {
            const err = document.createElement("div");
            err.className = "log-entry assistant";
            err.textContent = "Failed to load logs (backend unreachable).";
            this.chatUI.logsPanel.appendChild(err);
        }
    }

    async refreshChatHistoryFromBackend(node) {
        if (!this.chatUI || !node) {
            return;
        }
        const target = this.getNodeTarget(node);
        if (!target || (typeof target === "string" && target.startsWith("valley:"))) {
            return;
        }
        try {
            const res = await fetch(`/api/logs/${encodeURIComponent(target)}?limit=200`);
            if (!res.ok) {
                return;
            }
            const data = await res.json();
            const entries = Array.isArray(data && data.entries) ? data.entries : [];
            const history = entries.map((e) => ({
                role: (e && e.role) || "system",
                text: (e && e.text) || "",
                ts: (e && e.ts) || Date.now()
            }));
            this.chatByNodeId.set(this.getChatKeyForNode(node), history);
            if (this.selectedNode === node) {
                this.renderChatHistory(node);
            }
        } catch (e) {
        }
    }

    async sendUiDebugLog(event, data) {
        try {
            await fetch("/api/debug/ui-log", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event, data })
            });
        } catch (e) {
        }
    }

    appendChatMessage(node, message) {
        const key = this.getChatKeyForNode(node);
        const history = this.chatByNodeId.get(key) || [];
        history.push(message);
        this.chatByNodeId.set(key, history);
        this.renderChatHistory(node);
        if (message.role !== "user") {
            this.speakIfEnabled(node, message.text);
        }
    }

    async freezeBeliefsForSelectedNode() {
        if (!this.chatUI || !this.selectedNode) {
            return;
        }
        const node = this.selectedNode;
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        const key = this.getChatKeyForNode(node);
        const history = this.chatByNodeId.get(key) || [];
        this.chatUI.freeze.classList.add("busy");
        try {
            const res = await fetch("/api/beliefs/freeze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    campfire: target,
                    messages: history
                })
            });
            if (!res.ok) {
                this.appendChatMessage(node, { role: "system", text: `Freeze failed: ${res.status}`, ts: Date.now() });
                return;
            }
            const data = await res.json();
            const count = data && typeof data.count === "number" ? data.count : 0;
            this.appendChatMessage(node, { role: "system", text: `Beliefs frozen (${count}).`, ts: Date.now() });
        } catch (e) {
            this.appendChatMessage(node, { role: "system", text: "Freeze failed: backend unreachable", ts: Date.now() });
        } finally {
            this.chatUI.freeze.classList.remove("busy");
        }
    }

    async clearBeliefsForSelectedNode() {
        if (!this.chatUI || !this.selectedNode) {
            return;
        }
        const node = this.selectedNode;
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        const ok = window.confirm(`Clear saved beliefs for "${target}"? This removes persisted memory for this campfire.`);
        if (!ok) {
            return;
        }
        this.chatUI.clearBeliefsBtn.classList.add("busy");
        try {
            const res = await fetch("/api/beliefs/clear", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ campfire: target })
            });
            if (!res.ok) {
                this.appendChatMessage(node, { role: "system", text: `Clear beliefs failed: ${res.status}`, ts: Date.now() });
                return;
            }
            this.appendChatMessage(node, { role: "system", text: `Beliefs cleared for ${target}.`, ts: Date.now() });
        } catch (e) {
            this.appendChatMessage(node, { role: "system", text: "Clear beliefs failed: backend unreachable", ts: Date.now() });
        } finally {
            this.chatUI.clearBeliefsBtn.classList.remove("busy");
        }
    }

    async exportSelectedNode() {
        if (!this.chatUI || !this.selectedNode) {
            return;
        }
        const node = this.selectedNode;
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        try {
            const res = await fetch("/api/campfire/export", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ campfire: target })
            });
            if (!res.ok) {
                this.appendChatMessage(node, { role: "system", text: `Export failed: ${res.status}`, ts: Date.now() });
                return;
            }
            const data = await res.json();
            const filename = (data && data.filename) || `campfire_export_${target}.yaml`;
            const text = (data && data.yaml) || "";
            const blob = new Blob([text], { type: "text/yaml;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            this.appendChatMessage(node, { role: "system", text: `Exported: ${filename}`, ts: Date.now() });
        } catch (e) {
            this.appendChatMessage(node, { role: "system", text: "Export failed: backend unreachable", ts: Date.now() });
        }
    }

    createCampfireWithAuditorAt(position) {
        const base = Date.now().toString(36);
        const campfireId = `campfire_${base}`;
        const campfireName = `Campfire ${base}`;
        const auditorId = `auditor_${base}`;
        const campfire = this.addCampfire(campfireId, position);
        campfire.properties.name = campfireName;
        campfire.properties.type = "standard";
        campfire.title = campfire.properties.name;

        const auditorPos = [position[0] + 280, position[1]];
        const auditor = this.addCamper(auditorId, auditorPos);
        auditor.properties.name = "Auditor";
        auditor.properties.type = "auditor";
        auditor.properties.target = campfireName;
        auditor.properties.auditor_mode = true;
        auditor.properties.current_task = "ready";
        auditor.properties.role_prompt = "You are the Auditor and Orchestrator for this Campfire. You do not solve the user's domain problem. You identify which campers are needed, create them, assign them ordered tasks, and coordinate their outputs. Keep replies short and action-focused.";
        auditor.title = "Auditor";

        try {
            this._ensureCampfireCamperSlots();
            this._connectNearestCampfireCamper(campfire, auditor);
        } catch (e) {
        }

        if (this.canvas && this.canvas.selectNodes) {
            this.canvas.selectNodes([auditor]);
        }

        this.appendChatMessage(auditor, { role: "system", text: "Auditor created and linked. Select a node to chat.", ts: Date.now() });
        this.ensureBackendCampfire(campfireName, "You are a helpful campfire agent. Keep responses concise and actionable.", "gemma3:4b");
    }

    async ensureBackendCampfire(name, systemPrompt, model) {
        try {
            const res = await fetch("/api/team/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name,
                    persona: {
                        name,
                        provider: "ollama",
                        model: model || "gemma3:4b",
                        system_prompt: systemPrompt || ""
                    }
                })
            });
            if (!res.ok) {
                return;
            }
            await res.json();
        } catch (e) {
        }
    }

    async fetchBackendCampfires(force = false) {
        const now = Date.now();
        if (!force && now - this.backendCampfiresCache.ts < 2000) {
            return this.backendCampfiresCache.items;
        }
        try {
            const res = await fetch("/api/campfires");
            if (!res.ok) {
                return this.backendCampfiresCache.items;
            }
            const data = await res.json();
            const items = Array.isArray(data) ? data : [];
            this.backendCampfiresCache = { ts: now, items };
            return items;
        } catch (e) {
            return this.backendCampfiresCache.items;
        }
    }

    async updateChatTitleFromBackend(node) {
        if (!this.chatUI || !node) {
            return;
        }
        const displayName = (node.properties && (node.properties.name || node.properties.id)) || node.title || "Node";
        if (node.properties && node.properties.type === "auditor") {
            this.chatUI.title.textContent = displayName;
            return;
        }
        const target = this.getNodeTarget(node);
        if (!target) {
            this.chatUI.title.textContent = displayName;
            return;
        }
        if (typeof target === "string" && target.startsWith("valley:")) {
            this.chatUI.title.textContent = `${displayName} • remote`;
            return;
        }
        const campfires = await this.fetchBackendCampfires(false);
        const found = campfires.find((c) => c && c.id === target);
        if (!found) {
            this.chatUI.title.textContent = `${displayName} • not provisioned`;
            return;
        }
        const type = found.type || "Campfire";
        const running = found.running ? "running" : "stopped";
        this.chatUI.title.textContent = `${displayName} • ${type} • ${running}`;
    }

    async ensureBackendPresentForNode(node) {
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        if (typeof target === "string" && target.startsWith("valley:")) {
            return;
        }
        if (node && node.properties && node.properties.type === "auditor") {
            return;
        }
        const campfires = await this.fetchBackendCampfires(true);
        const exists = campfires.some((c) => c && c.id === target);
        if (exists) {
            return;
        }
        const systemPrompt = (node.properties && node.properties.role_prompt) || `You are ${target}.`;
        await this.ensureBackendCampfire(target, systemPrompt, "gemma3:4b");
        await this.fetchBackendCampfires(true);
    }

    async syncRemoteValleyNodes(anchorX, anchorY) {
        if (!this.graph) {
            return;
        }
        try {
            const res = await fetch("/api/dock/valleys");
            if (!res.ok) {
                return;
            }
            const data = await res.json();
            const valleys = (data && data.valleys) || [];
            if (!Array.isArray(valleys)) {
                return;
            }

            const existingNodes = Array.isArray(this.graph._nodes) ? [...this.graph._nodes] : [];
            existingNodes.forEach((n) => {
                if (n && n.properties && n.properties.remote === true) {
                    try {
                        this.graph.remove(n);
                    } catch (e) {
                    }
                }
            });

            const startX = (typeof anchorX === "number" ? anchorX : 900);
            const startY = (typeof anchorY === "number" ? anchorY : 100);
            const valleySpacingY = 260;
            const campfireOffsetX = 320;
            const campfireSpacingY = 180;

            valleys.forEach((v, idx) => {
                const valley = this._deriveRemoteValleySummary(v);
                const name = valley.displayName || null;
                if (!name) return;
                const valleyNode = LiteGraph.createNode("campfire/valley");
                valleyNode.pos = [startX, startY + (idx * valleySpacingY)];
                valleyNode.properties = valleyNode.properties || {};
                valleyNode.properties.remote = true;
                valleyNode.properties.local = false;
                valleyNode.properties.name = name;
                valleyNode.properties.display_name = name;
                valleyNode.properties.origin_label = "REMOTE";
                valleyNode.properties.route_name = valley.routeAddress;
                valleyNode.properties.route_key = valley.routeKey;
                valleyNode.properties.identifier = valley.identifier;
                valleyNode.properties.total_campfires = valley.campfireCount;
                valleyNode.properties.status = "remote";
                valleyNode.title = `Remote: ${name}`;
                this.graph.add(valleyNode);

                const exposed = Array.isArray(v.exposed_campfires) ? v.exposed_campfires : [];
                const exposedServices = Array.isArray(v.exposed_services) ? v.exposed_services : [];
                exposed.forEach((cf, j) => {
                    const cfName = cf ? String(cf) : null;
                    if (!cfName) return;
                    const matchingService = exposedServices.find((service) => String((service && service.name) || "").trim() === cfName) || {};
                    const campfireNode = LiteGraph.createNode("campfire/campfire");
                    campfireNode.pos = [valleyNode.pos[0] + campfireOffsetX, valleyNode.pos[1] + (j * campfireSpacingY)];
                    campfireNode.properties = campfireNode.properties || {};
                    campfireNode.properties.remote = true;
                    campfireNode.properties.name = cfName;
                    campfireNode.properties.target = `${valley.routeAddress}/${cfName}`;
                    campfireNode.properties.route_name = `${valley.routeAddress}/${cfName}`;
                    campfireNode.properties.remote_valley_name = valley.displayName;
                    campfireNode.properties.remote_valley_id = valley.identifier;
                    campfireNode.properties.service_id = String((matchingService && matchingService.service_id) || "").trim();
                    campfireNode.properties.service_summary = String((matchingService && matchingService.summary) || "").trim();
                    campfireNode.properties.backend_type = String((matchingService && matchingService.kind) || "campfire").trim();
                    campfireNode.title = cfName;
                    this.graph.add(campfireNode);
                    try {
                        valleyNode.connect(1, campfireNode, 0);
                    } catch (e) {
                    }
                });

                if (this.nodes.valley) {
                    try {
                        this.nodes.valley.connect(1, valleyNode, 0);
                    } catch (e) {
                    }
                }
            });
        } catch (e) {
        }
    }

    async syncBackendCampfireNodes() {
        if (!this.graph) {
            return;
        }
        if (this.backendSyncPromise) {
            return await this.backendSyncPromise;
        }
        this.backendSyncPromise = (async () => {
        let campfires = await this.fetchBackendCampfires(true);
        let localValley = null;
        try {
            localValley = await this._loadLocalValleySummary();
        } catch (e) {
            localValley = null;
        }
        const campfireRecords = Array.isArray(campfires) ? campfires : [];
        const byId = new Map();
        campfireRecords.forEach((c) => {
            if (c && c.id) byId.set(String(c.id), c);
        });
        const existingNodes = Array.isArray(this.graph._nodes) ? [...this.graph._nodes] : [];
        const validIds = new Set(
            campfireRecords
                .map((c) => (c && c.id ? String(c.id) : ""))
                .filter(Boolean)
        );
        existingNodes.forEach((n) => {
            if (!n || !n.type) return;
            if (n.properties && n.properties.remote === true) return;
            const props = n.properties || {};
            const nodeType = String(n.type || "");
            const target = String(props.target || props.id || props.name || n.title || "").trim();
            const isBackendMarked = props.backend === true;
            const isAuditorNode = props.type === "auditor" || String(n.title || "").trim().toLowerCase() === "auditor";
            const isBackendLike = nodeType === "campfire/campfire" || nodeType === "campfire/camper";
            const shouldRemoveStale =
                isBackendLike &&
                target &&
                !validIds.has(target) &&
                (isBackendMarked || isAuditorNode || props.target || props.id);
            if (isBackendMarked || shouldRemoveStale) {
                try {
                    this.graph.remove(n);
                } catch (e) {
                }
            }
        });
        this.nodes.backendCampers = [];

        const parents = new Map();
        campfireRecords.forEach((c) => {
            const id = c && c.id ? String(c.id) : null;
            const parent = c && c.parent ? String(c.parent) : null;
            if (id && parent) parents.set(id, parent);
        });
        if (this.nodes.valley && this.nodes.valley.properties) {
            if (localValley) {
                this.nodes.valley.properties.remote = false;
                this.nodes.valley.properties.local = true;
                this.nodes.valley.properties.name = localValley.displayName;
                this.nodes.valley.properties.display_name = localValley.displayName;
                this.nodes.valley.properties.origin_label = "LOCAL";
                this.nodes.valley.properties.route_name = localValley.routeAddress;
                this.nodes.valley.properties.route_key = localValley.routeKey;
                this.nodes.valley.properties.identifier = localValley.identifier;
                this.nodes.valley.title = `Local: ${localValley.displayName}`;
            }
            this.nodes.valley.properties.total_campfires = campfireRecords.length;
        }

        const base = this.nodes.regularCampfire && Array.isArray(this.nodes.regularCampfire.pos)
            ? this.nodes.regularCampfire.pos
            : (this.nodes.valley && Array.isArray(this.nodes.valley.pos) ? this.nodes.valley.pos : [400, 200]);
        const startX = base[0] + 340;
        const startY = base[1] - 140;
        const campfireSpacingY = 220;
        const auditorOffsetX = 280;
        const auditorOffsetY = 90;
        const childOffsetX = 280;
        const childSpacingY = 140;

        const allIds = [...campfireRecords]
            .map((c) => (c && c.id ? String(c.id) : null))
            .filter(Boolean);

        const primaryCampfires = [...campfireRecords]
            .filter((c) => c && c.id)
            .map((c) => ({ id: String(c.id), type: c.type, running: c.running }))
            .filter((c) => c.id.toLowerCase() !== "auditor" && !c.id.toLowerCase().endsWith(" auditor"))
            .filter((c) => !parents.has(c.id))
            .sort((a, b) => a.id.localeCompare(b.id));

        const localCampfireNodes = [];
        const campfireNodeById = new Map();
        const auditorNodeByParent = new Map();
        const camperNodesByParent = new Map();
        primaryCampfires.forEach((c, idx) => {
            let campfireNode = null;
            try {
                campfireNode = existingNodes.find((n) => {
                    if (!n || n.type !== "campfire/campfire") return false;
                    if (n.properties && n.properties.backend === true) return false;
                    if (n.properties && n.properties.remote === true) return false;
                    const t = (n.properties && (n.properties.target || n.properties.name)) || n.title || "";
                    return String(t) === String(c.id);
                }) || null;
            } catch (e) {
                campfireNode = null;
            }
            if (!campfireNode && primaryCampfires.length === 1) {
                try {
                    campfireNode = existingNodes.find((n) => {
                        if (!n || n.type !== "campfire/campfire") return false;
                        if (n.properties && n.properties.backend === true) return false;
                        if (n.properties && n.properties.remote === true) return false;
                        return true;
                    }) || null;
                } catch (e) {
                    campfireNode = null;
                }
            }
            if (!campfireNode) {
                campfireNode = LiteGraph.createNode("campfire/campfire");
                campfireNode.pos = [startX, startY + (idx * campfireSpacingY)];
                campfireNode.properties = campfireNode.properties || {};
                campfireNode.properties.backend = true;
                campfireNode.properties.name = c.id;
                campfireNode.properties.target = c.id;
                campfireNode.properties.id = c.id;
                campfireNode.properties.backend_type = c.type || "Campfire";
                campfireNode.title = c.id;
                this.graph.add(campfireNode);
                this.nodes.backendCampers.push(campfireNode);
            } else {
                campfireNode.properties = campfireNode.properties || {};
                campfireNode.properties.backend = true;
                campfireNode.properties.name = c.id;
                campfireNode.properties.target = c.id;
                campfireNode.properties.id = c.id;
                campfireNode.properties.backend_type = c.type || "Campfire";
                campfireNode.title = c.id;
            }
            this.nodes.backendCampers.push(campfireNode);
            localCampfireNodes.push(campfireNode);
            campfireNodeById.set(c.id, campfireNode);

            const auditor = LiteGraph.createNode("campfire/camper");
            // Position auditor at first radial slot (convert center -> top-left)
            try {
                const center = this._nodeCenter(campfireNode);
                const p = this._layoutPositionsAround(center, 1, 200, 140)[0];
                const a = this._avoidOverlap(p, existingNodes);
                const aw = (auditor.size && auditor.size[0]) ? auditor.size[0] : 160;
                const ah = (auditor.size && auditor.size[1]) ? auditor.size[1] : 120;
                auditor.pos = [a[0] - aw / 2, a[1] - ah / 2];
            } catch (e) {
                auditor.pos = [campfireNode.pos[0] + auditorOffsetX, campfireNode.pos[1] + auditorOffsetY];
            }
            auditor.properties = auditor.properties || {};
            auditor.properties.backend = true;
            auditor.properties.name = "Auditor";
            auditor.properties.target = c.id;
            auditor.properties.type = "auditor";
            auditor.properties.auditor_mode = true;
            auditor.properties.role_prompt = "You are the Auditor and Orchestrator for this Campfire. You do not solve the user's domain problem. You identify which campers are needed, create them, assign them ordered tasks, and coordinate their outputs. Ask clarifying questions when needed.";
            auditor.title = "Auditor";
            this.graph.add(auditor);
            auditorNodeByParent.set(c.id, auditor);
        });

        const childCampfires = (Array.isArray(campfires) ? campfires : [])
            .filter((c) => c && c.id && c.parent)
            .map((c) => ({ id: String(c.id), parent: String(c.parent), type: c.type, running: c.running }))
            .filter((c) => c.id.toLowerCase() !== "auditor" && !c.id.toLowerCase().endsWith(" auditor"))
            .sort((a, b) => a.id.localeCompare(b.id));
        const childrenByParent = new Map();
        childCampfires.forEach((c) => {
            if (!childrenByParent.has(c.parent)) childrenByParent.set(c.parent, []);
            childrenByParent.get(c.parent).push(c);
        });
        childrenByParent.forEach((children, parentId) => {
            const parentNode = campfireNodeById.get(parentId);
            if (!parentNode) return;
            const created = [];
            children.forEach((child, idx) => {
                const camperNode = LiteGraph.createNode("campfire/camper");
                camperNode.pos = [parentNode.pos[0] + childOffsetX, parentNode.pos[1] + (idx * childSpacingY) + 10];
                camperNode.properties = camperNode.properties || {};
                camperNode.properties.backend = true;
                camperNode.properties.name = child.id;
                camperNode.properties.target = child.id;
                camperNode.properties.id = child.id;
                camperNode.properties.backend_type = child.type || "Campfire";
                camperNode.title = child.id;
                this.graph.add(camperNode);
                created.push(camperNode);
            });
            camperNodesByParent.set(parentId, created);
            try {
                this._placeChildrenRadially(parentNode, created);
            } catch (e) {
            }
        });

        this._ensureCampfireCamperSlots();
        campfireNodeById.forEach((campfireNode, campfireId) => {
            const targets = [];
            const auditorNode = auditorNodeByParent.get(campfireId);
            const camperNodes = camperNodesByParent.get(campfireId) || [];
            if (auditorNode) targets.push(auditorNode);
            targets.push(...camperNodes.filter(Boolean));
            this._rebuildCampfireTeamLinks(campfireNode, targets);
        });

        if (this.nodes.valley) {
            this._rebuildLocalValleyCampfireLinks(this.nodes.valley, localCampfireNodes);
        }
        this._refreshStructuralLinkStyles();
        await this.syncRemoteValleyNodes(startX + 720, startY);
        this._refreshStructuralLinkStyles();
        this._scheduleStructuralLinkRefresh();
        if (this.canvas) {
            this.canvas.setDirty(true, true);
        }
        })();
        try {
            return await this.backendSyncPromise;
        } finally {
            this.backendSyncPromise = null;
        }
    }

    async sendChatToBackend(node, text) {
        const target = this.getNodeTarget(node);
        if (!target) {
            return;
        }
        const isRemote = (typeof target === "string") && target.startsWith("valley:");
        const isAuditor = !!(node && node.properties && node.properties.type === "auditor");
        if (isAuditor) {
            this.sendUiDebugLog("auditor_send_start", {
                node_id: node && node.id,
                node_title: node && node.title,
                node_name: node && node.properties && node.properties.name,
                node_target: target,
                node_type: node && node.properties && node.properties.type,
                auditor_mode: isAuditor,
                text
            });
        }
        const sendOnce = async () => {
            return await fetch("/api/voice/ingest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    campfire: target,
                    text,
                    role_prompt: isAuditor ? (node.properties.role_prompt || "") : "",
                    auditor_mode: isAuditor ? true : false
                })
            });
        };
        try {
            await this.ensureBackendPresentForNode(node);
            let res = await sendOnce();
            if (!res.ok && !isRemote && !isAuditor) {
                const bodyText = await res.text();
                const looksMissing = res.status === 500 && /campfire.+not found/i.test(bodyText);
                if (looksMissing) {
                    const systemPrompt = (node.properties && node.properties.role_prompt) || `You are ${target}.`;
                    await this.ensureBackendCampfire(target, systemPrompt, "gemma3:4b");
                    res = await sendOnce();
                }
            }
            if (!res.ok) {
                this.appendChatMessage(node, { role: "system", text: `Error: ${res.status}`, ts: Date.now() });
                return;
            }
            const data = await res.json();
            const response = data && data.response;
            let msg = { role: "system", text: "(no response)", ts: Date.now() };
            let renderBranch = "none";
            if (response && typeof response.text === "string" && typeof response.created_campfire === "string") {
                msg.text = response.text;
                renderBranch = "created_campfire_text";
            } else if (response && typeof response.llm_response === "string") {
                msg.text = response.llm_response;
                renderBranch = "llm_response";
            } else if (response && typeof response.text === "string") {
                msg.text = response.text;
                renderBranch = "text";
            } else if (response && typeof response === "string") {
                msg.text = response;
                renderBranch = "string_response";
            } else if (response != null) {
                msg.text = JSON.stringify(response);
                renderBranch = "json_stringify";
            }
            if (isAuditor) {
                this.sendUiDebugLog("auditor_send_result", {
                    node_id: node && node.id,
                    node_target: target,
                    response_keys: response && typeof response === "object" ? Object.keys(response) : [],
                    has_text: !!(response && typeof response.text === "string"),
                    has_llm_response: !!(response && typeof response.llm_response === "string"),
                    created_campfire: response && response.created_campfire,
                    render_branch: renderBranch,
                    rendered_preview: String(msg.text || "").slice(0, 300)
                });
            }
            if (response && Array.isArray(response.options)) {
                msg.options = response.options;
            }
            if (response && typeof response.options_action === "string") {
                msg.options_action = response.options_action;
            }
            if (response && typeof response.rename_from === "string") {
                msg.rename_from = response.rename_from;
            }
            this.appendChatMessage(node, msg);
            this.updateChatTitleFromBackend(node);
            const created = response && response.created;
            const removed = response && response.removed;
            const createdCampfire = response && response.created_campfire;
            if ((Array.isArray(created) && created.length > 0) || (Array.isArray(removed) && removed.length > 0) || (typeof createdCampfire === "string" && createdCampfire.length > 0)) {
                setTimeout(() => {
                    try {
                        this.syncBackendCampfireNodes();
                    } catch (e) {
                    }
                }, 250);
                this._scheduleBackendGraphSync([500, 1200, 2200]);
                this._scheduleStructuralLinkRefresh([200, 600, 1200]);
            }
        } catch (e) {
            this.appendChatMessage(node, { role: "system", text: "Error: failed to reach backend", ts: Date.now() });
        }
    }

    async toggleVoiceInput() {
        if (!this.chatUI) {
            return;
        }
        if (this.isListening) {
            try {
                this.speechRecognition && this.speechRecognition.stop && this.speechRecognition.stop();
            } catch (e) {
            }
            return;
        }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            if (this.selectedNode) {
                this.appendChatMessage(this.selectedNode, { role: "system", text: "Voice input not supported in this browser.", ts: Date.now() });
            }
            return;
        }
        if (!this.speechRecognition) {
            const rec = new SpeechRecognition();
            rec.continuous = false;
            rec.interimResults = false;
            rec.lang = "en-US";
            rec.onstart = () => {
                this.isListening = true;
                this.chatUI.mic.classList.add("listening");
            };
            rec.onend = () => {
                this.isListening = false;
                this.chatUI.mic.classList.remove("listening");
            };
            rec.onerror = () => {
                this.isListening = false;
                this.chatUI.mic.classList.remove("listening");
            };
            rec.onresult = (event) => {
                try {
                    const transcript = event.results && event.results[0] && event.results[0][0] ? event.results[0][0].transcript : "";
                    const text = (transcript || "").trim();
                    if (!text || !this.selectedNode) {
                        return;
                    }
                    this.chatUI.input.value = text;
                    this.chatUI.send.click();
                } catch (e) {
                }
            };
            this.speechRecognition = rec;
        }
        try {
            this.speechRecognition.start();
        } catch (e) {
        }
    }

    async startVoiceForNode(node) {
        this.setSelectedNode(node || null);
        if (!node) {
            return;
        }
        await this.toggleVoiceInput();
    }

    speakIfEnabled(node, text) {
        if (!node || !text) {
            return;
        }
        if (node.properties && node.properties.tts_enabled === false) {
            return;
        }
        const speaks = node.type === "campfire/campfire" || node.type === "campfire/camper" || (node.properties && node.properties.type === "auditor");
        if (!speaks) {
            return;
        }
        if (!window.speechSynthesis) {
            return;
        }
        try {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(utterance);
        } catch (e) {
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
