// CampfireValley LiteGraph Nodes - Complete UI Replacement

// Task Input Node - replaces task textarea and controls
function TaskInputNode() {
    this.addOutput("task_text", "string");
    this.addOutput("start_trigger", "trigger");
    this.addOutput("stop_trigger", "trigger");
    this.addProperty("task_description", "Enter a task for the campfires to process...");
    this.addProperty("status", "ready");
    this.size = [280, 160];
    this.widgets_up = true;
    
    // Add interactive widgets
    this.addWidget("text", "Task", this.properties.task_description, (v) => {
        this.properties.task_description = v;
        this.setOutputData(0, v);
    });
    
    this.addWidget("button", "🚀 Start Task", null, () => {
        this.properties.status = "running";
        this.triggerSlot(1);
    });
    
    this.addWidget("button", "⏹️ Stop Task", null, () => {
        this.properties.status = "ready";
        this.triggerSlot(2);
    });
}

TaskInputNode.title = "Task Input";
TaskInputNode.desc = "Interactive task input and control";

TaskInputNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    const statusColors = {
        "ready": "#4CAF50",
        "running": "#FF9800",
        "stopped": "#f44336"
    };
    
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Status indicator
    ctx.fillStyle = statusColors[this.properties.status] || "#666";
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Task icon
    ctx.fillStyle = "#8a5cf6";
    ctx.fillRect(10, 30, 20, 20);
    
    // Status text
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Status: ${this.properties.status}`, 10, 70);
};

// View Mode Node - replaces view mode dropdown
function ViewModeNode() {
    this.addOutput("view_mode", "string");
    this.addProperty("current_mode", "overview");
    this.size = [200, 120];
    
    this.addWidget("combo", "View Mode", this.properties.current_mode, (v) => {
        this.properties.current_mode = v;
        this.setOutputData(0, v);
    }, { values: ["overview", "campfires", "campers"] });
}

ViewModeNode.title = "View Mode";
ViewModeNode.desc = "Controls the current view mode";

ViewModeNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#4ade80";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Mode: ${this.properties.current_mode}`, 10, 70);
};

// Filter Node - replaces filter input
function FilterNode() {
    this.addOutput("filter_text", "string");
    this.addProperty("filter", "");
    this.size = [200, 100];
    
    this.addWidget("text", "Filter", this.properties.filter, (v) => {
        this.properties.filter = v;
        this.setOutputData(0, v);
    });
}

FilterNode.title = "Filter";
FilterNode.desc = "Filters nodes based on text input";

FilterNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#3a2a3a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Filter: ${this.properties.filter || "None"}`, 10, 70);
};

// Zoom Control Node - replaces zoom buttons
function ZoomControlNode() {
    this.addOutput("zoom_in", "trigger");
    this.addOutput("zoom_out", "trigger");
    this.addOutput("reset_view", "trigger");
    this.addProperty("zoom_level", 1.0);
    this.size = [180, 140];
    
    this.addWidget("button", "Zoom In", null, () => {
        this.properties.zoom_level = Math.min(this.properties.zoom_level * 1.2, 3.0);
        this.triggerSlot(0);
    });
    
    this.addWidget("button", "Zoom Out", null, () => {
        this.properties.zoom_level = Math.max(this.properties.zoom_level / 1.2, 0.3);
        this.triggerSlot(1);
    });
    
    this.addWidget("button", "Reset", null, () => {
        this.properties.zoom_level = 1.0;
        this.triggerSlot(2);
    });
}

ZoomControlNode.title = "Zoom Control";
ZoomControlNode.desc = "Controls canvas zoom level";

ZoomControlNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#3a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#06b6d4";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Zoom: ${(this.properties.zoom_level * 100).toFixed(0)}%`, 10, 70);
};

// Display Options Node - replaces checkboxes
function DisplayOptionsNode() {
    this.addOutput("show_connections", "boolean");
    this.addOutput("show_torch_flow", "boolean");
    this.addOutput("auto_refresh", "boolean");
    this.addProperty("connections", true);
    this.addProperty("torch_flow", true);
    this.addProperty("refresh", true);
    this.size = [220, 160];
    
    this.addWidget("toggle", "Show Connections", this.properties.connections, (v) => {
        this.properties.connections = v;
        this.setOutputData(0, v);
    });
    
    this.addWidget("toggle", "Show Torch Flow", this.properties.torch_flow, (v) => {
        this.properties.torch_flow = v;
        this.setOutputData(1, v);
    });
    
    this.addWidget("toggle", "Auto Refresh", this.properties.refresh, (v) => {
        this.properties.refresh = v;
        this.setOutputData(2, v);
    });
}

