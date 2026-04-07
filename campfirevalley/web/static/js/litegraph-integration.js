// LiteGraph Integration for CampfireValley
// This file manages the LiteGraph canvas and integrates it with the existing CampfireValley functionality

class CampfireValleyLiteGraph {
    constructor() {
        this.graph = null;
        this.canvas = null;
        this.nodes = {};
        this.websocket = null;
        this.isInitialized = false;
        this.selectedNode = null;
        this.chatByNodeId = new Map();
        this.chatUI = null;
        this.speechRecognition = null;
        this.isListening = false;
        this.backendCampfiresCache = { ts: 0, items: [] };
        this.backendSyncPromise = null;
        
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

            this.setupChatUI();
            
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
        this.graph.clear();
        this.nodes = {};

        const rootValleyNode = LiteGraph.createNode("campfire/valley");
        rootValleyNode.pos = [80, 220];
        rootValleyNode.properties = rootValleyNode.properties || {};
        rootValleyNode.properties.name = "Main Valley";
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
                    this.nodes.regularCampfire.connect(0, n, 0);
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
        const logsBtn = document.getElementById("chatLogs");
        const exportBtn = document.getElementById("chatExport");
        const speakBtn = document.getElementById("chatSpeak");
        const toolsBtn = document.getElementById("chatTools");
        const messages = document.getElementById("chatMessages");
        const logsPanel = document.getElementById("chatLogsPanel");
        const input = document.getElementById("chatInput");
        const send = document.getElementById("chatSend");
        const mic = document.getElementById("chatMic");
        const close = document.getElementById("chatClose");
        if (!panel || !actionBar || !title || !freeze || !logsBtn || !exportBtn || !speakBtn || !toolsBtn || !messages || !logsPanel || !input || !send || !mic || !close) {
            return;
        }
        const toolsPanel = document.createElement("div");
        toolsPanel.id = "chatToolsPanel";
        toolsPanel.className = "chat-tools-panel";
        toolsPanel.innerHTML = `
            <div class="chat-tools-row"><label>Enable Zeitgeist</label><input id="toolZeitgeistEnabled" type="checkbox"/></div>
            <div class="chat-tools-row"><label>Web Search</label><input id="toolWebSearch" type="checkbox"/></div>
            <div class="chat-tools-row"><label>Image OCR</label><input id="toolImageOCR" type="checkbox"/></div>
        `;
        document.body.appendChild(toolsPanel);
        this.chatUI = { panel, actionBar, title, freeze, logsBtn, exportBtn, speakBtn, toolsBtn, toolsPanel, messages, logsPanel, input, send, mic, close };

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
        toolsBtn.addEventListener("click", () => {
            if (!this.selectedNode) return;
            const target = this.getNodeTarget(this.selectedNode);
            if (!target) return;
            this.toggleToolsPanel(true);
            this.loadToolsForCampfire(target);
        });
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
        this.renderChatHistory(node);
        this.chatUI.input.focus();
        this.updateSpeakButtonForNode(node);
        this.updateChatTitleFromBackend(node);
    }

    updateSpeakButtonForNode(node) {
        if (!this.chatUI || !this.chatUI.speakBtn) {
            return;
        }
        const enabled = !(node && node.properties && node.properties.tts_enabled === false);
        this.chatUI.speakBtn.textContent = enabled ? "🔊 Speak: On" : "🔇 Speak: Off";
    }

    toggleToolsPanel(visible) {
        if (!this.chatUI || !this.chatUI.toolsPanel) return;
        if (visible) this.chatUI.toolsPanel.classList.add("visible");
        else this.chatUI.toolsPanel.classList.remove("visible");
    }