DisplayOptionsNode.title = "Display Options";
DisplayOptionsNode.desc = "Controls display settings";

DisplayOptionsNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Connections: ${this.properties.connections ? "On" : "Off"}`, 10, 70);
    ctx.fillText(`Torch Flow: ${this.properties.torch_flow ? "On" : "Off"}`, 10, 85);
    ctx.fillText(`Auto Refresh: ${this.properties.refresh ? "On" : "Off"}`, 10, 100);
};

// Node Details Display Node - replaces node info panel
function NodeDetailsNode() {
    this.addInput("selected_node", "object");
    this.addProperty("node_title", "No Selection");
    this.addProperty("node_details", "Select a node to view details");
    this.size = [250, 180];
}

NodeDetailsNode.title = "Node Details";
NodeDetailsNode.desc = "Displays details of selected nodes";

NodeDetailsNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a2a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(10, 30, 20, 20);
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(this.properties.node_title, 10, 70);
    
    ctx.font = "10px Arial";
    const details = this.properties.node_details;
    const lines = this.wrapText(ctx, details, this.size[0] - 20);
    for (let i = 0; i < Math.min(lines.length, 8); i++) {
        ctx.fillText(lines[i], 10, 90 + i * 12);
    }
};

NodeDetailsNode.prototype.wrapText = function(ctx, text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = words[0];
    
    for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = ctx.measureText(currentLine + " " + word).width;
        if (width < maxWidth) {
            currentLine += " " + word;
        } else {
            lines.push(currentLine);
            currentLine = word;
        }
    }
    lines.push(currentLine);
    return lines;
};

// Status Legend Node - replaces legend panel
function StatusLegendNode() {
    this.addProperty("show_legend", true);
    this.size = [180, 140];
}

StatusLegendNode.title = "Status Legend";
StatusLegendNode.desc = "Shows status indicator meanings";

StatusLegendNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a2a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    const statuses = [
        { name: "Active", color: "#4CAF50" },
        { name: "Busy", color: "#FF9800" },
        { name: "Error", color: "#f44336" },
        { name: "Offline", color: "#666666" }
    ];
    
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText("Legend", 10, 30);
    
    ctx.font = "10px Arial";
    statuses.forEach((status, i) => {
        const y = 50 + i * 20;
        ctx.fillStyle = status.color;
        ctx.fillRect(10, y - 8, 10, 10);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(status.name, 25, y);
    });
};

// Valley Node - represents a valley in the system (top of hierarchy)
function ValleyNode() {
    this.addOutput("dock_connection", "dock");
    this.addOutput("campfire_connection", "campfire");
    this.addProperty("name", "Valley");
    this.addProperty("status", "active");
    this.addProperty("total_campfires", 0);
    this.addProperty("total_campers", 0);
    this.addProperty("dock_status", "active");
    this.addProperty("federation_status", "disconnected");
    this.size = [220, 140];
}

ValleyNode.title = "Valley";
ValleyNode.desc = "Represents a valley in CampfireValley";

ValleyNode.prototype.onExecute = function() {
    const valleyData = {
        name: this.properties.name,
        status: this.properties.status,
        total_campfires: this.properties.total_campfires,
        total_campers: this.properties.total_campers,
        dock_status: this.properties.dock_status,
        federation_status: this.properties.federation_status
    };
    this.setOutputData(0, valleyData); // dock connection
    this.setOutputData(1, valleyData); // campfire connection
};

ValleyNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a4d3a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw valley icon
    ctx.fillStyle = "#4a7c59";
    ctx.fillRect(10, 30, this.size[0] - 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "12px Arial";
    ctx.fillText(`Campfires: ${this.properties.total_campfires}`, 10, 70);
    ctx.fillText(`Campers: ${this.properties.total_campers}`, 10, 85);
    ctx.fillText(`Dock: ${this.properties.dock_status}`, 10, 100);
};

// Dock Node - represents the valley's dock gateway
function DockNode() {
    this.addInput("valley_connection", "dock");
    this.addOutput("dockmaster_connection", "dockmaster");
    this.addOutput("sanitizer_connection", "sanitizer");
    this.addOutput("justice_connection", "justice");
    this.addProperty("name", "Dock Gateway");
    this.addProperty("status", "active");
    this.addProperty("mode", "private");
    this.addProperty("torch_throughput", 0);
    this.addProperty("security_level", "standard");
    this.size = [240, 160];
}

DockNode.title = "Dock";
DockNode.desc = "Represents the valley's dock gateway";

DockNode.prototype.onExecute = function() {
    const dockData = {
        name: this.properties.name,
        status: this.properties.status,
        mode: this.properties.mode,
        torch_throughput: this.properties.torch_throughput,
        security_level: this.properties.security_level
    };
    this.setOutputData(0, dockData); // dockmaster
    this.setOutputData(1, dockData); // sanitizer
    this.setOutputData(2, dockData); // justice
};

DockNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3a4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw dock icon
    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(10, 30, this.size[0] - 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Mode: ${this.properties.mode}`, 10, 70);
    ctx.fillText(`Throughput: ${this.properties.torch_throughput}`, 10, 85);
    ctx.fillText(`Security: ${this.properties.security_level}`, 10, 100);
};

// Dockmaster Campfire Node - handles torch loading, routing, and packing
function DockmasterCampfireNode() {
    this.addInput("dock_connection", "dockmaster");
    this.addOutput("loader_connection", "camper");
    this.addOutput("router_connection", "camper");
    this.addOutput("packer_connection", "camper");
    this.addProperty("name", "Dockmaster");
    this.addProperty("status", "active");
    this.addProperty("torch_queue", 0);
    this.addProperty("routing_efficiency", 95);
    this.size = [220, 140];
}

DockmasterCampfireNode.title = "Dockmaster Campfire";
DockmasterCampfireNode.desc = "Handles torch loading, routing, and packing";

DockmasterCampfireNode.prototype.onExecute = function() {
    const dockmasterData = {
        name: this.properties.name,
        status: this.properties.status,
        torch_queue: this.properties.torch_queue,
        routing_efficiency: this.properties.routing_efficiency
    };
    this.setOutputData(0, dockmasterData); // loader
    this.setOutputData(1, dockmasterData); // router
    this.setOutputData(2, dockmasterData); // packer
};

DockmasterCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon
    ctx.fillStyle = "#ff6b35";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Queue: ${this.properties.torch_queue}`, 10, 70);
    ctx.fillText(`Efficiency: ${this.properties.routing_efficiency}%`, 10, 85);
};

// Sanitizer Campfire Node - handles content security and sanitization
function SanitizerCampfireNode() {
    this.addInput("dock_connection", "sanitizer");
    this.addOutput("scanner_connection", "camper");
    this.addOutput("filter_connection", "camper");
    this.addOutput("quarantine_connection", "camper");
    this.addProperty("name", "Sanitizer");
    this.addProperty("status", "active");
    this.addProperty("threats_detected", 0);
    this.addProperty("quarantine_count", 0);
    this.size = [220, 140];
}

SanitizerCampfireNode.title = "Sanitizer Campfire";
SanitizerCampfireNode.desc = "Handles content security and sanitization";

SanitizerCampfireNode.prototype.onExecute = function() {
    const sanitizerData = {
        name: this.properties.name,
        status: this.properties.status,
        threats_detected: this.properties.threats_detected,
        quarantine_count: this.properties.quarantine_count
    };
    this.setOutputData(0, sanitizerData); // scanner
    this.setOutputData(1, sanitizerData); // filter
    this.setOutputData(2, sanitizerData); // quarantine
};

SanitizerCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon with security theme
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Threats: ${this.properties.threats_detected}`, 10, 70);
    ctx.fillText(`Quarantine: ${this.properties.quarantine_count}`, 10, 85);
};

// Justice Campfire Node - handles governance and compliance
function JusticeCampfireNode() {
    this.addInput("dock_connection", "justice");
    this.addOutput("detector_connection", "camper");
    this.addOutput("enforcer_connection", "camper");
    this.addOutput("governor_connection", "camper");
    this.addProperty("name", "Justice");
    this.addProperty("status", "active");
    this.addProperty("violations_detected", 0);
    this.addProperty("sanctions_applied", 0);
    this.size = [220, 140];
}