    async loadToolsForCampfire(campfireId) {
        try {
            const res = await fetch(`/api/campfire/tools?campfire=${encodeURIComponent(campfireId)}`);
            if (!res.ok) return;
            const data = await res.json();
            const z = (data.tools || {});
            const enabled = !!z.enabled;
            const ws = !!z.web_search;
            const ocr = !!z.image_ocr;
            document.getElementById("toolZeitgeistEnabled").checked = enabled;
            document.getElementById("toolWebSearch").checked = ws;
            document.getElementById("toolImageOCR").checked = ocr;
            this.bindToolsPanelEvents(campfireId);
        } catch (e) {
        }
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
        this.toggleToolsPanel(false);
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
            el.textContent = m.text;
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
        const auditorName = `${campfireName} Auditor`;
        const campfire = this.addCampfire(campfireId, position);
        campfire.properties.name = campfireName;
        campfire.properties.type = "standard";
        campfire.title = campfire.properties.name;

        const auditorPos = [position[0] + 280, position[1]];
        const auditor = this.addCamper(auditorId, auditorPos);
        auditor.properties.name = auditorName;
        auditor.properties.type = "auditor";
        auditor.properties.current_task = "ready";
        auditor.properties.role_prompt = "You are the Auditor and Orchestrator for this Campfire. You do not solve the user's domain problem. You identify which campers are needed, create them, assign them ordered tasks, and coordinate their outputs. Keep replies short and action-focused.";
        auditor.title = "Auditor";

        try {
            campfire.connect(0, auditor, 0);
        } catch (e) {
        }

        if (this.canvas && this.canvas.selectNodes) {
            this.canvas.selectNodes([auditor]);
        }

        this.appendChatMessage(auditor, { role: "system", text: "Auditor created and linked. Select a node to chat.", ts: Date.now() });
        this.ensureBackendCampfire(campfireName, "You are a helpful campfire agent. Keep responses concise and actionable.", "gemma3:4b");
        this.ensureBackendCampfire(auditorName, auditor.properties.role_prompt, "gemma3:4b");
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
                const name = v && v.name ? String(v.name) : null;
                if (!name) return;
                const valleyNode = LiteGraph.createNode("campfire/valley");
                valleyNode.pos = [startX, startY + (idx * valleySpacingY)];
                valleyNode.properties = valleyNode.properties || {};
                valleyNode.properties.remote = true;
                valleyNode.properties.name = name;
                valleyNode.title = name;
                this.graph.add(valleyNode);

                const exposed = Array.isArray(v.exposed_campfires) ? v.exposed_campfires : [];
                exposed.forEach((cf, j) => {
                    const cfName = cf ? String(cf) : null;
                    if (!cfName) return;
                    const campfireNode = LiteGraph.createNode("campfire/campfire");
                    campfireNode.pos = [valleyNode.pos[0] + campfireOffsetX, valleyNode.pos[1] + (j * campfireSpacingY)];
                    campfireNode.properties = campfireNode.properties || {};
                    campfireNode.properties.remote = true;
                    campfireNode.properties.name = cfName;
                    campfireNode.properties.target = `valley:${name}/${cfName}`;
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
        const existingNodes = Array.isArray(this.graph._nodes) ? [...this.graph._nodes] : [];
        existingNodes.forEach((n) => {
            if (n && n.properties && n.properties.backend === true) {
                try {
                    this.graph.remove(n);
                } catch (e) {
                }
            }
        });
        this.nodes.backendCampers = [];

        const campfireRecords = Array.isArray(campfires) ? campfires : [];
        const byId = new Map();
        campfireRecords.forEach((c) => {
            if (c && c.id) byId.set(String(c.id), c);
        });
        const parents = new Map();
        campfireRecords.forEach((c) => {
            const id = c && c.id ? String(c.id) : null;
            const parent = c && c.parent ? String(c.parent) : null;
            if (id && parent) parents.set(id, parent);
        });
        if (this.nodes.valley && this.nodes.valley.properties) {
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

        for (const c of primaryCampfires) {
            const auditorName = `${c.id} Auditor`;
            if (!allIds.includes(auditorName)) {
                await this.ensureBackendCampfire(
                    auditorName,
                    "You are the Auditor for this Campfire. Help the user construct the campfire, add campers, refine prompts, and confirm actions.",
                    "gemma3:4b"
                );
            }
        }

        campfires = await this.fetchBackendCampfires(true);

        const campfireNodeById = new Map();
        primaryCampfires.forEach((c, idx) => {
            const campfireNode = LiteGraph.createNode("campfire/campfire");
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
            campfireNodeById.set(c.id, campfireNode);

            const auditorName = `${c.id} Auditor`;
            const auditor = LiteGraph.createNode("campfire/camper");
            auditor.pos = [campfireNode.pos[0] + auditorOffsetX, campfireNode.pos[1] + auditorOffsetY];
            auditor.properties = auditor.properties || {};
            auditor.properties.backend = true;
            auditor.properties.name = "Auditor";
            auditor.properties.target = auditorName;
            auditor.properties.type = "auditor";
            auditor.properties.role_prompt = "You are the Auditor and Orchestrator for this Campfire. You do not solve the user's domain problem. You identify which campers are needed, create them, assign them ordered tasks, and coordinate their outputs. Ask clarifying questions when needed.";
            auditor.title = "Auditor";
            this.graph.add(auditor);
            try {
                campfireNode.connect(0, auditor, 0);
            } catch (e) {
            }
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
                try {
                    parentNode.connect(0, camperNode, 0);
                } catch (e) {
                }
            });
        });

        if (this.nodes.valley && Array.isArray(this.nodes.backendCampers)) {
            this.nodes.backendCampers.forEach((n) => {
                if (n && n.type === "campfire/campfire") {
                    try {
                        this.nodes.valley.connect(1, n, 0);
                    } catch (e) {
                    }
                }
            });
        }
        await this.syncRemoteValleyNodes(startX + 720, startY);
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
        const sendOnce = async () => {
            return await fetch("/api/voice/ingest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    campfire: target,
                    text
                })
            });
        };
        try {
            await this.ensureBackendPresentForNode(node);
            let res = await sendOnce();
            if (!res.ok && !isRemote) {
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
            if (response && typeof response.llm_response === "string") {
                msg.text = response.llm_response;
            } else if (response && typeof response.text === "string") {
                msg.text = response.text;
            } else if (response && typeof response === "string") {
                msg.text = response;
            } else if (response != null) {
                msg.text = JSON.stringify(response);
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
            if ((Array.isArray(created) && created.length > 0) || (Array.isArray(removed) && removed.length > 0)) {
                setTimeout(() => {
                    try {
                        this.syncBackendCampfireNodes();
                    } catch (e) {
                    }
                }, 250);
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