JusticeCampfireNode.title = "Justice Campfire";
JusticeCampfireNode.desc = "Handles governance and compliance";

JusticeCampfireNode.prototype.onExecute = function() {
    const justiceData = {
        name: this.properties.name,
        status: this.properties.status,
        violations_detected: this.properties.violations_detected,
        sanctions_applied: this.properties.sanctions_applied
    };
    this.setOutputData(0, justiceData); // detector
    this.setOutputData(1, justiceData); // enforcer
    this.setOutputData(2, justiceData); // governor
};

JusticeCampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon with justice theme
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Violations: ${this.properties.violations_detected}`, 10, 70);
    ctx.fillText(`Sanctions: ${this.properties.sanctions_applied}`, 10, 85);
};

// Regular Campfire Node - represents standard campfires from config
function CampfireNode() {
    this.addInput("valley_connection", "campfire");
    this.addOutput("camper_connection", "camper");
    this.addProperty("name", "Campfire");
    this.addProperty("type", "standard");
    this.addProperty("status", "active");
    this.addProperty("camper_count", 0);
    this.addProperty("torch_queue", 0);
    this.addProperty("config_source", "config file");
    this.size = [200, 140];
}

CampfireNode.title = "Campfire";
CampfireNode.desc = "Represents a campfire processing tasks";

CampfireNode.prototype.onExecute = function() {
    this.setOutputData(0, {
        name: this.properties.name,
        type: this.properties.type,
        status: this.properties.status,
        camper_count: this.properties.camper_count,
        torch_queue: this.properties.torch_queue,
        config_source: this.properties.config_source
    });
};

CampfireNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a2c2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw campfire icon
    ctx.fillStyle = "#ff6b35";
    ctx.fillRect(this.size[0]/2 - 10, 30, 20, 20);
    
    // Draw status indicator
    const statusColors = {
        "idle": "#4CAF50",
        "busy": "#FF9800",
        "error": "#f44336",
        "active": "#4CAF50"
    };
    ctx.fillStyle = statusColors[this.properties.status] || "#666";
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Status: ${this.properties.status}`, 10, 70);
    ctx.fillText(`Campers: ${this.properties.camper_count}`, 10, 85);
    ctx.fillText(`Queue: ${this.properties.torch_queue}`, 10, 100);
};

// Specialized Camper Nodes for Dock Campfires
function LoaderCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Loader");
    this.addProperty("status", "active");
    this.addProperty("torches_loaded", 0);
    this.addProperty("validation_rate", 100);
    this.size = [180, 100];
}

LoaderCamperNode.title = "Loader Camper";
LoaderCamperNode.desc = "Loads and validates torches";

LoaderCamperNode.prototype.onExecute = function() {
    // Loader camper processing logic
};

LoaderCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw loader icon
    ctx.fillStyle = "#10b981";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Loaded: ${this.properties.torches_loaded}`, 10, 60);
    ctx.fillText(`Rate: ${this.properties.validation_rate}%`, 10, 75);
};

function RouterCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Router");
    this.addProperty("status", "active");
    this.addProperty("routes_processed", 0);
    this.addProperty("routing_accuracy", 98);
    this.size = [180, 100];
}

RouterCamperNode.title = "Router Camper";
RouterCamperNode.desc = "Routes torches to destinations";

RouterCamperNode.prototype.onExecute = function() {
    // Router camper processing logic
};

RouterCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw router icon
    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Routed: ${this.properties.routes_processed}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.routing_accuracy}%`, 10, 75);
};

function PackerCamperNode() {
    this.addInput("dockmaster_connection", "camper");
    this.addProperty("name", "Packer");
    this.addProperty("status", "active");
    this.addProperty("torches_packed", 0);
    this.addProperty("compression_ratio", 75);
    this.size = [180, 100];
}

PackerCamperNode.title = "Packer Camper";
PackerCamperNode.desc = "Packs torches for transport";

PackerCamperNode.prototype.onExecute = function() {
    // Packer camper processing logic
};

PackerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw packer icon
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Packed: ${this.properties.torches_packed}`, 10, 60);
    ctx.fillText(`Ratio: ${this.properties.compression_ratio}%`, 10, 75);
};

function ScannerCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Scanner");
    this.addProperty("status", "active");
    this.addProperty("scans_completed", 0);
    this.addProperty("threats_found", 0);
    this.size = [180, 100];
}

ScannerCamperNode.title = "Scanner Camper";
ScannerCamperNode.desc = "Scans content for threats";

ScannerCamperNode.prototype.onExecute = function() {
    // Scanner camper processing logic
};

ScannerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw scanner icon
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Scanned: ${this.properties.scans_completed}`, 10, 60);
    ctx.fillText(`Threats: ${this.properties.threats_found}`, 10, 75);
};

function FilterCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Filter");
    this.addProperty("status", "active");
    this.addProperty("content_filtered", 0);
    this.addProperty("filter_accuracy", 99);
    this.size = [180, 100];
}

FilterCamperNode.title = "Filter Camper";
FilterCamperNode.desc = "Filters malicious content";

FilterCamperNode.prototype.onExecute = function() {
    // Filter camper processing logic
};

FilterCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw filter icon
    ctx.fillStyle = "#f97316";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Filtered: ${this.properties.content_filtered}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.filter_accuracy}%`, 10, 75);
};

function QuarantineCamperNode() {
    this.addInput("sanitizer_connection", "camper");
    this.addProperty("name", "Quarantine");
    this.addProperty("status", "active");
    this.addProperty("items_quarantined", 0);
    this.addProperty("quarantine_capacity", 100);
    this.size = [180, 100];
}

QuarantineCamperNode.title = "Quarantine Camper";
QuarantineCamperNode.desc = "Quarantines suspicious content";

QuarantineCamperNode.prototype.onExecute = function() {
    // Quarantine camper processing logic
};

QuarantineCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw quarantine icon
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Quarantined: ${this.properties.items_quarantined}`, 10, 60);
    ctx.fillText(`Capacity: ${this.properties.quarantine_capacity}`, 10, 75);
};

function DetectorCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Detector");
    this.addProperty("status", "active");
    this.addProperty("violations_detected", 0);
    this.addProperty("detection_accuracy", 97);
    this.size = [180, 100];
}

DetectorCamperNode.title = "Detector Camper";
DetectorCamperNode.desc = "Detects policy violations";

DetectorCamperNode.prototype.onExecute = function() {
    // Detector camper processing logic
};

DetectorCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw detector icon
    ctx.fillStyle = "#8b5cf6";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Detected: ${this.properties.violations_detected}`, 10, 60);
    ctx.fillText(`Accuracy: ${this.properties.detection_accuracy}%`, 10, 75);
};

function EnforcerCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Enforcer");
    this.addProperty("status", "active");
    this.addProperty("sanctions_applied", 0);
    this.addProperty("enforcement_rate", 100);
    this.size = [180, 100];
}

EnforcerCamperNode.title = "Enforcer Camper";
EnforcerCamperNode.desc = "Enforces policies and sanctions";

EnforcerCamperNode.prototype.onExecute = function() {
    // Enforcer camper processing logic
};

EnforcerCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw enforcer icon
    ctx.fillStyle = "#7c3aed";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Sanctions: ${this.properties.sanctions_applied}`, 10, 60);
    ctx.fillText(`Rate: ${this.properties.enforcement_rate}%`, 10, 75);
};

function GovernorCamperNode() {
    this.addInput("justice_connection", "camper");
    this.addProperty("name", "Governor");
    this.addProperty("status", "active");
    this.addProperty("policies_managed", 0);
    this.addProperty("compliance_rate", 95);
    this.size = [180, 100];
}

GovernorCamperNode.title = "Governor Camper";
GovernorCamperNode.desc = "Manages governance policies";

GovernorCamperNode.prototype.onExecute = function() {
    // Governor camper processing logic
};

GovernorCamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw governor icon
    ctx.fillStyle = "#6366f1";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Policies: ${this.properties.policies_managed}`, 10, 60);
    ctx.fillText(`Compliance: ${this.properties.compliance_rate}%`, 10, 75);
};

// Generic Camper Node - for regular campfire campers
function CamperNode() {
    this.addInput("campfire_connection", "camper");
    this.addProperty("name", "Camper");
    this.addProperty("type", "worker");
    this.addProperty("status", "active");
    this.addProperty("current_task", "idle");
    this.addProperty("tasks_completed", 0);
    this.size = [180, 120];
}

CamperNode.title = "Camper";
CamperNode.desc = "Represents a camper in the system";

CamperNode.prototype.onExecute = function() {
    this.setOutputData(0, {
        name: this.properties.name,
        type: this.properties.type,
        status: this.properties.status,
        current_task: this.properties.current_task,
        tasks_completed: this.properties.tasks_completed
    });
};

CamperNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#2a3d4a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw camper icon
    ctx.fillStyle = "#5a9fd4";
    ctx.fillRect(this.size[0]/2 - 8, 25, 16, 16);
    
    // Draw status indicator
    const statusColor = this.properties.status === "active" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Task: ${this.properties.current_task}`, 10, 60);
    ctx.fillText(`Completed: ${this.properties.tasks_completed}`, 10, 75);
};

// WebSocket Data Node - handles real-time data
function WebSocketDataNode() {
    this.addOutput("valley_data", "valley");
    this.addOutput("campfire_data", "campfire");
    this.addOutput("camper_data", "camper");
    this.addOutput("connection_status", "string");
    this.addProperty("connection_status", "disconnected");
    this.addProperty("auto_refresh", true);
    this.size = [200, 120];
}

WebSocketDataNode.title = "WebSocket Data";
WebSocketDataNode.desc = "Handles real-time data from WebSocket";

WebSocketDataNode.prototype.onDrawBackground = function(ctx) {
    if (this.flags.collapsed) return;
    
    ctx.fillStyle = "#4a3a2a";
    ctx.fillRect(0, 0, this.size[0], this.size[1]);
    
    // Draw connection status
    const statusColor = this.properties.connection_status === "connected" ? "#4CAF50" : "#f44336";
    ctx.fillStyle = statusColor;
    ctx.fillRect(this.size[0] - 20, 10, 10, 10);
    
    // Draw WebSocket icon
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(10, 30, 20, 20);
    
    // Draw text
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Status: ${this.properties.connection_status}`, 10, 70);
    ctx.fillText(`Auto Refresh: ${this.properties.auto_refresh ? "On" : "Off"}`, 10, 85);
};

// Register all nodes with LiteGraph
LiteGraph.registerNodeType("campfire/task_input", TaskInputNode);
LiteGraph.registerNodeType("campfire/view_mode", ViewModeNode);
LiteGraph.registerNodeType("campfire/filter", FilterNode);
LiteGraph.registerNodeType("campfire/zoom_control", ZoomControlNode);
LiteGraph.registerNodeType("campfire/display_options", DisplayOptionsNode);
LiteGraph.registerNodeType("campfire/node_details", NodeDetailsNode);
LiteGraph.registerNodeType("campfire/status_legend", StatusLegendNode);
LiteGraph.registerNodeType("campfire/valley", ValleyNode);
LiteGraph.registerNodeType("campfire/dock", DockNode);
LiteGraph.registerNodeType("campfire/dockmaster_campfire", DockmasterCampfireNode);
LiteGraph.registerNodeType("campfire/sanitizer_campfire", SanitizerCampfireNode);
LiteGraph.registerNodeType("campfire/justice_campfire", JusticeCampfireNode);
LiteGraph.registerNodeType("campfire/campfire", CampfireNode);
LiteGraph.registerNodeType("campfire/loader_camper", LoaderCamperNode);
LiteGraph.registerNodeType("campfire/router_camper", RouterCamperNode);
LiteGraph.registerNodeType("campfire/packer_camper", PackerCamperNode);
LiteGraph.registerNodeType("campfire/scanner_camper", ScannerCamperNode);
LiteGraph.registerNodeType("campfire/filter_camper", FilterCamperNode);
LiteGraph.registerNodeType("campfire/quarantine_camper", QuarantineCamperNode);
LiteGraph.registerNodeType("campfire/detector_camper", DetectorCamperNode);
LiteGraph.registerNodeType("campfire/enforcer_camper", EnforcerCamperNode);
LiteGraph.registerNodeType("campfire/governor_camper", GovernorCamperNode);
LiteGraph.registerNodeType("campfire/camper", CamperNode);
LiteGraph.registerNodeType("campfire/websocket_data", WebSocketDataNode);